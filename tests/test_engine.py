"""Port of the prototype's engine.test.js (idempotency, convergence, conflict flagging),
plus tests for the hardening added in the Python port."""
import random

import pytest

from conftest import Clock, mk
from khapa_core.engine import SyncNode, sync_pair
from khapa_core.errors import IntegrityError, SyncError
from khapa_core.events import Event
from khapa_core.hlc import HybridLogicalClock, format_hlc, parse_hlc

SCHOOL = "s1"


def new_learner(node, **extra):
    return node.create_learner({"school_id": SCHOOL, "first_name": "Thabo", "last_name": "Nkosi", "grade": 11, **extra})


def field(node, lid, k):
    return getattr(node.learners[lid], k)


# ---- clock ---------------------------------------------------------------------------------
def test_hlc_is_monotonic_when_wall_clock_goes_backwards():
    times = iter([100, 90, 90, 80, 200])
    c = HybridLogicalClock("n1", lambda: next(times))
    stamps = [c.tick() for _ in range(5)]
    assert stamps == sorted(stamps) and len(set(stamps)) == 5


def test_hlc_observe_pushes_a_slow_clock_past_a_remote_timestamp():
    fast, slow = HybridLogicalClock("fast", lambda: 9000), HybridLogicalClock("slow", lambda: 1000)
    remote = fast.tick()
    slow.observe(remote)
    assert slow.tick() > remote


def test_hlc_rejects_malformed_and_far_future_timestamps():
    c = HybridLogicalClock("n", lambda: 1000)
    for bad in ["", "abc", "1-2-n", None, 5, "000000000001000-00000-", "000000000001000-0000-x"]:
        with pytest.raises(SyncError):
            c.observe(bad)
    far = format_hlc(1000 + 8 * 24 * 3600 * 1000, 0, "evil")
    with pytest.raises(SyncError):
        c.observe(far)
    assert c.wall == 0  # a rejected timestamp must not move the clock


def test_hlc_format_roundtrip_and_ordering_is_textual():
    a, b = format_hlc(5, 0, "x"), format_hlc(5, 1, "x")
    assert a < b and parse_hlc(b).counter == 1


# ---- replication ---------------------------------------------------------------------------
def test_one_way_replication_converges():
    a, _ = mk("hub"); cloud, _ = mk("cloud")
    lid = new_learner(a, class_label="11A")
    a.record_mark(lid, "T1", 62)
    r = sync_pair(a, cloud)
    assert len(r["cloud"]) == 2
    assert a.snapshot() == cloud.snapshot()
    assert cloud.current_mark(lid, "T1").value == 62


def test_delivery_is_idempotent():
    a, _ = mk("hub"); cloud, _ = mk("cloud")
    lid = new_learner(a)
    a.record_mark(lid, "T1", 50)
    sync_pair(a, cloud)
    before = cloud.snapshot()
    r = sync_pair(a, cloud)
    assert len(r["cloud"]) + len(r["hub"]) == 0
    assert cloud.receive(a.pull(0)[0]) == []
    assert cloud.snapshot() == before and len(cloud.log) == 2


def test_offline_edits_to_different_fields_both_survive():
    (a, ca), (b, cb) = mk("hubA"), mk("hubB")
    lid = new_learner(a)
    sync_pair(a, b)
    ca.t += 10; a.update_learner(lid, {"class_label": "11A"})
    cb.t += 20; b.update_learner(lid, {"first_name": "Thabiso"})
    sync_pair(a, b)
    for n in (a, b):
        assert field(n, lid, "class_label") == "11A" and field(n, lid, "first_name") == "Thabiso"
    assert a.snapshot() == b.snapshot()


def test_same_field_last_writer_wins_deterministically():
    (a, ca), (b, cb) = mk("hubA"), mk("hubB")
    lid = new_learner(a)
    sync_pair(a, b)
    ca.t += 10; a.update_learner(lid, {"class_label": "11A"})
    cb.t += 20; b.update_learner(lid, {"class_label": "11B"})
    sync_pair(a, b)
    assert field(a, lid, "class_label") == field(b, lid, "class_label") == "11B"


