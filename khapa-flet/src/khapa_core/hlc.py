"""Hybrid logical clock (Kulkarni et al., 2014). Standard library only.

Timestamps are fixed-width strings, so plain string comparison orders them correctly:
``<wall_ms:15>-<counter:5>-<node_id>``. The node id is the final tie-breaker, which makes the
order total and identical on every node. School devices often have wrong wall clocks, so we
never rely on physical time alone: receiving a remote timestamp pushes our clock forward.

Differences from the prototype (deliberate hardening, see docs/DESIGN.md):
  * remote timestamps are parsed strictly (a malformed one is rejected, not compared as text);
  * a remote timestamp absurdly far in the future is rejected, because accepting it would drag
    this clock forward permanently (the ADR 0003 "sanity bound" limitation).
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import NamedTuple

from .errors import SyncError

WALL_W = 15
COUNTER_W = 5
MAX_COUNTER = 10**COUNTER_W - 1
MAX_WALL = 10**WALL_W - 1
DEFAULT_MAX_DRIFT_MS = 7 * 24 * 3600 * 1000  # a week: far above any plausible device skew

NODE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_HLC_RE = re.compile(r"^(\d{15})-(\d{5})-([A-Za-z0-9_.:-]{1,64})$")


class Hlc(NamedTuple):
    wall: int
    counter: int
    node: str


def format_hlc(wall_ms: int, counter: int, node_id: str) -> str:
    if counter > MAX_COUNTER:
        raise SyncError("HLC counter overflow")
    if not 0 <= wall_ms <= MAX_WALL:
        raise SyncError("HLC wall time out of range")
    return f"{wall_ms:0{WALL_W}d}-{counter:0{COUNTER_W}d}-{node_id}"


def parse_hlc(ts: object) -> Hlc:
    """Strict parse. Raises SyncError on anything that is not a well-formed timestamp."""
    if not isinstance(ts, str):
        raise SyncError("hlc must be a string")
    m = _HLC_RE.match(ts)
    if not m:
        raise SyncError("malformed hlc")
    return Hlc(int(m.group(1)), int(m.group(2)), m.group(3))


def _js_default_now() -> int:
    return time.time_ns() // 1_000_000


class HybridLogicalClock:
    def __init__(
        self,
        node_id: str,
        now_ms: Callable[[], int] | None = None,
        max_drift_ms: int = DEFAULT_MAX_DRIFT_MS,
    ) -> None:
        if not NODE_ID_RE.match(node_id):
            raise SyncError("bad node id")
        self.node_id = node_id
        self._now_ms = now_ms or _js_default_now
        self.max_drift_ms = max_drift_ms
        self.wall = 0
        self.counter = 0

    def tick(self) -> str:
        """Timestamp for a local event."""
        phys = int(self._now_ms())
        if phys > self.wall:
            self.wall, self.counter = phys, 0
        else:
            self.counter += 1
        return format_hlc(self.wall, self.counter, self.node_id)

    def check_remote(self, remote: str, check_drift: bool = True) -> Hlc:
        """Validate a remote timestamp without changing this clock. Timestamps from this device's
        own earlier sessions (read back from local storage) skip the drift bound, because the
        system clock may legitimately have been set back since they were written."""
        r = parse_hlc(remote)
        if check_drift and r.wall > int(self._now_ms()) + self.max_drift_ms:
            raise SyncError("remote hlc is too far in the future")
        return r

    def observe(self, remote: str, check_drift: bool = True) -> str:
        """Fold a received timestamp into the clock so later local events sort after it."""
        r = self.check_remote(remote, check_drift)
        phys = int(self._now_ms())
        wall = max(self.wall, r.wall, phys)
        if wall == self.wall and wall == r.wall:
            counter = max(self.counter, r.counter) + 1
        elif wall == self.wall:
            counter = self.counter + 1
        elif wall == r.wall:
            counter = r.counter + 1
        else:
            counter = 0
        out = format_hlc(wall, counter, self.node_id)  # may raise before state is changed
        self.wall, self.counter = wall, counter
        return out
