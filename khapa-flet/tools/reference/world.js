/* Builds the simulated devices and seeds them. Clock skew is deliberate: the sync engine
 * must cope with school devices whose clocks are minutes wrong. */
(function (root) {
  'use strict';

  var E = typeof require !== 'undefined' ? require('./engine.js') : root.KhapaEngine;
  var D = typeof require !== 'undefined' ? require('./data.js') : root.KhapaData;

  var SKEW_MS = { hub: 0, hubB: -240000, cloud: 0, phone: 90000 };
  var DEVICE_LABELS = {
    hub: 'School hub (teacher, principal)',
    hubB: 'HOD tablet (away from the school network)',
    cloud: 'Cloud',
    phone: 'Parent and learner phone'
  };

  function buildWorld(nowFn) {
    var now = nowFn || function () { return Date.now(); };
    var nodes = {};
    Object.keys(SKEW_MS).forEach(function (id) {
      nodes[id] = new E.SyncNode(id, function () { return now() + SKEW_MS[id]; });
    });

    var cloud = nodes.cloud;
    D.LEARNERS.forEach(function (l) {
      cloud.createLearner({ school_id: D.SCHOOL_ID, first_name: l.first, last_name: l.last, grade: 11, class_label: D.CLASS_LABEL }, l.id);
      l.marks.forEach(function (m, i) { cloud.recordMark(l.id, D.TASKS[i].id, m, D.PERSONAS.teacher.name); });
    });
    D.SEED_COMMENTS.forEach(function (c) {
      cloud.addComment(c.learner, D.PERSONAS.teacher.name, 'teacher', c.text);
    });
    ['hub', 'hubB', 'phone'].forEach(function (id) { E.syncPair(nodes[id], cloud); });
    return nodes;
  }

  var api = { buildWorld: buildWorld, SKEW_MS: SKEW_MS, DEVICE_LABELS: DEVICE_LABELS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KhapaWorld = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
