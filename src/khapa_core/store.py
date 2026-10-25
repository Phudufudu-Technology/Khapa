"""SQLite persistence (standard library ``sqlite3``): one local file, no native build problems.

The engine is event-sourced, so persistence is simply "append every event, replay on start".
Replay is idempotent and re-verifies every event digest, so a corrupted or hand-edited row is
detected on load. All SQL uses bound parameters; there is no string-built SQL anywhere.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading

SCHEMA_VERSION = 1


class StoreError(Exception):
    """The database cannot be used (wrong schema version, unreadable, read-only)."""


_SCHEMA = """
CREATE TABLE events (
    node_id  TEXT    NOT NULL CHECK (length(node_id) BETWEEN 1 AND 64),
    seq      INTEGER NOT NULL CHECK (seq >= 1),
    event_id TEXT    NOT NULL CHECK (length(event_id) BETWEEN 1 AND 64),
    body     TEXT    NOT NULL,
    PRIMARY KEY (node_id, seq),
    UNIQUE (node_id, event_id)
) WITHOUT ROWID;
CREATE TABLE audit (
    seq  INTEGER PRIMARY KEY CHECK (seq >= 1),
    body TEXT NOT NULL
);
CREATE TABLE kv (
    key   TEXT PRIMARY KEY CHECK (length(key) BETWEEN 1 AND 64),
    value TEXT NOT NULL
) WITHOUT ROWID;
"""


class Store:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or ":memory:"
        self._lock = threading.RLock()
        try:
            if path:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=5)
            if path:
                try:
                    os.chmod(path, 0o600)  # private to this user where the platform supports it
                except OSError:
                    pass
            self.conn.execute("PRAGMA foreign_keys = ON")
            self._init_schema()
        except sqlite3.Error as exc:
            raise StoreError(f"cannot open database: {exc}") from exc

    @property
    def in_memory(self) -> bool:
        return self.path == ":memory:"

    def _init_schema(self) -> None:
        with self._lock:
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                with self.conn:
                    self.conn.executescript(_SCHEMA)
                    self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")  # constant, not user input
            elif version != SCHEMA_VERSION:
                raise StoreError(f"database schema version {version} is not supported (expected {SCHEMA_VERSION})")

    # ---- events -------------------------------------------------------------------------
    def append_events(self, node_id: str, first_seq: int, events: list[dict]) -> None:
        rows = [(node_id, first_seq + i, e["event_id"], json.dumps(e, sort_keys=True, ensure_ascii=False)) for i, e in enumerate(events)]
        with self._lock, self.conn:
            self.conn.executemany("INSERT OR IGNORE INTO events (node_id, seq, event_id, body) VALUES (?, ?, ?, ?)", rows)

    def load_events(self, node_id: str) -> list[dict]:
        with self._lock:
            cur = self.conn.execute("SELECT body FROM events WHERE node_id = ? ORDER BY seq", (node_id,))
            try:
                return [json.loads(r[0]) for r in cur.fetchall()]
            except json.JSONDecodeError as exc:
                raise StoreError("stored event is not valid JSON") from exc

    # ---- audit --------------------------------------------------------------------------
    def append_audit(self, entries: list[dict]) -> None:
        rows = [(e["seq"], json.dumps(e, sort_keys=True, ensure_ascii=False)) for e in entries]
        with self._lock, self.conn:
            self.conn.executemany("INSERT OR IGNORE INTO audit (seq, body) VALUES (?, ?)", rows)

    def load_audit(self) -> list[dict]:
        with self._lock:
            try:
                return [json.loads(r[0]) for r in self.conn.execute("SELECT body FROM audit ORDER BY seq").fetchall()]
            except json.JSONDecodeError as exc:
                raise StoreError("stored audit entry is not valid JSON") from exc

    # ---- key/value ----------------------------------------------------------------------
    def get(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        with self._lock, self.conn:
            self.conn.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    # ---- lifecycle ----------------------------------------------------------------------
    def wipe_world(self) -> None:
        """Delete events, audit and sync state. Keeps preferences (language)."""
        with self._lock, self.conn:
            self.conn.execute("DELETE FROM events")
            self.conn.execute("DELETE FROM audit")
            self.conn.execute("DELETE FROM kv WHERE key IN ('seeded', 'cursors')")

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
