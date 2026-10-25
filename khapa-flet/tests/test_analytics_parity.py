"""Analytics tests (ported from analytics.test.js) and exact parity with the prototype's JavaScript.

tests/fixtures/js_golden.json was produced by running the prototype's own engine.js, analytics.js
and world.js (tools/gen_golden.js). Matching it proves the port preserves behaviour and copy.
"""
import json
from pathlib import Path

import pytest

from khapa_core import analytics as A
from khapa_core import data as D
from khapa_core.engine import sync_pair
from khapa_core.world import build_world

G = json.loads((Path(__file__).parent / "fixtures" / "js_golden.json").read_text(encoding="utf-8"))
IDS = [x["id"] for x in D.LEARNERS]
T0 = 1_800_000_000_000
TEACHER = D.PERSONAS["teacher"]["name"]


def world():
    return build_world(lambda: T0, with_canary=False)


def risk_dict(node, lid):
    r = A.risk(A.learner_marks(node, D.TASKS, lid))
    p = r.projection
    return {"level": r.level, "reasons": list(r.reasons), "weak": [[w.topic, w.value, w.task_id] for w in r.weak],
            "projection": {"value": p.value, "slope": p.slope, "n": p.n, "remaining": p.remaining, "average": p.average}}


def same(a, b):
    assert json.loads(json.dumps(a)) == json.loads(json.dumps(b))


# ---- ported tests ---------------------------------------------------------------------------
def test_level_bands_follow_the_seven_point_scale_edges():
    for pct, n in [(100, 7), (80, 7), (79.9, 6), (70, 6), (60, 5), (50, 4), (40, 3), (30, 2), (29.9, 1), (0, 1)]:
        assert A.level(pct).n == n, pct


def test_slope_is_exact_for_straight_lines_and_zero_for_flat_data():
    assert A.slope([10, 20, 30, 40]) == 10
    assert A.slope([50, 50, 50]) == 0
    assert A.slope([70]) == 0
    assert A.slope([58, 61, 55, 34, 41]) < -5


def test_world_seeds_every_device_identically():
    w = build_world(lambda: T0)
    snap = w["cloud"].snapshot()
    assert all(w[i].snapshot() == snap for i in ("hub", "hubB", "phone"))
    assert len(w["hub"].learners) == 14 + 1  # 14 fictional learners + the hidden canary
    assert len(w["hub"].marks) == 14 * 5
    assert w["hub"].current_mark("L03", "T6") is None


def test_risk_flags_match_the_demo_story():
    w = world()
    r = lambda i: A.risk(A.learner_marks(w["hub"], D.TASKS, i))
    assert [r(i).level for i in ("L03", "L06", "L10")] == ["high"] * 3
    assert r("L01").level == "ok" and r("L05").level == "ok"
    assert any("Improving" in s for s in r("L05").reasons)
    assert r("L09").level == "watch"
    assert [x.topic for x in r("L03").weak] == ["Trigonometry", "Analytical geometry"]
    assert sorted(i for i in IDS if r(i).level == "high") == ["L03", "L06", "L10"]


def test_every_flag_has_a_one_sentence_reason():
    w = world()
    for i in IDS:
        r = A.risk(A.learner_marks(w["hub"], D.TASKS, i))
        if r.level in ("high", "watch"):
            assert r.reasons, f"{i} is {r.level} with no explanation"
        assert all(s.endswith(".") and "\n" not in s for s in r.reasons)


def test_projection_assumes_the_recent_trend_continues():
    w = world()
    p = A.projection(A.learner_marks(w["hub"], D.TASKS, "L03"))
    assert (p.n, p.remaining) == (5, 1) and 40 < p.value < 50
    assert A.projection(A.learner_marks(w["hub"], D.TASKS, "L01")).value > 75


def test_capturing_the_last_assessment_changes_projection_and_class_average():
    w = world()
    before = A.class_average(w["hub"], D.TASKS, IDS)
    w["hub"].record_mark("L03", "T6", 38, TEACHER)
    assert A.class_average(w["hub"], D.TASKS, IDS) < before
    p = A.projection(A.learner_marks(w["hub"], D.TASKS, "L03"))
    assert p.remaining == 0 and p.value == round(A.mean([58, 61, 55, 34, 41, 38]), 1)


def test_class_topic_averages_count_captured_marks():
    avgs = A.class_topic_averages(world()["hub"], D.TASKS, IDS)
    assert len(avgs) == 6 and avgs[0].count == 14 and avgs[5].count == 0 and avgs[5].average is None


def test_school_weak_cells_flag_the_sample_gaps():
    live = A.class_average(world()["hub"], D.TASKS, IDS)
    matrix = [{"grade": r["grade"], "values": [live if r["grade"] == 11 and i == 1 else v for i, v in enumerate(r["values"])]} for r in D.SCHOOL_MATRIX]
    wc = A.weak_cells(matrix, D.AREAS, 8)
    keys = [f"{c.grade} {c.area}" for c in wc.cells]
    assert "9 Mathematics" in keys and "10 Sciences" in keys and wc.cells[0].value == 45 and 50 < wc.mean < 65


