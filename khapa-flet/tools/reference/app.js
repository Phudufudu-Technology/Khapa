/* Khapa prototype UI. Four simulated devices run inside this page (see world.js). */
(function () {
  'use strict';

  var E = window.KhapaEngine, D = window.KhapaData, A = window.KhapaAnalytics, W = window.KhapaWorld;
  var ROLES = ['guide', 'teacher', 'parent', 'learner', 'principal'];
  var SHORT = { hub: 'School hub', hubB: 'HOD tablet', cloud: 'Cloud', phone: 'Phone' };
  var N = null;
  var S = null;

  /* ---- helpers ------------------------------------------------------------------------ */
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  }
  function t(key, params) {
    var table = D.I18N[S.lang];
    var s = (table && table[key]) || D.I18N.en[key] || key;
    if (params) s = s.replace(/\{(\w+)\}/g, function (m, k) { return params[k] !== undefined ? params[k] : m; });
    return s;
  }
  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function timeStr(ms) { var d = new Date(ms); return pad2(d.getHours()) + ':' + pad2(d.getMinutes()); }
  function num(v) { return Number.isInteger(v) ? String(v) : v.toFixed(1); }
  function plural(n, w) { return n + ' ' + w + (n === 1 ? '' : 's'); }
  function learner(id) { return D.LEARNERS.filter(function (l) { return l.id === id; })[0]; }
  function fullName(id) { var l = learner(id); return l ? l.first + ' ' + l.last : id; }
  function firstName(id) { var l = learner(id); return l ? l.first : id; }
  function task(id) { return D.TASKS.filter(function (x) { return x.id === id; })[0]; }
  function learnerIds() { return D.LEARNERS.map(function (l) { return l.id; }); }
  function viewNode() { return S.role === 'teacher' || S.role === 'principal' ? N.hub : N.phone; }
  function $(id) { return document.getElementById(id); }
  function levelText(v) { var l = A.level(v); return 'Level ' + l.n + ', ' + l.label; }

  /* ---- state --------------------------------------------------------------------------- */
  function freshState(keepLang) {
    return { role: 'guide', lang: keepLang || 'en', online: true, learnerId: 'L03', overlay: null, devices: false, log: [], fresh: {}, lastSync: {}, demo: null, timer: null, toastTimer: null };
  }
  function resetWorld() {
    var lang = S ? S.lang : 'en';
    if (S && S.timer) clearTimeout(S.timer);
    N = W.buildWorld();
    S = freshState(lang);
    ['hub', 'hubB', 'phone'].forEach(function (id) { S.lastSync[id] = Date.now(); });
    log('Demo data loaded. All four devices are in sync.');
  }
  function log(msg) { S.log.unshift(timeStr(Date.now()) + '  ' + msg); if (S.log.length > 40) S.log.pop(); }
  function toast(msg) {
    var el = $('toast');
    if (!el) return;
    el.textContent = msg;
    clearTimeout(S.toastTimer);
    S.toastTimer = setTimeout(function () { el.textContent = ''; }, 2600);
  }

  /* ---- sync orchestration -------------------------------------------------------------- */
  function markFresh(nodeId, events) {
    var any = false;
    events.forEach(function (ev) {
      if (ev.entity === 'mark_version') { S.fresh[nodeId + '|' + ev.payload.learner_id + '|' + ev.payload.task_id] = true; any = true; }
    });
    if (any) setTimeout(function () { S.fresh = {}; render(); }, 2500);
  }
  function syncAll() {
    if (!S.online) return;
    var changed = true, guard = 0;
    while (changed && guard++ < 4) {
      changed = false;
      ['hub', 'hubB', 'phone'].forEach(function (id) {
        var r = E.syncPair(N[id], N.cloud);
        var up = r.cloud.length, down = r[id].length;
        if (up) { log(SHORT[id] + ' to cloud: ' + plural(up, 'event')); changed = true; }
        if (down) { log('Cloud to ' + SHORT[id].toLowerCase() + ': ' + plural(down, 'event')); changed = true; markFresh(id, down ? r[id] : []); }
        S.lastSync[id] = Date.now();
      });
    }
  }
  function scheduleSync() {
    if (!S.online) return;
    clearTimeout(S.timer);
    S.timer = setTimeout(function () { syncAll(); render(); }, 350);
  }
  function setNet(on) {
    S.online = on;
    log('Internet ' + (on ? 'on' : 'off'));
    if (on) syncAll();
  }

  /* ---- shared view pieces -------------------------------------------------------------- */
  function bars(marks) {
    var rows = marks.map(function (m) {
      if (m.value === null) {
        return '<div class="bar-row"><span class="lbl muted">' + esc(m.task.topic) + '</span><div class="track" aria-hidden="true"></div><span class="val muted">' + esc(t('marks.empty')) + '</span></div>';
      }
      var cls = m.value < A.SUPPORT_THRESHOLD ? 'weak' : m.value >= 70 ? 'good' : '';
      return '<div class="bar-row"><span class="lbl">' + esc(m.task.topic) + '</span>' +
        '<div class="track" role="img" aria-label="' + esc(m.task.topic) + ' ' + num(m.value) + ' percent"><div class="fill ' + cls + '" style="width:' + m.value + '%"></div><span class="line" style="left:' + A.SUPPORT_THRESHOLD + '%"></span></div>' +
        '<span class="val">' + num(m.value) + '%<small>' + esc(levelText(m.value)) + '</small></span></div>';
    }).join('');
    return '<div class="bars">' + rows + '</div>';
  }
  function spark(marks) {
    var w = 320, h = 80, p = 10, n = marks.length;
    var x = function (i) { return p + i * (w - 2 * p) / (n - 1); };
    var y = function (v) { return h - p - (v / 100) * (h - 2 * p); };
    var pts = [], dots = '';
    marks.forEach(function (m, i) {
      if (m.value === null) return;
      pts.push(x(i).toFixed(1) + ',' + y(m.value).toFixed(1));
      dots += '<circle cx="' + x(i).toFixed(1) + '" cy="' + y(m.value).toFixed(1) + '" r="4" fill="' + (m.value < A.SUPPORT_THRESHOLD ? 'var(--pen)' : 'var(--blue)') + '"/>';
    });
    var vals = marks.filter(function (m) { return m.value !== null; }).map(function (m) { return Math.round(m.value); });
    return '<svg class="spark" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="Marks over the year: ' + vals.join(', ') + ' percent">' +
      '<line x1="' + p + '" x2="' + (w - p) + '" y1="' + y(A.SUPPORT_THRESHOLD).toFixed(1) + '" y2="' + y(A.SUPPORT_THRESHOLD).toFixed(1) + '" stroke="var(--ink-2)" stroke-dasharray="4 4" opacity=".6"/>' +
      '<polyline points="' + pts.join(' ') + '" fill="none" stroke="var(--blue)" stroke-width="2"/>' + dots + '</svg>';
  }
  function riskPill(r) {
    var text = r.level === 'high' ? 'Needs support' : r.level === 'watch' ? 'Watch' : 'On track';
    return '<span class="pill ' + r.level + '">' + text + '</span>';
  }
  function trendSentence(p) {
    if (p.n < 2) return 'There are not enough marks yet to see a trend.';
    if (p.slope >= 4) return 'Marks are going up.';
    if (p.slope <= -4) return 'Marks have been going down.';
    return 'Marks are fairly steady.';
  }
  function commentsHtml(node, id) {
    var list = node.commentsFor(id).slice().reverse();
    if (!list.length) return '<p class="muted">' + esc(t('comments.none')) + '</p>';
    return list.map(function (c) {
      return '<div class="comment"><div class="pen">' + esc(c.text) + '</div><small>' + esc(c.author_name) + ', ' + esc(c.author_role) + '</small></div>';
    }).join('');
  }
  function learnerPicker() {
    var opts = D.LEARNERS.map(function (l) { return '<option value="' + l.id + '"' + (l.id === S.learnerId ? ' selected' : '') + '>' + esc(l.first + ' ' + l.last) + '</option>'; }).join('');
    return '<div class="field"><label for="viewAs">' + esc(t('view.as')) + '</label><select id="viewAs" data-change="viewAs">' + opts + '</select></div>';
  }
  function updatedText(nodeId) { return esc(t('updated')) + ' ' + timeStr(S.lastSync[nodeId] || Date.now()); }

  /* ---- teacher ------------------------------------------------------------------------- */
  function cellHtml(l, tk, pendingIds) {
    var cm = N.hub.currentMark(l, tk.id);
    var cls = ['cell'], label, aria;
    var who = fullName(l) + ', ' + tk.topic;
    if (!cm) { cls.push('empty'); label = '—'; aria = who + ': ' + t('marks.empty'); }
    else {
      label = cm.conflict ? esc(t('marks.conflict', { n: cm.alternatives.length + 1 })) : num(cm.value);
      if (cm.value < A.SUPPORT_THRESHOLD && !cm.conflict) cls.push('weak');
      if (cm.conflict) cls.push('conflict');
      if (pendingIds[cm.versionId]) cls.push('pending');
      aria = who + ': ' + (cm.conflict ? t('marks.conflict', { n: cm.alternatives.length + 1 }) : num(cm.value));
    }
    if (S.fresh['hub|' + l + '|' + tk.id]) cls.push('fresh');
    var act = cm && cm.conflict ? 'openResolve' : 'openMark';
    return '<td><button class="' + cls.join(' ') + '" data-act="' + act + '" data-l="' + l + '" data-t="' + tk.id + '" aria-label="' + esc(aria) + '">' + label + '</button></td>';
  }

  function viewTeacher() {
    var hub = N.hub, ids = learnerIds();
    var pendingIds = {};
    hub.pendingFor(N.cloud).forEach(function (e) { pendingIds[e.entity_id] = true; });
    var captured = D.TASKS.filter(function (tk) { return ids.some(function (id) { return hub.currentMark(id, tk.id); }); }).length;
    var head = D.TASKS.map(function (tk) { return '<th scope="col">' + esc(tk.topic) + '<small>' + esc(tk.kind) + ', term ' + tk.term + '</small></th>'; }).join('');
    var risks = {};
    ids.forEach(function (id) { risks[id] = A.risk(A.learnerMarks(hub, D.TASKS, id)); });
    var rows = ids.map(function (id) {
      var r = risks[id];
      var avg = r.projection.average;
      return '<tr><th scope="row" class="who"><button data-act="openLearner" data-l="' + id + '">' + esc(fullName(id)) + '</button></th>' +
        D.TASKS.map(function (tk) { return cellHtml(id, tk, pendingIds); }).join('') +
        '<td>' + (avg !== undefined && avg !== null ? num(avg) : '—') + '</td><td>' + riskPill(r) + '</td></tr>';
    }).join('');

    var flagged = ids.filter(function (id) { return risks[id].level !== 'ok'; }).sort(function (a, b) {
      var o = { high: 0, watch: 1 };
      return o[risks[a].level] - o[risks[b].level];
    });
    var notes = flagged.map(function (id) {
      var r = risks[id];
      var weakest = r.weak.slice().sort(function (a, b) { return a.value - b.value; })[0];
      var tip = weakest && D.TIPS[weakest.topic] ? D.TIPS[weakest.topic].teacher : '';
      return '<div class="note"><div class="pen"><span class="who-l">' + esc(firstName(id)) + '</span> ' + esc(r.reasons[0] || '') + '</div>' +
        '<div class="plain">' + esc(r.reasons.slice(1).join(' ')) + (tip ? ' ' + esc(tip) : '') + ' <button class="link" data-act="openLearner" data-l="' + id + '">Open ' + esc(firstName(id)) + '</button></div></div>';
    }).join('') || '<p class="muted">' + esc(t('needs.none')) + '</p>';

    var avgs = A.classTopicAverages(hub, D.TASKS, ids);
    var withData = avgs.filter(function (a) { return a.average !== null; });
    var weakest = withData.slice().sort(function (a, b) { return a.average - b.average; })[0];
    var topicBars = '<div class="bars">' + avgs.map(function (a) {
      if (a.average === null) return '<div class="bar-row"><span class="lbl muted">' + esc(a.task.topic) + '</span><div class="track" aria-hidden="true"></div><span class="val muted">' + esc(t('marks.empty')) + '</span></div>';
      var cls = a.average < A.SUPPORT_THRESHOLD ? 'weak' : a.average >= 70 ? 'good' : '';
      return '<div class="bar-row"><span class="lbl">' + esc(a.task.topic) + '</span><div class="track" role="img" aria-label="' + esc(a.task.topic) + ' class average ' + num(a.average) + ' percent"><div class="fill ' + cls + '" style="width:' + a.average + '%"></div><span class="line" style="left:' + A.SUPPORT_THRESHOLD + '%"></span></div><span class="val">' + num(a.average) + '%<small>' + a.count + ' of ' + a.total + '</small></span></div>';
    }).join('') + '</div>';
    var classNote = weakest ? '<div class="note" style="margin-top:12px"><div class="pen">Lowest class average: ' + esc(weakest.task.topic) + ', ' + num(weakest.average) + '%.</div><div class="plain">' + esc(D.TIPS[weakest.task.topic].teacher) + '</div></div>' : '';

    return '<div class="head"><h1>Grade ' + D.CLASS_LABEL + ' Mathematics</h1><p class="sub">Term 2, ' + esc(D.PERSONAS.teacher.name) + ', ' + ids.length + ' learners. ' + captured + ' of ' + D.TASKS.length + ' assessments captured.</p></div>' +
      '<section class="sheet" aria-labelledby="mk"><h2 id="mk">' + esc(t('marks.title')) + '</h2><p class="muted">' + esc(t('marks.hint')) + '</p>' +
      '<div class="grid-wrap"><table class="marks"><thead><tr><th scope="col" class="who">Learner</th>' + head + '<th scope="col">' + esc(t('marks.average')) + '</th><th scope="col">Support</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
      '<div class="legend"><span>Circled in red: below ' + A.SUPPORT_THRESHOLD + '%.</span><span>Yellow dot: saved on the hub, waiting to upload.</span><span>Yellow box: two people changed the same mark.</span></div></section>' +
      '<div class="grid2 wide-left"><section class="sheet" aria-labelledby="nd"><h2 id="nd">' + esc(t('needs.title')) + '</h2><div class="notes">' + notes + '</div><p class="ai">' + esc(t('ai.note')) + '</p></section>' +
      '<section class="sheet" aria-labelledby="ct"><h2 id="ct">Class average by topic</h2>' + topicBars + classNote + '</section></div>';
  }

  /* ---- parent -------------------------------------------------------------------------- */
  function viewParent() {
    var node = N.phone, id = S.learnerId;
    var marks = A.learnerMarks(node, D.TASKS, id), r = A.risk(marks), p = r.projection;
    var name = firstName(id);
    var summary = r.level === 'high' ? name + ' needs extra support right now.' : r.level === 'watch' ? name + ' is doing fine but needs watching.' : name + ' is on track.';
    var proj = p.value !== null ? '<div class="stat"><b>' + num(p.value) + '%</b><span>' + esc(t('marks.projected')) + ', ' + esc(levelText(p.value)) + '</span></div>' : '';
    var help = r.weak.slice().sort(function (a, b) { return a.value - b.value; }).slice(0, 3).map(function (w) {
      return '<li><strong>' + esc(w.topic) + ' (' + num(w.value) + '%).</strong> ' + esc(D.TIPS[w.topic] ? D.TIPS[w.topic].parent : '') + '</li>';
    }).join('');
    var banner = !S.online ? '<div class="banner" role="status">' + esc(t('parent.stale')) + ' ' + updatedText('phone') + '.</div>' : '';
    return '<div class="head"><h1>' + esc(fullName(id)) + '</h1><p class="sub">Grade ' + D.CLASS_LABEL + ' Mathematics. ' + updatedText('phone') + '.</p></div>' + banner +
      '<div class="grid2"><section class="sheet"><h2>Where things stand</h2><p style="margin-top:6px">' + esc(summary) + ' ' + esc(trendSentence(p)) + '</p><div class="stats" style="margin-top:14px">' + proj + '</div>' +
      '<div style="margin-top:14px">' + spark(marks) + '</div><p class="muted" style="font-size:.88rem">' + esc(t('trend.title')) + '. Dashed line: ' + A.SUPPORT_THRESHOLD + '%.</p></section>' +
      '<section class="sheet"><h2>' + esc(t('help.title')) + '</h2>' + (help ? '<ul class="tips">' + help + '</ul>' : '<p class="muted" style="margin-top:8px">' + esc(t('focus.none')) + '</p>') + '<p class="ai">' + esc(t('ai.note')) + '</p></section></div>' +
      '<section class="sheet"><h2>' + esc(t('marks.title')) + ' by topic</h2>' + bars(marks) + '</section>' +
      '<section class="sheet"><h2>' + esc(t('comments.title')) + '</h2>' + commentsHtml(node, id) + '</section>';
  }

  /* ---- learner ------------------------------------------------------------------------- */
  function viewLearner() {
    var node = N.phone, id = S.learnerId;
    var marks = A.learnerMarks(node, D.TASKS, id), r = A.risk(marks), p = r.projection;
    var byTopic = {};
    marks.forEach(function (m) { byTopic[m.task.topic] = m.value; });
    var focus = r.weak.slice().sort(function (a, b) { return a.value - b.value; }).slice(0, 3).map(function (w) {
      return '<li><strong>' + esc(w.topic) + ' (' + num(w.value) + '%).</strong> ' + esc(D.TIPS[w.topic] ? D.TIPS[w.topic].learner : '') + '</li>';
    }).join('');
    var paths = D.PATHWAYS.map(function (pw) {
      var chips = pw.topics.map(function (tp) {
        var v = byTopic[tp];
        return '<span class="tag">' + esc(tp) + ' ' + (v === null || v === undefined ? 'not captured' : num(v) + '%') + '</span>';
      }).join('');
      return '<div class="card"><h3>' + esc(pw.name) + '</h3><p class="muted" style="margin-top:4px">' + esc(pw.needs) + '</p><div class="tags">' + chips + '</div></div>';
    }).join('');
    var m = D.MARKET;
    var banner = !S.online ? '<div class="banner" role="status">' + esc(t('parent.stale')) + ' ' + updatedText('phone') + '.</div>' : '';
    return '<div class="head"><h1>' + esc(t('learner.hello', { name: firstName(id) })) + '</h1><p class="sub">Grade ' + D.CLASS_LABEL + ' Mathematics. ' + updatedText('phone') + '.</p></div>' + banner +
      '<div class="grid2"><section class="sheet"><h2>' + esc(t('learner.marks')) + '</h2>' + bars(marks) + '</section>' +
      '<section class="sheet"><h2>' + esc(t('focus.title')) + '</h2>' + (focus ? '<ul class="tips">' + focus + '</ul>' : '<p class="muted" style="margin-top:8px">' + esc(t('focus.none')) + '</p>') +
      (p.value !== null ? '<div class="stats" style="margin-top:14px"><div class="stat"><b>' + num(p.value) + '%</b><span>' + esc(t('marks.projected')) + '</span></div></div>' : '') +
      '<div style="margin-top:12px">' + spark(marks) + '</div><p class="ai">' + esc(t('ai.note')) + '</p></section></div>' +
      '<section class="sheet"><h2>' + esc(t('learner.next')) + '</h2><p class="muted">Sample guidance for the demo. Marks below come from your own results.</p><div class="cards">' + paths + '</div>' +
      '<p class="ai">Production loads dated, sourced data from Stats SA, DHET and the SETAs. The figures below are real.</p></section>' +
      '<div class="grid2"><section class="sheet"><h2>' + esc(t('market.title')) + '</h2><div class="stats" style="margin-top:10px"><div class="stat"><b>' + m.unemployment + '</b><span>South Africans looking for work, ' + m.period + '</span></div><div class="stat"><b>' + m.youthUnemployment + '</b><span>of 15 to 34 year olds, ' + m.period + '</span></div></div>' +
      '<p class="muted" style="margin-top:10px">Source: <a href="https://www.statssa.gov.za/?p=19804" target="_blank" rel="noopener">Stats SA Quarterly Labour Force Survey</a>. Studying and funding plans matter more when jobs are scarce.</p></section>' +
      '<section class="sheet"><h2>' + esc(t('links.title')) + '</h2><ul class="tips"><li><a href="https://www.careersportal.co.za/" target="_blank" rel="noopener">Careers Portal</a>: bursaries, learnerships and internships.</li><li><a href="https://www.siyavula.com/future" target="_blank" rel="noopener">Siyavula My Future</a>: career guidance and partner bursaries.</li></ul></section></div>' +
      '<section class="sheet"><h2>' + esc(t('comments.title')) + '</h2>' + commentsHtml(node, id) + '</section>';
  }

  /* ---- principal ----------------------------------------------------------------------- */
  function viewPrincipal() {
    var hub = N.hub, ids = learnerIds();
    var live = A.classAverage(hub, D.TASKS, ids);
    var matrix = D.SCHOOL_MATRIX.map(function (r) { return { grade: r.grade, values: r.values.map(function (v, i) { return r.grade === 11 && i === 1 ? live : v; }) }; });
    var wc = A.weakCells(matrix, D.AREAS, 8);
    var risks = ids.map(function (id) { return A.risk(A.learnerMarks(hub, D.TASKS, id)).level; });
    var high = risks.filter(function (x) { return x === 'high'; }).length, watch = risks.filter(function (x) { return x === 'watch'; }).length;
    var head = '<tr><th></th>' + D.AREAS.map(function (a) { return '<th scope="col">' + esc(a) + '</th>'; }).join('') + '</tr>';
    var body = matrix.map(function (r) {
      return '<tr><th scope="row" class="row">Grade ' + r.grade + '</th>' + r.values.map(function (v, i) {
        var isLive = r.grade === 11 && i === 1;
        var cls = v < wc.mean - 8 ? 'low' : v < 58 ? 'mid' : 'high';
        return '<td class="' + cls + (isLive ? ' liveC' : '') + '">' + (v === null ? '—' : num(v)) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    var list = wc.cells.map(function (c) {
      return '<div class="note"><div class="pen">Grade ' + c.grade + ' ' + esc(c.area) + ': ' + num(c.value) + '%, ' + num(c.gapToMean) + ' points under the school mean.</div><div class="plain">' + esc(t('principal.act')) + '</div></div>';
    }).join('') || '<p class="muted">' + esc(t('needs.none')) + '</p>';
    return '<div class="head"><h1>' + esc(t('principal.title')) + '</h1><p class="sub">' + esc(D.PERSONAS.principal.name) + '. Data from the school hub. ' + updatedText('hub') + '.</p></div>' +
      '<div class="sheet"><div class="stats"><div class="stat"><b>' + high + '</b><span>learners need support in Grade ' + D.CLASS_LABEL + ' Mathematics</span></div><div class="stat"><b>' + watch + '</b><span>more to watch</span></div><div class="stat"><b>' + (live !== null ? num(live) + '%' : '—') + '</b><span>Grade 11 Mathematics average, live</span></div><div class="stat"><b>' + num(wc.mean) + '%</b><span>school mean, Grades 8 to 12</span></div></div></div>' +
      '<div class="grid2 wide-left"><section class="sheet"><h2>Average mark by grade and learning area</h2>' +
      '<div class="grid-wrap"><table class="heat" aria-label="Average marks by grade and learning area">' + head + body + '</table></div>' +
      '<div class="tags"><span class="tag live">' + esc(t('principal.live')) + ': Grade 11 Mathematics (outlined)</span><span class="tag">' + esc(t('principal.sample')) + ': every other cell</span></div>' +
      '<div class="legend"><span>Red: more than 8 points under the school mean.</span><span>Yellow: under 58%.</span></div></section>' +
      '<section class="sheet"><h2>' + esc(t('principal.weak')) + '</h2><div class="notes">' + list + '</div><p class="ai">' + esc(t('ai.note')) + '</p></section></div>';
  }

  /* ---- guide --------------------------------------------------------------------------- */
  function viewGuide() {
    var m = D.MARKET;
    var crit = [
      ['Product', 'Four role views on one shared record. Marks, comments and support flags move between devices. Try: Teacher, then Parent.'],
      ['Creativity', 'Offline-first sync that keeps conflicting edits instead of overwriting them. Try: step 5 and 6 of the guided demo.'],
      ['Usability', 'Tap a mark to change it. Plain-language summaries for parents. Language switch (top right).'],
      ['Sustainability', 'Runs on a small school server plus cloud sync. Path to revenue: in preparation, not part of this prototype.'],
      ['Impact', 'Built for schools with poor or no internet. See the figures below.'],
      ['Presentation', 'This page and the guided demo.'],
      ['Intelligence', 'Trend projection and support flags from each learner’s marks. Rule-based, so every flag can be explained. Try: Teacher, red margin notes.']
    ].map(function (r) { return '<tr><th scope="row">' + r[0] + '</th><td>' + esc(r[1]) + '</td></tr>'; }).join('');
    var real = [
      ['Sync engine', 'Real. The same rules as the Khapa server code, covered by automated tests.'],
      ['Support flags and projections', 'Real. Calculated from the marks you see.'],
      ['Four devices and the internet switch', 'Simulated. All four devices run inside this page.'],
      ['Learners, marks, comments', 'Fictional.'],
      ['Suggestions', 'Rule-based text, in English only for now. No AI model runs in this prototype.'],
      ['Translations', 'Afrikaans and isiZulu are drafts waiting for human review. Nine languages are still to do.'],
      ['Not built yet', 'Sign-in, the real school hub, an installable offline app, SA-SAMS import, privacy review, a pilot school.']
    ].map(function (r) { return '<tr><th scope="row">' + r[0] + '</th><td>' + esc(r[1]) + '</td></tr>'; }).join('');
    return '<section class="hero"><h1>One mark, four people, no internet needed.</h1><p>Khapa gives teachers, parents, learners and principals the same picture of a learner’s progress, even when the school has no internet. Every name and mark in this demo is made up.</p>' +
      '<div class="ctas"><button class="btn" data-act="startDemo">Play the guided demo</button><span class="muted">About two minutes.</span></div>' +
      '<div class="explore"><span class="muted">Or explore as:</span><button class="btn ghost small" data-act="setRole" data-role="teacher">' + esc(t('role.teacher')) + '</button><button class="btn ghost small" data-act="setRole" data-role="parent">' + esc(t('role.parent')) + '</button><button class="btn ghost small" data-act="setRole" data-role="learner">' + esc(t('role.learner')) + '</button><button class="btn ghost small" data-act="setRole" data-role="principal">' + esc(t('role.principal')) + '</button></div></section>' +
      '<section class="sheet"><h2>Why this matters</h2><div class="stats" style="margin-top:10px"><div class="stat"><b>' + m.mobile + '</b><span>of households own a mobile phone, ' + m.ghsYear + '</span></div><div class="stat"><b>' + m.fixedInternet + '</b><span>have internet at home on a fixed line, ' + m.ghsYear + '</span></div><div class="stat"><b>' + m.youthUnemployment + '</b><span>of 15 to 34 year olds are unemployed, ' + m.period + '</span></div></div>' +
      '<p class="muted" style="margin-top:10px">Sources: <a href="https://www.gov.za/news/media-statements/statssa-releases-general-household-survey-2024-27-may-2025" target="_blank" rel="noopener">Stats SA General Household Survey 2024</a> (household level, not smartphone level) and <a href="https://www.statssa.gov.za/?p=19804" target="_blank" rel="noopener">Quarterly Labour Force Survey ' + m.period + '</a>.</p></section>' +
      '<section class="sheet"><h2>Where to look, by judging criterion</h2><table class="plain"><tbody>' + crit + '</tbody></table></section>' +
      '<section class="sheet"><h2>What is real and what is simulated</h2><table class="plain"><tbody>' + real + '</tbody></table></section>';
  }

  /* ---- chrome -------------------------------------------------------------------------- */
  function tickSvg() {
    return '<svg class="tick" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 13.5 9 19.5 21 5" fill="none" stroke="#ff6b5f" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  }
  function chipHtml() {
    var node = viewNode();
    var nodeId = node.id;
    var up = node.pendingFor(N.cloud).length;
    if (S.role === 'guide') { up = N.hub.pendingFor(N.cloud).length + N.hubB.pendingFor(N.cloud).length; }
    if (up > 0) return '<span class="chip wait" role="status"><span class="dot"></span>' + esc(t('sync.up', { n: up })) + '</span>';
    return '<span class="chip ok" role="status"><span class="dot"></span>' + esc(t('sync.allSynced')) + (S.role === 'guide' ? '' : ', ' + updatedText(nodeId).toLowerCase()) + '</span>';
  }
  function langNote() {
    var l = D.LANGS.filter(function (x) { return x.code === S.lang; })[0];
    if (!l || l.status === 'source') return '';
    return '<span class="lang-note">' + esc(l.status === 'draft' ? D.I18N.en['lang.draft'] : D.I18N.en['lang.pending']) + '</span>';
  }
  function devicesHtml() {
    var cards = ['hub', 'hubB', 'cloud', 'phone'].map(function (id) {
      var n = N[id];
      var skew = W.SKEW_MS[id] / 60000;
      var skewText = skew === 0 ? 'Clock is right.' : 'Clock is ' + Math.abs(skew) + (Math.abs(skew) === 1 ? ' minute ' : ' minutes ') + (skew < 0 ? 'slow.' : 'fast.');
      var up = id === 'cloud' ? '' : '<br>' + plural(n.pendingFor(N.cloud).length, 'event') + ' waiting to upload';
      var down = id === 'cloud' ? '' : '<br>' + plural(N.cloud.pendingFor(n).length, 'event') + ' waiting to download';
      return '<div class="dev"><b>' + esc(W.DEVICE_LABELS[id]) + '</b>' + plural(n.log.length, 'event') + ' stored' + up + down + '<br><span class="muted">' + skewText + '</span></div>';
    }).join('');
    return '<section class="devices"><div class="page" style="padding-top:16px;padding-bottom:16px"><h2>' + esc(t('sync.devices')) + '</h2>' +
      '<p class="muted">For the demo you can see every device. In real life each device only knows its own data. Clocks are deliberately wrong to show the sync copes with it.</p>' +
      '<div class="dev-grid">' + cards + '</div>' +
      '<div class="row" style="margin-top:12px"><button class="btn ghost small" data-act="hodEdit">Make the HOD tablet change Sipho’s Trigonometry mark to 52</button></div>' +
      '<ul class="log" aria-label="Sync activity">' + S.log.map(function (l) { return '<li>' + esc(l) + '</li>'; }).join('') + '</ul></div></section>';
  }
  function demoBanner() {
    if (!S.demo) return '';
    var i = S.demo.i, last = i >= DEMO.length - 1;
    return '<div class="demo" role="region" aria-label="Guided demo"><div class="demo-inner"><div class="grow"><strong>Step ' + (i + 1) + ' of ' + DEMO.length + '.</strong> ' + esc(DEMO[i].text) + '</div>' +
      (last ? '' : '<button class="btn small" data-act="demoNext">' + esc(t('demo.next')) + '</button>') +
      '<button class="btn ghost small" data-act="startDemo">' + esc(t('demo.restart')) + '</button><button class="btn ghost small" data-act="endDemo">Close</button></div></div>';
  }

  function render() {
    var root = $('app');
    if (!root) return;
    var wrap = root.querySelector('.grid-wrap');
    var scrollLeft = wrap ? wrap.scrollLeft : 0;
    var ae = document.activeElement, focusSel = null;
    if (ae && root.contains(ae)) {
      if (ae.id) focusSel = '#' + ae.id;
      else if (ae.dataset && ae.dataset.act) {
        focusSel = '[data-act="' + ae.dataset.act + '"]' + ['role', 'l', 't'].map(function (k) { return ae.dataset[k] ? '[data-' + k + '="' + ae.dataset[k] + '"]' : ''; }).join('');
        if (ae.classList.contains('tab')) focusSel = '.tab' + focusSel;
      }
    }
    var opts = D.LANGS.map(function (l) { return '<option value="' + l.code + '"' + (l.code === S.lang ? ' selected' : '') + '>' + esc(l.name) + '</option>'; }).join('');
    var tabs = ROLES.map(function (r) { return '<button class="tab"' + (r === S.role ? ' aria-current="page"' : '') + ' data-act="setRole" data-role="' + r + '">' + esc(t('role.' + r)) + '</button>'; }).join('');
    var view = S.role === 'teacher' ? viewTeacher() : S.role === 'parent' ? viewParent() : S.role === 'learner' ? viewLearner() : S.role === 'principal' ? viewPrincipal() : viewGuide();
    var picker = S.role === 'parent' || S.role === 'learner' ? learnerPicker() : '';
    document.documentElement.lang = S.lang;
    root.innerHTML =
      '<header class="top"><div class="top-inner"><div class="brand"><span class="name">' + tickSvg() + 'Khapa</span><span class="tag">' + esc(t('brand.tagline')) + '</span></div><nav class="tabs" aria-label="Choose a role">' + tabs + '</nav></div></header>' +
      '<div class="bar"><div class="bar-inner">' +
      '<div class="switch-row"><button class="switch" role="switch" aria-checked="' + S.online + '" aria-label="' + esc(t('net.label')) + '" data-act="toggleNet"><span class="knob"></span></button><span>' + esc(t('net.label')) + ': <strong>' + esc(S.online ? t('net.online') : t('net.offline')) + '</strong></span></div>' +
      chipHtml() + '<span class="grow"></span>' + picker +
      '<div class="field"><label for="lang">' + esc(t('lang.label')) + '</label><select id="lang" data-change="lang">' + opts + '</select></div>' + langNote() +
      '<button class="btn ghost small" data-act="toggleDevices" aria-expanded="' + S.devices + '">' + esc(t('sync.devices')) + '</button><button class="btn ghost small" data-act="reset">' + esc(t('reset')) + '</button></div></div>' +
      demoBanner() + '<main class="page">' + view + '</main>' + (S.devices ? devicesHtml() : '');
    var nw = root.querySelector('.grid-wrap');
    if (nw) nw.scrollLeft = scrollLeft;
    if (focusSel && !S.overlay) { var f = root.querySelector(focusSel); if (f && f.focus) f.focus(); }
  }

  /* ---- overlays ------------------------------------------------------------------------ */
  function renderOverlay() {
    var el = $('overlay');
    var o = S.overlay;
    if (!o) { el.hidden = true; el.innerHTML = ''; return; }
    var html = '';
    if (o.type === 'mark') {
      var cm = N.hub.currentMark(o.l, o.t), tk = task(o.t);
      html = '<div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlgT"><h2 id="dlgT">' + esc(fullName(o.l)) + '</h2><p class="muted">' + esc(tk.topic) + ' ' + esc(tk.kind.toLowerCase()) + ', term ' + tk.term + '</p>' +
        '<p style="margin-top:14px"><label for="markInput">Mark, 0 to 100</label></p><input id="markInput" type="number" min="0" max="100" step="0.5" inputmode="decimal" value="' + (cm ? cm.value : '') + '">' +
        '<div class="err" id="markErr" role="alert"></div><div class="row"><button class="btn" data-act="saveMark">' + esc(t('marks.save')) + '</button><button class="btn ghost" data-act="closeOverlay">' + esc(t('marks.cancel')) + '</button></div></div>';
    } else if (o.type === 'resolve') {
      var c = N.hub.currentMark(o.l, o.t), tk2 = task(o.t);
      var opts = [{ value: c.value, origin: c.enteredBy || 'unknown' }].concat(c.alternatives.map(function (a) { return { value: a.value, origin: a.enteredBy || 'unknown' }; }));
      var ch = opts.map(function (x) { return '<button class="choice" data-act="chooseMark" data-v="' + x.value + '">Keep ' + num(x.value) + ' <span class="muted">(entered by ' + esc(x.origin) + ')</span></button>'; }).join('');
      html = '<div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlgT"><h2 id="dlgT">Two values for one mark</h2><p class="muted">' + esc(fullName(o.l)) + ', ' + esc(tk2.topic) + '. Both are saved. Choose the final mark, or enter a new one.</p>' + ch +
        '<p style="margin-top:14px"><label for="markInput">Or enter a different mark</label></p><input id="markInput" type="number" min="0" max="100" step="0.5" inputmode="decimal">' +
        '<div class="err" id="markErr" role="alert"></div><div class="row"><button class="btn" data-act="saveMark">' + esc(t('marks.save')) + '</button><button class="btn ghost" data-act="closeOverlay">' + esc(t('marks.cancel')) + '</button></div></div>';
    } else if (o.type === 'learner') {
      var marks = A.learnerMarks(N.hub, D.TASKS, o.l), r = A.risk(marks);
      var tips = r.weak.slice().sort(function (a, b) { return a.value - b.value; }).map(function (w) { return '<li><strong>' + esc(w.topic) + '.</strong> ' + esc(D.TIPS[w.topic].teacher) + '</li>'; }).join('');
      html = '<div class="dialog drawer" role="dialog" aria-modal="true" aria-labelledby="dlgT"><h2 id="dlgT">' + esc(fullName(o.l)) + '</h2><p style="margin-top:6px">' + riskPill(r) + ' ' + (r.projection.value !== null ? '<span class="muted">Projected year mark ' + num(r.projection.value) + '%</span>' : '') + '</p>' +
        '<div style="margin-top:12px">' + spark(marks) + '</div>' + bars(marks) +
        (r.reasons.length ? '<div class="note" style="margin-top:14px"><div class="pen">' + esc(r.reasons.join(' ')) + '</div></div>' : '') +
        (tips ? '<h3 style="margin-top:14px">Suggested teaching focus</h3><ul class="tips">' + tips + '</ul>' : '') + '<p class="ai">' + esc(t('ai.note')) + '</p>' +
        '<h3 style="margin-top:16px">' + esc(t('comments.title')) + '</h3><div id="cmtList">' + commentsHtml(N.hub, o.l) + '</div>' +
        '<p style="margin-top:12px"><label for="commentInput">' + esc(t('comments.add')) + '</label></p><textarea id="commentInput" rows="3" maxlength="500" style="width:100%" placeholder="' + esc(t('comments.placeholder')) + '"></textarea><div class="err" id="cmtErr" role="alert"></div>' +
        '<div class="row"><button class="btn" data-act="addComment" data-l="' + o.l + '">' + esc(t('comments.add')) + '</button><button class="btn ghost" data-act="closeOverlay">Close</button></div></div>';
    }
    el.innerHTML = html;
    el.hidden = false;
    var f = el.querySelector('input, textarea, button');
    if (f) f.focus();
  }
  function openOverlay(o) { S.overlay = o; renderOverlay(); }
  function closeOverlay() {
    var o = S.overlay;
    S.overlay = null;
    renderOverlay();
    if (o && o.l && o.t) { var b = document.querySelector('[data-act][data-l="' + o.l + '"][data-t="' + o.t + '"]'); if (b) b.focus(); }
  }

  /* ---- guided demo --------------------------------------------------------------------- */
  function go(role) { S.role = role; try { window.scrollTo(0, 0); } catch (e) { /* not available in tests */ } }
  var TEACHER = D.PERSONAS.teacher.name;
  var DEMO = [
    { text: 'The school’s internet has gone down. Ms Dlamini can keep working, because the school hub runs on the school’s own network.', run: function () { go('teacher'); setNet(false); } },
    { text: 'She captures Sipho’s Statistics assignment. It saves on the hub and waits to upload (yellow dot).', run: function () { go('teacher'); N.hub.recordMark('L03', 'T6', 38, TEACHER); log('Ms Dlamini saved a mark on the school hub'); } },
    { text: 'Sipho’s parent opens Khapa on a phone. It shows what was last saved on the phone, and says so. The new mark is not there yet.', run: function () { S.learnerId = 'L03'; go('parent'); } },
    { text: 'The internet comes back. The hub uploads, the phone downloads, and the new mark and the updated projection appear.', run: function () { go('parent'); setNet(true); } },
    { text: 'Now two people change the same mark while apart. The teacher edits Trigonometry on the hub. The HOD edits it on a tablet away from the school network.', run: function () { setNet(false); N.hub.recordMark('L03', 'T4', 45, TEACHER); N.hubB.recordMark('L03', 'T4', 52, 'Mr HOD'); log('Hub and HOD tablet both changed Sipho’s Trigonometry mark'); go('teacher'); } },
    { text: 'The internet returns. Khapa keeps both values and flags the mark instead of overwriting either one. Tap the yellow mark to choose the final value.', run: function () { go('teacher'); setNet(true); } },
    { text: 'That is the demo. Explore any role, or restart to play it again.', run: function () { } }
  ];
  function startDemo() { resetWorld(); S.demo = { i: 0 }; DEMO[0].run(); render(); renderOverlay(); }
  function nextDemo() { if (!S.demo || S.demo.i >= DEMO.length - 1) return; S.demo.i += 1; DEMO[S.demo.i].run(); render(); }

  /* ---- actions ------------------------------------------------------------------------- */
  function saveMark() {
    var o = S.overlay;
    var raw = $('markInput').value;
    var v = raw === '' ? NaN : Number(raw);
    if (!isFinite(v) || v < 0 || v > 100) { $('markErr').textContent = 'Enter a mark between 0 and 100.'; return; }
    N.hub.recordMark(o.l, o.t, v, TEACHER);
    log('Ms Dlamini saved ' + fullName(o.l) + ', ' + task(o.t).topic + ': ' + num(v));
    toast(t('sync.saved'));
    closeOverlay();
    scheduleSync();
    render();
  }
  function chooseMark(v) {
    var o = S.overlay;
    N.hub.recordMark(o.l, o.t, Number(v), TEACHER);
    log('Ms Dlamini resolved ' + fullName(o.l) + ', ' + task(o.t).topic + ' at ' + num(Number(v)));
    toast('Final mark saved');
    closeOverlay();
    scheduleSync();
    render();
  }
  function addComment(l) {
    var ta = $('commentInput');
    var text = ta.value.trim();
    if (!text) { $('cmtErr').textContent = 'Write a comment first.'; return; }
    N.hub.addComment(l, TEACHER, 'teacher', text);
    log('Ms Dlamini commented on ' + fullName(l));
    toast(t('sync.saved'));
    $('cmtList').innerHTML = commentsHtml(N.hub, l);
    ta.value = '';
    scheduleSync();
    render();
  }

  function onClick(e) {
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var d = el.dataset;
    switch (d.act) {
      case 'setRole': go(d.role); render(); break;
      case 'toggleNet': setNet(!S.online); render(); break;
      case 'toggleDevices': S.devices = !S.devices; render(); break;
      case 'reset': resetWorld(); render(); renderOverlay(); break;
      case 'openMark': openOverlay({ type: 'mark', l: d.l, t: d.t }); break;
      case 'openResolve': openOverlay({ type: 'resolve', l: d.l, t: d.t }); break;
      case 'openLearner': openOverlay({ type: 'learner', l: d.l }); break;
      case 'closeOverlay': closeOverlay(); break;
      case 'saveMark': saveMark(); break;
      case 'chooseMark': chooseMark(d.v); break;
      case 'addComment': addComment(d.l); break;
      case 'startDemo': startDemo(); break;
      case 'demoNext': nextDemo(); break;
      case 'endDemo': S.demo = null; render(); break;
      case 'hodEdit':
        N.hubB.recordMark('L03', 'T4', 52, 'Mr HOD');
        log('HOD tablet changed Sipho’s Trigonometry mark to 52');
        toast('HOD tablet saved a mark');
        scheduleSync(); render(); break;
      default: break;
    }
  }
  function onChange(e) {
    var el = e.target.closest('[data-change]');
    if (!el) return;
    if (el.dataset.change === 'lang') { S.lang = el.value; render(); }
    if (el.dataset.change === 'viewAs') { S.learnerId = el.value; render(); }
  }
  function onKey(e) {
    if (e.key === 'Escape' && S.overlay) closeOverlay();
    if (e.key === 'Enter' && S.overlay && e.target && e.target.id === 'markInput') { e.preventDefault(); saveMark(); }
  }

  function start() {
    resetWorld();
    document.addEventListener('click', onClick);
    document.addEventListener('change', onChange);
    document.addEventListener('keydown', onKey);
    render();
  }
  window.KhapaApp = { start: start, _state: function () { return S; }, _nodes: function () { return N; }, _render: render };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
