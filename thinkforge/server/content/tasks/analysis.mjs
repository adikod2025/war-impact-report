import { c } from '../rubrics.mjs';

export default [
  {
    id: 'ana-t1-umbrella-parts',
    strand: 'analysis', moves: ['part_whole'], tier: 1, difficulty: -1.3,
    domain: 'design', register: [9, 11],
    title: 'What every bit is for',
    stimulus: 'An umbrella has: a curved handle, a sliding runner you push up, thin metal ribs, a fabric canopy, and a little cap on the very top.',
    prompt: 'For at least four of those parts, write one line: **the part = the job it does for the whole umbrella**. Not what it looks like — what it is *for*.',
    mode: 'open_list',
    payload: {
      minIdeas: 4,
      lineFormat: 'part = its job',
      commonIdeas: ['handle = to hold it', 'canopy = to keep rain off', 'ribs = to hold the fabric'],
      conceptVocabulary: ['handle', 'runner', 'rib', 'canopy', 'cap', 'rain', 'wind', 'grip', 'fold', 'water'],
    },
    rubric: {
      criteria: [c('completeness', 0.3, { name: 'Four parts covered' }), c('specificity', 0.4), c('distinctness', 0.3, { heuristic: { type: 'distinct', target: 4 } })],
      solo: {
        3: 'Each part has a job, and at least one job is explained by how it helps another part do its job.',
        4: 'Notices a general rule about designed objects — e.g. that a part usually exists because something else would fail without it — and applies it to a different object.',
      },
    },
    checks: { minWords: { response: 12 } },
    hints: [
      'Pick one part and cover it up in your head. What goes wrong with the umbrella if it is missing?',
      'The little cap on top is the tricky one. Look at where all the ribs meet — what would happen there in heavy rain without it?',
      'Here is one done for a bike: *the chain = it carries the push from your legs to the back wheel.* Notice it says what travels and where to. Try yours in that shape.',
    ],
    misconceptions: [
      { signal: 'describes appearance instead of function', tutorMove: 'Ask what breaks if that part is removed.' },
      { signal: 'gives the same job for two parts', tutorMove: 'Ask which of the two would fail first without the other.' },
    ],
    bridge: 'Pick something in your kitchen with at least four parts. What is each part for?',
  },
  {
    id: 'ana-t1-icecream-whys',
    strand: 'analysis', moves: ['five_whys'], tier: 1, difficulty: -0.9,
    domain: 'everyday', register: [9, 11],
    title: 'The van that stopped coming',
    stimulus: 'The ice cream van used to come down Maple Street every Saturday. Since March it has stopped coming. The driver still works — people have seen the van two streets over on Saturdays.',
    prompt: 'Build a why-chain. Start with "the van stopped coming to Maple Street" and ask **why** of your own answer, four times. Each answer has to explain the one above it.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'why1', label: 'Why 1 — why did it stop coming here?', required: true, minWords: 4 },
        { id: 'why2', label: 'Why 2 — and why is that?', required: true, minWords: 4 },
        { id: 'why3', label: 'Why 3 — and why is that?', required: true, minWords: 4 },
        { id: 'why4', label: 'Why 4 — and why is that?', required: true, minWords: 4 },
        { id: 'root', label: 'Which one is the root cause, and how do you know it is not just another symptom?', required: true, minWords: 8 },
      ],
      conceptVocabulary: ['customers', 'money', 'road', 'parking', 'roadworks', 'school', 'time', 'route', 'sales', 'street', 'children'],
    },
    rubric: {
      criteria: [c('depth_chain', 0.45), c('root_vs_symptom', 0.35), c('specificity', 0.2)],
      solo: {
        3: 'Four links that each genuinely explain the one above, ending at something a person could actually change.',
        4: 'Notices that the chain could branch — more than one root feeds the same symptom — and says which branch matters most and why.',
      },
    },
    checks: { requiredFields: ['why1', 'why2', 'why3', 'why4', 'root'], capIfMissing: { why4: 0.55, root: 0.6 } },
    hints: [
      'Read your Why 1 out loud, then ask it like a small child would: "but *why* is that?"',
      'The clue you have not used yet is that the van is two streets over on the same day. What does that tell you about whether the *driver* changed or whether *Maple Street* changed?',
      'Worked example on a different case: *The plant died → because it got no water → because nobody watered it that week → because the person who usually does it was away → because there is no backup when one person is away.* The last line is the root: it is about the system, not about one week. Now finish yours the same way.',
    ],
    misconceptions: [
      { signal: 'each why restates the previous one', tutorMove: 'Show the two lines side by side and ask what new information the second one adds.' },
      { signal: 'root cause is a person being blamed', tutorMove: 'Ask what would have to be true for a different person to make the same mistake.' },
    ],
    bridge: 'Next time something at home is annoying, run four whys on it before you complain about it.',
  },
  {
    id: 'ana-t2-library-rivals',
    strand: 'analysis', moves: ['cause_vs_correlate'], tier: 2, difficulty: -0.2,
    domain: 'data', register: [11, 14],
    title: 'More books, better readers?',
    stimulus: 'A newspaper reports: "Schools with more library books have higher reading scores. Councils should buy more books." The graph is real: across 300 schools, more books really does go with higher scores.',
    prompt: 'The data is not in doubt. The *explanation* is. Which of these are rival explanations worth checking before believing the headline?',
    mode: 'multi_select',
    payload: {
      options: [
        { id: 'a', text: 'Schools with more money buy more books **and** can afford smaller classes and more teachers.', correct: true, why: 'A third factor feeding both — the classic confound.' },
        { id: 'b', text: 'Schools where children already read well order more books, because the books get used.', correct: true, why: 'The arrow may run backwards: scores cause books.' },
        { id: 'c', text: 'The graph is drawn in the wrong colours.', correct: false, why: 'Presentation, not explanation. It does not change what the numbers could mean.' },
        { id: 'd', text: 'Only 300 schools were looked at, so the pattern could be a fluke.', correct: false, why: 'Fair to ask in general, but 300 is a large sample — this is the weakest of the challenges here.' },
        { id: 'e', text: 'Families who choose book-heavy schools may read more at home anyway.', correct: true, why: 'Another third factor, sitting outside the school entirely.' },
      ],
      minSelect: 1,
    },
    checks: {},
    hints: [
      'For each option ask: if this were true, would the graph still look exactly the same?',
      'There are three ways a link between A and B can be real without A causing B: B causes A, something else causes both, or chance. Try to find one option for each.',
      'Take option (a). Money buys books. Money also buys teachers. Teachers raise scores. So books and scores rise together with no arrow between them at all — that is a third-factor explanation. Now check the others for that shape.',
    ],
    misconceptions: [
      { signal: 'selects only the reverse-causation option', tutorMove: 'Ask whether anything outside the school could be pushing both numbers up.' },
    ],
    bridge: 'Find one headline this week that says "X linked to Y" and name the third factor nobody mentioned.',
  },
  {
    id: 'ana-t2-trip-criteria',
    strand: 'analysis', moves: ['criteria'], tier: 2, difficulty: 0.1,
    domain: 'social', register: [11, 14],
    title: 'Decide what "best" means first',
    stimulus: 'Your year group votes on one trip: (1) a theme park, (2) a coastal wildlife reserve, (3) a city museum and river walk. The vote is next week and everyone is already arguing.',
    prompt: 'Do not pick a trip. Instead, write the **criteria** the choice should be judged on — before anyone knows which trip wins on them. Then rank your criteria by importance and say why the top one is top.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'criteria', label: 'Your criteria (at least four, one per line)', required: true, minWords: 8, multiline: true },
        { id: 'ranking', label: 'Rank them, most important first', required: true, minWords: 4 },
        { id: 'why_top', label: 'Why does the top one outrank the second?', required: true, minWords: 10 },
        { id: 'blind', label: 'Which criterion would people forget if you did not write it down?', required: true, minWords: 5 },
      ],
      commonIdeas: ['cost', 'fun', 'distance', 'safety'],
      conceptVocabulary: ['cost', 'time', 'access', 'wheelchair', 'learning', 'safety', 'weather', 'fair', 'everyone', 'travel'],
    },
    rubric: {
      criteria: [c('criteria_named', 0.35), c('originality', 0.25, { name: 'At least one criterion others would miss' }), c('specificity', 0.2), c('integration', 0.2, { name: 'Ranking is justified, not asserted' })],
      solo: {
        3: 'Four or more non-overlapping criteria, ranked, with a real reason for the top one.',
        4: 'Notices that the ranking itself depends on a value ("we care most about nobody being left out") and states that value openly.',
      },
    },
    checks: { requiredFields: ['criteria', 'ranking', 'why_top', 'blind'], capIfMissing: { blind: 0.7 } },
    hints: [
      'Imagine the trip is over and it went badly. What went wrong? That thing was a criterion.',
      'Cost, fun and distance are the three everyone writes. Who in your year would find one of these trips hardest to take part in — and what criterion does that give you?',
      'Worked shape from choosing a school lunch supplier: *criteria = price per meal, time to serve 400 people, options for allergies, food waste. Ranked: allergies first, because a trip that excludes someone fails no matter how cheap it is.* Notice the reason is about what failure means. Now write yours.',
    ],
    misconceptions: [
      { signal: 'names options instead of criteria', tutorMove: 'Ask what quality would make any trip good, not which trip is good.' },
      { signal: 'criteria overlap heavily (fun/enjoyable/exciting)', tutorMove: 'Ask whether a trip could score high on one and low on the other.' },
    ],
    bridge: 'Before your next argument about what to watch, write the criteria first and see if the argument changes.',
  },
  {
    id: 'ana-t3-periods-firstprinciples',
    strand: 'analysis', moves: ['first_principles'], tier: 3, difficulty: 0.9,
    domain: 'design', register: [13, 15],
    title: 'Why fifty minutes?',
    stimulus: 'Almost every secondary school runs lessons of about 50 minutes, five or six a day, with a bell. Nobody in your school can tell you who chose 50.',
    prompt: 'Take it back to first principles. Separate what is **actually known to be true** about learning and running a building from what is only **assumed because it has always been that way**. Then say what you would build if you only kept the knowns.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'knowns', label: 'Things we genuinely know (each with why you are confident)', required: true, minWords: 15, multiline: true },
        { id: 'assumptions', label: 'Things that are only assumed / inherited', required: true, minWords: 12, multiline: true },
        { id: 'rebuild', label: 'What would you build from the knowns alone?', required: true, minWords: 20 },
        { id: 'cost', label: 'What does your version make harder? Be honest.', required: true, minWords: 10 },
      ],
      conceptVocabulary: ['attention', 'teacher', 'timetable', 'room', 'transition', 'practice', 'bell', 'subject', 'staff', 'cost', 'concentration'],
    },
    rubric: {
      criteria: [c('completeness', 0.2), c('specificity', 0.2), c('integration', 0.3, { name: 'Rebuild follows from the knowns' }), c('beyond_case', 0.3)],
      solo: {
        3: 'Knowns and assumptions cleanly separated, and the rebuild is visibly derived from the knowns rather than from taste.',
        4: 'Notices that some "knowns" are only true because of the current design (a self-fulfilling constraint) and handles that.',
      },
    },
    checks: { requiredFields: ['knowns', 'assumptions', 'rebuild', 'cost'], capIfMissing: { cost: 0.75, assumptions: 0.6 } },
    hints: [
      'Take one line from your knowns list and ask: how would I check that? If you cannot answer, it belongs in assumptions.',
      '"Children can only concentrate for 50 minutes" — is that a fact about children, or a fact about a room where a bell rings every 50 minutes?',
      'A worked separation for supermarket opening hours: *Known — staff need rest, deliveries arrive at fixed times, some customers can only shop at night. Assumed — that the shop must be open in one continuous block. Rebuild — two shorter blocks around the delivery window.* Notice the rebuild only uses the knowns. Now do yours.',
    ],
    misconceptions: [
      { signal: 'lists preferences as knowns', tutorMove: 'Ask what evidence would settle that line, and whether they have it.' },
      { signal: 'rebuild is a wish list unconnected to the knowns', tutorMove: 'Ask which known forces each feature of the rebuild.' },
    ],
    bridge: 'Find one rule at home that exists only because it has always existed, and test it the same way.',
  },
  {
    id: 'ana-t4-attendance-decompose',
    strand: 'analysis', moves: ['part_whole', 'cause_vs_correlate'], tier: 4, difficulty: 1.8,
    domain: 'data', register: [14, 16],
    title: 'The eight percent',
    stimulus: 'Attendance at a school of 900 pupils fell from 94% to 86% over two years. The head teacher says "families stopped caring after the pandemic". The data available: attendance by year group, by day of the week, by distance from school, and by whether a pupil gets free school meals.',
    prompt: 'Decompose the 8-point fall into the parts it could be made of, say which parts the available data could actually separate, and give the one rival explanation that would most change what the school should do.',
    mode: 'open_short',
    payload: {
      maxWords: 200,
      answerKey: 'A strong answer splits the aggregate (which pupils, which days, chronic absence vs a spread of small absences), notes that an average can fall because a small group collapsed rather than everyone slipping, states which cuts the four data fields can and cannot distinguish, and offers a rival to "families stopped caring" that implies a different action (e.g. transport/distance, illness policy change, a small group of chronically absent pupils, or a change in how absence is recorded).',
      conceptVocabulary: ['average', 'chronic', 'group', 'distance', 'transport', 'meals', 'recording', 'illness', 'Monday', 'Friday', 'year group', 'small number'],
    },
    rubric: {
      criteria: [c('integration', 0.3, { name: 'Decomposes rather than describes' }), c('rival_explanations', 0.3), c('specificity', 0.2), c('beyond_case', 0.2)],
      solo: {
        3: 'Splits the fall into identifiable components and ties each to a data cut that could test it.',
        4: 'Generalises: an average moving does not tell you that everyone moved — states this as a principle and applies it elsewhere.',
      },
    },
    checks: { minWords: { response: 60 } },
    hints: [
      'An average can fall two very different ways. What are they, and would the head teacher\'s explanation fit both?',
      'Take the four data cuts one at a time and ask: which rival explanation does this cut kill, and which does it leave alive?',
      'Worked fragment on a different case: *Average delivery time rose 20 minutes. Either every driver got slower, or one route collapsed. Splitting by route separates those, and the fix is completely different in each case.* Now apply that split to attendance.',
    ],
    misconceptions: [
      { signal: 'accepts the aggregate as describing every pupil', tutorMove: 'Ask whether 8% could be produced by 5% of pupils, and what that would change.' },
      { signal: 'lists rivals without linking to available data', tutorMove: 'Ask which of the four data cuts would tell those rivals apart.' },
    ],
    bridge: 'Where else does someone quote you an average as if it described everybody?',
  },
];
