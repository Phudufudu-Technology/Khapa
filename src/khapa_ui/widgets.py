"""Small reusable control builders. Pure functions: (palette, data) -> Flet control."""

from __future__ import annotations

import flet as ft
import flet.canvas as cv

from khapa_core import analytics as A

from .theme import Palette

W = ft.FontWeight


def txt(value: str, pal: Palette, size: float = 15, weight=None, color: str | None = None, italic: bool = False,
        selectable: bool = False, **kw) -> ft.Text:
    return ft.Text(value, size=size, weight=weight, color=color or pal.ink, italic=italic, selectable=selectable, **kw)


def muted(value: str, pal: Palette, size: float = 14, **kw) -> ft.Text:
    return txt(value, pal, size, color=pal.ink2, **kw)


def heading(value: str, pal: Palette, size: float = 20) -> ft.Text:
    return txt(value, pal, size, W.W_600)


def title(value: str, pal: Palette) -> ft.Text:
    return txt(value, pal, 28, W.W_700)


def sheet(pal: Palette, controls: list[ft.Control], spacing: float = 8) -> ft.Container:
    """A white card with a hairline border."""
    return ft.Container(
        content=ft.Column(controls, spacing=spacing, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
        padding=ft.Padding.all(14), bgcolor=pal.sheet, border=ft.Border.all(1, pal.rule), border_radius=10,
    )


def ai_note(pal: Palette, text: str) -> ft.Control:
    """The AI-suggestion disclosure, shown wherever analytics-driven suggestions appear."""
    return ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME, size=14, color=pal.ink2),
                   ft.Container(muted(text, pal, 13, italic=True), expand=True)], spacing=6,
                  vertical_alignment=ft.CrossAxisAlignment.START)


def pill(pal: Palette, level: str) -> ft.Container:
    text, bg, fg, bd = {
        "high": ("Needs support", pal.pen_soft, pal.pen, pal.pen),
        "watch": ("Watch", pal.hl_soft, pal.ink, pal.hl),
    }.get(level, ("On track", pal.tick_soft, pal.tick, pal.tick))
    return ft.Container(txt(text, pal, 12.5, W.W_600, color=fg), bgcolor=bg, border=ft.Border.all(1, bd),
                        border_radius=999, padding=ft.Padding.symmetric(horizontal=10, vertical=2))


def stat(pal: Palette, big: str, label: str) -> ft.Container:
    return ft.Container(ft.Column([txt(big, pal, 26, W.W_700), muted(label, pal, 13)], spacing=2, tight=True),
                        padding=ft.Padding.symmetric(horizontal=4, vertical=2), width=200)


def margin_note(pal: Palette, headline: str, body: str = "", action: ft.Control | None = None, lead: str = "") -> ft.Container:
    """The red-pen margin note: how every analytics-driven flag is explained."""
    head = (ft.Text(spans=[ft.TextSpan(lead + " ", ft.TextStyle(weight=W.W_800)), ft.TextSpan(headline)], size=15,
                    weight=W.W_600, color=pal.pen) if lead else txt(headline, pal, 15, W.W_600, color=pal.pen))
    rows: list[ft.Control] = [head]
    if body:
        rows.append(txt(body, pal, 14))
    if action:
        rows.append(action)
    return ft.Container(ft.Column(rows, spacing=4, tight=True), padding=ft.Padding.only(left=10, top=4, bottom=4),
                        border=ft.Border(left=ft.BorderSide(3, pal.pen)))


def banner(pal: Palette, text: str) -> ft.Container:
    return ft.Container(ft.Row([ft.Icon(ft.Icons.CLOUD_OFF, size=18, color=pal.ink),
                                ft.Container(txt(text, pal, 14), expand=True)], spacing=8),
                        bgcolor=pal.hl_soft, border=ft.Border.all(1, pal.hl), border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=12, vertical=10))


def link(pal: Palette, label: str, url: str) -> ft.TextButton:
    return ft.TextButton(content=label, url=url, style=ft.ButtonStyle(color=pal.blue))


