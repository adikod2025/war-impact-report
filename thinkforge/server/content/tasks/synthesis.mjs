import { c } from '../rubrics.mjs';

export default [
  {
    id: 'syn-t1-scamper-bag',
    strand: 'synthesis', moves: ['scamper'], tier: 1, difficulty: -1.2,
    domain: 'design', register: [9, 12],
    title: 'SCAMPER the school bag',
    stimulus: 'A normal school bag: two straps, one big pocket, one small pocket, a zip, fabric.',
    prompt: 'Use **SCAMPER** — one idea per letter, at least five letters. Substitute, Combine, Adapt, Modify, Put to another use, Eliminate, Reverse. Label each idea with its letter.',
    mode: 'open_list',
    payload: {
      minIdeas: 5,
      lineFormat: 'LETTER: idea',
      commonIdeas: ['make it waterproof', 'add wheels', 'more pockets', 'make it bigger'],
      categories: [
        { id: 'S', name: 'Substitute', keywords: ['instead', 'replace', 'swap', 'material'] },
        { id: 'C', name: 'Combine', keywords: ['combine', 'also', 'built in', 'together', 'plus'] },
        { id: 'A', name: 'Adapt', keywords: ['adapt', 'like a', 'borrow', 'from'] },
        { id: 'M', name: 'Modify', keywords: ['bigger', 'smaller', 'shape', 'stretch', 'thinner'] },
        { id: 'P', name: 'Put to other use', keywords: ['use it as', 'becomes', 'doubles as', 'seat'] },
        { id: 'E', name: 'Eliminate', keywords: ['remove', 'without', 'no ', 'get rid'] },
        { id: 'R', name: 'Reverse', keywords: ['inside out', 'backwards', 'upside', 'opposite', 'other way'] },
      ],
      conceptVocabulary: ['strap', 'pocket', 'zip', 'fabric', 'weight', 'shoulder', 'wheels', 'seat'],
    },
    rubric: {
      criteria: [c('flexibility_categories', 0.4, { heuristic: { type: 'distinct', target: 5 } }), c('originality', 0.35), c('specificity', 0.25)],
      solo: {
        3: 'Five letters used, each producing a genuinely different kind of change.',
        4: 'Notices that Eliminate and Reverse produce the strangest ideas because they attack what the bag is *assumed* to need.',
      },
    },
    checks: { minWords: { response: 20 } },
    hints: [
      'Which letters have you skipped? The skipped ones are where the new ideas are.',
      'Try E (Eliminate) properly: a bag with **no straps**. Do not reject it — say what it becomes.',
      'Worked on a lunchbox: *E: no lid — it seals by folding. R: the lid is the plate. P: the box doubles as a cool pack.* Notice each one removes an assumption. Now do three more letters on the bag.',
    ],
    bridge: 'SCAMPER one object in your bedroom tonight.',
  },
  {
    id: 'syn-t1-analogy-beehive',
    strand: 'synthesis', moves: ['analogy_map'], tier: 1, difficulty: -0.9,
    domain: 'story', register: [9, 12],
    title: 'School and beehive',
    stimulus: 'People say a busy school is "like a beehive". Below are parts of a hive and parts of a school.',
    prompt: 'Match each hive part to the school part that plays the **same role** — the same job in the system, not the thing that looks similar.',
    mode: 'match',
    payload: {
      left: [
        { id: 'l1', text: 'Worker bees fetching nectar' },
        { id: 'l2', text: 'The honeycomb cells where stores are kept' },
        { id: 'l3', text: 'The waggle dance that tells others where food is' },
        { id: 'l4', text: 'The narrow entrance guarded by a few bees' },
      ],
      right: [
        { id: 'r1', text: 'Students collecting and bringing back what they learn' },
        { id: 'r2', text: 'The library and the shared drive' },
        { id: 'r3', text: 'Assembly and the notice board' },
        { id: 'r4', text: 'The one reception door with a sign-in desk' },
      ],
      answer: { l1: 'r1', l2: 'r2', l3: 'r3', l4: 'r4' },
    },
    checks: {},
    hints: [
      'For each hive part, say its **job** out loud first: "this one stores things", "this one tells everyone something".',
      'Do not match by what it looks like — match by what it *does for the whole system*.',
      'Worked: *the queen ↔ ?* Her job is not "being important", it is "the single source that keeps the colony going". In a school the closest match is not the head teacher\'s office — it is whatever the whole place would stop without. Now match the four.',
    ],
    bridge: 'Say what your family is "like", then check whether the roles really match.',
  },
  {
    id: 'syn-t2-hmw-frame',
    strand: 'synthesis', moves: ['hmw_frame'], tier: 2, difficulty: 0.15,
    domain: 'design', register: [11, 14],
    title: 'Turn a moan into a question',
    stimulus: 'Complaint overheard: "Year 7s never know where anything is and it is so annoying."',
    prompt: 'Turn it into a proper **How might we…** question. It needs a user, a need and an insight — and it must not smuggle a solution inside it. Then write one HMW that is too broad and one that is secretly a solution, and say what is wrong with each.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'hmw', label: 'Your How might we… question', required: true, minWords: 8 },
        { id: 'insight', label: 'The insight behind it (what is really going on for them?)', required: true, minWords: 12 },
        { id: 'toobroad', label: 'A version that is too broad + what is wrong with it', required: true, minWords: 12 },
        { id: 'solution', label: 'A version that hides a solution + what is wrong with it', required: true, minWords: 12 },
      ],
      commonIdeas: ['how might we make a map', 'how might we help year 7s find rooms'],
      conceptVocabulary: ['user', 'need', 'insight', 'lost', 'new', 'ask', 'embarrassed', 'first weeks', 'confidence'],
    },
    rubric: {
      criteria: [c('specificity', 0.25), c('originality', 0.25, { name: 'The insight is not obvious' }), c('completeness', 0.2), c('integration', 0.3, { name: 'Diagnoses both bad versions correctly' })],
      solo: {
        3: 'A HMW with all three ingredients, plus correct diagnosis of the broad and solution-shaped versions.',
        4: 'The insight reframes the problem — e.g. that the real barrier is not knowing *who to ask* without looking new — and the HMW follows from it.',
      },
    },
    checks: { requiredFields: ['hmw', 'insight', 'toobroad', 'solution'], capIfMissing: { insight: 0.6 } },
    hints: [
      'Does your HMW name *who* and *what they need*? "How might we improve navigation" names neither.',
      'The insight is the interesting part. Being lost is not the problem — what makes it hard to just ask someone?',
      'Worked: complaint *"the bins are always full"* → weak HMW *"how might we add more bins"* (a solution in disguise) → better *"how might we help people finishing lunch outside get rid of packaging in the ten seconds they are willing to spend?"* Notice the user, the need, and the ten-second insight. Now sharpen yours.',
    ],
    misconceptions: [
      { signal: 'HMW contains the solution', tutorMove: 'Ask how many different answers their question allows — if it is one, it is a solution.' },
    ],
    bridge: 'Turn the next complaint you hear into a HMW before you agree with it.',
  },
  {
    id: 'syn-t2-contradiction',
    strand: 'synthesis', moves: ['contradiction'], tier: 2, difficulty: 0.4,
    domain: 'design', register: [11, 14],
    title: 'We want both',
    stimulus: 'A water bottle for school. It must be big enough to last all day, and small enough to fit the side pocket of a bag. Bigger and smaller.',
    prompt: 'State the **contradiction** properly ("we want X and also not-X"), then resolve it without compromising — do not just pick a medium size. Say what physical trick lets both be true, and where else that trick is used.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'contradiction', label: 'The contradiction, stated as X and not-X', required: true, minWords: 8 },
        { id: 'resolution', label: 'How both can be true at once', required: true, minWords: 15 },
        { id: 'principle', label: 'The general trick behind your solution', required: true, minWords: 10 },
        { id: 'elsewhere', label: 'Somewhere else the same trick is used', required: true, minWords: 6 },
      ],
      commonIdeas: ['a medium sized bottle', 'take two bottles', 'refill it'],
      conceptVocabulary: ['collapse', 'fold', 'separate in time', 'expand', 'nest', 'refill', 'shape', 'flexible'],
    },
    rubric: {
      criteria: [c('contradiction_stated', 0.35), c('beyond_case', 0.25, { name: 'Names the general trick' }), c('originality', 0.2), c('bridge_targets', 0.2, { name: 'Transfers the trick' })],
      solo: {
        3: 'Contradiction correctly stated and resolved by separating the two demands (in time, in space, or by condition) rather than compromising.',
        4: 'Names the resolution principle in general terms — e.g. "separate the two requirements in time" — and finds it in an unrelated object.',
      },
    },
    checks: { requiredFields: ['contradiction', 'resolution', 'principle', 'elsewhere'], capIfMissing: { principle: 0.7 } },
    hints: [
      'A compromise makes both sides a bit unhappy. A resolution makes both true. Which have you written?',
      'Ask *when* it needs to be big and *when* it needs to be small. Are those the same moment?',
      'Worked: *a ladder must be tall (to reach) and short (to carry). Resolution: it is tall in use and short in transport — separate the requirements in time.* That is the trick, and it is the same one behind folding chairs and umbrellas. Now do the bottle.',
    ],
    misconceptions: [
      { signal: 'answer is a medium compromise', tutorMove: 'Ask whether both demands are actually satisfied, or just half-satisfied.' },
    ],
    bridge: 'Find an object at home that resolved a contradiction instead of compromising.',
  },
  {
    id: 'syn-t3-analogy-immune',
    strand: 'synthesis', moves: ['analogy_map'], tier: 3, difficulty: 1.05,
    domain: 'science', register: [13, 16],
    title: 'Where the analogy breaks',
    stimulus: 'A textbook says the immune system is "like an army defending a country": soldiers, patrols, memory of past invaders, occasional friendly fire.',
    prompt: 'Map the analogy properly: at least four **relationships** that carry across. Then find the place where it **breaks** — something true of armies that is badly wrong about immune systems, or the reverse — and say what a learner would get wrong because of it.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'mapping', label: 'Four mapped relationships (army ↔ immune system)', required: true, minWords: 30, multiline: true },
        { id: 'breaks', label: 'Where the analogy breaks', required: true, minWords: 20 },
        { id: 'cost', label: 'What would a learner get wrong because of it?', required: true, minWords: 15 },
      ],
      conceptVocabulary: ['memory', 'antibody', 'invader', 'recognise', 'autoimmune', 'command', 'central', 'chemical', 'threshold', 'tolerance', 'decision'],
    },
    rubric: {
      criteria: [c('structure_mapping', 0.4), c('rebuttal_real', 0.3, { name: 'The breakage is real and specific' }), c('beyond_case', 0.3)],
      solo: {
        3: 'Four genuine relational mappings and one specific place the analogy fails.',
        4: 'Explains that the failure comes from a structural difference — e.g. no central command, no intention, recognition by chemical fit rather than decision — and says what misconception it creates.',
      },
    },
    checks: { requiredFields: ['mapping', 'breaks', 'cost'], capIfMissing: { breaks: 0.55 } },
    hints: [
      'A mapping is a relationship, not a noun pair. "White blood cell = soldier" is a label; "cells that met an invader before respond faster the second time = veterans who recognise a tactic" is a relationship.',
      'Armies have a general. Does the immune system have anything that decides? What does the analogy make people believe about *intention*?',
      'Worked breakage on another analogy: *"the atom is like a solar system" carries orbit and central mass, but breaks on the fact that electrons have no definite path — learners then draw neat circles and believe them.* Notice the format: what carries, what breaks, what the learner gets wrong. Now finish yours.',
    ],
    misconceptions: [
      { signal: 'maps nouns instead of relations', tutorMove: 'Ask what each pair *does*, and match the doing.' },
    ],
    bridge: 'Take an analogy a teacher used this week and find where it breaks.',
  },
  {
    id: 'syn-t4-invention-brief',
    strand: 'synthesis', moves: ['contradiction', 'ideality', 'hmw_frame'], tier: 4, difficulty: 2.1,
    domain: 'design', register: [14, 16],
    title: 'The invention brief',
    stimulus: 'Brief: **school corridors between lessons.** 900 people move in five minutes, twice as many at some junctions, and the crush is worst exactly where the crush matters most — outside the two science labs.',
    prompt: 'Run the full chain: frame it as a HMW, state the contradiction, write the **ideal final result** (the job gets done with no cost, no machine, no supervision), then work back to the nearest thing that could actually be built by half term. Say what you gave up on the way back.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'hmw', label: 'How might we…', required: true, minWords: 10 },
        { id: 'contradiction', label: 'The contradiction', required: true, minWords: 12 },
        { id: 'ifr', label: 'Ideal final result', required: true, minWords: 15 },
        { id: 'buildable', label: 'Nearest buildable version', required: true, minWords: 25 },
        { id: 'gaveup', label: 'What you gave up between the ideal and the buildable', required: true, minWords: 15 },
      ],
      commonIdeas: ['one way system', 'stagger lesson ends', 'wider corridors', 'more supervision'],
      conceptVocabulary: ['flow', 'junction', 'stagger', 'one-way', 'timetable', 'room allocation', 'self-organising', 'signage', 'supervision'],
    },
    rubric: {
      criteria: [c('ifr_stated', 0.25), c('contradiction_stated', 0.25), c('integration', 0.25, { name: 'The buildable version descends from the ideal' }), c('specificity', 0.25)],
      solo: {
        3: 'A real contradiction, a genuine ideal (no supervision, no cost) and a buildable version that visibly comes from it.',
        4: 'The buildable version keeps the *mechanism* of the ideal — the crowd organising itself — rather than falling back to supervision, and the trade-off is named honestly.',
      },
    },
    checks: { requiredFields: ['hmw', 'contradiction', 'ifr', 'buildable', 'gaveup'], capIfMissing: { ifr: 0.6, gaveup: 0.8 } },
    hints: [
      'Check your IFR. If a person or a machine is doing the work in it, it is not ideal yet — it is just better.',
      'The ideal here is that the crowd never forms in the first place, with nobody managing it. What arrangement of *rooms and times* would do that by itself?',
      'Worked descent: *IFR — the queue never exists. Nearest buildable — move the two classes that create the junction into rooms on the same side, so the flow never crosses. Given up — some teachers lose their preferred room.* Notice the buildable version keeps the ideal\'s mechanism (no crossing flow) rather than adding staff. Now redo your descent.',
    ],
    misconceptions: [
      { signal: 'IFR includes staff or equipment', tutorMove: 'Ask them to remove the person from it and see what is left.' },
      { signal: 'buildable version is unrelated to the ideal', tutorMove: 'Ask which part of the ideal survives in their build.' },
    ],
    bridge: 'Write the ideal final result for a chore at home, then find its nearest buildable version.',
  },
];
