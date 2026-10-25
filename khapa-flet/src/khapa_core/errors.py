"""Exception types for the sync layer."""

from __future__ import annotations


class SyncError(Exception):
    """An event or operation was rejected. Nothing was applied for that event."""


class IntegrityError(SyncError):
    """An event's digest does not match its content, or a known event id arrived with
    different content. Treated as corruption or tampering, never retried silently."""
