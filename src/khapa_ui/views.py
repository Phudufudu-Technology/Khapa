"""Role screens: pure builders that turn Session state into Flet control trees.

Each builder returns a list of controls for the body column. Nothing here mutates state: taps call
back into ``ctx`` (the app), which calls Session methods and re-renders only the scope that changed.
"""

from __future__ import annotations

from typing import Protocol

import flet as ft

from khapa_core import analytics as A
from khapa_core import data as D
from khapa_core import i18n
from khapa_core.session import Session

from . import widgets as w
from .theme import Palette

W = ft.FontWeight


class Ctx(Protocol):
    s: Session
    pal: Palette

    def open_mark(self, learner_id: str, task_id: str) -> None: ...
    def open_resolve(self, learner_id: str, task_id: str) -> None: ...
    def open_learner(self, learner_id: str) -> None: ...
    def start_demo(self) -> None: ...
    def go_role(self, role: str) -> None: ...
    def pick_learner(self, learner_id: str) -> None: ...
    def scroll_host(self, name: str) -> ft.Row: ...


def trend_sentence(p: A.Projection) -> str:
    if p.n < 2:
        return "There are not enough marks yet to see a trend."
    if p.slope >= 4:
        return "Marks are going up."
    if p.slope <= -4:
        return "Marks have been going down."
    return "Marks are fairly steady."


def _time(ms: int | None) -> str:
    import time
    return time.strftime("%H:%M", time.localtime((ms or 0) / 1000))


def _updated(c: Ctx, node_id: str) -> str:
    return f"{c.s.t('updated')} {_time(c.s.last_sync.get(node_id, c.s._now()))}"


def _head(c: Ctx, h1: str, sub: str) -> ft.Control:
    return ft.Column([w.title(h1, c.pal), w.muted(sub, c.pal, 14)], spacing=4, tight=True)


def _comments(c: Ctx, node, learner_id: str) -> list[ft.Control]:
    items = list(reversed(node.comments_for(learner_id)))
    if not items:
        return [w.muted(c.s.t("comments.none"), c.pal)]
    return [ft.Container(ft.Column([w.txt(x.text, c.pal, 15), w.muted(f"{x.author_name}, {x.author_role}", c.pal, 12)],
                                   spacing=2, tight=True),
                         padding=ft.Padding.only(left=10, top=2, bottom=2),
                         border=ft.Border(left=ft.BorderSide(3, c.pal.rule))) for x in items]


def learner_picker(c: Ctx) -> ft.Control:
    dd = ft.Dropdown(
        label=c.s.t("view.as"), value=c.s.learner_id, expand=True, dense=True,
        options=[ft.DropdownOption(key=l["id"], text=f"{l['first']} {l['last']}") for l in D.LEARNERS],
        on_select=lambda e: c.pick_learner(e.control.value),
    )
    return dd


def _weak_sorted(r: A.Risk, limit: int | None = None) -> list[A.WeakTopic]:
    ws = sorted(r.weak, key=lambda x: x.value)
    return ws[:limit] if limit else ws


# ---- teacher --------------------------------------------------------------------------------
CELL_W, NAME_W, AVG_W, RISK_W = 84, 132, 54, 116
CELL_HEAT = 66


