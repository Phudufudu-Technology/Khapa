"""Builds the four simulated devices and seeds them. Port of the prototype's world.js.

Clock skew is deliberate: the sync engine must cope with school devices whose clocks are minutes
wrong. The only addition is the hidden canary learner (see security.py), created on the cloud
node and synced everywhere like real data.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from . import data as D
from .engine import SyncNode, sync_pair
from .security import CANARY_FIELDS, CANARY_LEARNER_ID

SKEW_MS = {"hub": 0, "hubB": -240000, "cloud": 0, "phone": 90000}
DEVICE_IDS = ("hub", "hubB", "cloud", "phone")
EDGE_IDS = ("hub", "hubB", "phone")  # every device that syncs through the cloud
DEVICE_LABELS = {
    "hub": "School hub (teacher, principal)",
    "hubB": "HOD tablet (away from the school network)",
    "cloud": "Cloud",
    "phone": "Parent and learner phone",
}
SHORT = {"hub": "School hub", "hubB": "HOD tablet", "cloud": "Cloud", "phone": "Phone"}


def wall_clock_ms() -> int:
    return int(time.time() * 1000)


def make_nodes(now_fn: Callable[[], int] | None = None) -> dict[str, SyncNode]:
    now = now_fn or wall_clock_ms
    return {nid: SyncNode(nid, (lambda s=SKEW_MS[nid]: now() + s)) for nid in DEVICE_IDS}


def build_world(now_fn: Callable[[], int] | None = None, with_canary: bool = True) -> dict[str, SyncNode]:
    nodes = make_nodes(now_fn)
    cloud = nodes["cloud"]
    for lr in D.LEARNERS:
        cloud.create_learner(
            {"school_id": D.SCHOOL_ID, "first_name": lr["first"], "last_name": lr["last"], "grade": 11,
             "class_label": D.CLASS_LABEL}, lr["id"])
        for i, m in enumerate(lr["marks"]):
            cloud.record_mark(lr["id"], D.TASKS[i]["id"], m, D.PERSONAS["teacher"]["name"])
    for c in D.SEED_COMMENTS:
        cloud.add_comment(c["learner"], D.PERSONAS["teacher"]["name"], "teacher", c["text"])
    if with_canary:
        cloud.create_learner(dict(CANARY_FIELDS), CANARY_LEARNER_ID)
    for nid in EDGE_IDS:
        sync_pair(nodes[nid], cloud)
    return nodes
