"""Security controls for the demo: tamper-evident audit log, role guard, canary record.

Honest scope (also stated in README.md): this app has no network and no real accounts, so
these controls demonstrate the *design* a production hub would need. They are not a substitute
for authentication, signed events with managed keys, or a security review.

Mapped loosely to ISO/IEC 27001:2022 Annex A themes: access control (5.15, 8.3), logging
(8.15), secure development / input validation (8.28), data minimisation (5.34). "Loosely" means
the design intent, not a certification claim.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass

from .events import canonical_json

GENESIS = "0" * 64
LOG_TEXT_MAX = 200

# Severities
INFO, WARN, ALERT = "info", "warn", "alert"

# The canary ("honeytoken"): a learner record no role may ever open. It is stored and synced
# like real data, hidden from every list and every aggregate. Any attempt to read it is a
# strong signal of snooping. Named transparently because this is a demo; a production hub would
# generate plausible decoys per school.
CANARY_LEARNER_ID = "HP-0001"
CANARY_FIELDS = {"school_id": "demo-school", "first_name": "Canary", "last_name": "Record", "grade": 11, "class_label": "TRAP"}


def clean_log_text(s: object, limit: int = LOG_TEXT_MAX) -> str:
    """Stops log injection: control characters (incl. newlines) are replaced, length is capped."""
    text = "".join(" " if unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") else c for c in str(s))
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    ts_ms: int
    severity: str
    actor: str
    action: str
    detail: str
    prev: str
    hash: str

    def to_dict(self) -> dict:
        return {"seq": self.seq, "ts_ms": self.ts_ms, "severity": self.severity, "actor": self.actor,
                "action": self.action, "detail": self.detail, "prev": self.prev, "hash": self.hash}


def _entry_hash(seq: int, ts_ms: int, severity: str, actor: str, action: str, detail: str, prev: str) -> str:
    return hashlib.sha256(canonical_json([seq, ts_ms, severity, actor, action, detail, prev]).encode()).hexdigest()


class AuditLog:
    """Append-only hash chain. Editing, deleting or reordering any entry breaks verify()."""

    def __init__(self, entries: list[AuditEntry] | None = None) -> None:
        self.entries: list[AuditEntry] = list(entries or [])

    def append(self, ts_ms: int, severity: str, actor: str, action: str, detail: str) -> AuditEntry:
        seq = len(self.entries) + 1
        prev = self.entries[-1].hash if self.entries else GENESIS
        actor, action, detail = clean_log_text(actor, 60), clean_log_text(action, 60), clean_log_text(detail)
        e = AuditEntry(seq, int(ts_ms), severity, actor, action, detail, prev,
                       _entry_hash(seq, int(ts_ms), severity, actor, action, detail, prev))
        self.entries.append(e)
        return e

    def verify(self) -> tuple[bool, int | None]:
        """(True, None) if the chain is intact, else (False, index of the first bad entry)."""
        prev = GENESIS
        for i, e in enumerate(self.entries):
            if e.seq != i + 1 or e.prev != prev or e.hash != _entry_hash(e.seq, e.ts_ms, e.severity, e.actor, e.action, e.detail, e.prev):
                return False, i
            prev = e.hash
        return True, None

    def alerts(self) -> list[AuditEntry]:
        return [e for e in self.entries if e.severity == ALERT]

    def recent(self, n: int = 30) -> list[AuditEntry]:
        return list(reversed(self.entries[-n:]))


class AccessDenied(Exception):
    """A role tried something its policy does not allow. The attempt is already in the audit log."""


# role -> permitted actions. Principal sees aggregates only (data minimisation).
POLICY = {
    "teacher": {"read_class", "write_mark", "write_comment", "read_audit"},
    "principal": {"read_aggregates", "read_audit"},
    "parent": {"read_own_child"},
    "learner": {"read_self"},
    "guide": set(),
}


class Guard:
    """Role checks that sit between the UI and the data. Denials and canary reads are audited."""

    def __init__(self, audit: AuditLog, now_ms) -> None:
        self.audit = audit
        self._now = now_ms

    def _log(self, severity: str, role: str, action: str, detail: str) -> None:
        self.audit.append(self._now(), severity, role, action, detail)

    def require(self, role: str, action: str) -> None:
        if action not in POLICY.get(role, set()):
            self._log(WARN, role, "ACCESS_DENIED", f"{role} attempted {action}")
            raise AccessDenied(f"{role} may not {action}")

    def read_learner(self, role: str, learner_id: str, subject_id: str | None, node):
        """Open one learner's profile record. Parents and learners may only open their own."""
        if learner_id == CANARY_LEARNER_ID:
            self._log(ALERT, role, "CANARY_TRIPPED", f"{role} tried to open the hidden canary record {learner_id}")
            raise AccessDenied("that record does not exist")
        allowed = (
            ("read_class" in POLICY.get(role, set()))
            or (role in ("parent", "learner") and learner_id == subject_id)
        )
        if not allowed:
            self._log(WARN, role, "ACCESS_DENIED", f"{role} tried to open learner {learner_id}")
            raise AccessDenied(f"{role} may not open that record")
        row = node.learners.get(learner_id)
        if row is None:
            raise AccessDenied("that record does not exist")
        return row

    def list_learner_ids(self, role: str, node) -> list[str]:
        """The class list. The canary is never listed, for anyone."""
        self.require(role, "read_class")
        return sorted(i for i in node.learners if i != CANARY_LEARNER_ID)