def _cell(c: Ctx, learner_id: str, task: dict, pending: set[str]) -> ft.Control:
    p, s = c.pal, c.s
    cm = s.hub.current_mark(learner_id, task["id"])
    who = f"{s.full_name(learner_id)}, {task['topic']}"
    border = ft.Border.all(1, p.rule)
    bg, fg, label, radius = None, p.ink, "—", 8
    if cm is None:
        fg = p.ink2
    else:
        label = s.t("marks.conflict", n=len(cm.alternatives) + 1) if cm.conflict else A.num(cm.value)
        if cm.conflict:
            bg, border = p.hl_soft, ft.Border.all(2, p.hl)
        elif cm.value < A.SUPPORT_THRESHOLD:
            border, fg, radius = ft.Border.all(2, p.pen), p.pen, 22
    if s.fresh.get(f"hub|{learner_id}|{task['id']}"):
        bg = p.hl_soft
    dot = ft.Container(width=7, height=7, border_radius=4, bgcolor=p.hl, border=ft.Border.all(1, p.ink2),
                       visible=bool(cm and cm.version_id in pending))
    handler = (lambda e, l=learner_id, t=task["id"]: c.open_resolve(l, t)) if (cm and cm.conflict) else \
              (lambda e, l=learner_id, t=task["id"]: c.open_mark(l, t))
    return ft.Container(
        ft.Row([w.txt(label, p, 13 if cm and cm.conflict else 15, W.W_600, color=fg), dot], spacing=3,
               alignment=ft.MainAxisAlignment.CENTER, tight=True),
        width=CELL_W, height=44, alignment=ft.Alignment.CENTER, bgcolor=bg, border=border, border_radius=radius,
        on_click=handler, ink=True, tooltip=f"{who}: {label}",
    )


def view_teacher(c: Ctx) -> list[ft.Control]:
    p, s, hub = c.pal, c.s, c.s.hub
    ids = s.learner_ids()
    pending = {e.entity_id for e in hub.pending_for(s.cloud)}
    captured = sum(1 for t in D.TASKS if any(hub.current_mark(i, t["id"]) for i in ids))
    risks = {i: A.risk(A.learner_marks(hub, D.TASKS, i)) for i in ids}

    header = ft.Row([ft.Container(w.muted("Learner", p, 12, weight=W.W_600), width=NAME_W)] +
                    [ft.Container(ft.Column([w.txt(t["topic"], p, 11, W.W_600), w.muted(f"{t['kind']}, term {t['term']}", p, 10)],
                                            spacing=0, tight=True), width=CELL_W) for t in D.TASKS] +
                    [ft.Container(w.muted(s.t("marks.average"), p, 12, weight=W.W_600), width=AVG_W),
                     ft.Container(w.muted("Support", p, 12, weight=W.W_600), width=RISK_W)], spacing=6)
    rows = []
    for i in ids:
        r = risks[i]
        avg = r.projection.average
        rows.append(ft.Row(
            [ft.Container(ft.TextButton(content=s.full_name(i), on_click=lambda e, l=i: c.open_learner(l),
                                        style=ft.ButtonStyle(color=p.blue, padding=ft.Padding.all(0), alignment=ft.Alignment.CENTER_LEFT)),
                          width=NAME_W)] +
            [_cell(c, i, t, pending) for t in D.TASKS] +
            [ft.Container(w.txt(A.num(avg) if avg is not None else "—", p, 14), width=AVG_W),
             ft.Container(w.pill(p, r.level), width=RISK_W)],
            spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER))
    # A persistent scrolling Row: re-renders refill it instead of replacing it, so the horizontal
    # scroll position survives syncs (a rebuilt Row would snap back to the first column).
    grid = c.scroll_host("marks_grid")
    grid.controls = [ft.Column([header, *rows], spacing=6, tight=True)]

    flagged = sorted((i for i in ids if risks[i].level != "ok"), key=lambda i: {"high": 0, "watch": 1}[risks[i].level])
    notes: list[ft.Control] = []
    for i in flagged:
        r = risks[i]
        weakest = _weak_sorted(r, 1)
        tip = c.s.suggester.tip("teacher", weakest[0].topic) if weakest else ""
        body = " ".join([*r.reasons[1:], tip]).strip()
        notes.append(w.margin_note(p, r.reasons[0] if r.reasons else "", body, lead=s.first_name(i), action=
                                   ft.TextButton(content=f"Open {s.first_name(i)}", on_click=lambda e, l=i: c.open_learner(l),
                                                 style=ft.ButtonStyle(color=p.blue, padding=ft.Padding.all(0)))))
    if not notes:
        notes = [w.muted(s.t("needs.none"), p)]

    avgs = A.class_topic_averages(hub, D.TASKS, ids)
    with_data = [a for a in avgs if a.average is not None]
    weakest_t = min(with_data, key=lambda a: a.average) if with_data else None
    topic_rows = []
    for a in avgs:
        if a.average is None:
            topic_rows.append(ft.Row([ft.Container(w.muted(a.task["topic"], p, 13), width=118),
                                      ft.Container(height=12, expand=True, bgcolor=p.rule, border_radius=6, opacity=.5),
                                      ft.Container(w.muted(s.t("marks.empty"), p, 12), width=96)], spacing=8))
        else:
            topic_rows.append(w._bar_row(p, a.task["topic"], a.average, f"{a.count} of {a.total}", w._color(p, a.average)))
    class_note = [w.margin_note(p, f"Lowest class average: {weakest_t.task['topic']}, {A.num(weakest_t.average)}%.",
                                c.s.suggester.tip("teacher", weakest_t.task["topic"]))] if weakest_t else []

    legend = [w.muted(f"Circled in red: below {A.SUPPORT_THRESHOLD}%.", p, 12),
              w.muted("Yellow dot: saved on the hub, waiting to upload.", p, 12),
              w.muted("Yellow box: two people changed the same mark.", p, 12)]
    return [
        _head(c, f"Grade {D.CLASS_LABEL} Mathematics",
              f"Term 2, {D.PERSONAS['teacher']['name']}, {len(ids)} learners. {captured} of {len(D.TASKS)} assessments captured."),
        w.sheet(p, [w.heading(s.t("marks.title"), p), w.muted(s.t("marks.hint"), p), grid, ft.Column(legend, spacing=2, tight=True)]),
        w.sheet(p, [w.heading(s.t("needs.title"), p), *notes, w.ai_note(p, s.t("ai.note"))], spacing=10),
        w.sheet(p, [w.heading("Class average by topic", p), ft.Column(topic_rows, spacing=10, tight=True), *class_note], spacing=10),
    ]


