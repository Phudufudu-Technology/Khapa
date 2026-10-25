"""The guided demo, end to end, through the same controller the Flet UI uses."""
import dataclasses
import json

import pytest

from conftest import ManualScheduler
from khapa_core import analytics as A
from khapa_core import data as D
from khapa_core.demo import DEMO
from khapa_core.security import ALERT, CANARY_LEARNER_ID
from khapa_core.session import Session, parse_mark
from khapa_core.store import Store, StoreError

NOW = 1_800_000_000_000


def make(sched=None, store=None):
    s = Session(store=store, now_ms=lambda: NOW, scheduler=sched or ManualScheduler())
    return s


def test_demo_has_seven_steps_with_the_prototype_copy():
    assert len(DEMO) == 7
    assert DEMO[0].text.startswith("The school’s internet has gone down.")
    assert DEMO[6].text.startswith("That is the demo.")


def test_all_seven_steps_end_to_end():
    s = make()
    assert s.role == "guide" and s.online
    s.start_demo()                                                     # step 1: internet drops
    assert s.demo_index == 0 and not s.online and s.role == "teacher"
    s.next_demo()                                                      # step 2: captured offline
    assert s.hub.current_mark("L03", "T6").value == 38
    assert s.chip().waiting and s.chip().count == 1
    s.next_demo()                                                      # step 3: parent sees stale data
    assert s.role == "parent" and s.phone.current_mark("L03", "T6") is None and not s.online
    s.next_demo()                                                      # step 4: back online, phone catches up
    assert s.online and s.phone.current_mark("L03", "T6").value == 38
    assert not s.chip().waiting
    s.next_demo()                                                      # step 5: concurrent offline edits
    assert not s.online and s.role == "teacher"
    assert len(s.hub.pending_for(s.cloud)) == 1 and len(s.nodes["hubB"].pending_for(s.cloud)) == 1
    s.next_demo()                                                      # step 6: conflict flagged, not overwritten
    cm = s.hub.current_mark("L03", "T4")
    assert cm.conflict and sorted([cm.value, *[a.value for a in cm.alternatives]]) == [45, 52]
    assert {m.value for m in s.hub.marks.values() if m.learner_id == "L03" and m.task_id == "T4"} >= {45, 52}
    assert any(e.action == "CONFLICT_FLAGGED" for e in s.audit.entries)
    s.next_demo()                                                      # step 7: end card
    assert s.demo_index == 6
    s.next_demo()                                                      # does not run past the end
    assert s.demo_index == 6
    assert s.choose_mark("L03", "T4", 48) is None                      # teacher resolves
    s._auto_sync()
    for n in s.nodes.values():
        c = n.current_mark("L03", "T4")
        assert c.value == 48 and not c.conflict
    assert s.converged() and any(e.action == "CONFLICT_RESOLVED" for e in s.audit.entries)
    assert s.audit_status() == (True, None)


def test_demo_restart_resets_everything():
    s = make()
    s.start_demo(); s.next_demo(); s.next_demo()
    s.start_demo()
    assert s.demo_index == 0 and s.hub.current_mark("L03", "T6") is None


def test_offline_capture_does_not_sync_until_internet_returns(sched):
    s = make(sched)
    s.set_role("teacher")
    s.toggle_net()
    assert s.save_mark("L03", "T6", "38") is None
    sched.flush()
    assert s.chip().waiting and s.phone.current_mark("L03", "T6") is None
    s.toggle_net()
    assert s.phone.current_mark("L03", "T6").value == 38 and not s.chip().waiting


def test_online_edits_sync_by_themselves_after_the_debounce(sched):
    s = make(sched)
    s.set_role("teacher")
    s.save_mark("L01", "T6", "90")
    assert s.chip().waiting
    sched.flush()
    assert not s.chip().waiting and s.phone.current_mark("L01", "T6").value == 90


def test_hod_button_makes_a_conflict_only_when_both_sides_edit():
    s = make()
    s.set_role("teacher")
    s.toggle_net()
    s.save_mark("L03", "T4", "45"); s.hod_edit()
    s.toggle_net()
    assert s.hub.current_mark("L03", "T4").conflict


@pytest.mark.parametrize("raw,expected", [("38", 38), ("38.5", 38.5), ("38,5", 38.5), (" 7 ", 7), ("0", 0), ("100", 100),
                                          ("101", None), ("-1", None), ("", None), ("abc", None), ("nan", None), ("inf", None),
                                          ("1e3", None), (None, None), ("1" * 20, None), ("٣٨", 38)])
def test_mark_input_parsing(raw, expected):
    assert parse_mark(raw) == expected


def test_invalid_input_returns_a_message_and_changes_nothing():
    s = make(); s.set_role("teacher")
    n = len(s.hub.log)
    assert s.save_mark("L03", "T6", "150") and s.save_mark("L03", "T6", "x") and s.save_mark("NOPE", "T6", "5") and s.save_mark("L03", "T99", "5")
    assert s.add_comment("L03", "   ")
    assert len(s.hub.log) == n


def test_comments_sync_and_are_length_limited():
    s = make(); s.set_role("teacher")
    assert s.add_comment("L03", "Please check corrections.") is None
    assert s.add_comment("L03", "x" * 501)
    s._auto_sync()
    assert any(c.text == "Please check corrections." for c in s.phone.comments_for("L03"))