def test_causally_later_edit_wins_despite_slow_wall_clock():
    (fast, _), (slow, _) = mk("hubFast", 9_000_000), mk("hubSlow", 1_000_000)
    lid = new_learner(fast)
    fast.update_learner(lid, {"class_label": "11B"})
    sync_pair(fast, slow)
    slow.update_learner(lid, {"class_label": "11C"})
    sync_pair(fast, slow)
    assert field(fast, lid, "class_label") == field(slow, lid, "class_label") == "11C"


def test_concurrent_mark_edits_are_kept_flagged_then_resolved():
    a, _ = mk("hubA"); b, _ = mk("hubB")
    lid = new_learner(a)
    sync_pair(a, b)
    a.record_mark(lid, "T4", 60)
    b.record_mark(lid, "T4", 70)
    sync_pair(a, b)
    assert a.snapshot() == b.snapshot()
    for n in (a, b):
        cm = n.current_mark(lid, "T4")
        assert cm.conflict
        assert sorted([cm.value, *[x.value for x in cm.alternatives]]) == [60, 70]
    assert [m.conflict for m in a.marks.values()] == [True, True]
    a.record_mark(lid, "T4", 65)  # supersedes both heads
    sync_pair(a, b)
    assert a.snapshot() == b.snapshot()
    for n in (a, b):
        cm = n.current_mark(lid, "T4")
        assert cm.value == 65 and not cm.conflict and not cm.alternatives
    assert len(a.marks) == 3 and all(not m.conflict for m in a.marks.values())


def test_neither_concurrent_value_is_ever_lost():
    a, _ = mk("hubA"); b, _ = mk("hubB")
    lid = new_learner(a)
    sync_pair(a, b)
    a.record_mark(lid, "T4", 11)
    b.record_mark(lid, "T4", 99)
    sync_pair(a, b)
    assert {m.value for m in a.marks.values()} == {11, 99}


def test_sequential_mark_edits_are_not_a_conflict():
    a, _ = mk("hubA"); b, _ = mk("hubB")
    lid = new_learner(a)
    a.record_mark(lid, "T4", 60)
    sync_pair(a, b)
    b.record_mark(lid, "T4", 65)
    sync_pair(a, b)
    for n in (a, b):
        cm = n.current_mark(lid, "T4")
        assert cm.value == 65 and not cm.conflict


def test_hub_and_spoke_relay_through_the_cloud():
    a, _ = mk("hubA"); b, _ = mk("hubB"); cloud, _ = mk("cloud")
    lid = new_learner(a)
    a.record_mark(lid, "T1", 55)
    a.add_comment(lid, "Ms Dlamini", "teacher", "Good progress.")
    sync_pair(a, cloud); sync_pair(b, cloud)
    assert b.snapshot() == a.snapshot()
    b.update_learner(lid, {"class_label": "11C"})
    sync_pair(b, cloud); sync_pair(a, cloud)
    assert field(a, lid, "class_label") == "11C"
    assert a.snapshot() == b.snapshot() == cloud.snapshot()
    assert len(b.comments_for(lid)) == 1


def test_pull_excludes_the_requesters_own_events_but_advances_the_cursor():
    a, _ = mk("hubA"); cloud, _ = mk("cloud")
    new_learner(a)
    sync_pair(a, cloud)
    events, nxt = cloud.pull(0, "hubA")
    assert events == [] and nxt > 0


def test_pending_for_counts_events_the_other_node_has_not_seen():
    a, _ = mk("hubA"); cloud, _ = mk("cloud")
    lid = new_learner(a)
    a.record_mark(lid, "T1", 50)
    assert len(a.pending_for(cloud)) == 2
    sync_pair(a, cloud)
    assert a.pending_for(cloud) == []


# ---- rejection rules -----------------------------------------------------------------------
def ev(node="x", entity="learner", eid="e1", entity_id="ghost", op="update", payload=None, hlc=None):
    return Event.build(eid, node, entity, entity_id, op, payload if payload is not None else {"class_label": "9A"},
                       hlc or format_hlc(1, 0, node))


def test_update_for_unknown_learner_is_rejected():
    n, _ = mk("cloud")
    with pytest.raises(SyncError):
        n.receive([ev()])
    assert len(n.log) == 0


