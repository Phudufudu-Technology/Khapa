"""UI-layer tests. No display and no Flutter needed: the Flet control trees are built for real
(Flet 1.0.5 objects), only the page connection is stubbed. They check that every role screen builds in
every demo state, that required copy (AI disclosure, stale banner, not-translated notice) is present, that
updates are targeted, and that dialogs and handlers behave.

Rendering itself was checked separately in the real Flet desktop client (see docs/VERIFICATION.md).
"""
import asyncio

import flet as ft
import pytest

from conftest import ManualScheduler
from khapa_core import data as D
from khapa_core.demo import DEMO
from khapa_core.session import Session
from khapa_core.store import Store
from khapa_ui import views
from khapa_ui.app import KhapaApp, make_ui_scheduler, safe

AI = "generated automatically"


class StubPage:
    def __init__(self):
        self.controls, self.width, self.dialogs = [], 390, []
        self.navigation_bar = self.on_resize = self.bgcolor = self.padding = self.theme_mode = None
        self.tasks = []

    def add(self, *c):
        self.controls.extend(c)

    def update(self, *a):
        pass

    def show_dialog(self, d):
        d.open = True
        self.dialogs.append(d)

    def pop_dialog(self):
        return self.dialogs.pop() if self.dialogs else None

    def run_task(self, fn, *a, **k):
        self.tasks.append((fn, a, k))
        return None

    def run_thread(self, fn, *a, **k):
        fn(*a, **k)


@pytest.fixture
def updates(monkeypatch):
    """Record every Control.update() call (the real one needs a live client connection)."""
    seen = []
    monkeypatch.setattr(ft.Control, "update", lambda self: seen.append(self), raising=True)
    return seen


@pytest.fixture
def app(updates):
    page = StubPage()
    s = Session(store=Store(None), now_ms=lambda: 1_800_000_000_000, scheduler=ManualScheduler())
    a = KhapaApp(page, s)
    a.mount()
    a.page_stub, a.sched = page, s._schedule
    updates.clear()
    return a


def texts(node, out=None):
    """Every visible string in a control tree."""
    out = [] if out is None else out
    if isinstance(node, (list, tuple)):
        for n in node:
            texts(n, out)
        return out
    if isinstance(node, str):
        out.append(node)
        return out
    if not isinstance(node, ft.BaseControl):
        return out
    for attr in ("value", "content", "label", "title", "text", "hint_text", "tooltip", "error_text"):
        v = getattr(node, attr, None)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, ft.BaseControl):
            texts(v, out)
    for sp in getattr(node, "spans", None) or []:
        out.append(getattr(sp, "text", "") or "")
    for attr in ("controls", "actions"):
        for ch in getattr(node, attr, None) or []:
            texts(ch, out)
    ch = getattr(node, "content", None)
    if isinstance(ch, ft.BaseControl):
        texts(ch, out)
    return out


def find(node, pred, out=None):
    out = [] if out is None else out
    if isinstance(node, (list, tuple)):
        for n in node:
            find(n, pred, out)
        return out
    if pred(node):
        out.append(node)
    if isinstance(node, ft.BaseControl):
        for attr in ("controls", "actions"):
            for ch in getattr(node, attr, None) or []:
                find(ch, pred, out)
        if isinstance(getattr(node, "content", None), ft.BaseControl):
            find(node.content, pred, out)
    return out


def body_text(app):
    return " ".join(texts(app.body.controls))


# ---- mounting and chrome ----------------------------------------------------------------------
def test_mount_shows_guide_and_synced_chip(app):
    assert app.s.role == "guide" and "One mark, four people" in body_text(app)
    assert app.chip_text.value.startswith("Everything is synced")
    assert len(app.nav.destinations) == 5 and app.nav.selected_index == 0
    assert app.net.value is True


def test_guide_is_honest_about_what_is_simulated(app):
    t = body_text(app)
    assert "Simulated" in t and "Fictional" in t and "No AI model runs in this app" in t
    assert "Afrikaans and isiZulu are drafts" in t


@pytest.mark.parametrize("role", ["guide", "teacher", "parent", "learner", "principal"])
def test_every_role_builds_in_every_demo_state(app, role):
    s = app.s
    s.start_demo()
    for step in range(len(DEMO)):
        if step:
            s.next_demo()
        s.role = role
        ctrls = views.VIEWS[role](app)
        assert ctrls and texts(ctrls)