# ---- parent ---------------------------------------------------------------------------------
def view_parent(c: Ctx) -> list[ft.Control]:
    p, s = c.pal, c.s
    node, lid = s.phone, s.learner_id
    marks = A.learner_marks(node, D.TASKS, lid)
    r = A.risk(marks)
    pr = r.projection
    name = s.first_name(lid)
    summary = (f"{name} needs extra support right now." if r.level == "high" else
               f"{name} is doing fine but needs watching." if r.level == "watch" else f"{name} is on track.")
    out: list[ft.Control] = [learner_picker(c), _head(c, s.full_name(lid), f"Grade {D.CLASS_LABEL} Mathematics. {_updated(c, 'phone')}.")]
    if not s.online:
        out.append(w.banner(p, f"{s.t('parent.stale')} {_updated(c, 'phone')}."))
    stand: list[ft.Control] = [w.heading("Where things stand", p), w.txt(f"{summary} {trend_sentence(pr)}", p, 15)]
    if pr.value is not None:
        stand.append(w.stat(p, f"{A.num(pr.value)}%", f"{s.t('marks.projected')}, {A.level_text(pr.value)}"))
    stand += [w.spark(p, marks), w.muted(f"{s.t('trend.title')}. Dashed line: {A.SUPPORT_THRESHOLD}%.", p, 12)]
    help_items = [ft.Column([w.txt(f"{x.topic} ({A.num(x.value)}%).", p, 15, W.W_600), w.txt(s.suggester.tip("parent", x.topic), p, 14)],
                            spacing=2, tight=True) for x in _weak_sorted(r, 3)]
    help_box = [w.heading(s.t("help.title"), p), *(help_items or [w.muted(s.t("focus.none"), p)]), w.ai_note(p, s.t("ai.note"))]
    out += [w.sheet(p, stand, 10), w.sheet(p, help_box, 10),
            w.sheet(p, [w.heading(f"{s.t('marks.title')} by topic", p), w.mark_bars(p, marks, s.t("marks.empty"))], 10),
            w.sheet(p, [w.heading(s.t("comments.title"), p), *_comments(c, node, lid)], 10)]
    return out