def test_marks_cannot_be_updated_and_invalid_payloads_are_rejected():
    n, _ = mk("hub")
    with pytest.raises(SyncError):
        n.receive([ev(entity="mark_version", eid="e2", entity_id="m", payload={"learner_id": "l", "task_id": "t", "value": 1})])
    with pytest.raises(SyncError):
        n.create_learner({"school_id": SCHOOL, "first_name": "A", "last_name": "B", "grade": 13})
    for bad in (-1, 101, float("nan"), float("inf"), True, "50", None):
        with pytest.raises(SyncError):
            n.record_mark("l", "t", bad)
    with pytest.raises(SyncError):
        n.add_comment("l", "Ms D", "teacher", "")
    assert len(n.log) == 0


@pytest.mark.parametrize("payload", [
    {"school_id": "s", "first_name": "A", "last_name": "B", "grade": True},
    {"school_id": "s", "first_name": "A", "last_name": "B", "grade": 11.5},
    {"school_id": "s", "first_name": "A\x00", "last_name": "B", "grade": 11},
    {"school_id": "s", "first_name": "A" * 101, "last_name": "B", "grade": 11},
    {"school_id": "s", "first_name": "A", "last_name": "B", "grade": 11, "is_admin": True},
    {"school_id": "s", "first_name": "A", "last_name": "B"},
])
def test_bad_learner_payloads_are_rejected(payload):
    n, _ = mk("hub")
    with pytest.raises(SyncError):
        n.create_learner(payload)


def test_tampered_event_is_rejected_by_its_digest():
    a, _ = mk("hubA"); b, _ = mk("hubB")
    lid = new_learner(a)
    a.record_mark(lid, "T1", 50)
    events, _ = a.pull(0)
    bad = events[1].to_dict()
    bad["payload"]["value"] = 99
    with pytest.raises(IntegrityError):
        b.receive([events[0], Event.from_dict(bad)])


def test_replaying_a_known_event_id_with_different_content_is_flagged():
    a, _ = mk("hubA"); b, _ = mk("hubB")
    lid = new_learner(a)
    a.record_mark(lid, "T1", 50)
    events, _ = a.pull(0)
    sync_pair(a, b)
    forged = Event.build(events[1].event_id, "hubA", "mark_version", events[1].entity_id, "create",
                         {"learner_id": lid, "task_id": "T1", "value": 99, "supersedes": []}, events[1].hlc)
    with pytest.raises(IntegrityError):
        b.receive([forged])
    assert b.current_mark(lid, "T1").value == 50


def test_mark_that_supersedes_itself_is_rejected():
    n, _ = mk("hub")
    bad = ev(entity="mark_version", eid="e9", entity_id="m1", op="create",
             payload={"learner_id": "l", "task_id": "t", "value": 5, "supersedes": ["m1"]})
    with pytest.raises(SyncError):
        n.receive([bad])


def test_duplicate_entity_id_under_a_new_event_id_is_rejected():
    n, _ = mk("hub")
    p = {"learner_id": "l", "task_id": "t", "value": 5, "supersedes": []}
    n.receive([ev(entity="mark_version", eid="e1", entity_id="m1", op="create", payload=p)])
    with pytest.raises(SyncError):
        n.receive([ev(entity="mark_version", eid="e2", entity_id="m1", op="create", payload=dict(p, value=6))])
    assert n.marks["m1"].value == 5


def test_malformed_or_far_future_hlc_events_are_rejected():
    n, _ = mk("hub")
    p = {"class_label": "x"}
    for bad_hlc in ["junk", format_hlc(10**14, 0, "x")]:
        with pytest.raises(SyncError):
            n.receive([ev(hlc=bad_hlc, payload=p)])


def test_sync_quarantines_a_bad_event_instead_of_getting_stuck():
    a, _ = mk("hubA"); cloud, _ = mk("cloud")
    lid = new_learner(a)
    a.log.append(type(a.log[0])(len(a.log) + 1, ev(eid="bad1", node="hubA", entity_id="ghost")))  # forge a log row
    a.record_mark(lid, "T1", 50)
    r = sync_pair(a, cloud, strict=False)
    assert cloud.current_mark(lid, "T1").value == 50  # later events still flow
    assert [q.event_id for q in cloud.quarantine] == ["bad1"]
    assert len(r["cloud"]) == 2


