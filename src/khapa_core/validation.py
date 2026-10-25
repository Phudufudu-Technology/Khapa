"""Manual input validation. No Pydantic, no third-party libraries (see docs/DESIGN.md).

Every function takes untrusted data and returns a clean, normalised copy, or raises SyncError.
Rules mirror the prototype (engine.js) and add: unknown-key rejection, bool-is-not-a-number,
control-character rejection, id syntax checks and a self-supersede check.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any

from .errors import SyncError

ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")

LEARNER_FIELDS = ("school_id", "first_name", "last_name", "grade", "class_label")
LEARNER_REQUIRED = ("school_id", "first_name", "last_name", "grade")
MARK_KEYS = {"learner_id", "task_id", "value", "supersedes", "entered_by"}
COMMENT_KEYS = {"learner_id", "author_name", "author_role", "text"}
COMMENT_MAX = 500
NAME_MAX = 100
LABEL_MAX = 20
MAX_SUPERSEDES = 50


def is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def clean_text(v: Any, name: str, min_len: int, max_len: int, multiline: bool = False) -> str:
    if not isinstance(v, str):
        raise SyncError(f"{name} must be text")
    if not min_len <= len(v) <= max_len:
        raise SyncError(f"{name} must be {min_len} to {max_len} characters")
    for ch in v:
        cat = unicodedata.category(ch)
        if cat == "Cc" and not (multiline and ch in "\n\t"):
            raise SyncError(f"{name} contains control characters")
        if cat == "Cs":
            raise SyncError(f"{name} contains invalid characters")
    return v


def clean_id(v: Any, name: str) -> str:
    if not isinstance(v, str) or not ID_RE.match(v):
        raise SyncError(f"bad {name}")
    return v


def require_dict(p: Any, name: str) -> dict:
    if not isinstance(p, dict):
        raise SyncError(f"{name} must be an object")
    return p


def validate_learner(p: Any) -> dict:
    p = require_dict(p, "learner payload")
    out: dict[str, Any] = {}
    for k, v in p.items():
        if k not in LEARNER_FIELDS:
            raise SyncError(f"unknown learner field: {k}")
        if k == "grade":
            if not is_int(v) or not 0 <= v <= 12:
                raise SyncError("grade must be an integer 0-12")
        elif k == "class_label":
            if v is not None:
                clean_text(v, "class_label", 1, LABEL_MAX)
        else:
            clean_text(v, k, 1, NAME_MAX)
        out[k] = v
    return out


def normalise_mark_value(v: float | int) -> int | float:
    """Whole numbers become ints so equal marks always serialise (and hash) identically."""
    f = float(v)
    return int(f) if f.is_integer() else f


def validate_mark(p: Any) -> dict:
    p = require_dict(p, "mark payload")
    extra = set(p) - MARK_KEYS
    if extra:
        raise SyncError(f"unknown mark field: {sorted(extra)[0]}")
    learner_id = clean_id(p.get("learner_id"), "learner_id")
    task_id = clean_id(p.get("task_id"), "task_id")
    value = p.get("value")
    if not is_number(value) or not 0 <= value <= 100:
        raise SyncError("mark must be between 0 and 100")
    sup = p.get("supersedes", [])
    if not isinstance(sup, list) or len(sup) > MAX_SUPERSEDES:
        raise SyncError("bad supersedes")
    sup = [clean_id(s, "supersedes entry") for s in sup]
    entered_by = p.get("entered_by")
    if entered_by is not None:
        entered_by = clean_text(entered_by, "entered_by", 1, NAME_MAX)
    return {
        "learner_id": learner_id,
        "task_id": task_id,
        "value": normalise_mark_value(value),
        "supersedes": sup,
        "entered_by": entered_by,
    }


def validate_comment(p: Any) -> dict:
    p = require_dict(p, "comment payload")
    extra = set(p) - COMMENT_KEYS
    if extra:
        raise SyncError(f"unknown comment field: {sorted(extra)[0]}")
    return {
        "learner_id": clean_id(p.get("learner_id"), "learner_id"),
        "author_name": clean_text(p.get("author_name"), "author_name", 1, NAME_MAX),
        "author_role": clean_text(p.get("author_role"), "author_role", 1, 30),
        "text": clean_text(p.get("text"), "comment", 1, COMMENT_MAX, multiline=True),
    }
