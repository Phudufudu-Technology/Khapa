"""KhapaApp: builds the control tree once and updates only the region that changed.

Regions (each has its own render method and its own ``.update()``):
  chrome   network switch, sync chip, language note, bottom navigation
  body     the current role screen
  demo     the guided-demo banner
  devices  the devices + audit/security panel
Session announces which scopes changed; nothing is rebuilt wholesale except on a theme change.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import threading
import time

import flet as ft

from khapa_core import analytics as A
from khapa_core import data as D
from khapa_core import i18n
from khapa_core.demo import DEMO
from khapa_core.security import ALERT, WARN, AccessDenied
from khapa_core.session import ROLES, Session

from . import views
from . import widgets as w
from .theme import DARK, LIGHT, MAX_WIDTH, Palette

W = ft.FontWeight
log = logging.getLogger("khapa.ui")


def safe(fn):
    """UI event handlers must never fail silently or crash a judge's session: log the traceback,
    show a short message, and carry on."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception:  # noqa: BLE001 - last line of defence at the UI boundary
            log.exception("UI handler %s failed", fn.__name__)
            try:
                self._toast("Something went wrong. Please try again.")
            except Exception:
                pass
    return wrapper


class _Handle:
    """Cancellable handle returned to Session for a scheduled callback."""

    def __init__(self) -> None:
        self.cancelled = False
        self.future = None

    def cancel(self) -> None:
        self.cancelled = True
        if self.future is not None:
            self.future.cancel()


def make_ui_scheduler(page: ft.Page):
    """Session timers (auto-sync debounce, highlight fade) must run inside Flet's page context, or
    their control updates are silently dropped. page.run_task provides that context."""
    def schedule(delay_s: float, fn):
        handle = _Handle()

        async def job() -> None:
            await asyncio.sleep(delay_s)
            if not handle.cancelled:
                fn()
        handle.future = page.run_task(job)
        return handle
    return schedule


NAV_ICONS = {"guide": ft.Icons.HOME_OUTLINED, "teacher": ft.Icons.EDIT_NOTE, "parent": ft.Icons.FAMILY_RESTROOM,
             "learner": ft.Icons.SCHOOL_OUTLINED, "principal": ft.Icons.INSIGHTS}