def test_only_a_teacher_can_write_and_refusals_are_audited():
    s = make()
    for role in ("parent", "learner", "principal", "guide"):
        s.set_role(role)
        assert s.save_mark("L03", "T6", "38") is not None and s.add_comment("L03", "hi") is not None
    assert s.hub.current_mark("L03", "T6") is None
    assert sum(e.action == "ACCESS_DENIED" for e in s.audit.entries) == 8


def test_canary_probe_raises_an_alert_and_changes_no_marks():
    s = make(); s.set_role("parent")
    assert "Blocked" in s.probe_canary() and "Blocked" in s.probe_other_child()
    assert [e.action for e in s.audit.alerts()] == ["CANARY_TRIPPED"]
    assert s.audit_status()[0] and "BROKEN" in s.tamper_demo() and s.audit_status()[0]


def test_canary_never_leaks_into_class_lists_or_statistics():
    s = make()
    assert CANARY_LEARNER_ID not in s.learner_ids()
    ids = s.learner_ids()
    assert len(ids) == 14 and A.class_average(s.hub, D.TASKS, ids) == A.class_average(s.hub, D.TASKS, [i for i in s.hub.learners if i != CANARY_LEARNER_ID])


def test_devices_panel_and_clock_skew():
    s = make()
    d = {x["id"]: x for x in s.devices()}
    assert "4 minutes slow" in d["hubB"]["skew"] and "right" in d["hub"]["skew"] and "fast" in d["phone"]["skew"]
    assert s.converged() and len({x["fingerprint"] for x in d.values()}) == 1


def test_language_switch_falls_back_and_persists_choice():
    store = Store(None)
    s = make(store=store)
    s.set_lang("xh")
    assert s.t("role.teacher") == "Teacher"                           # falls back to English
    s.set_lang("af")
    assert s.t("role.teacher") == "Onderwyser" and s.t("comments.add") == "Voeg kommentaar by"
    assert make(store=store).lang == "af"
    s.set_lang("klingon")
    assert s.lang == "af"


def test_ai_disclosure_copy_is_present_in_every_translation_that_has_it():
    assert D.I18N["en"]["ai.note"] == "These suggestions are generated automatically. Your teacher makes the final decision."
    for code in ("en", "af", "zu"):
        assert "ai.note" in D.I18N[code]


# ---- persistence ------------------------------------------------------------------------------
def test_state_survives_a_restart_and_resumes_in_sync(tmp_path):
    path = str(tmp_path / "k.db")
    s = make(store=Store(path)); s.set_role("teacher"); s.toggle_net()
    s.save_mark("L03", "T6", "38")
    n_hub = len(s.hub.log); s.store.close()
    s2 = make(store=Store(path))
    assert len(s2.hub.log) >= n_hub and s2.hub.current_mark("L03", "T6").value == 38
    assert s2.phone.current_mark("L03", "T6").value == 38            # restart syncs, converged
    assert s2.converged() and s2.audit_status()[0]


def test_restart_mid_conflict_keeps_both_values(tmp_path):
    path = str(tmp_path / "k.db")
    s = make(store=Store(path)); s.start_demo()
    for _ in range(5):
        s.next_demo()                                                  # offline concurrent edits, not yet synced
    s.store.close()
    s2 = make(store=Store(path))                                       # restart: syncs on load -> conflict flagged
    cm = s2.hub.current_mark("L03", "T4")
    assert cm.conflict and sorted([cm.value, *[a.value for a in cm.alternatives]]) == [45, 52]


def test_reset_wipes_saved_data(tmp_path):
    path = str(tmp_path / "k.db")
    s = make(store=Store(path)); s.set_role("teacher"); s.save_mark("L03", "T6", "38"); s.reset()
    assert s.hub.current_mark("L03", "T6") is None
    assert make(store=Store(path)).hub.current_mark("L03", "T6") is None


def test_tampered_database_row_is_detected_and_the_app_recovers(tmp_path):
    path = str(tmp_path / "k.db")
    s = make(store=Store(path)); s.store.close()
    import sqlite3
    c = sqlite3.connect(path)
    body, = c.execute("SELECT body FROM events WHERE node_id='hub' AND seq=20").fetchone()
    d = json.loads(body); d["payload"]["value"] = 99
    c.execute("UPDATE events SET body=? WHERE node_id='hub' AND seq=20", (json.dumps(d),)); c.commit(); c.close()
    s2 = make(store=Store(path))                                       # digest mismatch -> reseed, never crash
    assert s2.hub.current_mark("L03", "T4").value == 34
    assert any(e.action == "STORAGE_RESET" for e in s2.audit.entries)


def test_unsupported_schema_version_is_refused(tmp_path):
    import sqlite3
    path = str(tmp_path / "k.db")
    c = sqlite3.connect(path); c.execute("PRAGMA user_version = 99"); c.commit(); c.close()
    with pytest.raises(StoreError):
        Store(path)


def test_unwritable_storage_falls_back_to_memory_without_crashing(tmp_path):
    s = make(store=Store(str(tmp_path / "k.db")))
    s.store.close()                                                    # simulate the disk going away
    s.set_role("teacher")
    assert s.save_mark("L03", "T6", "38") is None
    assert "memory" in s.persistence_note or "lost" in s.persistence_note
    assert s.hub.current_mark("L03", "T6").value == 38


def test_sql_injection_in_text_is_just_text(tmp_path):
    s = make(store=Store(str(tmp_path / "k.db"))); s.set_role("teacher")
    evil = "'); DROP TABLE events;--"
    assert s.add_comment("L03", evil) is None
    s.store.close()
    s2 = make(store=Store(str(tmp_path / "k.db")))
    assert any(c.text == evil for c in s2.hub.comments_for("L03"))