@pytest.mark.parametrize("role", ["teacher", "parent", "learner", "principal"])
def test_ai_disclosure_is_shown_wherever_suggestions_are(app, role):
    app.s.set_role(role)
    assert AI in body_text(app)


def test_suggestion_text_comes_from_the_rule_based_suggester_only(app):
    app.s.pick_learner("L03"); app.s.set_role("parent")
    assert D.TIPS["Trigonometry"]["parent"] in body_text(app)
    assert app.s.suggester.name == "rules"


# ---- offline / stale banner -------------------------------------------------------------------
def test_phone_shows_a_stale_banner_only_while_offline(app):
    s = app.s
    s.set_role("parent")
    assert "last saved on this phone" not in body_text(app)
    s.toggle_net()
    assert "last saved on this phone" in body_text(app) and app.net.value is False
    s.toggle_net()
    assert "last saved on this phone" not in body_text(app)


def test_waiting_chip_counts_pending_events(app):
    s = app.s
    s.set_role("teacher"); s.toggle_net(); s.save_mark("L03", "T6", "38")
    assert app.chip_text.value == "1 waiting to upload"
    s.toggle_net()
    assert app.chip_text.value.startswith("Everything is synced")


# ---- language ---------------------------------------------------------------------------------
def test_untranslated_language_shows_a_visible_notice(app):
    app.s.set_lang("xh")
    assert app.lang_note.visible and app.lang_note.value == "Not translated yet. Showing English."
    app.s.set_lang("af")
    assert app.lang_note.visible and "human review" in app.lang_note.value
    app.s.set_role("teacher")
    assert "Onderwyser" in [d.label for d in app.nav.destinations]
    app.s.set_lang("en")
    assert not app.lang_note.visible


# ---- demo banner ------------------------------------------------------------------------------
def test_demo_banner_follows_the_seven_steps(app):
    s = app.s
    assert not app.demo_box.visible
    s.start_demo()
    for i, step in enumerate(DEMO):
        if i:
            s.next_demo()
        assert app.demo_box.visible
        t = " ".join(texts(app.demo_box.content))
        assert f"Step {i + 1} of 7." in t and step.text in t
        has_next = any(isinstance(b, ft.FilledButton) for b in app.demo_box.content.controls[0].controls)
        assert has_next == (i < len(DEMO) - 1)
    s.end_demo()
    assert not app.demo_box.visible


# ---- targeted updates (the brief's "no innerHTML rebuild" requirement) ---------------------------
def test_scopes_update_only_their_own_region(app, updates):
    s = app.s
    s.toggle_devices()
    assert set(map(id, updates)) <= {id(app.devices_toggle), id(app.devices_box)}
    updates.clear()
    s.end_demo()
    assert [id(u) for u in updates] == [id(app.demo_box)]
    updates.clear()
    s.pick_learner("L05")
    assert [id(u) for u in updates] == [id(app.body)]


def test_wide_tables_keep_one_persistent_scroll_host(app):
    app.s.set_role("teacher")
    host = app.scroll_host("marks_grid")
    app.s.toggle_net(); app.s.toggle_net()
    app.s.set_role("teacher")
    assert find(app.body.controls, lambda n: n is host)  # same object, so Flutter keeps the scroll offset


# ---- teacher interactions ---------------------------------------------------------------------
def alerts(app):
    """AlertDialogs that are open (toasts are SnackBars in the same stack)."""
    return [d for d in app.page.dialogs if isinstance(d, ft.AlertDialog) and d.open]


def action(dlg, label):
    return next(b for b in dlg.actions if b.content == label)


def test_mark_dialog_validates_saves_and_closes(app):
    s = app.s
    s.set_role("teacher")
    app.open_mark("L03", "T6")
    dlg = alerts(app)[0]
    field = find(dlg.content, lambda n: isinstance(n, ft.TextField))[0]
    field.value = "abc"
    action(dlg, "Save mark").on_click(None)
    assert field.error_text == "Enter a mark between 0 and 100." and alerts(app)
    field.value = "38,5"
    action(dlg, "Save mark").on_click(None)
    # the "Saved" toast is a dialog too: the mark dialog itself must be the one that closed
    assert not alerts(app) and s.hub.current_mark("L03", "T6").value == 38.5
    assert any(isinstance(d, ft.SnackBar) for d in app.page.dialogs)


