"""Rule-based analytics. No machine learning: every flag can be explained in one sentence.

Port of the prototype's analytics.js. Numbers are formatted the way JavaScript formats them
(whole numbers without a trailing .0, round-half-up) so the copy matches the prototype exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SUPPORT_THRESHOLD = 50  # marks below this count as a weak topic (demo default, set per school)
RECENT = 3  # how many recent assessments count towards current weak topics


# ---- JS-compatible number helpers ---------------------------------------------------------
def js_round(x: float) -> int:
    """Math.round: halves round up (towards +infinity), unlike Python's banker's rounding."""
    return math.floor(x + 0.5)


def round1(v: float) -> float:
    return js_round(v * 10) / 10


def fmt(v: float | int) -> str:
    """How JS stringifies a number: 41.0 -> '41', 41.5 -> '41.5'."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def num(v: float | int) -> str:
    """The UI's display rule: integers as-is, everything else to one decimal."""
    return str(int(v)) if float(v).is_integer() else f"{v:.1f}"


# ---- CAPS-style seven-point scale ---------------------------------------------------------
@dataclass(frozen=True)
class Level:
    n: int
    label: str


_BANDS = ((80, 7, "Outstanding"), (70, 6, "Meritorious"), (60, 5, "Substantial"), (50, 4, "Adequate"),
          (40, 3, "Moderate"), (30, 2, "Elementary"))


def level(pct: float) -> Level:
    """Indicative scale: verify against DBE documents before production."""
    for floor, n, label in _BANDS:
        if pct >= floor:
            return Level(n, label)
    return Level(1, "Not achieved")


def level_text(v: float) -> str:
    lv = level(v)
    return f"Level {lv.n}, {lv.label}"


# ---- basic statistics ---------------------------------------------------------------------
def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def slope(values: list[float]) -> float:
    """Least-squares slope of values against their position (points per assessment)."""
    n = len(values)
    if n < 2:
        return 0.0
    mx = (n - 1) / 2
    my = sum(values) / n
    num_ = sum((i - mx) * (values[i] - my) for i in range(n))
    den = sum((i - mx) ** 2 for i in range(n))
    return 0.0 if den == 0 else num_ / den


# ---- per-learner ----------------------------------------------------------------------------
@dataclass(frozen=True)
class MarkPoint:
    task: dict
    value: float | None
    conflict: bool = False


def learner_marks(node, tasks: list[dict], learner_id: str) -> list[MarkPoint]:
    """Marks for one learner over the tasks, in order."""
    out = []
    for t in tasks:
        cm = node.current_mark(learner_id, t["id"])
        out.append(MarkPoint(t, cm.value if cm else None, cm.conflict if cm else False))
    return out


@dataclass(frozen=True)
class WeakTopic:
    topic: str
    value: float
    task_id: str


def weak_topics(marks: list[MarkPoint], recent_n: int | None = None) -> list[WeakTopic]:
    """Weak topics among the most recent `recent_n` captured marks (all captured if omitted).
    Older weak marks that have since been overtaken are not counted as current weaknesses."""
    captured = [m for m in marks if m.value is not None]
    if recent_n:
        captured = captured[-recent_n:]
    return [WeakTopic(m.task["topic"], m.value, m.task["id"]) for m in captured if m.value < SUPPORT_THRESHOLD]


@dataclass(frozen=True)
class Projection:
    value: float | None
    slope: float
    n: int
    remaining: int
    average: float | None = None


def projection(marks: list[MarkPoint]) -> Projection:
    """Assumes the recent trend continues for the assessments still to come."""
    vals = [m.value for m in marks if m.value is not None]
    remaining = len(marks) - len(vals)
    if len(vals) < 2:
        return Projection(vals[0] if vals else None, 0.0, len(vals), remaining)
    s = slope(vals)
    recent = mean(vals[-3:])
    nxt = clamp(recent + s, 0, 100)
    total = sum(vals) + remaining * nxt
    return Projection(round1(total / (len(vals) + remaining)), round1(s), len(vals), remaining, round1(mean(vals)))


@dataclass(frozen=True)
class Risk:
    level: str  # 'ok' | 'watch' | 'high'
    reasons: tuple[str, ...]
    weak: tuple[WeakTopic, ...]
    projection: Projection


def risk(marks: list[MarkPoint]) -> Risk:
    """high: needs support now. watch: keep an eye on. ok: on track."""
    weak = weak_topics(marks, RECENT)
    p = projection(marks)
    lvl = "ok"
    if len(weak) >= 2:
        lvl = "high"
    if p.value is not None and p.value < SUPPORT_THRESHOLD:
        lvl = "high"
    if lvl != "high" and (len(weak) == 1 or p.slope <= -4 or (p.value is not None and p.value < 58)):
        lvl = "watch"
    reasons: list[str] = []
    if weak:
        listing = ", ".join(f"{w.topic} {js_round(w.value)}%" for w in weak)
        reasons.append(f"Recently below {SUPPORT_THRESHOLD}%: {listing}.")
    if p.n >= 2 and p.slope <= -4:
        reasons.append(f"Marks are falling by about {fmt(abs(p.slope))} points per assessment.")
    if p.value is not None and p.value < SUPPORT_THRESHOLD:
        reasons.append(f"Projected year mark is {fmt(p.value)}%.")
    if lvl == "ok" and p.slope >= 4:
        reasons.append(f"Improving by about {fmt(p.slope)} points per assessment.")
    return Risk(lvl, tuple(reasons), tuple(weak), p)


# ---- class and school ---------------------------------------------------------------------
@dataclass(frozen=True)
class TopicAverage:
    task: dict
    average: float | None
    count: int
    total: int


def class_topic_averages(node, tasks: list[dict], learner_ids: list[str]) -> list[TopicAverage]:
    """Class average per task over captured marks."""
    out = []
    for t in tasks:
        vals = [cm.value for i in learner_ids if (cm := node.current_mark(i, t["id"]))]
        out.append(TopicAverage(t, round1(mean(vals)) if vals else None, len(vals), len(learner_ids)))
    return out


def class_average(node, tasks: list[dict], learner_ids: list[str]) -> float | None:
    """Mean of every current mark in the class (the live cell on the principal's view)."""
    vals = [cm.value for t in tasks for i in learner_ids if (cm := node.current_mark(i, t["id"]))]
    return round1(mean(vals)) if vals else None


@dataclass(frozen=True)
class WeakCell:
    grade: int
    area: str
    value: float
    gap_to_mean: float


@dataclass(frozen=True)
class WeakCells:
    mean: float | None
    cells: list[WeakCell] = field(default_factory=list)


def weak_cells(matrix: list[dict], areas: list[str], gap: float | None = 8) -> WeakCells:
    """Cells more than `gap` points under the school mean. `matrix` rows are {grade, values}."""
    allv = [v for r in matrix for v in r["values"] if v is not None]
    m = mean(allv)
    g = gap or 8  # the prototype treats a falsy gap as the default
    cells = [WeakCell(r["grade"], areas[i], v, round1(m - v))
             for r in matrix for i, v in enumerate(r["values"]) if v is not None and v < m - g]
    cells.sort(key=lambda c: c.value)
    return WeakCells(round1(m) if m is not None else None, cells)
