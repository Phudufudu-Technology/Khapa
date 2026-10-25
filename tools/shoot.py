"""Drive the REAL Flet desktop client under a virtual display (Xvfb) and take screenshots.

usage: python tools/shoot.py OUT_DIR "step;step;..."
steps: wait:N | shot:name | click:X,Y | key:KEY | type:text | scroll:N (down) | scrollup:N
Needs: Xvfb, xdotool, scrot (apt install xvfb xdotool scrot libgtk-3-0t64 libmpv2).
The window is 390x800 (a phone) and placed at the top-left of an 800x1000 screen.
"""
import os
import signal
import subprocess
import sys
import time

out = sys.argv[1]
steps = [s for s in sys.argv[2].split(";") if s]
os.makedirs(out, exist_ok=True)
display = os.environ.get("SHOOT_DISPLAY", ":97")
env = dict(os.environ, DISPLAY=display, SHOT_DIR=out, KHAPA_PERSIST="0", KHAPA_PREVIEW_PHONE=os.environ.get("KHAPA_PREVIEW_PHONE", "1"))
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "800x1000x24"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
time.sleep(1.5)
log = open(os.path.join(out, "flet.log"), "w")
app = subprocess.Popen(["flet", "run", *os.environ.get("SHOOT_FLET_ARGS", "").split(), os.environ.get("ENTRY", "src/main.py")], cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                       start_new_session=True)


def sh(*a):
    return subprocess.run(a, env=env, capture_output=True, text=True, timeout=20).stdout.strip()


try:
    time.sleep(float(os.environ.get("BOOT_WAIT", "14")))
    wid = (sh("xdotool", "search", "--name", "Khapa") or "").split("\n")[0]
    if wid:
        sh("xdotool", "windowmove", wid, "0", "0")
    for st in steps:
        cmd, _, arg = st.partition(":")
        if cmd == "wait":
            time.sleep(float(arg))
        elif cmd == "shot":
            sh("scrot", "-o", os.path.join(out, arg + ".png"))
        elif cmd == "click":
            x, y = arg.split(",")
            sh("xdotool", "mousemove", x, y, "click", "1")
        elif cmd == "drag":
            x1, y1, x2, y2 = arg.split(",")
            sh("xdotool", "mousemove", x1, y1, "mousedown", "1", "mousemove_relative", "--", "-60", "0",
               "mousemove", x2, y2, "mouseup", "1")
        elif cmd == "hscroll":
            n, x, y = arg.split(",")
            sh("xdotool", "mousemove", x, y, "keydown", "shift")
            for _ in range(int(n)):
                sh("xdotool", "click", "5")
            sh("xdotool", "keyup", "shift")
        elif cmd == "key":
            sh("xdotool", "key", arg)
        elif cmd == "type":
            sh("xdotool", "type", "--delay", "40", arg)
        elif cmd in ("scroll", "scrollup"):
            sh("xdotool", "mousemove", "200", "400")
            for _ in range(int(arg)):
                sh("xdotool", "click", "5" if cmd == "scroll" else "4")
        time.sleep(0.7)
finally:
    try:
        os.killpg(os.getpgid(app.pid), signal.SIGTERM)
    except Exception:
        pass
    for pid in subprocess.run(["pgrep", "-f", "flet-desktop"], capture_output=True, text=True).stdout.split():
        try:
            os.kill(int(pid), signal.SIGTERM)
        except Exception:
            pass
    xvfb.terminate()
    log.close()
