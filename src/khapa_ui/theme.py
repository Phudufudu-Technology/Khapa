"""Palette ported from the prototype's style.css: ink navy, pen red, highlighter yellow,
exercise-book blue, tick green, cool paper. Light and dark variants."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    paper: str
    sheet: str
    rule: str
    ink: str
    ink2: str
    pen: str
    pen_soft: str
    hl: str
    hl_soft: str
    blue: str
    blue_soft: str
    tick: str
    tick_soft: str
    top: str
    top_ink: str


LIGHT = Palette(paper="#f5f8fc", sheet="#ffffff", rule="#d5e0eb", ink="#14243b", ink2="#41546f", pen="#c1302a",
                pen_soft="#fde8e6", hl="#f4d24a", hl_soft="#fff3bf", blue="#2a64a8", blue_soft="#e4eefa",
                tick="#156b47", tick_soft="#ddf3e8", top="#14243b", top_ink="#f5f8fc")
DARK = Palette(paper="#0d1626", sheet="#142238", rule="#2a3b57", ink="#e8eef7", ink2="#a9b8cd", pen="#ff8177",
               pen_soft="#4a1f1c", hl="#f4d24a", hl_soft="#3d3410", blue="#7db3f0", blue_soft="#1a2f4d",
               tick="#5fd6a0", tick_soft="#12392b", top="#09111d", top_ink="#e8eef7")

MAX_WIDTH = 980
FONT = "Schibsted Grotesk"  # not bundled: falls back to the platform font, which is fine
