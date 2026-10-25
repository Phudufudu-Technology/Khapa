"""The 7-step guided demo, ported from the prototype's app.js. Text is verbatim."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .session import Session

TEACHER = "Ms N. Dlamini"
HOD = "Mr HOD"


@dataclass(frozen=True)
class DemoStep:
    text: str
    run: Callable[[Session], None]


def _step1(s: Session) -> None:
    s.go("teacher")
    s.set_net(False)


def _step2(s: Session) -> None:
    s.go("teacher")
    s.scripted_mark("hub", "L03", "T6", 38, TEACHER)
    s.log("Ms Dlamini saved a mark on the school hub")


def _step3(s: Session) -> None:
    s.set_learner("L03")
    s.go("parent")


def _step4(s: Session) -> None:
    s.go("parent")
    s.set_net(True)


def _step5(s: Session) -> None:
    s.set_net(False)
    s.scripted_mark("hub", "L03", "T4", 45, TEACHER)
    s.scripted_mark("hubB", "L03", "T4", 52, HOD)
    s.log("Hub and HOD tablet both changed Sipho’s Trigonometry mark")
    s.go("teacher")


def _step6(s: Session) -> None:
    s.go("teacher")
    s.set_net(True)


def _step7(s: Session) -> None:
    pass


DEMO: tuple[DemoStep, ...] = (
    DemoStep("The school’s internet has gone down. Ms Dlamini can keep working, because the school hub runs on the school’s own network.", _step1),
    DemoStep("She captures Sipho’s Statistics assignment. It saves on the hub and waits to upload (yellow dot).", _step2),
    DemoStep("Sipho’s parent opens Khapa on a phone. It shows what was last saved on the phone, and says so. The new mark is not there yet.", _step3),
    DemoStep("The internet comes back. The hub uploads, the phone downloads, and the new mark and the updated projection appear.", _step4),
    DemoStep("Now two people change the same mark while apart. The teacher edits Trigonometry on the hub. The HOD edits it on a tablet away from the school network.", _step5),
    DemoStep("The internet returns. Khapa keeps both values and flags the mark instead of overwriting either one. Tap the yellow mark to choose the final value.", _step6),
    DemoStep("That is the demo. Explore any role, or restart to play it again.", _step7),
)
