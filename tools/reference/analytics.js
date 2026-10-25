/* Rule-based analytics. No machine learning: every flag can be explained in one sentence. */
(function (root) {
  'use strict';

  var SUPPORT_THRESHOLD = 50; // marks below this count as a weak topic (demo default, set per school)
  var RECENT = 3; // how many recent assessments count towards current weak topics

  /* CAPS-style seven-point scale (indicative: verify against DBE documents before production). */
  function level(pct) {
    if (pct >= 80) return { n: 7, label: 'Outstanding' };
    if (pct >= 70) return { n: 6, label: 'Meritorious' };
    if (pct >= 60) return { n: 5, label: 'Substantial' };
    if (pct >= 50) return { n: 4, label: 'Adequate' };
    if (pct >= 40) return { n: 3, label: 'Moderate' };
    if (pct >= 30) return { n: 2, label: 'Elementary' };
    return { n: 1, label: 'Not achieved' };
  }

  function mean(a) { return a.length ? a.reduce(function (s, v) { return s + v; }, 0) / a.length : null; }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function round1(v) { return Math.round(v * 10) / 10; }

  /** Least-squares slope of values against their position (points per assessment). */
  function slope(values) {
    var n = values.length;
    if (n < 2) return 0;
    var mx = (n - 1) / 2, my = mean(values), num = 0, den = 0;
    for (var i = 0; i < n; i++) { num += (i - mx) * (values[i] - my); den += (i - mx) * (i - mx); }
    return den === 0 ? 0 : num / den;
  }

  /** Marks for one learner over the tasks, in order. */
  function learnerMarks(node, tasks, learnerId) {
    return tasks.map(function (t) {
      var cm = node.currentMark(learnerId, t.id);
      return { task: t, value: cm ? cm.value : null, conflict: cm ? cm.conflict : false };
    });
  }

  /** Weak topics among the most recent `recentN` captured marks (all captured marks if omitted).
   *  Older weak marks that have since been overtaken are not counted as current weaknesses. */
  function weakTopics(marks, recentN) {
    var captured = marks.filter(function (m) { return m.value !== null; });
    if (recentN) captured = captured.slice(-recentN);
    return captured.filter(function (m) { return m.value < SUPPORT_THRESHOLD; })
      .map(function (m) { return { topic: m.task.topic, value: m.value, taskId: m.task.id }; });
  }

  /** Assumes the recent trend continues for the assessments still to come. */
  function projection(marks) {
    var vals = marks.filter(function (m) { return m.value !== null; }).map(function (m) { return m.value; });
    var remaining = marks.length - vals.length;
    if (vals.length < 2) return { value: vals.length ? vals[0] : null, slope: 0, n: vals.length, remaining: remaining };
    var s = slope(vals);
    var recent = mean(vals.slice(-3));
    var next = clamp(recent + s, 0, 100);
    var total = vals.reduce(function (a, v) { return a + v; }, 0) + remaining * next;
    return { value: round1(total / (vals.length + remaining)), slope: round1(s), n: vals.length, remaining: remaining, average: round1(mean(vals)) };
  }

  /** high: needs support now. watch: keep an eye on. ok: on track. */
  function risk(marks) {
    var weak = weakTopics(marks, RECENT);
    var p = projection(marks);
    var reasons = [];
    var lvl = 'ok';
    if (weak.length >= 2) { lvl = 'high'; }
    if (p.value !== null && p.value < SUPPORT_THRESHOLD) { lvl = 'high'; }
    if (lvl !== 'high') {
      if (weak.length === 1 || p.slope <= -4 || (p.value !== null && p.value < 58)) lvl = 'watch';
    }
    if (weak.length) reasons.push('Recently below ' + SUPPORT_THRESHOLD + '%: ' + weak.map(function (w) { return w.topic + ' ' + Math.round(w.value) + '%'; }).join(', ') + '.');
    if (p.n >= 2 && p.slope <= -4) reasons.push('Marks are falling by about ' + Math.abs(p.slope) + ' points per assessment.');
    if (p.value !== null && p.value < SUPPORT_THRESHOLD) reasons.push('Projected year mark is ' + p.value + '%.');
    if (lvl === 'ok' && p.slope >= 4) reasons.push('Improving by about ' + p.slope + ' points per assessment.');
    return { level: lvl, reasons: reasons, weak: weak, projection: p };
  }

  /** Class average per task over captured marks. */
  function classTopicAverages(node, tasks, learnerIds) {
    return tasks.map(function (t) {
      var vals = [];
      learnerIds.forEach(function (id) { var cm = node.currentMark(id, t.id); if (cm) vals.push(cm.value); });
      return { task: t, average: vals.length ? round1(mean(vals)) : null, count: vals.length, total: learnerIds.length };
    });
  }

  /** Mean of every current mark in the class (used for the live cell on the principal's view). */
  function classAverage(node, tasks, learnerIds) {
    var vals = [];
    tasks.forEach(function (t) { learnerIds.forEach(function (id) { var cm = node.currentMark(id, t.id); if (cm) vals.push(cm.value); }); });
    return vals.length ? round1(mean(vals)) : null;
  }

  /** Cells more than `gap` points under the school mean. `matrix` rows are {grade, values}. */
  function weakCells(matrix, areas, gap) {
    var all = [];
    matrix.forEach(function (r) { r.values.forEach(function (v) { if (v !== null) all.push(v); }); });
    var m = mean(all);
    var out = [];
    matrix.forEach(function (r) {
      r.values.forEach(function (v, i) {
        if (v !== null && v < m - (gap || 8)) out.push({ grade: r.grade, area: areas[i], value: v, gapToMean: round1(m - v) });
      });
    });
    out.sort(function (a, b) { return a.value - b.value; });
    return { mean: round1(m), cells: out };
  }

  var api = {
    SUPPORT_THRESHOLD: SUPPORT_THRESHOLD, level: level, slope: slope, mean: mean, learnerMarks: learnerMarks,
    weakTopics: weakTopics, projection: projection, risk: risk, classTopicAverages: classTopicAverages,
    classAverage: classAverage, weakCells: weakCells
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KhapaAnalytics = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
