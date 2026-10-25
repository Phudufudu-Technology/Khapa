/* Synthetic data and sample content. Every learner and teacher here is fictional. */
(function (root) {
  'use strict';

  var SCHOOL_ID = 'demo-school';
  var CLASS_LABEL = '11A';

  /* Assessments for Grade 11 Mathematics. Topics are a sample, to be aligned with CAPS by a curriculum specialist. */
  var TASKS = [
    { id: 'T1', term: 1, topic: 'Exponents and surds', kind: 'Test' },
    { id: 'T2', term: 1, topic: 'Equations and inequalities', kind: 'Test' },
    { id: 'T3', term: 1, topic: 'Functions and graphs', kind: 'Assignment' },
    { id: 'T4', term: 2, topic: 'Trigonometry', kind: 'Test' },
    { id: 'T5', term: 2, topic: 'Analytical geometry', kind: 'Test' },
    { id: 'T6', term: 2, topic: 'Statistics', kind: 'Assignment' }
  ];

  /* T1..T5 captured; T6 (Statistics) is left empty so the teacher can capture it live. */
  var LEARNERS = [
    { id: 'L01', first: 'Lerato', last: 'Dlamini', marks: [82, 78, 85, 80, 84] },
    { id: 'L02', first: 'Pieter', last: 'van Wyk', marks: [64, 58, 61, 57, 62] },
    { id: 'L03', first: 'Sipho', last: 'Mokoena', marks: [58, 61, 55, 34, 41] },
    { id: 'L04', first: 'Ayesha', last: 'Patel', marks: [74, 79, 71, 76, 80] },
    { id: 'L05', first: 'Naledi', last: 'Khumalo', marks: [45, 52, 60, 66, 68] },
    { id: 'L06', first: 'Kabelo', last: 'Molefe', marks: [52, 47, 44, 39, 36] },
    { id: 'L07', first: 'Zanele', last: 'Ndlovu', marks: [68, 72, 66, 70, 73] },
    { id: 'L08', first: 'Johan', last: 'Botha', marks: [59, 63, 57, 61, 55] },
    { id: 'L09', first: 'Nomsa', last: 'Zulu', marks: [71, 65, 69, 48, 62] },
    { id: 'L10', first: 'Tshepo', last: 'Sithole', marks: [49, 43, 51, 47, 45] },
    { id: 'L11', first: 'Fatima', last: 'Essop', marks: [77, 81, 74, 79, 83] },
    { id: 'L12', first: 'Bongani', last: 'Mahlangu', marks: [62, 55, 58, 52, 49] },
    { id: 'L13', first: 'Lindiwe', last: 'Maseko', marks: [56, 60, 63, 59, 64] },
    { id: 'L14', first: 'Mandla', last: 'Cele', marks: [66, 70, 62, 68, 71] }
  ];

  var PARENTS = {
    L03: 'Mr Mokoena', L05: 'Mrs Khumalo', L06: 'Ms Molefe', L01: 'Mrs Dlamini'
  };

  var SEED_COMMENTS = [
    { learner: 'L03', text: 'Sipho’s Term 1 work was solid. Trigonometry needs daily practice. Please check that he completes his corrections.' },
    { learner: 'L05', text: 'Naledi has improved every assessment this year. Well done, keep going.' },
    { learner: 'L06', text: 'Kabelo can do this work but has stopped finishing corrections. I would like to meet this week.' }
  ];

  var PERSONAS = {
    teacher: { name: 'Ms N. Dlamini', title: 'Mathematics teacher' },
    principal: { name: 'Mrs A. Naidoo', title: 'Principal' }
  };

  /* Sample school-wide averages, Grades 8-12 by learning area. Gr 11 Mathematics is replaced by live data. */
  var AREAS = ['Languages', 'Mathematics', 'Sciences', 'Humanities', 'Commerce'];
  var SCHOOL_MATRIX = [
    { grade: 8, values: [63, 52, 56, 61, 58] },
    { grade: 9, values: [60, 47, 53, 59, 55] },
    { grade: 10, values: [62, 50, 45, 58, 57] },
    { grade: 11, values: [64, null, 55, 60, 59] },
    { grade: 12, values: [66, 57, 54, 63, 61] }
  ];

  /* Study suggestions per topic. Written to be safe generic guidance, not curriculum claims. */
  var TIPS = {
    'Exponents and surds': {
      teacher: 'Reteach the exponent laws with worked examples, then set mixed practice.',
      parent: 'Ask them to explain each exponent law aloud, then check five practice sums together.',
      learner: 'Write the exponent laws on one page and do five mixed sums a day.'
    },
    'Equations and inequalities': {
      teacher: 'Revisit solving step by step. Check inequality sign changes on a number line.',
      parent: 'Ask them to solve one equation a day and check it by substituting the answer back.',
      learner: 'Check every answer by putting it back into the equation.'
    },
    'Functions and graphs': {
      teacher: 'Practise sketching from key points: intercepts, turning points and asymptotes.',
      parent: 'Ask them to sketch one graph from a table of values and describe its shape.',
      learner: 'Sketch from a table of values, then mark the intercepts.'
    },
    'Trigonometry': {
      teacher: 'Reteach the three ratios on right-angled triangles before special angles and identities.',
      parent: 'Ask them to label a triangle (opposite, adjacent, hypotenuse) and work out one ratio a day.',
      learner: 'Label the sides first, then choose sin, cos or tan.'
    },
    'Analytical geometry': {
      teacher: 'Practise distance, midpoint and gradient with coordinate sketches.',
      parent: 'Plot two points together and find the distance and gradient between them.',
      learner: 'Always sketch the points first, then apply the formula.'
    },
    'Statistics': {
      teacher: 'Practise reading data displays and calculating summary measures.',
      parent: 'Look at a graph in the news together and ask what it shows.',
      learner: 'Practise mean, median and quartiles on a small data set.'
    }
  };

  /* Sample pathway guidance (illustrative). Production loads dated, sourced datasets. */
  var PATHWAYS = [
    { name: 'Engineering and the built environment', needs: 'Mathematics and Physical Sciences are usually required.', topics: ['Trigonometry', 'Analytical geometry', 'Functions and graphs'] },
    { name: 'Data, software and IT', needs: 'Mathematics is a strong advantage. Check each institution’s requirements.', topics: ['Functions and graphs', 'Statistics', 'Equations and inequalities'] },
    { name: 'Business, accounting and finance', needs: 'Mathematics or Mathematical Literacy requirements vary by programme.', topics: ['Equations and inequalities', 'Statistics', 'Exponents and surds'] }
  ];

  /* Verified figures (docs/research-log.md R4, R5). */
  var MARKET = {
    unemployment: '33.6%', youthUnemployment: '47.4%', period: 'Q2 2026',
    mobile: '96.1%', fixedInternet: '17.4%', ghsYear: '2024'
  };

  var LANGS = [
    { code: 'en', name: 'English', status: 'source' },
    { code: 'af', name: 'Afrikaans', status: 'draft' },
    { code: 'zu', name: 'isiZulu', status: 'draft' },
    { code: 'xh', name: 'isiXhosa', status: 'pending' },
    { code: 'st', name: 'Sesotho', status: 'pending' },
    { code: 'tn', name: 'Setswana', status: 'pending' },
    { code: 'nso', name: 'Sepedi', status: 'pending' },
    { code: 'ts', name: 'Xitsonga', status: 'pending' },
    { code: 'ss', name: 'siSwati', status: 'pending' },
    { code: 've', name: 'Tshivenda', status: 'pending' },
    { code: 'nr', name: 'isiNdebele', status: 'pending' }
  ];

  var EN = {
    'brand.tagline': 'Every learner, every school, even offline.',
    'role.guide': 'Start here', 'role.teacher': 'Teacher', 'role.parent': 'Parent', 'role.learner': 'Learner', 'role.principal': 'Principal',
    'net.label': 'Internet', 'net.online': 'Online', 'net.offline': 'Offline',
    'sync.now': 'Sync now', 'sync.devices': 'Devices and sync', 'sync.up': '{n} waiting to upload', 'sync.down': '{n} waiting to download',
    'sync.saved': 'Saved on the school hub', 'sync.allSynced': 'Everything is synced',
    'lang.label': 'Language', 'lang.draft': 'Draft translation of the main labels, waiting for human review. Other text is in English.', 'lang.pending': 'Not translated yet. Showing English.',
    'reset': 'Reset demo',
    'marks.title': 'Marks', 'marks.hint': 'Tap a mark to capture or change it.', 'marks.empty': 'Not captured',
    'marks.conflict': '{n} values', 'marks.resolve': 'Resolve', 'marks.save': 'Save mark', 'marks.cancel': 'Cancel',
    'marks.projected': 'Projected year mark', 'marks.level': 'Level', 'marks.average': 'Average',
    'needs.title': 'Learners who need support', 'needs.none': 'No learners flagged.',
    'ai.note': 'These suggestions are generated automatically. Your teacher makes the final decision.',
    'comments.title': 'Teacher comments', 'comments.none': 'No comments yet.', 'comments.add': 'Add comment', 'comments.placeholder': 'Write a comment the parent and learner can read',
    'focus.title': 'Focus areas', 'focus.none': 'No weak areas right now. Keep it up.',
    'help.title': 'How you can help', 'trend.title': 'Progress over the year',
    'parent.stale': 'Showing what was last saved on this phone.', 'parent.waiting': '{n} new updates are waiting. Turn the internet on to load them.',
    'learner.hello': 'Hello, {name}', 'learner.marks': 'My marks', 'learner.next': 'Where to go next',
    'principal.title': 'School overview', 'principal.weak': 'Where the school is struggling', 'principal.live': 'Live from Khapa', 'principal.sample': 'Sample data',
    'principal.act': 'Suggested action: review results with the subject head and consider extra classes or peer tutoring.',
    'market.title': 'Job market today', 'links.title': 'Find funding and opportunities',
    'view.as': 'Viewing as', 'updated': 'Updated', 'topic': 'Topic', 'demo.next': 'Next step', 'demo.restart': 'Restart demo'
  };

  var AF = {
    'brand.tagline': 'Elke leerder, elke skool, selfs vanlyn.',
    'role.guide': 'Begin hier', 'role.teacher': 'Onderwyser', 'role.parent': 'Ouer', 'role.learner': 'Leerder', 'role.principal': 'Skoolhoof',
    'net.label': 'Internet', 'net.online': 'Aanlyn', 'net.offline': 'Vanlyn',
    'sync.now': 'Sinkroniseer nou', 'sync.devices': 'Toestelle en sinkronisering', 'sync.up': '{n} wag om op te laai', 'sync.down': '{n} wag om af te laai',
    'sync.saved': 'Gestoor op die skoolhub', 'sync.allSynced': 'Alles is gesinkroniseer',
    'lang.label': 'Taal',
    'reset': 'Herstel demonstrasie',
    'marks.title': 'Punte', 'marks.hint': 'Tik op ’n punt om dit in te voer of te verander.', 'marks.empty': 'Nog nie ingevoer nie',
    'marks.conflict': '{n} waardes', 'marks.resolve': 'Besleg', 'marks.save': 'Stoor punt', 'marks.cancel': 'Kanselleer',
    'marks.projected': 'Geprojekteerde jaarpunt', 'marks.level': 'Vlak', 'marks.average': 'Gemiddeld',
    'needs.title': 'Leerders wat ondersteuning nodig het', 'needs.none': 'Geen leerders gemerk nie.',
    'ai.note': 'Hierdie voorstelle word outomaties gegenereer. Jou onderwyser neem die finale besluit.',
    'comments.title': 'Onderwyserkommentaar', 'comments.none': 'Nog geen kommentaar nie.', 'comments.add': 'Voeg kommentaar by',
    'focus.title': 'Fokusareas', 'focus.none': 'Geen swak areas nou nie. Hou so aan.',
    'help.title': 'Hoe jy kan help', 'trend.title': 'Vordering deur die jaar',
    'learner.hello': 'Hallo, {name}', 'learner.marks': 'My punte',
    'principal.title': 'Skooloorsig', 'principal.live': 'Regstreeks vanaf Khapa', 'principal.sample': 'Voorbeelddata',
    'updated': 'Opgedateer', 'topic': 'Onderwerp'
  };

  var ZU = {
    'brand.tagline': 'Wonke umfundi, zonke izikole, ngisho ngaphandle kwe-inthanethi.',
    'role.guide': 'Qala lapha', 'role.teacher': 'Uthisha', 'role.parent': 'Umzali', 'role.learner': 'Umfundi', 'role.principal': 'Uthishanhloko',
    'net.label': 'I-inthanethi', 'net.online': 'Ku-inthanethi', 'net.offline': 'Ngaphandle kwe-inthanethi',
    'lang.label': 'Ulimi',
    'marks.title': 'Amamaka',
    'ai.note': 'Lezi zincomo zenziwa ngokuzenzakalelayo. Uthisha wakho unquma ekugcineni.',
    'comments.title': 'Amazwana othisha',
    'learner.hello': 'Sawubona, {name}'
  };

  var I18N = { en: EN, af: AF, zu: ZU };

  var api = {
    SCHOOL_ID: SCHOOL_ID, CLASS_LABEL: CLASS_LABEL, TASKS: TASKS, LEARNERS: LEARNERS, PARENTS: PARENTS,
    SEED_COMMENTS: SEED_COMMENTS, PERSONAS: PERSONAS, AREAS: AREAS, SCHOOL_MATRIX: SCHOOL_MATRIX,
    TIPS: TIPS, PATHWAYS: PATHWAYS, MARKET: MARKET, LANGS: LANGS, I18N: I18N
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.KhapaData = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
