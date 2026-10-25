"""Dev-only: drive the REAL Flet app from inside (same code paths as taps) and screenshot it.

Run through tools/shoot.py:  ENTRY=tools/scenario.py SCENARIO=resolve python tools/shoot.py OUT ""
Not shipped in the app bundle (flet build packages src/ only).
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import flet as ft  # noqa: E402

from khapa_core.session import Session  # noqa: E402
from khapa_core.store import Store  # noqa: E402
from khapa_ui.app import KhapaApp, make_ui_scheduler  # noqa: E402

OUT = os.environ.get("SHOT_DIR", "/tmp/scn")
SCENARIO = os.environ.get("SCENARIO", "resolve")


def shot(name: str) -> None:
    """Nudge the pointer first: under software GL in Xvfb the client only repaints on input, so a
    scripted screenshot can otherwise capture a stale frame."""
    os.makedirs(OUT, exist_ok=True)
    for x, y in ((200, 400), (260, 430), (200, 400), (240, 450), (300, 420)):
        subprocess.run(["xdotool", "mousemove", str(x), str(y)], env=dict(os.environ), capture_output=True, timeout=10)
        time.sleep(0.25)
    time.sleep(0.6)
    subprocess.run(["scrot", "-o", f"{OUT}/{name}.png"], env=dict(os.environ), capture_output=True, timeout=20)


def scenarios(app: KhapaApp, s: Session, page: ft.Page):
    def settle(t=1.6):
        time.sleep(t)

    if SCENARIO == "resolve":
        s.start_demo(); settle()
        for _ in range(5):
            s.next_demo(); settle(1.0)
        settle(3)
        app.open_resolve("L03", "T4"); settle(2); shot("resolve_dialog")
        page.pop_dialog(); settle(1)
        s.choose_mark("L03", "T4", 48); settle(3)
        shot("resolved")
        s.next_demo(); settle(1); shot("end")
    elif SCENARIO == "dlgtest":
        import flet as ft
        def show(name, dlg):
            page.show_dialog(dlg); settle(2); shot(name); page.pop_dialog(); settle(1)
        show("a_simple", ft.AlertDialog(title=ft.Text("A"), content=ft.Text("hello")))
        show("b_buttons", ft.AlertDialog(title=ft.Text("B"), content=ft.Column([ft.FilledButton(content="Keep 45 (entered by Ms N. Dlamini)", on_click=lambda e: None), ft.FilledButton(content="Keep 52", on_click=lambda e: None)], tight=True, width=320)))
        show("c_field", ft.AlertDialog(title=ft.Text("C"), content=ft.Column([ft.TextField(label="Or enter a different mark", keyboard_type=ft.KeyboardType.NUMBER, max_length=6)], tight=True, width=320)))
        show("d_long_title", ft.AlertDialog(title=ft.Text("Two values for one mark"), content=ft.Text("x")))
    elif SCENARIO == "dlgtest2":
        import flet as ft
        a = ft.AlertDialog(title=ft.Text("A"), content=ft.Text("hello A"))
        page.show_dialog(a); settle(2); shot("e1_open_A")
        r = page.pop_dialog(); print("popped:", r is a, a.open, flush=True); settle(2.5); shot("e2_after_pop")
        b = ft.AlertDialog(title=ft.Text("B"), content=ft.Text("hello B"))
        page.show_dialog(b); settle(2); shot("e3_open_B")
        b.open = False; b.update(); settle(2.5); shot("e4_after_open_false")
        print("stack:", [(d.title.value, d.open) for d in page._dialogs.controls], flush=True)
    elif SCENARIO == "roles":
        s.set_lang("af"); s.set_role("teacher"); settle(2); shot("teacher_af")
        s.set_role("learner"); settle(2); shot("learner_af")
        s.set_lang("xh"); settle(2); shot("learner_xh")
        s.set_lang("en"); s.set_role("principal"); settle(2); shot("principal")
    elif SCENARIO == "devices":
        s.set_role("teacher"); s.toggle_devices(); settle(2)
        s.probe_canary(); s.probe_other_child(); settle(1)
        app._probe_text = s.tamper_demo(); app._render_devices(); settle(1.5)
        app.scroll_top()
        page.run_task(app.scroller.scroll_to, offset=900, duration=0); settle(1.5)
        shot("devices")
    elif SCENARIO == "dark":
        app._toggle_theme(None); settle(2); shot("dark_guide")
        s.set_role("parent"); settle(2); shot("dark_parent")
    elif SCENARIO == "entry":
        s.set_role("teacher"); settle(1.5)
        app.open_mark("L01", "T6"); settle(1.5)
        shot("entry_open")
        err = s.save_mark("L01", "T6", "abc"); settle(1); shot("entry_error")
        print("ERR:", err, flush=True)
        s.save_mark("L01", "T6", "91,5"); settle(1.5)
        page.pop_dialog(); settle(1); shot("entry_saved")
    print("SCENARIO DONE", flush=True)


def main(page: ft.Page) -> None:
    page.title = "Khapa"
    page.window.width, page.window.height = 390, 800
    s = Session(store=Store(None), scheduler=make_ui_scheduler(page))
    app = KhapaApp(page, s, dark=False)
    app.mount()

    def run():
        time.sleep(float(os.environ.get("SCN_BOOT", "6")))
        try:
            done = threading.Event()

            def in_ctx():
                try:
                    scenarios(app, s, page)
                finally:
                    done.set()
            page.run_thread(in_ctx)
            done.wait(timeout=150)
        except Exception as exc:  # report, never hang the runner
            import traceback
            traceback.print_exc()
            print("SCENARIO FAILED", exc, flush=True)
    threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    ft.run(main)
