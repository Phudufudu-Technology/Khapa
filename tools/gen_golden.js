// Runs the PROTOTYPE's own JavaScript (tools/reference/*.js) and writes golden outputs that the
// Python port must reproduce exactly. Re-run only if the prototype changes:
//   node tools/gen_golden.js > tests/fixtures/js_golden.json
const E = require('./reference/engine.js');
const A = require('./reference/analytics.js');
const D = require('./reference/data.js');
const W = require('./reference/world.js');

const ids = D.LEARNERS.map((l) => l.id);
const T0 = 1800000000000;
const out = { levels: [], risk: {}, demo: [] };

for (let p = 0; p <= 100; p += 0.5) { const l = A.level(p); out.levels.push([p, l.n, l.label]); }
for (let p = 29.5; p <= 80.5; p += 10) { const l = A.level(p - 0.1); out.levels.push([p - 0.1, l.n, l.label]); }

function riskOf(node, id) {
  const r = A.risk(A.learnerMarks(node, D.TASKS, id));
  const p = r.projection;
  return { level: r.level, reasons: r.reasons, weak: r.weak.map((w) => [w.topic, w.value, w.taskId]),
    projection: { value: p.value, slope: p.slope, n: p.n, remaining: p.remaining, average: p.average === undefined ? null : p.average } };
}
function summary(w, label) {
  const hub = w.hub;
  const cm = (n, l, t) => { const c = n.currentMark(l, t); return c ? { value: c.value, conflict: c.conflict, alts: c.alternatives.map((a) => a.value).sort() } : null; };
  const nodes = {};
  ['hub', 'hubB', 'cloud', 'phone'].forEach((id) => {
    nodes[id] = { L03_T4: cm(w[id], 'L03', 'T4'), L03_T6: cm(w[id], 'L03', 'T6'), log: w[id].log.length,
      pendingUp: id === 'cloud' ? 0 : w[id].pendingFor(w.cloud).length };
  });
  return { label, nodes, L03: riskOf(hub, 'L03'), L03_phone: riskOf(w.phone, 'L03'),
    classAverage: A.classAverage(hub, D.TASKS, ids),
    topicAverages: A.classTopicAverages(hub, D.TASKS, ids).map((a) => [a.task.id, a.average, a.count]) };
}
function syncAll(N) {
  let changed = true, guard = 0;
  while (changed && guard++ < 4) {
    changed = false;
    ['hub', 'hubB', 'phone'].forEach((id) => {
      const r = E.syncPair(N[id], N.cloud);
      if (r.cloud.length || r[id].length) changed = true;
    });
  }
}

const w = W.buildWorld(() => T0);
ids.forEach((id) => { out.risk[id] = riskOf(w.hub, id); });
out.seed = summary(w, 'seed');
out.seedLogLen = w.hub.log.length;
out.teacherName = D.PERSONAS.teacher.name;

// the guided demo, step by step (the same actions as DEMO[] in app.js)
out.demo.push(summary(w, 'step 0: seeded and synced'));
let online = false;                                   // step 1: internet down
out.demo.push(summary(w, 'step 1: internet off'));
w.hub.recordMark('L03', 'T6', 38, D.PERSONAS.teacher.name);   // step 2
out.demo.push(summary(w, 'step 2: teacher captured offline'));
out.demo.push(summary(w, 'step 3: parent phone (stale)'));     // step 3: no data change
online = true; syncAll(w);                                      // step 4
out.demo.push(summary(w, 'step 4: internet back, phone caught up'));
w.hub.recordMark('L03', 'T4', 45, D.PERSONAS.teacher.name);     // step 5 (offline)
w.hubB.recordMark('L03', 'T4', 52, 'Mr HOD');
out.demo.push(summary(w, 'step 5: concurrent offline edits'));
syncAll(w);                                                     // step 6
out.demo.push(summary(w, 'step 6: conflict flagged'));
w.hub.recordMark('L03', 'T4', 48, D.PERSONAS.teacher.name);     // teacher resolves
syncAll(w);
out.demo.push(summary(w, 'resolved: converged'));

// school matrix with the live cell
const live = A.classAverage(w.hub, D.TASKS, ids);
const matrix = D.SCHOOL_MATRIX.map((r) => ({ grade: r.grade, values: r.values.map((v, i) => (r.grade === 11 && i === 1 ? live : v)) }));
const wc = A.weakCells(matrix, D.AREAS, 8);
out.weakCells = { mean: wc.mean, cells: wc.cells.map((c) => [c.grade, c.area, c.value, c.gapToMean]) };
// edge inputs for slope / projection / risk on synthetic series
out.series = [[], [50], [70, 60], [40, 40, 40], [90, 80, 70, 60, 50], [30, 35, 41, 52, 60], [49.5, 50, 50.5], [100, 100], [0, 0, 0]].map((vals) => {
  const marks = vals.map((v, i) => ({ task: { id: 'X' + i, topic: 'Topic ' + i }, value: v }));
  const padded = marks.concat([{ task: { id: 'Xe', topic: 'Empty' }, value: null }]);
  const r = A.risk(padded), p = r.projection;
  return { vals, slope: A.slope(vals), level: r.level, reasons: r.reasons,
    projection: { value: p.value, slope: p.slope, n: p.n, remaining: p.remaining, average: p.average === undefined ? null : p.average } };
});
process.stdout.write(JSON.stringify(out, null, 1));
