"""Sync events: immutable, content-hashed, validated on the way in."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .errors import IntegrityError, SyncError
from .validation import clean_id, require_dict

ENTITIES = ("learner", "mark_version", "comment")
OPS = ("create", "update")


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, no whitespace, no NaN/Infinity."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def compute_digest(event_id: str, origin_node: str, entity: str, entity_id: str, op: str, payload: dict, hlc: str) -> str:
    try:
        body = canonical_json([event_id, origin_node, entity, entity_id, op, payload, hlc])
    except (ValueError, TypeError, RecursionError) as exc:  # NaN/Infinity, non-JSON types, absurd nesting
        raise SyncError("payload is not valid JSON data") from exc
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Event:
    event_id: str
    origin_node: str
    entity: str
    entity_id: str
    op: str
    payload: dict
    hlc: str
    digest: str

    @staticmethod
    def build(event_id: str, origin_node: str, entity: str, entity_id: str, op: str, payload: dict, hlc: str) -> Event:
        payload = copy.deepcopy(payload)
        return Event(event_id, origin_node, entity, entity_id, op, payload, hlc,
                     compute_digest(event_id, origin_node, entity, entity_id, op, payload, hlc))

    def verify(self) -> None:
        expected = compute_digest(self.event_id, self.origin_node, self.entity, self.entity_id, self.op, self.payload, self.hlc)
        if expected != self.digest:
            raise IntegrityError("event digest mismatch")

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id, "origin_node": self.origin_node, "entity": self.entity,
            "entity_id": self.entity_id, "op": self.op, "payload": copy.deepcopy(self.payload),
            "hlc": self.hlc, "digest": self.digest,
        }

    @staticmethod
    def from_dict(d: Any) -> Event:
        """Strict parse of an untrusted dict (network or database). Does not verify the digest;
        SyncNode does that on ingest."""
        d = require_dict(d, "event")
        keys = {"event_id", "origin_node", "entity", "entity_id", "op", "payload", "hlc", "digest"}
        if set(d) != keys:
            raise SyncError("event has missing or unknown fields")
        if d["entity"] not in ENTITIES:
            raise SyncError(f"unknown entity {d['entity']!r}")
        if d["op"] not in OPS:
            raise SyncError(f"bad op {d['op']!r}")
        if not isinstance(d["digest"], str) or len(d["digest"]) != 64:
            raise SyncError("bad digest")
        return Event(
            clean_id(d["event_id"], "event_id"), clean_id(d["origin_node"], "origin_node"),
            d["entity"], clean_id(d["entity_id"], "entity_id"), d["op"],
            copy.deepcopy(require_dict(d["payload"], "payload")), d["hlc"], d["digest"],
        )
