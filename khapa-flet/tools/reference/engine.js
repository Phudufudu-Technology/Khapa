/* Khapa sync engine (browser port of src/khapa/sync, see docs/adr/0003).
 * Same rules as the Python engine: idempotent events, hybrid logical clocks,
 * per-field last-writer-wins for learner profiles, append-only marks whose
 * concurrent edits are all kept and flagged for a teacher to resolve.
 * Differences from the Python version: in memory only, and a batch that fails
 * halfway is not rolled back (causal delivery means it should not fail). */
(function (root) {
  'use strict';

  var WALL_W = 15;
  var CTR_W = 5;

  function pad(n, w) { return String(n).padStart(w, '0'); }
  function fmt(wall, ctr, node) { return pad(wall, WALL_W) + '-' + pad(ctr, CTR_W) + '-' + node; }
  function parseHlc(ts) {
    var i = ts.indexOf('-');
    var j = ts.indexOf('-', i + 1);
    return { wall: Number(ts.slice(0, i)), ctr: Number(ts.slice(i + 1, j)), node: ts.slice(j + 1) };
  }

  function uuid() {
    if (root.crypto && typeof root.crypto.randomUUID === 'function') return root.crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0;
      return (c === 'x' ? r : (r & 3) | 8).toString(16);
    });
  }

  function SyncError(message) {
    var e = new Error(message);
    e.name = 'SyncError';
    return e;
  }

  /* ---- hybrid logical clock -------------------------------------------------------------- */
  function HLC(nodeId, nowMs) {
    this.nodeId = nodeId;
    this.now = nowMs || function () { return Date.now(); };
    this.wall = 0;
    this.ctr = 0;
  }
  HLC.prototype.tick = function () {
    var phys = this.now();
    if (phys > this.wall) { this.wall = phys; this.ctr = 0; } else { this.ctr += 1; }
    return fmt(this.wall, this.ctr, this.nodeId);
  };
  HLC.prototype.observe = function (remote) {
    var r = parseHlc(remote);
    var phys = this.now();
    var wall = Math.max(this.wall, r.wall, phys);
    var ctr;
    if (wall === this.wall && wall === r.wall) ctr = Math.max(this.ctr, r.ctr) + 1;
    else if (wall === this.wall) ctr = this.ctr + 1;
    else if (wall === r.wall) ctr = r.ctr + 1;
    else ctr = 0;
    this.wall = wall;
    this.ctr = ctr;
    return fmt(wall, ctr, this.nodeId);
  };

  /* ---- validation ------------------------------------------------------------------------ */
  var LEARNER_FIELDS = ['school_id', 'first_name', 'last_name', 'grade', 'class_label'];
  var LEARNER_REQUIRED = ['school_id', 'first_name', 'last_name', 'grade'];

  function validateLearner(p) {
    var out = {};
    Object.keys(p).forEach(function (k) {
      if (LEARNER_FIELDS.indexOf(k) === -1) throw SyncError('unknown learner field: ' + k);
      var v = p[k];
      if (k === 'grade') {
        if (!Number.isInteger(v) || v < 0 || v > 12) throw SyncError('grade must be an integer 0-12');
      } else if (k === 'class_label') {
        if (v !== null && (typeof v !== 'string' || v.length > 20)) throw SyncError('bad class_label');
      } else if (typeof v !== 'string' || v.length < 1 || v.length > 100) {
        throw SyncError('bad ' + k);
      }
      out[k] = v;
    });
    return out;
  }

  function validateMark(p) {
    if (typeof p.learner_id !== 'string' || typeof p.task_id !== 'string') throw SyncError('mark needs learner_id and task_id');
    if (typeof p.value !== 'number' || !isFinite(p.value) || p.value < 0 || p.value > 100) throw SyncError('mark must be between 0 and 100');
    var sup = p.supersedes || [];
    if (!Array.isArray(sup) || sup.some(function (s) { return typeof s !== 'string'; })) throw SyncError('bad supersedes');
    return { learner_id: p.learner_id, task_id: p.task_id, value: p.value, supersedes: sup.slice(), entered_by: p.entered_by || null };
  }

  function validateComment(p) {
    ['learner_id', 'author_name', 'author_role', 'text'].forEach(function (k) {
      if (typeof p[k] !== 'string' || p[k].length < 1) throw SyncError('comment needs ' + k);
    });
    if (p.text.length > 500) throw SyncError('comment too long');
    return { learner_id: p.learner_id, author_name: p.author_name, author_role: p.author_role, text: p.text };
  }

  /* ---- handlers -------------------------------------------------------------------------- */
  function applyLearner(node, ev) {
    var changes = validateLearner(ev.payload);
    var row = node.learners.get(ev.entity_id);
    if (ev.op === 'create') {
      LEARNER_REQUIRED.forEach(function (k) {
        if (changes[k] === undefined || changes[k] === null) throw SyncError('learner create missing ' + k);
      });
      if (!row) {
        var hl = {};
        Object.keys(changes).forEach(function (k) { hl[k] = ev.hlc; });
        node.learners.set(ev.entity_id, Object.assign({ id: ev.entity_id, class_label: null, field_hlc: hl }, changes));
        return;
      }
    } else if (ev.op !== 'update') {
      throw SyncError('bad op ' + ev.op);
    }
    if (!row) throw SyncError('update for unknown learner ' + ev.entity_id + ': causal delivery violated');
    Object.keys(changes).forEach(function (k) {
      if (ev.hlc > (row.field_hlc[k] || '')) { row[k] = changes[k]; row.field_hlc[k] = ev.hlc; }
    });
  }

  function markKey(l, t) { return l + '|' + t; }

  function heads(node, learnerId, taskId) {
    var ids = node.markIndex.get(markKey(learnerId, taskId)) || [];
    var versions = ids.map(function (id) { return node.marks.get(id); });
    var superseded = new Set();
    versions.forEach(function (v) { v.supersedes.forEach(function (s) { superseded.add(s); }); });
    return versions.filter(function (v) { return !superseded.has(v.id); });
  }

  function applyMark(node, ev) {
    if (ev.op !== 'create') throw SyncError('mark versions are append-only: only create is allowed');
    var p = validateMark(ev.payload);
    if (!node.marks.has(ev.entity_id)) {
      node.marks.set(ev.entity_id, {
        id: ev.entity_id, learner_id: p.learner_id, task_id: p.task_id, value: p.value,
        supersedes: p.supersedes, hlc: ev.hlc, origin_node: ev.origin_node, entered_by: p.entered_by, conflict: false
      });
      var key = markKey(p.learner_id, p.task_id);
      if (!node.markIndex.has(key)) node.markIndex.set(key, []);
      node.markIndex.get(key).push(ev.entity_id);
    }
    var hs = heads(node, p.learner_id, p.task_id);
    var headIds = new Set(hs.map(function (h) { return h.id; }));
    var conflict = hs.length > 1;
    node.markIndex.get(markKey(p.learner_id, p.task_id)).forEach(function (id) {
      var v = node.marks.get(id);
      v.conflict = conflict && headIds.has(id);
    });
  }

  function applyComment(node, ev) {
    if (ev.op !== 'create') throw SyncError('comments are append-only');
    var p = validateComment(ev.payload);
    if (!node.comments.has(ev.entity_id)) {
      node.comments.set(ev.entity_id, Object.assign({ id: ev.entity_id, hlc: ev.hlc }, p));
    }
  }

  var HANDLERS = { learner: applyLearner, mark_version: applyMark, comment: applyComment };

  /* ---- node ------------------------------------------------------------------------------ */
  function SyncNode(id, nowMs) {
    this.id = id;
    this.clock = new HLC(id, nowMs);
    this.log = [];
    this.known = new Set();
    this.learners = new Map();
    this.marks = new Map();
    this.markIndex = new Map();
    this.comments = new Map();
    this.cursors = {};
  }

  SyncNode.prototype._ingest = function (ev) {
    if (this.known.has(ev.event_id)) return false;
    var handler = HANDLERS[ev.entity];
    if (!handler) throw SyncError('unknown entity ' + ev.entity);
    handler(this, ev); // validates and throws before the event is logged
    this.log.push(Object.assign({ seq: this.log.length + 1 }, ev));
    this.known.add(ev.event_id);
    return true;
  };

  SyncNode.prototype.emit = function (entity, entityId, op, payload) {
    var ev = { event_id: uuid(), origin_node: this.id, entity: entity, entity_id: entityId, op: op, payload: payload, hlc: this.clock.tick() };
    this._ingest(ev);
    return ev;
  };

  SyncNode.prototype.createLearner = function (fields, id) {
    var learnerId = id || uuid();
    this.emit('learner', learnerId, 'create', fields);
    return learnerId;
  };
  SyncNode.prototype.updateLearner = function (id, fields) { this.emit('learner', id, 'update', fields); };

  /** Append a mark version that supersedes every version this node currently sees. */
  SyncNode.prototype.recordMark = function (learnerId, taskId, value, enteredBy) {
    var sup = heads(this, learnerId, taskId).map(function (h) { return h.id; });
    var id = uuid();
    this.emit('mark_version', id, 'create', {
      learner_id: learnerId, task_id: taskId, value: value, supersedes: sup, entered_by: enteredBy || null
    });
    return id;
  };

  SyncNode.prototype.addComment = function (learnerId, authorName, authorRole, text) {
    var id = uuid();
    this.emit('comment', id, 'create', { learner_id: learnerId, author_name: authorName, author_role: authorRole, text: text });
    return id;
  };

  /** Apply remote events. Returns the events that were new to this node. */
  SyncNode.prototype.receive = function (events) {
    var applied = [];
    for (var i = 0; i < events.length; i++) {
      if (this._ingest(events[i])) {
        this.clock.observe(events[i].hlc);
        applied.push(events[i]);
      }
    }
    return applied;
  };

  SyncNode.prototype.pull = function (afterSeq, excludeOrigin, limit) {
    var lim = limit || 500;
    var rows = this.log.slice(afterSeq, afterSeq + lim); // seq is 1-based, so slice(afterSeq) starts at seq afterSeq+1
    var events = rows.filter(function (r) { return r.origin_node !== excludeOrigin; });
    return { events: events, next: rows.length ? rows[rows.length - 1].seq : afterSeq };
  };

  /** Events in this node's log that the given node has not seen. */
  SyncNode.prototype.pendingFor = function (other) {
    return this.log.filter(function (e) { return !other.known.has(e.event_id); });
  };

  SyncNode.prototype.currentMark = function (learnerId, taskId) {
    var hs = heads(this, learnerId, taskId);
    if (!hs.length) return null;
    hs.sort(function (a, b) { return a.hlc < b.hlc ? -1 : a.hlc > b.hlc ? 1 : 0; });
    var win = hs[hs.length - 1];
    return {
      value: win.value, versionId: win.id, conflict: hs.length > 1, hlc: win.hlc, enteredBy: win.entered_by,
      alternatives: hs.slice(0, -1).map(function (h) { return { versionId: h.id, value: h.value, origin: h.origin_node, enteredBy: h.entered_by }; })
    };
  };

  SyncNode.prototype.commentsFor = function (learnerId) {
    return Array.from(this.comments.values())
      .filter(function (c) { return c.learner_id === learnerId; })
      .sort(function (a, b) { return a.hlc < b.hlc ? -1 : a.hlc > b.hlc ? 1 : 0; });
  };

  /** Canonical state for equality checks across nodes. */
  SyncNode.prototype.snapshot = function () {
    return JSON.stringify({
      learners: Array.from(this.learners.values()).map(function (l) { return [l.id, l.school_id, l.first_name, l.last_name, l.grade, l.class_label]; }).sort(),
      marks: Array.from(this.marks.values()).map(function (m) { return [m.id, m.learner_id, m.task_id, m.value, m.supersedes.slice().sort().join(','), m.conflict]; }).sort(),
      comments: Array.from(this.comments.values()).map(function (c) { return [c.id, c.learner_id, c.text]; }).sort()
    });
  };

  /** Two-way in-process sync. Returns the events newly applied on each side. */
  function syncPair(a, b) {
    var out = {};
    [[a, b], [b, a]].forEach(function (pair) {
      var dst = pair[0], src = pair[1];
      var cursor = dst.cursors[src.id] || 0;
      var applied = [];
      for (;;) {
        var r = src.pull(cursor, dst.id);
        if (r.next === cursor) break;
        applied = applied.concat(dst.receive(r.events));
        cursor = r.next;
        dst.cursors[src.id] = cursor;
      }
      out[dst.id] = applied;
    });
    return out;
  }

  var api = { HLC: HLC, SyncNode: SyncNode, SyncError: SyncError, syncPair: syncPair, uuid: uuid };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KhapaEngine = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
