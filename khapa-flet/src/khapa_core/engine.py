"""Khapa sync engine: pure Python, standard library only, no Flet import.

Port of the prototype's engine.js (itself a port of the Python backend in src/khapa/sync).
Same rules: idempotent events, hybrid logical clocks, per-field last-writer-wins for learner
profiles, append-only marks whose concurrent edits are ALL kept and flagged for a teacher to
resolve, convergence regardless of sync order.

Added on top of the prototype (each is covered by tests): content digests on every event,
strict validation, quarantine of rejected events during sync instead of a stuck cursor,
duplicate-id replay detection, and a self-supersede check.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from .errors import IntegrityError, SyncError
from .events import Event, canonical_json
from .hlc import HybridLogicalClock
from .validation import LEARNER_REQUIRED, validate_comment, validate_learner, validate_mark

PULL_LIMIT = 500
QUARANTINE_CAP = 100


@dataclass
class Learner:
    id: str
    school_id: str
    first_name: str
    last_name: str
    grade: int
    class_label: str | None
    field_hlc: dict[str, str] = field(default_factory=dict)


@dataclass
class MarkVersion:
    id: str
    learner_id: str
    task_id: str
    value: int | float
    supersedes: list[str]
    hlc: str
    origin_node: str
    entered_by: str | None
    conflict: bool = False


@dataclass
class Comment:
    id: str
    hlc: str
    learner_id: str
    author_name: str
    author_role: str
    text: str


@dataclass(frozen=True)
class Alternative:
    version_id: str
    value: int | float
    origin: str
    entered_by: str | None


@dataclass(frozen=True)
class CurrentMark:
    value: int | float
    version_id: str
    conflict: bool
    hlc: str
    entered_by: str | None
    alternatives: tuple[Alternative, ...]


@dataclass(frozen=True)
class LogRow:
    seq: int
    event: Event


@dataclass(frozen=True)
class Rejected:
    event_id: str
    reason: str


def mark_key(learner_id: str, task_id: str) -> str:
    return f"{learner_id}|{task_id}"


class SyncNode:
    """One simulated device. Holds an append-only event log and the state derived from it."""

    def __init__(self, node_id: str, now_ms: Callable[[], int] | None = None) -> None:
        self.id = node_id
        self.clock = HybridLogicalClock(node_id, now_ms)
        self.log: list[LogRow] = []
        self.known: set[str] = set()
        self._digests: dict[str, str] = {}
        self.learners: dict[str, Learner] = {}
        self.marks: dict[str, MarkVersion] = {}
        self.mark_index: dict[str, list[str]] = {}
        self.comments: dict[str, Comment] = {}
        self.cursors: dict[str, int] = {}
        self.quarantine: list[Rejected] = []

    # ---- handlers ------------------------------------------------------------------------
    def _apply_learner(self, ev: Event) -> None:
        changes = validate_learner(ev.payload)
        row = self.learners.get(ev.entity_id)
        if ev.op == "create":
            for k in LEARNER_REQUIRED:
                if changes.get(k) is None:
                    raise SyncError(f"learner create missing {k}")
            if row is None:
                self.learners[ev.entity_id] = Learner(
                    id=ev.entity_id, school_id=changes["school_id"], first_name=changes["first_name"],
                    last_name=changes["last_name"], grade=changes["grade"],
                    class_label=changes.get("class_label"),
                    field_hlc={k: ev.hlc for k in changes},
                )
                return
        elif ev.op != "update":
            raise SyncError(f"bad op {ev.op}")
        if row is None:
            raise SyncError(f"update for unknown learner {ev.entity_id}: causal delivery violated")
        for k, v in changes.items():
            if ev.hlc > row.field_hlc.get(k, ""):
                setattr(row, k, v)
                row.field_hlc[k] = ev.hlc

    def heads(self, learner_id: str, task_id: str) -> list[MarkVersion]:
        ids = self.mark_index.get(mark_key(learner_id, task_id), [])
        versions = [self.marks[i] for i in ids]
        superseded = {s for v in versions for s in v.supersedes}
        return [v for v in versions if v.id not in superseded]

    def _apply_mark(self, ev: Event) -> None:
        if ev.op != "create":
            raise SyncError("mark versions are append-only: only create is allowed")
        p = validate_mark(ev.payload)
        if ev.entity_id in p["supersedes"]:
            raise SyncError("a mark version cannot supersede itself")
        if ev.entity_id in self.marks:
            raise SyncError("mark version id already used by a different event")
        self.marks[ev.entity_id] = MarkVersion(
            id=ev.entity_id, learner_id=p["learner_id"], task_id=p["task_id"], value=p["value"],
            supersedes=list(p["supersedes"]), hlc=ev.hlc, origin_node=ev.origin_node,
            entered_by=p["entered_by"], conflict=False,
        )
        key = mark_key(p["learner_id"], p["task_id"])
        self.mark_index.setdefault(key, []).append(ev.entity_id)
        head_ids = {h.id for h in self.heads(p["learner_id"], p["task_id"])}
        conflict = len(head_ids) > 1
        for vid in self.mark_index[key]:
            self.marks[vid].conflict = conflict and vid in head_ids

    def _apply_comment(self, ev: Event) -> None:
        if ev.op != "create":
            raise SyncError("comments are append-only")
        p = validate_comment(ev.payload)
        if ev.entity_id in self.comments:
            raise SyncError("comment id already used by a different event")
        self.comments[ev.entity_id] = Comment(id=ev.entity_id, hlc=ev.hlc, **p)

    # ---- ingest / emit -------------------------------------------------------------------
    def _ingest(self, ev: Event, trusted: bool = False) -> bool:
        """Verify, apply and log one event. Returns False if it was already known.
        Everything is validated before any state changes, so a rejected event leaves no trace."""
        if ev.event_id in self.known:
            if self._digests.get(ev.event_id) != ev.digest:
                raise IntegrityError("known event id replayed with different content")
            return False
        ev.verify()
        self.clock.check_remote(ev.hlc, check_drift=not trusted)
        handler = {"learner": self._apply_learner, "mark_version": self._apply_mark,
                   "comment": self._apply_comment}.get(ev.entity)
        if handler is None:
            raise SyncError(f"unknown entity {ev.entity}")
        handler(ev)
        self.log.append(LogRow(len(self.log) + 1, ev))
        self.known.add(ev.event_id)
        self._digests[ev.event_id] = ev.digest
        return True

    def emit(self, entity: str, entity_id: str, op: str, payload: dict) -> Event:
        ev = Event.build(str(uuid.uuid4()), self.id, entity, entity_id, op, payload, self.clock.tick())
        self._ingest(ev)
        return ev

    def create_learner(self, fields: dict, learner_id: str | None = None) -> str:
        lid = learner_id or str(uuid.uuid4())
        self.emit("learner", lid, "create", fields)
        return lid

    def update_learner(self, learner_id: str, fields: dict) -> None:
        self.emit("learner", learner_id, "update", fields)

    def record_mark(self, learner_id: str, task_id: str, value: float, entered_by: str | None = None) -> str:
        """Append a mark version that supersedes every version this node currently sees."""
        sup = [h.id for h in self.heads(learner_id, task_id)]
        vid = str(uuid.uuid4())
        self.emit("mark_version", vid, "create", {
            "learner_id": learner_id, "task_id": task_id, "value": value,
            "supersedes": sup, "entered_by": entered_by,
        })
        return vid

    def add_comment(self, learner_id: str, author_name: str, author_role: str, text: str) -> str:
        cid = str(uuid.uuid4())
        self.emit("comment", cid, "create", {
            "learner_id": learner_id, "author_name": author_name, "author_role": author_role, "text": text,
        })
        return cid

    def receive(self, events: list[Event], strict: bool = True, trusted: bool = False) -> list[Event]:
        """Apply remote events. Returns the events that were new to this node.

        trusted=True is for replaying this device's own saved log: digests are still verified.
        strict=True: the first bad event raises (earlier events in the batch stay applied; each
        event is atomic). strict=False: bad events are put in ``quarantine`` and the rest carry on.
        """
        applied: list[Event] = []
        for ev in events:
            try:
                if self._ingest(ev, trusted):
                    self.clock.observe(ev.hlc, check_drift=not trusted)
                    applied.append(ev)
            except SyncError as exc:
                if strict:
                    raise
                self.quarantine.append(Rejected(getattr(ev, "event_id", "?"), str(exc)))
                del self.quarantine[:-QUARANTINE_CAP]
        return applied

    def pull(self, after_seq: int, exclude_origin: str | None = None, limit: int = PULL_LIMIT) -> tuple[list[Event], int]:
        rows = self.log[after_seq:after_seq + limit]  # seq is 1-based, so [after_seq:] starts at seq after_seq+1
        events = [r.event for r in rows if r.event.origin_node != exclude_origin]
        return events, (rows[-1].seq if rows else after_seq)

    def pending_for(self, other: SyncNode) -> list[Event]:
        """Events in this node's log that the given node has not seen."""
        return [r.event for r in self.log if r.event.event_id not in other.known]

    # ---- queries -------------------------------------------------------------------------
    def current_mark(self, learner_id: str, task_id: str) -> CurrentMark | None:
        hs = self.heads(learner_id, task_id)
        if not hs:
            return None
        hs.sort(key=lambda v: v.hlc)
        win = hs[-1]
        return CurrentMark(
            value=win.value, version_id=win.id, conflict=len(hs) > 1, hlc=win.hlc, entered_by=win.entered_by,
            alternatives=tuple(Alternative(h.id, h.value, h.origin_node, h.entered_by) for h in hs[:-1]),
        )

    def comments_for(self, learner_id: str) -> list[Comment]:
        return sorted((c for c in self.comments.values() if c.learner_id == learner_id), key=lambda c: c.hlc)

    def snapshot(self) -> str:
        """Canonical state for equality checks across nodes."""
        def key(row: list) -> str:
            return canonical_json(row)
        return canonical_json({
            "learners": sorted(([l.id, l.school_id, l.first_name, l.last_name, l.grade, l.class_label]
                                for l in self.learners.values()), key=key),
            "marks": sorted(([m.id, m.learner_id, m.task_id, m.value, ",".join(sorted(m.supersedes)), m.conflict]
                             for m in self.marks.values()), key=key),
            "comments": sorted(([c.id, c.learner_id, c.text] for c in self.comments.values()), key=key),
        })

    def fingerprint(self) -> str:
        """Short hash of the converged state, shown in the device panel."""
        return hashlib.sha256(self.snapshot().encode("utf-8")).hexdigest()[:10]

    def export_log(self) -> list[dict]:
        return [r.event.to_dict() for r in self.log]


def sync_pair(a: SyncNode, b: SyncNode, strict: bool = False) -> dict[str, list[Event]]:
    """Two-way in-process sync. Returns the events newly applied on each side, keyed by node id."""
    out: dict[str, list[Event]] = {}
    for dst, src in ((a, b), (b, a)):
        cursor = dst.cursors.get(src.id, 0)
        applied: list[Event] = []
        while True:
            events, nxt = src.pull(cursor, dst.id)
            if nxt == cursor:
                break
            applied += dst.receive(events, strict=strict)
            cursor = nxt
            dst.cursors[src.id] = cursor
        out[dst.id] = applied
    return out