# ---- learner --------------------------------------------------------------------------------
def view_learner(c: Ctx) -> list[ft.Control]:
    p, s = c.pal, c.s
    node, lid = s.phone, s.learner_id
    marks = A.learner_marks(node, D.TASKS, lid)
    r = A.risk(marks)
    pr = r.projection
    by_topic = {m.task["topic"]: m.value for m in marks}
    focus = [ft.Column([w.txt(f"{x.topic} ({A.num(x.value)}%).", p, 15, W.W_600), w.txt(s.suggester.tip("learner", x.topic), p, 14)],
                       spacing=2, tight=True) for x in _weak_sorted(r, 3)]
    out: list[ft.Control] = [learner_picker(c), _head(c, s.t("learner.hello", name=s.first_name(lid)),
                                                      f"Grade {D.CLASS_LABEL} Mathematics. {_updated(c, 'phone')}.")]
    if not s.online:
        out.append(w.banner(p, f"{s.t('parent.stale')} {_updated(c, 'phone')}."))
    focus_box: list[ft.Control] = [w.heading(s.t("focus.title"), p), *(focus or [w.muted(s.t("focus.none"), p)])]
    if pr.value is not None:
        focus_box.append(w.stat(p, f"{A.num(pr.value)}%", s.t("marks.projected")))
    focus_box += [w.spark(p, marks), w.ai_note(p, s.t("ai.note"))]
    paths = []
    for pw in D.PATHWAYS:
        tags = [ft.Container(w.txt(f"{tp} {('not captured' if by_topic.get(tp) is None else A.num(by_topic[tp]) + '%')}", p, 12),
                             bgcolor=p.blue_soft, border_radius=999, padding=ft.Padding.symmetric(horizontal=10, vertical=3))
                for tp in pw["topics"]]
        paths.append(w.sheet(p, [w.txt(pw["name"], p, 16, W.W_600), w.muted(pw["needs"], p, 13), ft.Row(tags, wrap=True, spacing=6, run_spacing=6)], 6))
    m = D.MARKET
    out += [
        w.sheet(p, [w.heading(s.t("learner.marks"), p), w.mark_bars(p, marks, s.t("marks.empty"))], 10),
        w.sheet(p, focus_box, 10),
        w.sheet(p, [w.heading(s.t("learner.next"), p), w.muted("Sample guidance for the demo. Marks below come from your own results.", p),
                    *paths, w.muted("Production loads dated, sourced data from Stats SA, DHET and the SETAs. The figures below are real.", p, 12)], 10),
        w.sheet(p, [w.heading(s.t("market.title"), p),
                    w.stat(p, m["unemployment"], f"South Africans looking for work, {m['period']}"),
                    w.stat(p, m["youthUnemployment"], f"of 15 to 34 year olds, {m['period']}"),
                    w.link(p, "Stats SA Quarterly Labour Force Survey", "https://www.statssa.gov.za/?p=19804"),
                    w.muted("Studying and funding plans matter more when jobs are scarce.", p, 13)], 6),
        w.sheet(p, [w.heading(s.t("links.title"), p),
                    w.link(p, "Careers Portal: bursaries, learnerships and internships", "https://www.careersportal.co.za/"),
                    w.link(p, "Siyavula My Future: career guidance and partner bursaries", "https://www.siyavula.com/future")], 4),
        w.sheet(p, [w.heading(s.t("comments.title"), p), *_comments(c, node, lid)], 10),
    ]
    return out


def _heat_host(c: Ctx, head: ft.Control, body: list[ft.Control]) -> ft.Row:
    host = c.scroll_host("heat_grid")
    host.controls = [ft.Column([head, *body], spacing=4, tight=True)]
    return host


