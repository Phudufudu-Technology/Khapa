"""Khapa (Flet). Entry point for `flet run`, `flet run --web` and `flet build apk`.

Everything here is simulated in-process: no network access is made or needed.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import flet as ft

from khapa_core.session import Session
from khapa_core.store import Store, StoreError
from khapa_ui.app import KhapaApp, make_ui_scheduler


def make_store(page: ft.Page) -> Store:
    """One private SQLite file per installed app. Web sessions get memory only: many judges can
    open the same hosted demo at once, and each must get their own isolated world."""
    if os.environ.get("KHAPA_PERSIST") == "0" or getattr(page, "web", False):
        return Store(None)
    base = os.environ.get("FLET_APP_STORAGE_DATA") or str(Path.home() / ".khapa-demo")
    try:
        return Store(str(Path(base) / "khapa.db"))
    except StoreError:
        return Store(None)


def main(page: ft.Page) -> None:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    page.title = "Khapa"
    if os.environ.get("KHAPA_PREVIEW_PHONE") == "1":  # desktop preview at a phone-sized window
        page.window.width, page.window.height = 390, 800
    dark = page.platform_brightness == ft.Brightness.DARK
    session = Session(store=make_store(page), scheduler=make_ui_scheduler(page))
    KhapaApp(page, session, dark=dark).mount()


if __name__ == "__main__":
    ft.run(main)