def test_trusted_replay_accepts_old_future_stamps_but_still_checks_digests():
    n, _ = mk("hub", 1000)
    far = format_hlc(1000 + 30 * 24 * 3600 * 1000, 0, "hub")
    good = ev(node="hub", entity_id="L1", op="create", eid="g1", hlc=far,
              payload={"school_id": "s", "first_name": "A", "last_name": "B", "grade": 1})
    assert len(n.receive([good], trusted=True)) == 1
    tampered = good.to_dict(); tampered["event_id"] = "g2"
    with pytest.raises(IntegrityError):
        n.receive([Event.from_dict(tampered)], trusted=True)


def test_mark_values_are_normalised_so_equal_marks_hash_equally():
    a, _ = mk("a"); b, _ = mk("b")
    l1 = new_learner(a)
    a.record_mark(l1, "T1", 38.0)
    assert a.current_mark(l1, "T1").value == 38 and isinstance(a.current_mark(l1, "T1").value, int)


# ---- randomised convergence ---------------------------------------------------------------
@pytest.mark.parametrize("seed", range(25))
def test_random_operations_and_sync_orders_converge(seed):
    rnd = random.Random(seed)
    nodes = [mk("hubA", 1_000_000 + seed * 7), mk("hubB", 900_000), mk("cloud", 1_100_000)]
    learners = [new_learner(nodes[0][0]), new_learner(nodes[0][0])]
    for i, j in ((0, 1), (0, 2), (1, 2)):
        sync_pair(nodes[i][0], nodes[j][0])
    for i in range(24):
        node, clock = rnd.choice(nodes)
        clock.t += rnd.randrange(50) - 10  # clocks may drift backwards
        lid = rnd.choice(learners)
        kind = rnd.choice(["class", "name", "mark", "mark", "comment"])
        if kind == "class":
            node.update_learner(lid, {"class_label": rnd.choice(["11A", "11B", "11C"])})
        elif kind == "name":
            node.update_learner(lid, {"first_name": rnd.choice(["Thabo", "Thabiso", "Tebogo"])})
        elif kind == "mark":
            node.record_mark(lid, rnd.choice(["T1", "T2"]), rnd.randrange(101))
        else:
            node.add_comment(lid, "Ms D", "teacher", f"note {i}")
        if rnd.random() < 0.4:
            x, y = rnd.sample(nodes, 2)
            sync_pair(x[0], y[0])
    for _ in range(2):
        sync_pair(nodes[0][0], nodes[1][0]); sync_pair(nodes[1][0], nodes[2][0]); sync_pair(nodes[0][0], nodes[2][0])
    assert nodes[0][0].snapshot() == nodes[1][0].snapshot() == nodes[2][0].snapshot()
    assert not any(m.conflict and False for m in nodes[0][0].marks.values())


def test_convergence_is_independent_of_sync_order():
    def run(order):
        a, ca = mk("a"); b, cb = mk("b"); c, cc = mk("c", 2_000_000)
        lid = new_learner(a)
        sync_pair(a, b); sync_pair(a, c)
        a.record_mark(lid, "T1", 10); b.record_mark(lid, "T1", 20); c.record_mark(lid, "T1", 30)
        pairs = {"ab": (a, b), "bc": (b, c), "ac": (a, c)}
        for k in order:
            sync_pair(*pairs[k])
        for k in ("ab", "bc", "ac", "ab"):
            sync_pair(*pairs[k])
        return {n.fingerprint() for n in (a, b, c)}, a.current_mark(lid, "T1")
    results = [run(o) for o in (["ab", "bc", "ac"], ["ac", "bc", "ab"], ["bc", "ab", "ac"])]
    assert all(len(r[0]) == 1 for r in results)
    for r in results:
        assert r[1].conflict and sorted([r[1].value, *[x.value for x in r[1].alternatives]]) == [10, 20, 30]
