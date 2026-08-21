import { c } from '../rubrics.mjs';

export default [
  {
    id: 'met-t1-plan-first',
    strand: 'metacog', moves: ['plan_monitor_evaluate'], tier: 1, difficulty: -1.2,
    domain: 'everyday', register: [9, 12],
    title: 'Say the plan out loud',
    stimulus: 'You have 25 minutes to plan a two-minute talk about a place you know well, to a class who have never been there.',
    prompt: 'Do not write the talk. Write the **plan**: what you will do first, what would tell you halfway through that it is going wrong, and how you will know at the end that it is good enough.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'plan', label: 'Before: what will you do, in what order?', required: true, minWords: 15 },
        { id: 'monitor', label: 'During: what would tell you it is going wrong?', required: true, minWords: 10 },
        { id: 'evaluate', label: 'After: how will you know it is good enough?', required: true, minWords: 10 },
      ],
      commonIdeas: ['write it down', 'practise it', 'do my best'],
      conceptVocabulary: ['first', 'then', 'check', 'time', 'notes', 'practise', 'audience', 'stuck', 'too long'],
    },
    rubric: {
      criteria: [c('plan_quality', 0.4), c('specificity', 0.3), c('completeness', 0.3)],
      solo: {
        3: 'Three real answers: an ordered plan, a specific warning sign, and a checkable finish test.',
        4: 'The warning sign is something they could actually notice at the time (e.g. "I am still on the first point after ten minutes"), not a feeling.',
      },
    },
    checks: { requiredFields: ['plan', 'monitor', 'evaluate'], capIfMissing: { monitor: 0.6 } },
    hints: [
      'Your "during" answer is the hard one. What could you *notice at minute 12* that would tell you to change course?',
      'A good warning sign is something you can see or time — not "if I feel stuck". Try one with a number in it.',
      'Worked plan for revising a topic: *Before — list what I already know, then find the three things I cannot explain. During — if I am still making the list at 10 minutes, I am avoiding the hard part. After — I can explain all three out loud without looking.* Notice all three are checkable. Now redo yours.',
    ],
    bridge: 'Before your next piece of homework, write the three lines first.',
  },
  {
    id: 'met-t1-strategy-match',
    strand: 'metacog', moves: ['strategy_select'], tier: 1, difficulty: -0.8,
    domain: 'everyday', register: [9, 12],
    title: 'Which tool for which job?',
    stimulus: 'Four situations, four thinking moves you have met.',
    prompt: 'Match each situation to the move that fits it best.',
    mode: 'match',
    payload: {
      left: [
        { id: 'l1', text: 'Everyone has already decided, and you think they are rushing.' },
        { id: 'l2', text: 'A machine does something and nobody knows why.' },
        { id: 'l3', text: 'Two people want opposite things and both have a point.' },
        { id: 'l4', text: 'You have one idea and it is the obvious one.' },
      ],
      right: [
        { id: 'r1', text: 'PMI — plus, minus, interesting, before judging' },
        { id: 'r2', text: 'Change one thing at a time and watch what happens' },
        { id: 'r3', text: 'Other people\'s views — state each side fairly' },
        { id: 'r4', text: 'Provocation — say something impossible and move from it' },
      ],
      answer: { l1: 'r1', l2: 'r2', l3: 'r3', l4: 'r4' },
    },
    checks: {},
    hints: [
      'For each situation ask: what is actually missing here — options, information, fairness, or judgement?',
      'One of these situations is missing *information about how something works*. Which tool produces information?',
      'Worked: *"I keep getting the same wrong answer"* — what is missing is not ideas, it is a look at your own method. So the move is an error autopsy. Now match the four.',
    ],
    bridge: 'Next time you get stuck, name the move before you start.',
  },
  {
    id: 'met-t2-error-autopsy',
    strand: 'metacog', moves: ['error_autopsy'], tier: 2, difficulty: 0.1,
    domain: 'story', register: [11, 14],
    title: 'Autopsy of a wrong answer',
    stimulus: 'Task given: *"If it rains, the match is cancelled. The match was cancelled. What can you conclude?"*\nJas answered: *"It rained. The rule says so."*\nJas is quick, confident, and got it wrong in under five seconds.',
    prompt: 'Do an **error autopsy** on Jas. What kind of mistake is this — misread the question / missed a step / wrong tool / stopped too early / never checked an assumption? Name it, explain what produced it, and give the one check that would have caught it.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'type', label: 'Type of error', required: true, minWords: 3 },
        { id: 'cause', label: 'What produced it?', required: true, minWords: 15 },
        { id: 'check', label: 'The check that would have caught it', required: true, minWords: 12 },
      ],
      answerKey: 'The error is "stopped too early / never checked an assumption": Jas walked a one-way rule backwards without noticing there was a direction to check. Confidence and speed are the mechanism — the answer felt obviously right, so no check ran. The catching check: ask "is there any other reason the match could have been cancelled?" — i.e. look for one counter-example before accepting.',
      conceptVocabulary: ['backwards', 'direction', 'assumption', 'counter-example', 'check', 'quick', 'confident', 'other reason'],
    },
    rubric: {
      criteria: [c('error_classification', 0.4), c('integration', 0.3, { name: 'Explains the mechanism, not just the mistake' }), c('specificity', 0.3, { name: 'The check is runnable' })],
      solo: {
        3: 'Correct error type with a runnable check.',
        4: 'Notices that speed and confidence are what removed the check, and generalises the lesson to their own fast answers.',
      },
    },
    checks: { requiredFields: ['type', 'cause', 'check'], capIfMissing: { check: 0.65 } },
    hints: [
      'Jas did not misread anything — the words were understood correctly. So what was skipped?',
      'Notice the "under five seconds". What does speed do to checking?',
      'Worked autopsy: *Type — never checked an assumption. Cause — I assumed the units matched because they usually do. Check — before dividing, write both units and cancel them.* The check is a thing you can actually do. Now finish Jas\'s.',
    ],
    misconceptions: [
      { signal: 'says Jas is careless or bad at logic', tutorMove: 'Redirect to the process: what specific step was skipped, not what kind of person Jas is.' },
    ],
    bridge: 'Run this on your own next wrong answer, before you look at the right one.',
  },
  {
    id: 'met-t2-calibration-run',
    strand: 'metacog', moves: ['calibration'], tier: 2, difficulty: 0.2,
    domain: 'data', register: [11, 14],
    title: 'How sure are you, really?',
    stimulus: 'Five quick questions are coming. Before each one you will say how confident you are, from 50% (a coin flip) to 100% (certain).',
    prompt: 'Answer this one, and then judge yourself honestly: **"A bat and a ball cost £1.10 together. The bat costs £1.00 more than the ball. How much is the ball?"** Give your answer, your confidence, and then — before you find out — say what would make you wrong.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'answer', label: 'Your answer', required: true, minWords: 1 },
        { id: 'confidence', label: 'Confidence (50-100%)', required: true, minWords: 1 },
        { id: 'wrong', label: 'What would make you wrong?', required: true, minWords: 12 },
      ],
      answerKey: '5p. The intuitive answer 10p fails the check: if the ball were 10p the bat would be £1.10 and the total £1.20. The point of the task is not the arithmetic — it is whether the student ran the check *before* reporting high confidence.',
      conceptVocabulary: ['check', 'total', 'more than', 'substitute', 'add up', 'sure', 'verify'],
    },
    rubric: {
      criteria: [c('error_classification', 0.3, { name: 'Knows what could go wrong' }), c('specificity', 0.35, { name: 'Names a real check' }), c('qualifier_fit', 0.35, { name: 'Confidence matches the checking done' })],
      solo: {
        3: 'Answers, and names a real way of being wrong rather than "I might have misread it".',
        4: 'Runs the check (substitute the answer back) *before* stating confidence, and says so.',
      },
    },
    checks: { requiredFields: ['answer', 'confidence', 'wrong'], capIfMissing: { wrong: 0.55 } },
    hints: [
      'Before you commit: put your answer back into the problem. Do both conditions hold?',
      'If the ball were 10p, what would the bat cost, and what would the total be? Check the total against £1.10.',
      'The general move: high confidence is only earned *after* a substitution check. Say what your check was, then set your confidence.',
    ],
    misconceptions: [
      { signal: 'answers 10p with high confidence', tutorMove: 'Ask them to add up their own two prices and compare to £1.10 — do not tell them the answer.' },
    ],
    bridge: 'For the next thing you are sure about, name the check that earned the certainty.',
  },
  {
    id: 'met-t3-monitor-live',
    strand: 'metacog', moves: ['plan_monitor_evaluate', 'strategy_select'], tier: 3, difficulty: 0.9,
    domain: 'design', register: [13, 16],
    title: 'Pick your tool and watch yourself use it',
    stimulus: 'Open problem: your year group wastes about 60 packed-lunch portions a day. You have twenty minutes and access to nothing but a notebook.',
    prompt: 'Before you attack it: name the **thinking move** you will use first and why *this* problem has that shape. Then attack it. Then report what actually happened to your plan — including the moment you should have switched tools.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'choice', label: 'The move you will start with, and why this problem has that shape', required: true, minWords: 20 },
        { id: 'work', label: 'Your actual thinking (the output of using it)', required: true, minWords: 40 },
        { id: 'monitor', label: 'What happened to the plan — where did it stop working?', required: true, minWords: 20 },
        { id: 'switch', label: 'The move you should have switched to, and when', required: true, minWords: 15 },
      ],
      conceptVocabulary: ['five whys', 'CAF', 'stakeholders', 'loop', 'root cause', 'alternatives', 'switch', 'stuck', 'evidence'],
    },
    rubric: {
      criteria: [c('strategy_fit', 0.3), c('plan_quality', 0.2), c('integration', 0.25, { name: 'The monitoring is about the real attempt' }), c('error_classification', 0.25)],
      solo: {
        3: 'A justified tool choice, real work, and an honest account of where it stopped working.',
        4: 'Identifies the *signal* that should have triggered the switch (e.g. "I was generating more causes but no new kinds of cause") as a general stopping rule.',
      },
    },
    checks: { requiredFields: ['choice', 'work', 'monitor', 'switch'], capIfMissing: { monitor: 0.6, switch: 0.75 } },
    hints: [
      'Your reason for choosing the tool should describe the *shape* of the problem: is information missing, are options missing, or is fairness missing?',
      'Reread your own working. Where did it start producing more of the same instead of anything new? That is the switch point.',
      'Worked monitoring note: *"By why number three I was still listing reasons children do not eat — all the same kind. The signal was that new items stopped changing my picture. I should have switched to OPV and asked the kitchen staff\'s view."* Now write yours with that level of honesty.',
    ],
    bridge: 'On your next long piece of work, write the switch signal in advance.',
  },
  {
    id: 'met-t4-bridging-audit',
    strand: 'metacog', moves: ['bridging', 'error_autopsy'], tier: 4, difficulty: 1.9,
    domain: 'social', register: [14, 16],
    title: 'Where else does this work?',
    stimulus: 'You have now used several moves — warrant audits, second-order chains, control of variables, leverage points, contradictions.',
    prompt: 'Pick **one move you are actually good at**. Name two situations *outside school* where it would work, from two different areas of life, and say precisely what makes each situation the right shape for it. Then name one situation where using it would be a **mistake**, and what you would use instead.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'move', label: 'The move', required: true, minWords: 2 },
        { id: 'target1', label: 'Transfer target 1 — where, and why that shape', required: true, minWords: 20 },
        { id: 'target2', label: 'Transfer target 2 — different area of life', required: true, minWords: 20 },
        { id: 'misfit', label: 'Where this move would be the wrong tool, and what beats it there', required: true, minWords: 20 },
      ],
      conceptVocabulary: ['shape', 'because', 'unlike', 'instead', 'family', 'money', 'sport', 'online', 'work', 'friendship'],
    },
    rubric: {
      criteria: [c('bridge_targets', 0.35), c('strategy_fit', 0.3), c('rebuttal_real', 0.2, { name: 'The misfit case is genuine' }), c('beyond_case', 0.15)],
      solo: {
        3: 'Two real targets from different areas with reasons that name the structural feature, plus a genuine misfit case.',
        4: 'The reasons describe an abstract condition ("this move needs a system with a feedback loop and a delay"), which is what makes it a transfer rule rather than two anecdotes.',
      },
    },
    checks: { requiredFields: ['move', 'target1', 'target2', 'misfit'], capIfMissing: { misfit: 0.7 } },
    hints: [
      'Your two targets should not both be about school or both about friends. Move one of them into money, sport, health, or something online.',
      'The reason must name the *shape*, not the topic: "there is a rule everyone follows that nobody has said out loud" is a shape; "it is about football" is a topic.',
      'Worked: *Move — second-order chains. Target 1 (money): any time a shop offers something free, ask what it changes about what people then buy. Target 2 (health): any time a fix removes a symptom, ask what the symptom was doing. Misfit: choosing between two equally-known options — nothing is hidden, so the move adds nothing; there, criteria-first beats it.* Now write yours.',
    ],
    misconceptions: [
      { signal: 'both targets from the same area', tutorMove: 'Ask them to keep the move but change the whole area of life.' },
      { signal: 'no genuine misfit', tutorMove: 'Ask when this move wastes time — every tool has a case where it does.' },
    ],
    bridge: 'Use your chosen move once outside school this week and note what happened.',
  },
];