# ---- principal ------------------------------------------------------------------------------
def view_principal(c: Ctx) -> list[ft.Control]:
    p, s, hub = c.pal, c.s, c.s.hub
    ids = s.learner_ids()
    live = A.class_average(hub, D.TASKS, ids)
    matrix = [{"grade": r["grade"], "values": [live if r["grade"] == 11 and i == 1 else v for i, v in enumerate(r["values"])]}
              for r in D.SCHOOL_MATRIX]
    wc = A.weak_cells(matrix, D.AREAS, 8)
    levels = [A.risk(A.learner_marks(hub, D.TASKS, i)).level for i in ids]
    high, watch = levels.count("high"), levels.count("watch")

    def cell(v: float | None, is_live: bool) -> ft.Control:
        if v is None:
            bg, fg, bd = None, p.ink2, p.rule
        elif v < wc.mean - 8:
            bg, fg, bd = p.pen_soft, p.pen, p.pen
        elif v < 58:
            bg, fg, bd = p.hl_soft, p.ink, "transparent"
        else:
            bg, fg, bd = p.tick_soft, p.tick, "transparent"
        return ft.Container(w.txt("—" if v is None else A.num(v), p, 14, W.W_600, color=fg), width=CELL_HEAT, height=40,
                            alignment=ft.Alignment.CENTER, bgcolor=bg, border_radius=6,
                            border=ft.Border.all(2 if is_live else 1, p.blue if is_live else bd))

    head = ft.Row([ft.Container(width=76)] + [ft.Container(w.muted(a, p, 10, text_align=ft.TextAlign.CENTER), width=CELL_HEAT) for a in D.AREAS], spacing=4)
    body = [ft.Row([ft.Container(w.muted(f"Grade {r['grade']}", p, 13), width=76)] +
                   [cell(v, r["grade"] == 11 and i == 1) for i, v in enumerate(r["values"])], spacing=4) for r in matrix]
    weak_notes = [w.margin_note(p, f"Grade {x.grade} {x.area}: {A.num(x.value)}%, {A.num(x.gap_to_mean)} points under the school mean.", s.t("principal.act"))
                  for x in wc.cells] or [w.muted(s.t("needs.none"), p)]
    tags = ft.Row([
        ft.Container(w.txt(f"{s.t('principal.live')}: Grade 11 Mathematics (outlined)", p, 12), border=ft.Border.all(2, p.blue), border_radius=999,
                     padding=ft.Padding.symmetric(horizontal=10, vertical=3)),
        ft.Container(w.txt(f"{s.t('principal.sample')}: every other cell", p, 12), bgcolor=p.blue_soft, border_radius=999,
                     padding=ft.Padding.symmetric(horizontal=10, vertical=3))], wrap=True, spacing=6, run_spacing=6)
    return [
        _head(c, s.t("principal.title"), f"{D.PERSONAS['principal']['name']}. Data from the school hub. {_updated(c, 'hub')}."),
        w.sheet(p, [ft.Row([w.stat(p, str(high), f"learners need support in Grade {D.CLASS_LABEL} Mathematics"),
                            w.stat(p, str(watch), "more to watch"),
                            w.stat(p, f"{A.num(live)}%" if live is not None else "—", "Grade 11 Mathematics average, live"),
                            w.stat(p, f"{A.num(wc.mean)}%", "school mean, Grades 8 to 12")], wrap=True, spacing=8, run_spacing=8)]),
        w.sheet(p, [w.heading("Average mark by grade and learning area", p),
                    _heat_host(c, head, body), tags,
                    w.muted(f"Red: more than 8 points under the school mean. Yellow: under 58%.", p, 12)], 10),
        w.sheet(p, [w.heading(s.t("principal.weak"), p), *weak_notes, w.ai_note(p, s.t("ai.note"))], 10),
    ]