def test_conflict_cell_opens_the_resolve_dialog_and_choosing_converges(app):
    s = app.s
    s.start_demo()
    for _ in range(5):
        s.next_demo()
    cell = find(app.body.controls, lambda n: isinstance(n, ft.Container) and (n.tooltip or "").startswith("Sipho Mokoena, Trigonometry"))[0]
    assert "2 values" in " ".join(texts(cell))
    cell.on_click(None)
    dlg = alerts(app)[0]
    keeps = [b for b in find(dlg.content, lambda n: isinstance(n, ft.FilledButton)) if str(b.content).startswith("Keep")]
    assert sorted(str(b.content).split()[1] for b in keeps) == ["45", "52"]
    next(b for b in keeps if " 52 " in f" {b.content} ").on_click(None)
    assert not alerts(app)
    s._auto_sync()
    assert s.converged() and not s.hub.current_mark("L03", "T4").conflict
    assert all(n.current_mark("L03", "T4").value == 52 for n in s.nodes.values())


def test_learner_dialog_has_ai_note_and_comment_flow(app):
    s = app.s
    s.set_role("teacher")
    app.open_learner("L03")
    dlg = alerts(app)[0]
    t = " ".join(texts(dlg.content))
    assert "Needs support" in t and AI in t and "Trigonometry" in t
    field = find(dlg.content, lambda n: isinstance(n, ft.TextField))[0]
    field.value = "Please practise daily."
    action(dlg, "Add comment").on_click(None)
    assert any(c.text == "Please practise daily." for c in s.hub.comments_for("L03"))
    field.value = "   "
    action(dlg, "Add comment").on_click(None)
    assert field.error_text


def test_non_teachers_cannot_open_a_learner_record(app):
    app.s.set_role("parent")
    app.open_learner("L01")
    assert not alerts(app)  # denied: a toast is shown instead, and the audit log records it
    assert any(e.action == "ACCESS_DENIED" for e in app.s.audit.entries)


# ---- devices and security panel ---------------------------------------------------------------
def test_devices_panel_shows_four_devices_clock_skew_and_audit(app):
    s = app.s
    s.toggle_devices()
    t = " ".join(texts(app.devices_box.controls))
    for label in ("School hub", "HOD tablet", "Cloud", "Parent and learner phone"):
        assert label in t
    assert "4 minutes slow" in t and "Audit chain intact" in t and "canary" in t.lower()


def test_security_probes_show_in_the_panel(app):
    s = app.s
    s.set_role("parent"); s.toggle_devices()
    app._probe(s.probe_canary)
    t = " ".join(texts(app.devices_box.controls))
    assert "Blocked" in t and "CANARY_TRIPPED" in t
    app._probe(s.tamper_demo)
    assert "BROKEN" in " ".join(texts(app.devices_box.controls)) or "chain check says BROKEN" in app._probe_text


# ---- robustness -----------------------------------------------------------------------------------
def test_safe_wrapper_swallows_handler_errors_and_toasts(app):
    toasts = []
    app._toast = toasts.append

    class X:
        _toast = staticmethod(toasts.append)

        @safe
        def boom(self):
            raise RuntimeError("x")
    X().boom()
    assert toasts == ["Something went wrong. Please try again."]


def test_ui_scheduler_runs_in_page_context_and_can_be_cancelled():
    ran = []

    class P:
        def run_task(self, fn):
            asyncio.run(fn())

    handle = make_ui_scheduler(P())(0, lambda: ran.append(1))
    assert ran == [1]
    h2 = make_ui_scheduler(P())(0, lambda: ran.append(2))
    assert ran == [1, 2] and hasattr(h2, "cancel")


def test_theme_toggle_rebuilds_without_losing_state(app):
    s = app.s
    s.set_role("parent"); s.pick_learner("L06")
    before = app.pal
    app._toggle_theme(None)
    assert app.pal is not before and s.learner_id == "L06" and "Kabelo" in body_text(app)