def test_offline_edit_on_the_hub_is_invisible_on_the_phone_until_sync():
    w = world()
    w["hub"].record_mark("L03", "T6", 38, TEACHER)
    assert w["phone"].current_mark("L03", "T6") is None
    assert len(w["hub"].pending_for(w["cloud"])) == 1
    sync_pair(w["hub"], w["cloud"]); sync_pair(w["phone"], w["cloud"])
    assert w["phone"].current_mark("L03", "T6").value == 38


def test_hod_edit_made_off_network_becomes_a_flagged_conflict_then_resolves():
    w = world()
    w["hub"].record_mark("L03", "T4", 45, TEACHER)
    w["hubB"].record_mark("L03", "T4", 52, "Mr HOD")
    sync_pair(w["hub"], w["cloud"]); sync_pair(w["hubB"], w["cloud"]); sync_pair(w["hub"], w["cloud"])
    cm = w["hub"].current_mark("L03", "T4")
    assert cm.conflict and len(cm.alternatives) == 1
    w["hub"].record_mark("L03", "T4", 48, TEACHER)
    for n in ("hub", "hubB", "phone"):
        sync_pair(w[n], w["cloud"])
    for i in ("hub", "hubB", "cloud", "phone"):
        c = w[i].current_mark("L03", "T4")
        assert c.value == 48 and not c.conflict, i


# ---- exact parity with the JavaScript prototype -----------------------------------------------
@pytest.mark.parametrize("pct,n,label", G["levels"])
def test_level_matches_js(pct, n, label):
    lv = A.level(pct)
    assert (lv.n, lv.label) == (n, label)


@pytest.mark.parametrize("lid", IDS)
def test_risk_matches_js_for_every_learner(lid):
    same(risk_dict(world()["hub"], lid), G["risk"][lid])


@pytest.mark.parametrize("case", G["series"], ids=lambda c: str(c["vals"]))
def test_slope_projection_and_risk_match_js_on_edge_series(case):
    vals = case["vals"]
    assert A.slope(vals) == pytest.approx(case["slope"])
    marks = [A.MarkPoint({"id": f"X{i}", "topic": f"Topic {i}"}, v) for i, v in enumerate(vals)] + [A.MarkPoint({"id": "Xe", "topic": "Empty"}, None)]
    r = A.risk(marks)
    assert r.level == case["level"] and list(r.reasons) == case["reasons"]
    p = r.projection
    same({"value": p.value, "slope": p.slope, "n": p.n, "remaining": p.remaining, "average": p.average}, case["projection"])


def test_seed_state_matches_js():
    w = world()
    assert len(w["hub"].log) == G["seedLogLen"]
    assert A.class_average(w["hub"], D.TASKS, IDS) == G["seed"]["classAverage"]
    same([[t.task["id"], t.average, t.count] for t in A.class_topic_averages(w["hub"], D.TASKS, IDS)], G["seed"]["topicAverages"])


def test_guided_demo_state_matches_js_at_every_step():
    w = world()

    def sync_all():
        for _ in range(4):
            changed = False
            for i in ("hub", "hubB", "phone"):
                r = sync_pair(w[i], w["cloud"])
                changed |= bool(r["cloud"] or r[i])
            if not changed:
                break

    def summary():
        def cm(n, l, t):
            c = w[n].current_mark(l, t)
            return {"value": c.value, "conflict": c.conflict, "alts": sorted(a.value for a in c.alternatives)} if c else None
        nodes = {i: {"L03_T4": cm(i, "L03", "T4"), "L03_T6": cm(i, "L03", "T6"), "log": len(w[i].log),
                     "pendingUp": 0 if i == "cloud" else len(w[i].pending_for(w["cloud"]))} for i in ("hub", "hubB", "cloud", "phone")}
        return {"nodes": nodes, "L03": risk_dict(w["hub"], "L03"), "L03_phone": risk_dict(w["phone"], "L03"),
                "classAverage": A.class_average(w["hub"], D.TASKS, IDS),
                "topicAverages": [[t.task["id"], t.average, t.count] for t in A.class_topic_averages(w["hub"], D.TASKS, IDS)]}

    actions = [
        lambda: None, lambda: None,
        lambda: w["hub"].record_mark("L03", "T6", 38, TEACHER),
        lambda: None,
        sync_all,
        lambda: (w["hub"].record_mark("L03", "T4", 45, TEACHER), w["hubB"].record_mark("L03", "T4", 52, "Mr HOD")),
        sync_all,
        lambda: (w["hub"].record_mark("L03", "T4", 48, TEACHER), sync_all()),
    ]
    assert len(actions) == len(G["demo"])
    for i, act in enumerate(actions):
        act()
        s = summary()
        for k in ("nodes", "L03", "L03_phone", "classAverage", "topicAverages"):
            same(s[k], {kk: G["demo"][i][kk] for kk in G["demo"][i] if kk == k}[k])
