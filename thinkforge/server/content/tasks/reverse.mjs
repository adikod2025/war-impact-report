import { c } from '../rubrics.mjs';

export default [
  {
    id: 'rev-t1-workbackwards-bus',
    strand: 'reverse', moves: ['work_backwards'], tier: 1, difficulty: -1.3,
    domain: 'everyday', register: [9, 11],
    title: 'Start at the end',
    stimulus: 'Goal: **you are sitting on the 8:05 bus with your PE kit.** Here are the things that had to happen, jumbled up.',
    prompt: 'Put them in order **working backwards from the goal** — last thing first. The point is to start at the end and ask "what had to happen just before this?"',
    mode: 'order',
    payload: {
      items: [
        { id: 'a', text: 'You are on the 8:05 bus with your PE kit.' },
        { id: 'b', text: 'You reach the bus stop by 8:03.' },
        { id: 'c', text: 'You leave the house by 7:55.' },
        { id: 'd', text: 'Your PE kit is by the door.' },
        { id: 'e', text: 'You put the kit by the door the night before.' },
        { id: 'f', text: 'You checked which day PE is on.' },
      ],
      answer: ['a', 'b', 'c', 'd', 'e', 'f'],
      direction: 'backwards',
    },
    checks: {},
    hints: [
      'Do not start at "wake up". Start at the goal and ask: what happened one step before that?',
      'You are at the stop by 8:03. What had to happen before *that*? Keep going one step at a time.',
      'Worked backwards for "the cake is on the table": *cake on table ← cake out of the tin ← cake baked ← oven was already hot ← you turned the oven on before mixing.* Notice the last step is the earliest and the least obvious. Now finish the bus chain.',
    ],
    bridge: 'Plan tomorrow morning backwards from the moment you need to be somewhere.',
  },
  {
    id: 'rev-t1-blackbox-chime',
    strand: 'reverse', moves: ['blackbox', 'cvs'], tier: 1, difficulty: -0.7,
    domain: 'science', register: [9, 12],
    title: 'The chime box',
    stimulus: 'A sealed box has a number dial (1-20) and a colour switch (red / blue). Sometimes it chimes. Nobody knows the rule.',
    prompt: 'Test the box until you can predict it. Then write the rule in one sentence. **Change one thing at a time** — that is the whole trick.',
    mode: 'probe',
    payload: {
      machine: {
        label: 'Chime box',
        inputs: [
          { id: 'number', label: 'Number dial', type: 'number', min: 1, max: 20 },
          { id: 'colour', label: 'Colour switch', type: 'enum', options: ['red', 'blue'] },
        ],
        outputText: { true: 'CHIME', false: 'silent' },
        rule: { op: 'and', terms: [{ fn: 'parity', var: 'number', cmp: '==', val: 'even' }] },
        canonicalForms: ['it chimes when the number is even', 'even numbers chime', 'chimes on even, colour does not matter'],
        minTests: 3, maxUseful: 8,
      },
      conceptVocabulary: ['even', 'odd', 'number', 'colour', 'matter', 'always', 'never'],
    },
    rubric: {
      criteria: [c('rule_generality', 0.5), c('test_design', 0.3), c('specificity', 0.2)],
      solo: {
        3: 'States the rule correctly and mentions that the colour makes no difference.',
        4: 'Says how they know colour is irrelevant — because they held the number fixed and switched only the colour.',
      },
    },
    checks: { minWords: { rule: 4 } },
    hints: [
      'Run two tests that are almost the same, changing only one thing. What did that one change do?',
      'Try 4-red and then 5-red. Then try 4-red and 4-blue. Those two pairs answer two different questions.',
      'Worked on a different box: *3-red silent, 4-red chime → the number matters. 4-red chime, 4-blue chime → the colour does not.* Two pairs, two answers. Now do that here and write the rule.',
    ],
    misconceptions: [
      { signal: 'changes both inputs between tests', tutorMove: 'Ask which of the two changes caused the difference — and whether their tests can tell.' },
      { signal: 'rule describes the tests instead of a rule', tutorMove: 'Ask what the box would do on a number they never tried.' },
    ],
    bridge: 'Next time something works sometimes, change one thing only and see what happens.',
  },
  {
    id: 'rev-t2-blackbox-gate',
    strand: 'reverse', moves: ['blackbox', 'cvs', 'disconfirm'], tier: 2, difficulty: 0.35,
    domain: 'science', register: [11, 14],
    title: 'The gate that needs two things',
    stimulus: 'A locked gate has a weight pad (0-10 kg), a key switch (in / out) and a light sensor (day / night). It opens on some combinations and not others.',
    prompt: 'Find the rule. You have limited tests, so make them count — and at some point run a test whose result would prove **your own current guess wrong**.',
    mode: 'probe',
    payload: {
      machine: {
        label: 'Gate',
        inputs: [
          { id: 'weight', label: 'Weight on pad (kg)', type: 'number', min: 0, max: 10 },
          { id: 'key', label: 'Key switch', type: 'enum', options: ['in', 'out'] },
          { id: 'light', label: 'Light sensor', type: 'enum', options: ['day', 'night'] },
        ],
        outputText: { true: 'OPEN', false: 'locked' },
        rule: {
          op: 'and',
          terms: [
            { var: 'weight', cmp: '>=', val: 3 },
            { op: 'or', terms: [{ var: 'key', cmp: '==', val: 'in' }, { var: 'light', cmp: '==', val: 'day' }] },
          ],
        },
        canonicalForms: [
          'weight at least 3 and (key in or daytime)',
          'needs 3kg or more, plus either the key or daylight',
        ],
        minTests: 4, maxUseful: 10,
      },
      conceptVocabulary: ['weight', 'key', 'light', 'and', 'or', 'both', 'either', 'threshold', 'at least'],
    },
    rubric: {
      criteria: [c('rule_generality', 0.4), c('test_design', 0.35), c('integration', 0.25, { name: 'Handles the "and/or" structure' })],
      solo: {
        3: 'Rule captures both the weight threshold and the either/or condition.',
        4: 'Explains which test settled the "or" — i.e. shows the reasoning that separated "needs both" from "needs either".',
      },
    },
    checks: { minWords: { rule: 8 } },
    hints: [
      'Hold two inputs still and sweep the third. What is the smallest weight that ever opens it?',
      'Once you have the weight threshold, the question is whether the key and the light are both needed, or just one of them. There is a single test that separates those two possibilities — find it.',
      'Worked reasoning: *if "both needed" were true, then key-out + day would stay locked. Test it. It opened. So it is "either", not "both".* That is a disconfirming test — it was designed to kill a hypothesis. Now run yours.',
    ],
    misconceptions: [
      { signal: 'stops after finding one working combination', tutorMove: 'Ask what other combination their rule predicts will open it — then have them test that prediction.' },
      { signal: 'assumes all three inputs must be right', tutorMove: 'Ask them to design a test that would prove that assumption wrong.' },
    ],
    bridge: 'When something works, predict one *other* case it should work in and check.',
  },
  {
    id: 'rev-t2-intent-trolley',
    strand: 'reverse', moves: ['design_intent'], tier: 2, difficulty: 0.15,
    domain: 'design', register: [11, 14],
    title: 'Why the trolley wants a coin',
    stimulus: 'Supermarket trolleys have a slot that takes a £1 coin, releasing the chain from the trolley in front. You get the coin back when you return it.',
    prompt: 'Reverse-engineer the design. What problem was this built to solve, and what could the designer **not afford** to do instead? Use details of the mechanism itself as your evidence.',
    mode: 'open_short',
    payload: {
      maxWords: 150,
      answerKey: 'Problem: trolleys get abandoned across the car park and beyond — collecting them costs staff time and lost trolleys cost money. Constraint: the shop cannot charge for trolleys (customers would object), cannot employ someone to police them, and cannot rely on goodwill. The coin is not a payment — it is a returnable deposit, which is why the amount matters less than the fact that it comes back. Evidence from the mechanism: the coin is refunded (so it is not revenue), the chain links trolley to trolley (so returning it must be to a bay, not anywhere), and it is self-enforcing (no staff needed).',
      conceptVocabulary: ['deposit', 'refund', 'abandon', 'staff', 'cost', 'incentive', 'return', 'chain', 'bay', 'enforce'],
    },
    rubric: {
      criteria: [c('intent_reconstruction', 0.45), c('specificity', 0.3, { name: 'Uses the mechanism as evidence' }), c('beyond_case', 0.25)],
      solo: {
        3: 'Names the problem and the constraint, and points at a specific feature of the mechanism as evidence.',
        4: 'Generalises: notices this is a *deposit*, a general design pattern for getting things returned, and names another place it is used.',
      },
    },
    checks: { minWords: { response: 40 } },
    hints: [
      'The coin comes back. So the shop earns nothing from it. What is the coin *for*, if not money?',
      'Ask what the alternatives were: pay staff to collect trolleys, trust people, or charge for use. What was wrong with each — and what does that tell you about the constraint?',
      'Worked example on a different object: *hotel key cards that switch off the room lights when removed. Problem: guests leave lights on. Constraint: you cannot police it and you cannot annoy guests. Evidence in the object: the slot is by the door, so the behaviour is enforced by the act of leaving.* Now do the trolley.',
    ],
    misconceptions: [
      { signal: 'says the shop makes money from the coins', tutorMove: 'Ask what happens to the coin when the trolley is returned.' },
      { signal: 'describes the mechanism without naming a constraint', tutorMove: 'Ask what the designer could not do, and why.' },
    ],
    bridge: 'Find one everyday object whose odd feature is really a solution to a problem you never noticed.',
  },
  {
    id: 'rev-t3-intent-bench',
    strand: 'reverse', moves: ['design_intent', 'work_backwards'], tier: 3, difficulty: 1.1,
    domain: 'social', register: [13, 16],
    title: 'The bench with a bar in the middle',
    stimulus: 'A council installs new benches in the town centre. Each has a metal armrest bolted in the exact middle of the seat. The old benches had no middle armrest. The council press release mentions "improved comfort and accessibility".',
    prompt: 'Reverse-engineer the real design intent. What is the middle bar for? Give the evidence in the object itself, name the constraint the designer worked under, and say who pays the cost of this design.',
    mode: 'open_short',
    payload: {
      maxWords: 200,
      answerKey: 'The middle armrest prevents lying down — it is anti-homeless (or anti-sleeping) design, sometimes called hostile or defensive architecture. Evidence in the object: it is in the exact middle rather than at the ends where an armrest helps most people stand up; it appears on a redesign; the stated reason (comfort) does not explain the position. Constraint: the council cannot say "we do not want people sleeping here" and cannot enforce it with staff, so the rule is built into the furniture, where it is permanent, silent and unarguable. Cost falls on the people who need to lie down, and also on anyone else who would benefit from a full bench — the design cannot distinguish between them. A strong answer notes that "accessibility" is a real second function, which is exactly what makes the design deniable.',
      conceptVocabulary: ['hostile', 'defensive', 'sleep', 'homeless', 'enforce', 'middle', 'armrest', 'deniable', 'accessibility', 'cost'],
    },
    rubric: {
      criteria: [c('intent_reconstruction', 0.35), c('specificity', 0.2, { name: 'Evidence comes from the object' }), c('stakeholder_fairness', 0.2, { name: 'Names who bears the cost' }), c('beyond_case', 0.25)],
      solo: {
        3: 'Identifies the real function, evidences it from the position of the bar, and names who bears the cost.',
        4: 'Generalises to the pattern — rules built into objects rather than stated — and names another example, noting that a genuine second function makes it deniable.',
      },
    },
    checks: { minWords: { response: 60 } },
    hints: [
      'Armrests usually go at the ends, where they help people push themselves up. Why would you put one in the *middle*?',
      'Ask what becomes impossible with the bar there, that was possible without it. Then ask who that was aimed at.',
      'Worked on a different object: *blue lighting in some public toilets. Stated reason: modern look. Real function: it makes veins hard to see, deterring injecting drug use. Evidence: it appears only in certain locations, and it makes ordinary use harder too.* Notice the pattern — an unstated rule built into a physical thing. Now finish the bench.',
    ],
    misconceptions: [
      { signal: 'accepts the press release at face value', tutorMove: 'Ask whether the *position* of the bar is what a comfort armrest would look like.' },
      { signal: 'names the intent but gives no evidence from the object', tutorMove: 'Ask what in the bench itself proves it, to someone who has not heard of hostile architecture.' },
    ],
    bridge: 'Find one thing in a public space that quietly enforces a rule nobody wrote down.',
  },
  {
    id: 'rev-t4-reconstruct',
    strand: 'reverse', moves: ['work_backwards', 'disconfirm'], tier: 4, difficulty: 1.9,
    domain: 'data', register: [14, 16],
    title: 'Reconstruct what happened',
    stimulus: 'A school\'s printing costs tripled in October and stayed high. Facts available: total pages up 3×; number of print jobs up only 15%; the average job went from 4 pages to 11; colour printing up 6×; the science department got a new teacher in September; a new "print your revision pack" homework was set for Years 10-11 in late September; the printer firmware was updated on 1 October.',
    prompt: 'Work backwards from the cost to the mechanism. Give the explanation that best fits **all** the numbers, then name the single check that would most cleanly prove your explanation wrong.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'mechanism', label: 'What actually happened, and how each number fits it', required: true, minWords: 45 },
        { id: 'rejected', label: 'One explanation you rejected, and which number kills it', required: true, minWords: 20 },
        { id: 'disconfirm', label: 'The single check that would prove *you* wrong', required: true, minWords: 15 },
      ],
      answerKey: 'Jobs barely rose but pages per job nearly tripled, so this is not "more people printing" — it is the same population printing much longer documents, which fits the revision-pack homework rather than a new teacher (a new teacher would raise job count) and rather than firmware (which would not change document length, though it could change colour defaults). The 6× colour rise may be a separate cause: a firmware update that changed the default from greyscale to colour. Best answer: two overlapping causes, distinguished by the fact that pages-per-job and colour-share moved for different reasons. Disconfirming check: pages-per-job broken down by year group and date — if Years 10-11 did not drive the rise, the revision-pack explanation dies; colour share before/after 1 October by department would similarly test the firmware explanation.',
      conceptVocabulary: ['per job', 'jobs', 'pages', 'colour', 'firmware', 'default', 'year group', 'date', 'split', 'department'],
    },
    rubric: {
      criteria: [c('integration', 0.3, { name: 'Explanation fits every number' }), c('rival_explanations', 0.25), c('test_design', 0.25), c('specificity', 0.2)],
      solo: {
        3: 'Uses the jobs-vs-pages split to rule out "more people printing" and lands on a mechanism that fits most numbers.',
        4: 'Recognises two overlapping causes and designs a check that separates them rather than confirming one.',
      },
    },
    checks: { requiredFields: ['mechanism', 'rejected', 'disconfirm'], capIfMissing: { disconfirm: 0.65, rejected: 0.8 } },
    hints: [
      'Two numbers move very differently: job count (+15%) and pages per job (4 → 11). What kind of change produces that pattern, and what kind does not?',
      'Colour is up 6× — does your mechanism explain that, or does it need a second cause? It is allowed to need two.',
      'Worked shape from another case: *"Water use tripled but the number of showers barely changed → so it is not more people, it is longer showers → check by time-per-shower, not by count."* That is working backwards from a ratio. Apply it here.',
    ],
    misconceptions: [
      { signal: 'blames the new teacher', tutorMove: 'Ask what the job count would have done if a whole new class started printing.' },
      { signal: 'proposes a check that would only confirm', tutorMove: 'Ask what result of their check would make them abandon their explanation.' },
    ],
    bridge: 'Next time a total jumps, split it into count × size before explaining it.',
  },
];
