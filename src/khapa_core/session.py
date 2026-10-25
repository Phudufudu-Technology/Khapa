"""Application controller: all behaviour of the app, with no Flet import.

The Flet UI is a thin layer over this class: it calls methods here and re-renders the scopes
that ``subscribe`` callbacks announce ("body", "chrome", "demo", "devices", "security").
Everything is testable with pytest, including the full 7-step demo.
"""

from __future__ import annotations

import json
import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from . import analytics as A
from . import data as D
from . import i18n
from .demo import DEMO, HOD, TEACHER
from .engine import SyncNode, sync_pair
from .errors import SyncError
from .events import Event
from .security import CANARY_LEARNER_ID, INFO, WARN, AccessDenied, AuditEntry, AuditLog, Guard
from .store import Store, StoreError
from .suggest import RuleBasedSuggester, Suggester
from .world import DEVICE_IDS, DEVICE_LABELS, EDGE_IDS, SHORT, SKEW_MS, build_world, make_nodes, wall_clock_ms

ROLES = ("guide", "teacher", "parent", "learner", "principal")
LOG_MAX = 40
FRESH_SECONDS = 2.5
AUTO_SYNC_SECONDS = 0.35
ERR_MARK = "Enter a mark between 0 and 100."
ERR_COMMENT = "Write a comment first."


def threading_scheduler(delay_s: float, fn: Callable[[], None]):
    t = threading.Timer(delay_s, fn)
    t.daemon = True
    t.start()
    return t


def parse_mark(raw: str | None) -> float | None:
    """Parse what a person typed into the mark box. Accepts '38', '38.5' and the comma decimal
    separator common in South Africa ('38,5'). Returns None if it is not a mark from 0 to 100."""
    if raw is None:
        return None
    s = str(raw).strip().replace(",", ".")
    if not s or len(s) > 8:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if not math.isfinite(v) or not 0 <= v <= 100:
        return None
    return v


@dataclass(frozen=True)
class ChipState:
    waiting: bool
    count: int
    updated_ms: int | None  # None on the guide page


