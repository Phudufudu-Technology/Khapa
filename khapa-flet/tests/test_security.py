import dataclasses

import pytest

from khapa_core.security import (ALERT, CANARY_LEARNER_ID, AccessDenied, AuditLog, Guard, clean_log_text)
from khapa_core.world import build_world


def log_with(n=5):
    a = AuditLog()
    for i in range(n):
        a.append(1000 + i, "info", "sys", "ACT", f"detail {i}")
    return a


def test_audit_chain_verifies_when_untouched_and_empty():
    assert AuditLog().verify() == (True, None)
    assert log_with().verify() == (True, None)


@pytest.mark.parametrize("field,value", [("detail", "changed"), ("actor", "mallory"), ("ts_ms", 1), ("severity", "info2"), ("action", "X")])
def test_editing_any_audit_field_breaks_the_chain(field, value):
    a = log_with()
    a.entries[2] = dataclasses.replace(a.entries[2], **{field: value})
    assert a.verify() == (False, 2)


def test_deleting_or_reordering_audit_entries_breaks_the_chain():
    a = log_with(); del a.entries[1]
    assert a.verify()[0] is False
    b = log_with(); b.entries[1], b.entries[2] = b.entries[2], b.entries[1]
    assert b.verify()[0] is False
    c = log_with(); c.entries.pop()  # truncating the tail is not detectable by a chain alone
    assert c.verify()[0] is True


def test_log_injection_is_neutralised():
    s = clean_log_text("ok\nFAKE 12:00 ADMIN LOGIN\r\x1b[31m" + "x" * 500)
    assert "\n" not in s and "\r" not in s and "\x1b" not in s and len(s) <= 200
    a = AuditLog(); e = a.append(1, "info", "a\nb", "ACT\n", "d\ne")
    assert "\n" not in e.actor + e.action + e.detail


def guard():
    w = build_world(lambda: 1_800_000_000_000)
    a = AuditLog()
    return Guard(a, lambda: 5), a, w


def test_canary_read_is_blocked_hidden_and_raises_an_alert_for_every_role():
    g, audit, w = guard()
    assert CANARY_LEARNER_ID in w["hub"].learners  # it is stored and synced like real data
    for role in ("teacher", "principal", "parent", "learner", "guide"):
        with pytest.raises(AccessDenied):
            g.read_learner(role, CANARY_LEARNER_ID, "L03", w["hub"])
    assert len(audit.alerts()) == 5 and all(e.action == "CANARY_TRIPPED" and e.severity == ALERT for e in audit.alerts())
    assert audit.verify()[0]


def test_canary_is_never_listed():
    g, _, w = guard()
    assert CANARY_LEARNER_ID not in g.list_learner_ids("teacher", w["hub"])
    assert len(g.list_learner_ids("teacher", w["hub"])) == 14


def test_parents_can_only_open_their_own_child_and_denials_are_audited():
    g, audit, w = guard()
    assert g.read_learner("parent", "L03", "L03", w["phone"]).first_name == "Sipho"
    with pytest.raises(AccessDenied):
        g.read_learner("parent", "L01", "L03", w["phone"])
    assert audit.entries[-1].action == "ACCESS_DENIED"


def test_role_policy():
    g, audit, _ = guard()
    g.require("teacher", "write_mark")
    for role, act in [("parent", "write_mark"), ("learner", "write_comment"), ("principal", "write_mark"), ("guide", "read_class"), ("nobody", "write_mark")]:
        with pytest.raises(AccessDenied):
            g.require(role, act)
    assert len(audit.entries) == 5