class KhapaApp:
    def __init__(self, page: ft.Page, session: Session, dark: bool = False) -> None:
        self.page, self.s = page, session
        self.pal: Palette = DARK if dark else LIGHT
        self._lock = threading.RLock()
        self._mounted = False
        self._probe_text = ""
        self._dialog_refresh = None
        self._hosts: dict[str, ft.Row] = {}

    # ---- mounting -------------------------------------------------------------------------
    def mount(self) -> None:
        self.s.subscribe(self._on_scope)
        self.s.on_toast(self._toast)
        self.page.on_resize = self._on_resize
        self._build()
        self._mounted = True

    def _build(self) -> None:
        p, s = self.pal, self.s
        self.page.bgcolor = p.paper
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.DARK if p is DARK else ft.ThemeMode.LIGHT

        # chrome
        self.net = ft.Switch(label="Internet", value=s.online, on_change=self._on_net, active_color=p.tick,
                             label_text_style=ft.TextStyle(color=p.top_ink, size=14))
        self.chip_text = ft.Text("", size=13, color=p.ink)
        self.chip_dot = ft.Container(width=8, height=8, border_radius=4)
        self.chip = ft.Container(ft.Row([self.chip_dot, self.chip_text], spacing=6, tight=True), border_radius=999,
                                 padding=ft.Padding.symmetric(horizontal=12, vertical=4))
        self.lang = ft.Dropdown(
            value=s.lang, dense=True, width=170, text_size=13, bgcolor=p.sheet, filled=True, fill_color=p.sheet,
            color=p.ink, border_color=p.rule,
            options=[ft.DropdownOption(key=l["code"], text=l["name"]) for l in D.LANGS],
            on_select=lambda e: s.set_lang(e.control.value), tooltip="Language")
        self.lang_note = ft.Text("", size=12.5, color=p.top_ink, visible=False)
        self.theme_btn = ft.IconButton(ft.Icons.DARK_MODE if p is LIGHT else ft.Icons.LIGHT_MODE, icon_color=p.top_ink,
                                       tooltip="Switch light or dark", on_click=self._toggle_theme)
        header = ft.Container(
            ft.Column([
                ft.Row([ft.Text("Khapa", size=24, weight=W.W_700, color=p.top_ink), self.lang, self.theme_btn],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.net,
                ft.Row([self.chip], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.lang_note], spacing=2, tight=True),
            bgcolor=p.top, padding=ft.Padding.only(left=14, right=8, top=6, bottom=8))

        self.demo_box = ft.Container(visible=False)
        self.body = ft.Column(spacing=14, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.devices_toggle = ft.TextButton(content="Show devices and security", icon=ft.Icons.DEVICES,
                                            on_click=lambda e: s.toggle_devices(), style=ft.ButtonStyle(color=p.blue))
        self.devices_box = ft.Column(spacing=10, visible=False, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.scroller = ft.Column([ft.Container(ft.Column([self.body, self.devices_toggle, self.devices_box], spacing=14,
                                                                          horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                                                padding=ft.Padding.all(14))], scroll=ft.ScrollMode.AUTO, expand=True,
                                  horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self.shell = ft.Container(ft.Column([header, self.demo_box, self.scroller], spacing=0, expand=True),
                                  width=self._shell_width(), expand=True)
        self.nav = ft.NavigationBar(
            destinations=[ft.NavigationBarDestination(icon=NAV_ICONS[r], label=s.t(f"role.{r}")) for r in ROLES],
            selected_index=ROLES.index(s.role), on_change=lambda e: s.set_role(ROLES[int(e.control.selected_index)]),
            bgcolor=p.sheet, indicator_color=p.blue_soft)
        self.page.controls.clear()
        self.page.navigation_bar = self.nav
        self.page.add(ft.SafeArea(ft.Row([self.shell], alignment=ft.MainAxisAlignment.CENTER, expand=True), expand=True))
        self._render_all(update=False)
        self.page.update()

    def _shell_width(self) -> float | None:
        w_ = self.page.width or MAX_WIDTH
        return min(w_, MAX_WIDTH)

    def _on_resize(self, e) -> None:
        with self._lock:
            self.shell.width = self._shell_width()
            self.shell.update()

    # ---- scope dispatch ---------------------------------------------------------------------
    def run_ui(self, fn, *args) -> None:
        """Run fn inside the page context (for code that did not start from a Flet event)."""
        self.page.run_thread(fn, *args)

    @safe
    def _on_scope(self, scope: str) -> None:
        if not self._mounted:
            return
        with self._lock:
            {"chrome": self._render_chrome, "body": self._render_body, "demo": self._render_demo,
             "devices": self._render_devices, "security": self._render_devices}.get(scope, lambda: None)()

    def _render_all(self, update: bool = True) -> None:
        for fn in (self._render_chrome, self._render_body, self._render_demo, self._render_devices):
            fn(update) if update else fn(False)

    # ---- chrome ---------------------------------------------------------------------------
    def _render_chrome(self, update: bool = True) -> None:
        s, p = self.s, self.pal
        self.net.value = s.online
        chip = s.chip()
        if chip.waiting:
            self.chip_text.value = s.t("sync.up", n=chip.count)
            self.chip.bgcolor, self.chip.border = p.hl_soft, ft.Border.all(1, p.hl)
            self.chip_dot.bgcolor = p.ink
        else:
            when = "" if chip.updated_ms is None else f", {s.t('updated').lower()} {views._time(chip.updated_ms)}"
            self.chip_text.value = s.t("sync.allSynced") + when
            self.chip.bgcolor, self.chip.border = p.tick_soft, ft.Border.all(1, p.tick)
            self.chip_dot.bgcolor = p.tick
        self.chip_text.color = p.ink
        note = i18n.note_for(s.lang)
        self.lang_note.value, self.lang_note.visible = note, bool(note)
        self.lang.value = s.lang
        self.nav.selected_index = ROLES.index(s.role)
        for i, r in enumerate(ROLES):
            self.nav.destinations[i].label = s.t(f"role.{r}")
        if update:
            for ctl in (self.net, self.chip, self.lang, self.lang_note, self.nav):
                ctl.update()

    # ---- body -----------------------------------------------------------------------------
    def _render_body(self, update: bool = True) -> None:
        self.body.controls = views.VIEWS[self.s.role](self)
        if update:
            self.body.update()

    def scroll_top(self) -> None:
        try:
            self.page.run_task(self.scroller.scroll_to, offset=0)
        except Exception:
            pass

    # ---- demo banner ----------------------------------------------------------------------
    def _render_demo(self, update: bool = True) -> None:
        s, p = self.s, self.pal
        i = s.demo_index
        if i is None:
            self.demo_box.visible = False
        else:
            last = i >= len(DEMO) - 1
            buttons = [] if last else [ft.FilledButton(content=s.t("demo.next"), on_click=lambda e: s.next_demo())]
            buttons += [ft.OutlinedButton(content=s.t("demo.restart"), on_click=lambda e: s.start_demo()),
                        ft.TextButton(content="Close", on_click=lambda e: s.end_demo(), style=ft.ButtonStyle(color=p.blue))]
            self.demo_box.content = ft.Column([
                ft.Row(buttons, wrap=True, spacing=8, run_spacing=4),
                ft.Text(spans=[ft.TextSpan(f"Step {i + 1} of {len(DEMO)}. ", ft.TextStyle(weight=W.W_700)), ft.TextSpan(DEMO[i].text)],
                        size=14.5, color=p.ink)], spacing=8, tight=True)
            self.demo_box.bgcolor = p.blue_soft
            self.demo_box.padding = ft.Padding.symmetric(horizontal=14, vertical=10)
            self.demo_box.border = ft.Border(bottom=ft.BorderSide(2, p.blue))
            self.demo_box.visible = True
        if update:
            self.demo_box.update()

    # ---- devices + security panel ---------------------------------------------------------
    def _render_devices(self, update: bool = True) -> None:
        s, p = self.s, self.pal
        self.devices_toggle.content = "Hide devices and security" if s.devices_open else "Show devices and security"
        self.devices_box.visible = s.devices_open
        if s.devices_open:
            self.devices_box.controls = self._devices_controls()
        if update:
            self.devices_toggle.update()
            self.devices_box.update()

    def _devices_controls(self) -> list[ft.Control]:
        s, p = self.s, self.pal
        cards = []
        for d in s.devices():
            lines = [w.txt(d["label"], p, 14, W.W_600), w.txt(f"{s.plural(d['stored'], 'event')} stored", p, 13)]
            if d["id"] != "cloud":
                lines += [w.txt(f"{s.plural(d['up'], 'event')} waiting to upload", p, 13),
                          w.txt(f"{s.plural(d['down'], 'event')} waiting to download", p, 13)]
            lines += [w.muted(d["skew"], p, 12), w.muted(f"State fingerprint {d['fingerprint']}", p, 11)]
            cards.append(ft.Container(ft.Column(lines, spacing=2, tight=True), padding=ft.Padding.all(10), width=250,
                                      border=ft.Border.all(1, p.rule), border_radius=8))
        ok, bad = s.audit_status()
        chain = (w.txt("Audit chain intact", p, 13, W.W_600, color=p.tick) if ok else
                 w.txt(f"Audit chain BROKEN at entry {bad + 1}", p, 13, W.W_600, color=p.pen))
        entries = []
        for e in s.audit_recent(12):
            color = p.pen if e.severity == ALERT else p.ink if e.severity == WARN else p.ink2
            entries.append(w.txt(f"{e.seq:>3}  {time.strftime('%H:%M:%S', time.localtime(e.ts_ms / 1000))}  {e.action}  {e.actor}: {e.detail}",
                                 p, 12, color=color, selectable=True))
        probe = [ft.OutlinedButton(content="Snoop: open the hidden canary record", on_click=lambda e: self._probe(s.probe_canary)),
                 ft.OutlinedButton(content="Snoop: parent opens another child", on_click=lambda e: self._probe(s.probe_other_child)),
                 ft.OutlinedButton(content="Tamper with the audit log", on_click=lambda e: self._probe(s.tamper_demo))]
        sec = [w.heading("Audit and security", p, 17),
               w.muted("Every save, conflict, refused action and snooping attempt is written to a hash-chained log. "
                       "Editing any entry breaks the chain. The canary is a hidden decoy learner: no screen lists it, so any attempt to open it is an alert.", p, 13),
               chain, ft.Row(probe, wrap=True, spacing=8, run_spacing=6),
               w.txt(self._probe_text, p, 13, W.W_600, color=p.blue, visible=bool(self._probe_text)),
               ft.Column(entries, spacing=2, tight=True)]
        if s.persistence_note:
            sec.insert(1, w.banner(p, s.persistence_note))
        return [
            w.sheet(p, [w.heading(s.t("sync.devices"), p),
                        w.muted("For the demo you can see every device. In real life each device only knows its own data. "
                                "Clocks are deliberately wrong to show the sync copes with it.", p, 13),
                        ft.Row(cards, wrap=True, spacing=8, run_spacing=8),
                        ft.Row([ft.OutlinedButton(content="Make the HOD tablet change Sipho’s Trigonometry mark to 52", on_click=lambda e: s.hod_edit()),
                                ft.TextButton(content="Reset demo data", on_click=lambda e: s.reset(), style=ft.ButtonStyle(color=p.pen))],
                               wrap=True, spacing=8, run_spacing=4),
                        ft.Column([w.txt(l, p, 12, color=p.ink2) for l in s.log_lines[:14]], spacing=1, tight=True)], 10),
            w.sheet(p, sec, 8)]

    @safe
    def _probe(self, fn) -> None:
        self._probe_text = fn()
        self._render_devices()

    def scroll_host(self, name: str) -> ft.Row:
        """One long-lived horizontally scrolling Row per wide table (see views.view_teacher)."""
        if name not in self._hosts:
            self._hosts[name] = ft.Row(scroll=ft.ScrollMode.AUTO)
        return self._hosts[name]

    # ---- ctx methods used by views -------------------------------------------------------------
    @safe
    def go_role(self, role: str) -> None:
        self.s.set_role(role)
        self.scroll_top()

    @safe
    def pick_learner(self, learner_id: str) -> None:
        self.s.pick_learner(learner_id)

    @safe
    def start_demo(self) -> None:
        self.s.start_demo()
        self.scroll_top()

    @safe
    def open_mark(self, learner_id: str, task_id: str) -> None:
        s, p = self.s, self.pal
        cm, tk = s.hub.current_mark(learner_id, task_id), s.task(task_id)
        field = ft.TextField(label="Mark, 0 to 100", value="" if cm is None else A.num(cm.value), autofocus=True,
                             keyboard_type=ft.KeyboardType.NUMBER, on_submit=lambda e: save(e))

        def save(e) -> None:
            err = s.save_mark(learner_id, task_id, field.value)
            if err:
                field.error_text = err
                field.update()
            else:
                self._close(dlg)
        dlg = self._show(ft.AlertDialog(
            title=ft.Text(s.full_name(learner_id)), modal=False,
            content=ft.Column([w.muted(f"{tk['topic']} {tk['kind'].lower()}, term {tk['term']}", p), field], tight=True, spacing=12, width=300),
            actions=[ft.FilledButton(content=s.t("marks.save"), on_click=save),
                     ft.TextButton(content=s.t("marks.cancel"), on_click=lambda e: self._close(dlg))]))

    @safe
    def open_resolve(self, learner_id: str, task_id: str) -> None:
        s, p = self.s, self.pal
        cm, tk = s.hub.current_mark(learner_id, task_id), s.task(task_id)
        if cm is None:
            return
        options = [(cm.value, cm.entered_by or "unknown")] + [(a.value, a.entered_by or "unknown") for a in cm.alternatives]
        field = ft.TextField(label="Or enter a different mark", keyboard_type=ft.KeyboardType.NUMBER)

        def choose(v: float) -> None:
            err = s.choose_mark(learner_id, task_id, v)
            if err:
                field.error_text = err
                field.update()
            else:
                self._close(dlg)

        def save(e) -> None:
            err = s.save_mark(learner_id, task_id, field.value)
            if err:
                field.error_text = err
                field.update()
            else:
                self._close(dlg)
        dlg = self._show(ft.AlertDialog(
            title=ft.Text("Two values for one mark"),
            content=ft.Column([w.muted(f"{s.full_name(learner_id)}, {tk['topic']}. Both are saved. Choose the final mark, or enter a new one.", p),
                               *[ft.FilledButton(content=f"Keep {A.num(v)} (entered by {who})", on_click=lambda e, v=v: choose(v))
                                 for v, who in options], field], tight=True, spacing=10, width=320),
            actions=[ft.FilledButton(content=s.t("marks.save"), on_click=save),
                     ft.TextButton(content=s.t("marks.cancel"), on_click=lambda e: self._close(dlg))]))

    @safe
    def open_learner(self, learner_id: str) -> None:
        s, p = self.s, self.pal
        try:
            s.open_learner(learner_id)
        except AccessDenied as exc:
            self._toast(str(exc))
            return
        comments_col = ft.Column(spacing=6, tight=True)
        field = ft.TextField(hint_text=s.t("comments.placeholder"), multiline=True, min_lines=2, max_lines=4, max_length=500)

        def refresh() -> None:
            comments_col.controls = views._comments(self, s.hub, learner_id)

        def add(e) -> None:
            err = s.add_comment(learner_id, field.value)
            if err:
                field.error_text = err
            else:
                field.value, field.error_text = "", None
                refresh()
                comments_col.update()
            field.update()
        refresh()
        marks = A.learner_marks(s.hub, D.TASKS, learner_id)
        r = A.risk(marks)
        tips = [ft.Column([w.txt(f"{x.topic}.", p, 14, W.W_600), w.txt(s.suggester.tip("teacher", x.topic), p, 14)], spacing=1, tight=True)
                for x in sorted(r.weak, key=lambda x: x.value)]
        body: list[ft.Control] = [
            ft.Row([w.pill(p, r.level), w.muted(f"Projected year mark {A.num(r.projection.value)}%" if r.projection.value is not None else "", p)],
                   spacing=8, wrap=True),
            w.spark(p, marks), w.mark_bars(p, marks, s.t("marks.empty"))]
        if r.reasons:
            body.append(w.margin_note(p, " ".join(r.reasons)))
        if tips:
            body += [w.txt("Suggested teaching focus", p, 15, W.W_600), *tips]
        body += [w.ai_note(p, s.t("ai.note")), w.txt(s.t("comments.title"), p, 15, W.W_600), comments_col,
                 ft.Text(s.t("comments.add"), size=13, color=p.ink2), field]
        dlg = self._show(ft.AlertDialog(
            title=ft.Text(s.full_name(learner_id)), scrollable=True,
            content=ft.Column(body, tight=True, spacing=10, width=340),
            actions=[ft.FilledButton(content=s.t("comments.add"), on_click=add),
                     ft.TextButton(content="Close", on_click=lambda e: self._close(dlg))]))

    def _show(self, dlg: ft.AlertDialog) -> ft.AlertDialog:
        self.page.show_dialog(dlg)
        return dlg

    def _close(self, dlg: ft.AlertDialog) -> None:
        """Close one specific dialog. page.pop_dialog() closes the TOPMOST open dialog, and a toast
        (SnackBar) is also a dialog, so after a save it would close the toast and leave this open."""
        dlg.open = False
        dlg.update()

    # ---- handlers -------------------------------------------------------------------------
    @safe
    def _on_net(self, e) -> None:
        if e.control.value != self.s.online:
            self.s.toggle_net()

    @safe
    def _toggle_theme(self, e) -> None:
        with self._lock:
            self.pal = LIGHT if self.pal is DARK else DARK
            self._build()

    def _toast(self, msg: str) -> None:
        try:
            self.page.show_dialog(ft.SnackBar(ft.Text(msg), duration=2200))
        except Exception:
            pass