# ---- guide ----------------------------------------------------------------------------------
CRITERIA = [
    ("Product", "Four role views on one shared record. Marks, comments and support flags move between devices. Try: Teacher, then Parent."),
    ("Creativity", "Offline-first sync that keeps conflicting edits instead of overwriting them. Try: step 5 and 6 of the guided demo."),
    ("Usability", "Tap a mark to change it. Plain-language summaries for parents. Language switch (top right)."),
    ("Sustainability", "Runs on a small school server plus cloud sync. Path to revenue: in preparation, not part of this prototype."),
    ("Impact", "Built for schools with poor or no internet. See the figures below."),
    ("Presentation", "This page and the guided demo."),
    ("Intelligence", "Trend projection and support flags from each learner’s marks. Rule-based, so every flag can be explained. Try: Teacher, red margin notes."),
]
REAL = [
    ("Sync engine", "Real. Pure Python, the same rules as the Khapa server code. Covered by automated tests, including a check against the web prototype’s own results."),
    ("Support flags and projections", "Real. Calculated from the marks you see."),
    ("Four devices and the internet switch", "Simulated. All four devices run inside this app. No network is used."),
    ("Learners, marks, comments", "Fictional."),
    ("Suggestions", "Rule-based text, in English only for now. No AI model runs in this app."),
    ("Translations", "Afrikaans and isiZulu are drafts waiting for human review. Nine languages are still to do."),
    ("Security demo", "Real code, demo scope. Tamper-evident audit log, role checks and a hidden canary record. There are no real accounts or network."),
    ("Not built yet", "Sign-in, the real school hub, SA-SAMS import, privacy review, a pilot school."),
]


def view_guide(c: Ctx) -> list[ft.Control]:
    p, s = c.pal, c.s
    m = D.MARKET
    explore = ft.Row([w.muted("Or explore as:", p)] + [
        ft.OutlinedButton(content=s.t(f"role.{r}"), on_click=lambda e, r=r: c.go_role(r)) for r in ("teacher", "parent", "learner", "principal")],
        wrap=True, spacing=8, run_spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
    hero = ft.Container(ft.Column([
        w.txt("One mark, four people, no internet needed.", p, 30, W.W_700),
        w.txt("Khapa gives teachers, parents, learners and principals the same picture of a learner’s progress, even when the school has "
              "no internet. Every name and mark in this demo is made up.", p, 16),
        ft.Row([ft.FilledButton(content="Play the guided demo", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: c.start_demo()),
                w.muted("About two minutes.", p)], wrap=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        explore], spacing=12, tight=True), padding=ft.Padding.all(16), bgcolor=p.blue_soft, border_radius=12)
    return [
        hero,
        w.sheet(p, [w.heading("Why this matters", p),
                    ft.Row([w.stat(p, m["mobile"], f"of households own a mobile phone, {m['ghsYear']}"),
                            w.stat(p, m["fixedInternet"], f"have internet at home on a fixed line, {m['ghsYear']}"),
                            w.stat(p, m["youthUnemployment"], f"of 15 to 34 year olds are unemployed, {m['period']}")],
                           wrap=True, spacing=8, run_spacing=8),
                    ft.Row([w.muted("Sources:", p, 12),
                            w.link(p, "Stats SA General Household Survey 2024", "https://www.gov.za/news/media-statements/statssa-releases-general-household-survey-2024-27-may-2025"),
                            w.link(p, f"Quarterly Labour Force Survey {m['period']}", "https://www.statssa.gov.za/?p=19804")], wrap=True, spacing=4),
                    w.muted("The household figure is not a smartphone figure.", p, 12)], 10),
        w.sheet(p, [w.heading("Where to look, by judging criterion", p), w.kv_table(p, CRITERIA)], 10),
        w.sheet(p, [w.heading("What is real and what is simulated", p), w.kv_table(p, REAL)], 10),
    ]


VIEWS = {"guide": view_guide, "teacher": view_teacher, "parent": view_parent, "learner": view_learner, "principal": view_principal}
