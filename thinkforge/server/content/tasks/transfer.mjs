/**
 * Second and third instantiations of the **core transfer moves**.
 *
 * docs/02 §3 rule 6: because far transfer is weak by default, a move the
 * platform claims to teach must be practised in at least three different
 * domains. These tasks exist to make that true for the eight core moves — one
 * per strand — rather than leaving transfer to hope. The rest of the bank's
 * moves are introduced, not claimed; `tests/content.test.mjs` prints that
 * coverage debt on every run.
 */
import { c } from '../rubrics.mjs';

export const CORE_TRANSFER_MOVES = [
  'five_whys',            // analysis
  'analogy_map',          // synthesis
  'pmi',                  // lateral
  'conditional',          // logic
  'toulmin',              // argument
  'work_backwards',       // reverse
  'causal_loop',          // systems
  'plan_monitor_evaluate', // metacognition
];

export default [
  {
    id: 'ana-t2-greenhouse-whys',
    strand: 'analysis', moves: ['five_whys'], tier: 2, difficulty: -0.15,
    domain: 'science', register: [11, 14],
    title: 'The greenhouse that kills seedlings',
    stimulus: 'The school greenhouse grows healthy seedlings in April and kills them in June. Same trays, same seeds, same compost, same watering rota. The June trays are on the same bench as the April ones.',
    prompt: 'Run a why-chain, four deep, on the June deaths. Then say which link you could test first, and how.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'why1', label: 'Why 1', required: true, minWords: 5 },
        { id: 'why2', label: 'Why 2', required: true, minWords: 5 },
        { id: 'why3', label: 'Why 3', required: true, minWords: 5 },
        { id: 'why4', label: 'Why 4', required: true, minWords: 5 },
        { id: 'test', label: 'The link you would test first, and how', required: true, minWords: 12 },
      ],
      conceptVocabulary: ['heat', 'sun', 'temperature', 'water', 'evaporate', 'roots', 'vents', 'shade', 'June', 'April', 'angle'],
    },
    rubric: {
      criteria: [c('depth_chain', 0.4), c('root_vs_symptom', 0.3), c('test_design', 0.3, { name: 'The test could actually settle it' })],
      solo: {
        3: 'Four links that each explain the one above, landing on something about the season rather than the plants.',
        4: 'Notices that "same everything" is the clue — what changed is outside the list of things being controlled — and states that as a general investigative principle.',
      },
    },
    checks: { requiredFields: ['why1', 'why2', 'why3', 'why4', 'test'], capIfMissing: { test: 0.7, why4: 0.6 } },
    hints: [
      'Everything in the list stayed the same between April and June. So the cause is not in the list. What is not in the list?',
      'A greenhouse in June is doing something to the air that it was not doing in April. What, and what does that do to a seedling in a shallow tray?',
      'A worked chain on a different case: *the bread goes mouldy faster in August → the kitchen is warmer → the window faces west → the afternoon sun heats that wall → nobody thought about which wall the bread bin was on.* The chain leaves the object and ends up at the room. Do the same here.',
    ],
    misconceptions: [{ signal: 'blames the seeds or the compost', tutorMove: 'Ask what the stimulus already ruled out, and what that leaves.' }],
    bridge: 'Next time something works sometimes, list what stayed the same — the cause is in what did not.',
  },
  {
    id: 'ana-t3-club-whys',
    strand: 'analysis', moves: ['five_whys', 'cause_vs_correlate'], tier: 3, difficulty: 0.75,
    domain: 'social', register: [13, 16],
    title: 'The club that emptied',
    stimulus: 'Debate club went from 22 members to 5 across one term. The teacher who runs it changed in September. So did the room, the day, and the year groups allowed to attend. Two members say "it just got boring".',
    prompt: 'Build a why-chain, then do something harder: say which of the four changes your chain actually depends on, and what evidence would tell the real cause apart from the ones that merely happened at the same time.',
    mode: 'open_short',
    payload: {
      maxWords: 200,
      answerKey: 'Four things changed at once, so no single explanation is identifiable from the drop alone — this is a confounded natural experiment. A good answer builds a chain (fewer members → the people who left were the ones who used to bring friends → the day now clashes with something → the clash is what removed them), then names which change its chain depends on and gives a discriminating check: attendance split by year group (tests the eligibility change), whether leavers had a clash on the new day (tests the day), whether the drop is gradual or a cliff at the switch date, and asking leavers directly rather than asking the two who stayed.',
      conceptVocabulary: ['room', 'day', 'clash', 'teacher', 'year group', 'confounded', 'leavers', 'gradual', 'cliff', 'timing'],
    },
    rubric: {
      criteria: [c('depth_chain', 0.3), c('rival_explanations', 0.3), c('test_design', 0.25), c('beyond_case', 0.15)],
      solo: {
        3: 'A real chain plus at least two rivals, with a check that separates them.',
        4: 'Names the general problem — four things changed at once, so nothing is identifiable — and says what should have been done at the time.',
      },
    },
    checks: { minWords: { response: 60 } },
    hints: [
      '"It got boring" is a report, not a cause. What would have had to change to make it boring?',
      'Four things changed at once. Pick one and ask: if only that had changed, would the drop look the same? Now find the check that tells them apart.',
      'Worked: *a shop’s sales fell when it repainted, moved its door and raised prices in the same week. Sales by hour would separate the door from the price: a door problem hits all hours evenly, a price problem hits the cheapest lines hardest.* Find the equivalent split here.',
    ],
    misconceptions: [{ signal: 'settles on one cause with no discriminating evidence', tutorMove: 'Ask what they would expect to see if a different one of the four changes were responsible.' }],
    bridge: 'When several things change at once, ask what evidence would separate them — before you pick a story.',
  },
  {
    id: 'lat-t2-pmi-solar',
    strand: 'lateral', moves: ['pmi'], tier: 2, difficulty: -0.3,
    domain: 'science', register: [11, 14],
    title: 'PMI: solar panels on every roof',
    stimulus: 'A council decides every school roof in the town gets covered in solar panels this year, paid for by a loan repaid out of the electricity saved.',
    prompt: 'Run a PMI. The Interesting column has to contain something a scientist would want to measure.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'plus', label: 'P — pluses (at least 3)', required: true, minWords: 8, multiline: true },
        { id: 'minus', label: 'M — minuses (at least 3)', required: true, minWords: 8, multiline: true },
        { id: 'interesting', label: 'I — interesting, including one thing worth measuring', required: true, minWords: 10, multiline: true },
      ],
      commonIdeas: ['good for the environment', 'saves money', 'expensive to install', 'looks ugly'],
      conceptVocabulary: ['energy', 'roof', 'angle', 'cloud', 'summer', 'holiday', 'grid', 'maintenance', 'measure', 'output', 'loan'],
    },
    rubric: {
      criteria: [c('completeness', 0.25), c('distinctness', 0.25, { heuristic: { type: 'distinct', target: 5 } }), c('originality', 0.3), c('specificity', 0.2)],
      solo: {
        3: 'Three real columns, with an Interesting entry naming something measurable.',
        4: 'Spots the timing problem — schools use least electricity exactly when the sun is strongest — and treats it as a question rather than an objection.',
      },
    },
    checks: { requiredFields: ['plus', 'minus', 'interesting'], capIfMissing: { interesting: 0.5 } },
    hints: [
      'When is a school empty? When is the sun strongest? Is that a plus, a minus, or an interesting?',
      'Something measurable means a number you could actually collect: kilowatt-hours by month, output on cloudy days, how much is used on site versus sold back.',
      'A worked Interesting for wind turbines: *I wonder how much of the output arrives at night, when nobody needs it — that is measurable, and it decides whether storage matters more than more turbines.* Write one like that.',
    ],
    bridge: 'Run a PMI on the next "obviously good idea" you hear about the environment.',
  },
  {
    id: 'lat-t3-pmi-scoreboard',
    strand: 'lateral', moves: ['pmi', 'opv'], tier: 3, difficulty: 0.85,
    domain: 'data', register: [13, 16],
    title: 'PMI: every class average on a public board',
    stimulus: 'A school proposes putting each class’s average test score on a screen in reception, updated every half term.',
    prompt: 'PMI it. Then add the move that PMI on its own misses: for the strongest Minus, name whose Minus it is, and say whether the same thing is a Plus for someone else.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'plus', label: 'P', required: true, minWords: 10, multiline: true },
        { id: 'minus', label: 'M', required: true, minWords: 10, multiline: true },
        { id: 'interesting', label: 'I', required: true, minWords: 10, multiline: true },
        { id: 'whose', label: 'The strongest Minus — whose is it, and who does it benefit?', required: true, minWords: 15 },
      ],
      commonIdeas: ['motivates people', 'embarrassing for some classes', 'competition is good', 'unfair on lower sets'],
      conceptVocabulary: ['average', 'class', 'teacher', 'parent', 'set', 'compare', 'gaming', 'teach to the test', 'pressure', 'small class'],
    },
    rubric: {
      criteria: [c('distinctness', 0.2, { heuristic: { type: 'distinct', target: 6 } }), c('originality', 0.25), c('stakeholder_fairness', 0.3), c('second_order_chain', 0.25)],
      solo: {
        3: 'Three columns plus a Minus correctly attributed to a specific group, with a matching Plus for another group.',
        4: 'Notices that publishing a number changes the behaviour that produces the number, and names the specific behaviour that would shift.',
      },
    },
    checks: { requiredFields: ['plus', 'minus', 'interesting', 'whose'], capIfMissing: { whose: 0.65 } },
    hints: [
      'An average of a class of 12 moves much more than an average of a class of 32. Which column does that belong in?',
      'Ask what a teacher would rationally start doing differently once the number is on a screen in reception. Then ask whether that is good.',
      'Worked shape from hospital waiting-time boards: *published times fell, and the way they fell was that patients were held in ambulances outside, because the clock started at the door. Plus for the manager, minus for the patient, and the number stopped meaning what it used to mean.* Now find the school version.',
    ],
    misconceptions: [{ signal: 'treats the number as unaffected by publishing it', tutorMove: 'Ask what people do differently once a number is watched.' }],
    bridge: 'When a number gets published, ask what people will do to it.',
  },
  {
    id: 'syn-t2-analogy-appstore',
    strand: 'synthesis', moves: ['analogy_map'], tier: 2, difficulty: 0.2,
    domain: 'design', register: [11, 14],
    title: 'A library and an app store',
    stimulus: 'Someone says a library is "the app store of books".',
    prompt: 'Test the analogy properly. Map **three relationships** that really carry across, then name one that does not — and say what a librarian would lose if the library were redesigned as if the analogy were completely true.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'mapping', label: 'Three relationships that carry across', required: true, minWords: 25, multiline: true },
        { id: 'breaks', label: 'One that does not', required: true, minWords: 15 },
        { id: 'cost', label: 'What would be lost if you redesigned the library on this analogy?', required: true, minWords: 15 },
      ],
      conceptVocabulary: ['browse', 'recommend', 'ranking', 'popular', 'free', 'return', 'shelf', 'discovery', 'curate', 'copy', 'scarce'],
    },
    rubric: {
      criteria: [c('structure_mapping', 0.4), c('rebuttal_real', 0.3, { name: 'The breakage is specific' }), c('beyond_case', 0.3)],
      solo: {
        3: 'Three genuine relational mappings and one clear break.',
        4: 'Identifies the structural difference — a book is a scarce physical copy that must come back, an app is copied at no cost — and follows it through to a design consequence.',
      },
    },
    checks: { requiredFields: ['mapping', 'breaks', 'cost'], capIfMissing: { breaks: 0.6 } },
    hints: [
      'A mapping is a relationship, not a pair of nouns. "Shelves = categories" is a label; "things nobody borrows lose shelf space, like apps that fall out of the charts" is a relationship.',
      'What happens when two people want the same thing at the same time — in a library, and in an app store? That difference is the break.',
      'Worked break on another analogy: *"a school is a factory" carries throughput and standardisation, and breaks on the fact that the raw material has opinions and can refuse.* Now write yours that sharply.',
    ],
    bridge: 'Next time someone says "X is basically Y", find the relationship that does not carry.',
  },
  {
    id: 'log-t3-conditional-lab',
    strand: 'logic', moves: ['conditional', 'falsification'], tier: 3, difficulty: 0.7,
    domain: 'science', register: [13, 16],
    title: 'The rule about the green flame',
    stimulus: 'A lab handbook says: **if a sample contains copper, the flame turns green.** In four tests: sample A burned green; sample B did not burn green; sample C is known to contain copper; sample D is known to contain no copper.',
    prompt: 'For each of the four, say exactly what the rule lets you conclude — and, where it lets you conclude nothing, say why. Then say which single test could show the handbook rule is wrong.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'a', label: 'A — burned green', required: true, minWords: 8 },
        { id: 'b', label: 'B — did not burn green', required: true, minWords: 8 },
        { id: 'c', label: 'C — contains copper', required: true, minWords: 8 },
        { id: 'd', label: 'D — contains no copper', required: true, minWords: 8 },
        { id: 'falsify', label: 'The test that could break the rule', required: true, minWords: 12 },
      ],
      answerKey: 'A (green) tells you nothing — other things burn green, so this is affirming the consequent. B (not green) tells you there is no copper — denying the consequent, which is valid. C (copper) tells you it will burn green — affirming the antecedent, valid. D (no copper) tells you nothing — the rule says nothing about non-copper samples. The falsifying test: a sample known to contain copper that does not burn green.',
      conceptVocabulary: ['copper', 'green', 'conclude', 'nothing', 'valid', 'antecedent', 'consequent', 'falsify', 'contains'],
    },
    rubric: {
      criteria: [c('completeness', 0.2), c('integration', 0.4, { name: 'Directions of the conditional handled correctly' }), c('rival_explanations', 0.2, { name: 'Says why the empty cases are empty' }), c('beyond_case', 0.2)],
      solo: {
        3: 'All four correct, with the two "nothing follows" cases explained rather than asserted.',
        4: 'States the general shape — a conditional licenses two inferences and forbids two — and identifies the falsifying case from the shape rather than from the chemistry.',
      },
    },
    checks: { requiredFields: ['a', 'b', 'c', 'd', 'falsify'], capIfMissing: { falsify: 0.7 } },
    hints: [
      'Two of these four tell you something. Two tell you nothing at all. Which two do you keep wanting to over-read?',
      'Write the rule as an arrow: copper → green. You may travel along the arrow, and you may travel backwards from a *missing* end. Nothing else is allowed.',
      'Same shape, different content: *if it is a dog, it is a mammal. This is a mammal → nothing follows. This is not a mammal → it is not a dog.* Map your four cases onto those.',
    ],
    misconceptions: [{ signal: 'concludes copper from a green flame', tutorMove: 'Ask whether anything else could turn a flame green, and whether the rule says otherwise.' }],
    bridge: 'Find a rule in a set of instructions and work out which way you are allowed to read it.',
  },
  {
    id: 'arg-t3-toulmin-experiment',
    strand: 'argument', moves: ['toulmin', 'warrant_audit'], tier: 3, difficulty: 0.8,
    domain: 'science', register: [13, 16],
    title: 'The warrant behind the experiment',
    stimulus: 'A group reports: "Plants grown under blue light grew 3 cm taller on average than plants under white light in our 10-day experiment (6 plants each). Blue light makes plants grow faster."',
    prompt: 'Audit the argument. State the claim, the evidence, and the **warrant they have not written down**. Then say whether the warrant survives, and rewrite the claim so it matches what the evidence actually supports.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'claim', label: 'Their claim', required: true, minWords: 5 },
        { id: 'evidence', label: 'Their evidence', required: true, minWords: 8 },
        { id: 'warrant', label: 'The unstated warrant', required: true, minWords: 12 },
        { id: 'audit', label: 'Does the warrant hold? What would break it?', required: true, minWords: 15 },
        { id: 'rewrite', label: 'The claim rewritten to fit the evidence', required: true, minWords: 10 },
      ],
      answerKey: 'The unstated warrant is roughly: "a height difference between two small groups over ten days is caused by the light colour and would hold generally." It has several weak points: six plants per group is small enough for chance to produce 3 cm; taller is not the same as healthier or faster-growing (plants stretch toward poor light); ten days is short; nothing says the two groups were otherwise identical. A fitting rewrite: "In our ten-day trial, six plants under blue light were on average 3 cm taller than six under white light — which may reflect stretching rather than growth, and needs a larger, longer trial to interpret."',
      conceptVocabulary: ['average', 'six', 'chance', 'stretch', 'taller', 'ten days', 'sample', 'control', 'warrant', 'generally'],
    },
    rubric: {
      criteria: [c('warrant', 0.3), c('qualifier_fit', 0.25), c('rival_explanations', 0.25), c('evidence_fit', 0.2)],
      solo: {
        3: 'Warrant stated as a general rule and audited against at least two specific weaknesses; the rewrite is genuinely narrower.',
        4: 'Separates two different failures — the sample is too small to trust, and "taller" may not mean what the claim needs it to mean — and says which matters more.',
      },
    },
    checks: { requiredFields: ['claim', 'evidence', 'warrant', 'audit', 'rewrite'], capIfMissing: { warrant: 0.5, rewrite: 0.75 } },
    hints: [
      'The jump is from "these six were taller" to "blue light makes plants grow faster". What rule would have to be true for that jump to be legal?',
      'Two separate problems live in that jump: how many plants, and whether "taller" means "grew faster". Handle them separately.',
      'Worked audit of a different claim: *"our class did better after we started the quiz, so quizzes work" — warrant: a before-and-after difference in one class is caused by the change. It breaks because the class also got older, had a different topic, and knew it was being watched.* Now audit the plants.',
    ],
    misconceptions: [{ signal: 'rewrite is as strong as the original', tutorMove: 'Ask which word in their rewrite the six plants cannot pay for.' }],
    bridge: 'Take a science claim from a lesson and say the warrant out loud.',
  },
  {
    id: 'met-t2-plan-investigation',
    strand: 'metacog', moves: ['plan_monitor_evaluate', 'strategy_select'], tier: 2, difficulty: 0.05,
    domain: 'data', register: [11, 14],
    title: 'Plan before you dig',
    stimulus: 'You are given a spreadsheet: every lunch item sold in your school for a term, with the day, the price and how many were sold. The question is "what should the canteen stop making?"',
    prompt: 'Do not answer the question. Write the **plan**: which move you will use first and why this question has that shape, what you will look at first, and the signal that would tell you your plan is not working.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'move', label: 'The move you will start with, and why this question has that shape', required: true, minWords: 15 },
        { id: 'first', label: 'The first thing you will actually look at', required: true, minWords: 10 },
        { id: 'signal', label: 'The signal that your plan is not working', required: true, minWords: 12 },
        { id: 'done', label: 'How you will know the answer is good enough to hand over', required: true, minWords: 10 },
      ],
      commonIdeas: ['look at what sells least', 'sort the list', 'ask people'],
      conceptVocabulary: ['criteria', 'least', 'profit', 'waste', 'day', 'price', 'sold', 'sort', 'average', 'compare'],
    },
    rubric: {
      criteria: [c('strategy_fit', 0.3), c('plan_quality', 0.3), c('specificity', 0.2), c('error_classification', 0.2, { name: 'The failure signal is noticeable at the time' })],
      solo: {
        3: 'A named move with a reason about the shape of the problem, a concrete first look, and a signal you could actually notice mid-task.',
        4: 'Notices that "should stop making" needs criteria defined before any sorting — least sold is not the same as least worth making — and puts that first.',
      },
    },
    checks: { requiredFields: ['move', 'first', 'signal', 'done'], capIfMissing: { signal: 0.6 } },
    hints: [
      'Before you sort anything: what makes an item worth stopping? Cheapest? Least sold? Most wasted? That question has a move of its own.',
      '"Least sold" and "least worth making" are different lists. Which does the canteen actually care about, and what would you need to tell them apart?',
      'A worked plan for a different dataset: *Move — criteria first, because the question hides a value judgement. First look — total sold and price per item, to see whether cheap-and-popular is subsidising the rest. Signal — if I am still adding columns after ten minutes I have started exploring instead of answering.* Now write yours.',
    ],
    misconceptions: [{ signal: 'starts analysing instead of planning', tutorMove: 'Ask them to write the plan in three lines before touching the data.' }],
    bridge: 'Before your next piece of research, write the move, the first look and the failure signal.',
  },
];