def kv_table(pal: Palette, rows: list[tuple[str, str]]) -> ft.Column:
    return ft.Column([
        ft.Container(ft.Column([txt(k, pal, 14, W.W_600), txt(v, pal, 14)], spacing=2, tight=True),
                     padding=ft.Padding.symmetric(vertical=6), border=ft.Border(bottom=ft.BorderSide(1, pal.rule)))
        for k, v in rows], spacing=0, tight=True)


# ---- charts ---------------------------------------------------------------------------------
def _bar_row(pal: Palette, label: str, value: float, caption: str, color: str) -> ft.Control:
    """One labelled bar with the 50% support line marked. Widths use flex ratios, so it adapts to any screen."""
    frac = max(0.0, min(1.0, value / 100))
    fill_flex, rest_flex = round(frac * 1000), round((1 - frac) * 1000)
    track = ft.Row([
        ft.Container(expand=max(fill_flex, 1), height=12, bgcolor=color, visible=fill_flex > 0,
                     border_radius=ft.BorderRadius.only(top_left=6, bottom_left=6, top_right=6 if rest_flex == 0 else 0,
                                                        bottom_right=6 if rest_flex == 0 else 0)),
        ft.Container(expand=max(rest_flex, 1), height=12, bgcolor=pal.rule, visible=rest_flex > 0,
                     border_radius=ft.BorderRadius.only(top_right=6, bottom_right=6)),
    ], spacing=0)
    line = ft.Row([ft.Container(expand=1), ft.Container(width=2, height=12, bgcolor=pal.ink2, opacity=.7),
                   ft.Container(expand=1)], spacing=0)
    return ft.Row([
        ft.Container(txt(label, pal, 13), width=118),
        ft.Container(ft.Stack([track, line], height=12), expand=True, tooltip=f"{label}: {A.num(value)}%"),
        ft.Container(ft.Column([txt(f"{A.num(value)}%", pal, 13, W.W_600), muted(caption, pal, 11)], spacing=0, tight=True), width=96),
    ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def mark_bars(pal: Palette, marks: list[A.MarkPoint], empty_label: str) -> ft.Column:
    rows = []
    for m in marks:
        rows.append(_bar_row(pal, m.task["topic"], m.value, A.level_text(m.value), _color(pal, m.value))
                    if m.value is not None else
                    ft.Row([ft.Container(muted(m.task["topic"], pal, 13), width=118),
                            ft.Container(height=12, expand=True, bgcolor=pal.rule, border_radius=6, opacity=.5),
                            ft.Container(muted(empty_label, pal, 12), width=96)], spacing=8))
    return ft.Column(rows, spacing=10, tight=True)


def _color(pal: Palette, v: float) -> str:
    return pal.pen if v < A.SUPPORT_THRESHOLD else pal.tick if v >= 70 else pal.blue


def spark(pal: Palette, marks: list[A.MarkPoint], width: int = 320, height: int = 80) -> ft.Control:
    """Marks over the year, with a dashed-looking 50% line. Drawn on a canvas (no chart library)."""
    p, n = 10, len(marks)
    x = lambda i: p + i * (width - 2 * p) / (n - 1)
    y = lambda v: height - p - (v / 100) * (height - 2 * p)
    shapes: list = [cv.Line(p, y(A.SUPPORT_THRESHOLD), width - p, y(A.SUPPORT_THRESHOLD),
                            paint=ft.Paint(color=ft.Colors.with_opacity(0.6, pal.ink2), stroke_width=1))]
    pts = [(x(i), y(m.value)) for i, m in enumerate(marks) if m.value is not None]
    if len(pts) >= 2:
        elems = [cv.Path.MoveTo(*pts[0])] + [cv.Path.LineTo(*q) for q in pts[1:]]
        shapes.append(cv.Path(elems, paint=ft.Paint(color=pal.blue, stroke_width=2, style=ft.PaintingStyle.STROKE)))
    for i, m in enumerate(marks):
        if m.value is not None:
            shapes.append(cv.Circle(x(i), y(m.value), 4, paint=ft.Paint(
                color=pal.pen if m.value < A.SUPPORT_THRESHOLD else pal.blue, style=ft.PaintingStyle.FILL)))
    vals = ", ".join(str(round(m.value)) for m in marks if m.value is not None)
    return ft.Container(cv.Canvas(shapes, width=width, height=height), width=width, height=height,
                        tooltip=f"Marks over the year: {vals} percent")