class Session:
    def __init__(
        self,
        store: Store | None = None,
        now_ms: Callable[[], int] | None = None,
        scheduler: Callable[[float, Callable[[], None]], object] = threading_scheduler,
        suggester: Suggester | None = None,
    ) -> None:
        self._now = now_ms or wall_clock_ms
        self._schedule = scheduler
        self.suggester: Suggester = suggester or RuleBasedSuggester()
        self.lock = threading.RLock()
        self._subs: list[Callable[[str], None]] = []
        self._toast_cb: Callable[[str], None] | None = None
        self.persistence_note = ""
        self.store = store or Store(None)
        self._timer = None
        self.lang = "en"
        self._load_language()
        self._init_world()

    # ---- subscriptions -------------------------------------------------------------------
    def subscribe(self, fn: Callable[[str], None]) -> None:
        self._subs.append(fn)

    def on_toast(self, fn: Callable[[str], None]) -> None:
        self._toast_cb = fn

    def _notify(self, *scopes: str) -> None:
        for fn in list(self._subs):
            for sc in scopes:
                fn(sc)

    def toast(self, msg: str) -> None:
        if self._toast_cb:
            self._toast_cb(msg)

    # ---- world lifecycle -----------------------------------------------------------------
    def _fresh_ui_state(self) -> None:
        self.role = "guide"
        self.online = True
        self.learner_id = "L03"
        self.devices_open = False
        self.log_lines: list[str] = []
        self.fresh: dict[str, bool] = {}
        self.last_sync: dict[str, int] = {}
        self.demo_index: int | None = None
        self._conflicts: set[str] = set()
        self._quarantine_seen: dict[str, int] = {}

    def _init_world(self) -> None:
        self._fresh_ui_state()
        loaded = False
        try:
            loaded = self._try_load()
        except (StoreError, SyncError, KeyError, ValueError, TypeError) as exc:
            self._audit_boot_failure(f"saved data could not be loaded ({type(exc).__name__}); starting fresh")
        if not loaded:
            self._seed_new_world("Demo data loaded. All four devices are in sync.")
        else:
            self.log("Saved demo data restored.")
            self.sync_all()
            self._scan_conflicts(quiet=True)
        for nid in EDGE_IDS:
            self.last_sync[nid] = self._now()

    def _audit_boot_failure(self, why: str) -> None:
        try:
            self.store.wipe_world()
        except StoreError:
            pass
        self._boot_note = why

    def _make_guard(self) -> None:
        self.guard = Guard(self.audit, self._now)

    def _seed_new_world(self, message: str) -> None:
        self.nodes = build_world(self._now)
        self.audit = AuditLog()
        self._make_guard()
        self._persisted = {nid: 0 for nid in DEVICE_IDS}
        self._audited = 0
        note = getattr(self, "_boot_note", "")
        self._boot_note = ""
        self._audit(INFO, "system", "WORLD_SEEDED", "Fictional demo data loaded; canary record planted")
        if note:
            self._audit(WARN, "system", "STORAGE_RESET", note)
        self.log(message)
        try:
            self.store.set("seeded", "1")
        except Exception:
            pass
        self._persist()

    def _try_load(self) -> bool:
        if self.store.get("seeded") != "1":
            return False
        nodes = make_nodes(self._now)
        persisted = {}
        for nid in DEVICE_IDS:
            events = [Event.from_dict(d) for d in self.store.load_events(nid)]
            nodes[nid].receive(events, strict=True, trusted=True)
            persisted[nid] = len(nodes[nid].log)
        cursors = json.loads(self.store.get("cursors", "{}") or "{}")
        for nid, cur in cursors.items():
            if nid in nodes and isinstance(cur, dict):
                nodes[nid].cursors = {k: int(v) for k, v in cur.items() if k in nodes}
        entries = [AuditEntry(**e) for e in self.store.load_audit()]
        self.nodes = nodes
        self.audit = AuditLog(entries)
        self._make_guard()
        self._persisted = persisted
        self._audited = len(entries)
        return True

    @property
    def hub(self) -> SyncNode:
        return self.nodes["hub"]

    @property
    def phone(self) -> SyncNode:
        return self.nodes["phone"]

    @property
    def cloud(self) -> SyncNode:
        return self.nodes["cloud"]

    def reset(self) -> None:
        with self.lock:
            self._cancel_timer()
            try:
                self.store.wipe_world()
            except StoreError:
                pass
            lang = self.lang
            self._fresh_ui_state()
            self.lang = lang
            self._seed_new_world("Demo data loaded. All four devices are in sync.")
            for nid in EDGE_IDS:
                self.last_sync[nid] = self._now()
            self._notify("chrome", "body", "demo", "devices", "security")

    # ---- persistence ---------------------------------------------------------------------
    def _persist(self) -> None:
        """Write whatever is new. Persistence failure never breaks the app: we fall back to
        memory only and say so (a read-only or full disk must not crash a judge's session)."""
        try:
            for nid, node in self.nodes.items():
                start = self._persisted[nid]
                if len(node.log) > start:
                    self.store.append_events(nid, start + 1, [r.event.to_dict() for r in node.log[start:]])
                    self._persisted[nid] = len(node.log)
            self.store.set("cursors", json.dumps({nid: n.cursors for nid, n in self.nodes.items()}))
            if len(self.audit.entries) > self._audited:
                self.store.append_audit([e.to_dict() for e in self.audit.entries[self._audited:]])
                self._audited = len(self.audit.entries)
        except Exception as exc:  # sqlite3.Error, OSError, StoreError
            if not self.persistence_note:
                self.persistence_note = "Saving to this device failed, so changes will be lost when the app closes."
                self.store = Store(None)
                self._persisted = {nid: 0 for nid in DEVICE_IDS}
                self._audited = 0
                self._audit(WARN, "system", "PERSISTENCE_FAILED", f"{type(exc).__name__}: running in memory only")

    def _audit(self, severity: str, actor: str, action: str, detail: str) -> None:
        self.audit.append(self._now(), severity, actor, action, detail)

    def _load_language(self) -> None:
        try:
            code = self.store.get("lang", "en")
            if i18n.lang_info(code or "en"):
                self.lang = code or "en"
        except Exception:
            self.lang = "en"

    # ---- small helpers -------------------------------------------------------------------
    def t(self, key: str, **params) -> str:
        return i18n.translate(self.lang, key, **params)

    def log(self, msg: str) -> None:
        stamp = time.strftime("%H:%M", time.localtime(self._now() / 1000))
        self.log_lines.insert(0, f"{stamp}  {msg}")
        del self.log_lines[LOG_MAX:]

    @staticmethod
    def plural(n: int, word: str) -> str:
        return f"{n} {word}{'' if n == 1 else 's'}"

    def learner_ids(self) -> list[str]:
        return [x["id"] for x in D.LEARNERS]

    def learner(self, lid: str) -> dict | None:
        return next((x for x in D.LEARNERS if x["id"] == lid), None)

    def full_name(self, lid: str) -> str:
        x = self.learner(lid)
        return f"{x['first']} {x['last']}" if x else lid

    def first_name(self, lid: str) -> str:
        x = self.learner(lid)
        return x["first"] if x else lid

    def task(self, tid: str) -> dict | None:
        return next((x for x in D.TASKS if x["id"] == tid), None)

    def view_node(self) -> SyncNode:
        return self.hub if self.role in ("teacher", "principal") else self.phone

    # ---- navigation / preferences --------------------------------------------------------
    def go(self, role: str) -> None:
        if role in ROLES:
            self.role = role

    def set_role(self, role: str) -> None:
        with self.lock:
            self.go(role)
            self._notify("chrome", "body")

    def set_learner(self, lid: str) -> None:
        if self.learner(lid):
            self.learner_id = lid

    def pick_learner(self, lid: str) -> None:
        with self.lock:
            self.set_learner(lid)
            self._notify("body")

    def set_lang(self, code: str) -> None:
        with self.lock:
            if not i18n.lang_info(code):
                return
            self.lang = code
            try:
                self.store.set("lang", code)
            except Exception:
                pass
            self._notify("chrome", "body", "demo")

    def toggle_devices(self) -> None:
        with self.lock:
            self.devices_open = not self.devices_open
            self._notify("devices")

    # ---- sync orchestration --------------------------------------------------------------
    def _mark_fresh(self, node_id: str, events: list[Event]) -> None:
        any_ = False
        for ev in events:
            if ev.entity == "mark_version":
                self.fresh[f"{node_id}|{ev.payload['learner_id']}|{ev.payload['task_id']}"] = True
                any_ = True
        if any_:
            self._schedule(FRESH_SECONDS, self._clear_fresh)

    def _clear_fresh(self) -> None:
        with self.lock:
            self.fresh = {}
            self._notify("body")

    def sync_all(self) -> None:
        if not self.online:
            return
        changed, guard = True, 0
        while changed and guard < 4:
            guard += 1
            changed = False
            for nid in EDGE_IDS:
                r = sync_pair(self.nodes[nid], self.cloud)
                up, down = len(r["cloud"]), len(r[nid])
                if up:
                    self.log(f"{SHORT[nid]} to cloud: {self.plural(up, 'event')}")
                    changed = True
                if down:
                    self.log(f"Cloud to {SHORT[nid].lower()}: {self.plural(down, 'event')}")
                    changed = True
                    self._mark_fresh(nid, r[nid])
                self.last_sync[nid] = self._now()
        self._audit_quarantine()
        self._scan_conflicts()
        self._persist()

    def _audit_quarantine(self) -> None:
        for nid, node in self.nodes.items():
            seen = self._quarantine_seen.get(nid, 0)
            for rej in node.quarantine[seen:]:
                self._audit(WARN, nid, "EVENT_REJECTED", f"{rej.event_id}: {rej.reason}")
            self._quarantine_seen[nid] = len(node.quarantine)

    def _scan_conflicts(self, quiet: bool = False) -> None:
        now: set[str] = set()
        for key in self.hub.mark_index:
            lid, tid = key.split("|", 1)
            if len(self.hub.heads(lid, tid)) > 1:
                now.add(key)
        for key in sorted(now - self._conflicts):
            lid, tid = key.split("|", 1)
            if not quiet:
                self._audit(WARN, "hub", "CONFLICT_FLAGGED", f"Two values kept for {lid} {tid}; a teacher must resolve it")
        for key in sorted(self._conflicts - now):
            lid, tid = key.split("|", 1)
            if not quiet:
                self._audit(INFO, "hub", "CONFLICT_RESOLVED", f"{lid} {tid} has one final value again")
        self._conflicts = now

    def set_net(self, on: bool) -> None:
        self.online = on
        self.log(f"Internet {'on' if on else 'off'}")
        self._audit(INFO, "system", "NETWORK", "online" if on else "offline")
        if on:
            self.sync_all()
        else:
            self._persist()

    def toggle_net(self) -> None:
        with self.lock:
            self.set_net(not self.online)
            self._notify("chrome", "body", "devices", "demo", "security")

    def _cancel_timer(self) -> None:
        t = self._timer
        if t is not None and hasattr(t, "cancel"):
            t.cancel()
        self._timer = None

    def _schedule_sync(self) -> None:
        if not self.online:
            return
        self._cancel_timer()
        self._timer = self._schedule(AUTO_SYNC_SECONDS, self._auto_sync)

    def _auto_sync(self) -> None:
        with self.lock:
            self.sync_all()
            self._notify("chrome", "body", "devices", "security")

    # ---- scripted device actions (guided demo, HOD button) -------------------------------
    def scripted_mark(self, node_id: str, learner_id: str, task_id: str, value: float, actor: str) -> None:
        node = self.nodes[node_id]
        before = node.current_mark(learner_id, task_id)
        node.record_mark(learner_id, task_id, value, actor)
        self._audit(INFO, actor, "MARK_SAVED", f"{learner_id} {task_id}: {A.num(before.value) if before else 'empty'} -> {A.num(value)} on {node_id}")
        self._persist()

    # ---- teacher actions -----------------------------------------------------------------
    def save_mark(self, learner_id: str, task_id: str, raw: str | None) -> str | None:
        """Returns an error message to show, or None on success."""
        with self.lock:
            try:
                self.guard.require(self.role, "write_mark")
            except AccessDenied as exc:
                return str(exc)
            v = parse_mark(raw)
            if v is None or not self.learner(learner_id) or not self.task(task_id):
                return ERR_MARK
            try:
                self.scripted_mark("hub", learner_id, task_id, v, TEACHER)
            except SyncError:
                return ERR_MARK
            self.log(f"Ms Dlamini saved {self.full_name(learner_id)}, {self.task(task_id)['topic']}: {A.num(v)}")
            self.toast(self.t("sync.saved"))
            self._schedule_sync()
            self._notify("chrome", "body", "devices", "security")
            return None

    def choose_mark(self, learner_id: str, task_id: str, value: float) -> str | None:
        with self.lock:
            try:
                self.guard.require(self.role, "write_mark")
            except AccessDenied as exc:
                return str(exc)
            v = parse_mark(str(value))
            if v is None or not self.learner(learner_id) or not self.task(task_id):
                return ERR_MARK
            self.scripted_mark("hub", learner_id, task_id, v, TEACHER)
            self._audit(INFO, TEACHER, "CONFLICT_CHOICE", f"{learner_id} {task_id} resolved at {A.num(v)}")
            self.log(f"Ms Dlamini resolved {self.full_name(learner_id)}, {self.task(task_id)['topic']} at {A.num(v)}")
            self.toast("Final mark saved")
            self._schedule_sync()
            self._notify("chrome", "body", "devices", "security")
            return None

    def add_comment(self, learner_id: str, text: str | None) -> str | None:
        with self.lock:
            try:
                self.guard.require(self.role, "write_comment")
            except AccessDenied as exc:
                return str(exc)
            body = (text or "").strip()
            if not body:
                return ERR_COMMENT
            if not self.learner(learner_id):
                return ERR_COMMENT
            try:
                self.hub.add_comment(learner_id, TEACHER, "teacher", body)
            except SyncError as exc:
                return str(exc)
            self._audit(INFO, TEACHER, "COMMENT_ADDED", f"on {learner_id}")
            self.log(f"Ms Dlamini commented on {self.full_name(learner_id)}")
            self.toast(self.t("sync.saved"))
            self._persist()
            self._schedule_sync()
            self._notify("chrome", "body", "devices")
            return None

    def hod_edit(self) -> None:
        with self.lock:
            self.scripted_mark("hubB", "L03", "T4", 52, HOD)
            self.log("HOD tablet changed Sipho’s Trigonometry mark to 52")
            self.toast("HOD tablet saved a mark")
            self._schedule_sync()
            self._notify("chrome", "body", "devices", "security")

    def open_learner(self, learner_id: str):
        """Teacher opens one learner's record (goes through the guard)."""
        return self.guard.read_learner(self.role, learner_id, self.learner_id, self.hub)

    # ---- guided demo ---------------------------------------------------------------------
    def start_demo(self) -> None:
        with self.lock:
            lang = self.lang
            self._cancel_timer()
            try:
                self.store.wipe_world()
            except StoreError:
                pass
            self._fresh_ui_state()
            self.lang = lang
            self._seed_new_world("Demo data loaded. All four devices are in sync.")
            for nid in EDGE_IDS:
                self.last_sync[nid] = self._now()
            self.demo_index = 0
            DEMO[0].run(self)
            self._persist()
            self._notify("chrome", "body", "demo", "devices", "security")

    def next_demo(self) -> None:
        with self.lock:
            if self.demo_index is None or self.demo_index >= len(DEMO) - 1:
                return
            self.demo_index += 1
            DEMO[self.demo_index].run(self)
            self._persist()
            self._notify("chrome", "body", "demo", "devices", "security")

    def end_demo(self) -> None:
        with self.lock:
            self.demo_index = None
            self._notify("demo")

    def demo_text(self) -> str | None:
        return None if self.demo_index is None else DEMO[self.demo_index].text

    # ---- read models for the UI ----------------------------------------------------------
    def chip(self) -> ChipState:
        if self.role == "guide":
            n = len(self.hub.pending_for(self.cloud)) + len(self.nodes["hubB"].pending_for(self.cloud))
            return ChipState(n > 0, n, None)
        node = self.view_node()
        n = len(node.pending_for(self.cloud))
        return ChipState(n > 0, n, self.last_sync.get(node.id, self._now()))

    def devices(self) -> list[dict]:
        out = []
        for nid in DEVICE_IDS:
            n = self.nodes[nid]
            skew = SKEW_MS[nid] / 60000
            if skew == 0:
                skew_text = "Clock is right."
            else:
                mins = abs(int(skew))
                skew_text = f"Clock is {mins} {'minute' if mins == 1 else 'minutes'} {'slow' if skew < 0 else 'fast'}."
            is_cloud = nid == "cloud"
            out.append({
                "id": nid, "label": DEVICE_LABELS[nid], "stored": len(n.log),
                "up": 0 if is_cloud else len(n.pending_for(self.cloud)),
                "down": 0 if is_cloud else len(self.cloud.pending_for(n)),
                "skew": skew_text, "fingerprint": n.fingerprint(),
            })
        return out

    def converged(self) -> bool:
        return len({n.fingerprint() for n in self.nodes.values()}) == 1

    def audit_status(self) -> tuple[bool, int | None]:
        return self.audit.verify()

    def audit_recent(self, n: int = 30) -> list[AuditEntry]:
        return self.audit.recent(n)

    # ---- security probes (the Audit & security panel) ------------------------------------
    def probe_canary(self) -> str:
        with self.lock:
            try:
                self.guard.read_learner(self.role, CANARY_LEARNER_ID, self.learner_id, self.view_node())
                return "Unexpectedly allowed"
            except AccessDenied as exc:
                self._persist()
                self._notify("security")
                return f"Blocked: {exc}. An alert was written to the audit log."

    def probe_other_child(self) -> str:
        with self.lock:
            other = "L01" if self.learner_id != "L01" else "L02"
            try:
                self.guard.read_learner("parent", other, self.learner_id, self.phone)
                return "Unexpectedly allowed"
            except AccessDenied as exc:
                self._persist()
                self._notify("security")
                return f"Blocked: {exc}."

    def tamper_demo(self) -> str:
        """Edits an audit entry in memory to show the chain detects it, then restores it."""
        with self.lock:
            if not self.audit.entries:
                return "Nothing to tamper with yet."
            i = len(self.audit.entries) // 2
            original = self.audit.entries[i]
            self.audit.entries[i] = replace(original, detail="edited by an attacker")
            ok, bad = self.audit.verify()
            self.audit.entries[i] = original
            ok2, _ = self.audit.verify()
            return (f"Edited entry {original.seq}: chain check says {'intact' if ok else 'BROKEN at entry ' + str(bad + 1)}. "
                    f"Restored: {'intact' if ok2 else 'still broken'}.")
