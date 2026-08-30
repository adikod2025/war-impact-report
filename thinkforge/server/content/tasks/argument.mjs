import { c } from '../rubrics.mjs';

export default [
  {
    id: 'arg-t1-evidence-match',
    strand: 'argument', moves: ['toulmin'], tier: 1, difficulty: -1.35,
    domain: 'everyday', register: [9, 11],
    title: 'Which evidence actually helps?',
    stimulus: 'Four claims, and five pieces of evidence lying about.',
    prompt: 'Match each claim to the **one** piece of evidence that actually supports it. One piece of evidence supports nothing here.',
    mode: 'match',
    payload: {
      left: [
        { id: 'l1', text: 'The school gate is dangerous at 3:30.' },
        { id: 'l2', text: 'The new library opening hours are working.' },
        { id: 'l3', text: 'Year 7 needs a second water fountain.' },
        { id: 'l4', text: 'The bus is arriving late more often than it used to.' },
      ],
      right: [
        { id: 'r1', text: 'Three near-misses were logged there last term, all between 3:25 and 3:40.' },
        { id: 'r2', text: 'Borrowing has gone from 40 to 130 books a week since the change.' },
        { id: 'r3', text: 'The queue at break is 6 minutes long and 90 pupils share one fountain.' },
        { id: 'r4', text: 'The bus was late 14 times this term, against 3 times in the same term last year.' },
        { id: 'r5', text: 'Lots of people say the school is much better than it used to be.' },
      ],
      answer: { l1: 'r1', l2: 'r2', l3: 'r3', l4: 'r4' },
      distractor: 'r5',
    },
    checks: {},
    hints: [
      'Read a claim, then ask each piece of evidence: does this tell me about *exactly that thing*?',
      'One piece of evidence is vague and about everything in general. It cannot support a specific claim — leave it out.',
      'Worked: claim *"the printer is broken more often this year"* needs a **count this year against a count last year**, not "everyone complains about the printer". Match the rest that way.',
    ],
    bridge: 'Next time you make a claim at home, ask yourself what number or event would back it.',
  },
  {
    id: 'arg-t1-toulmin-lite',
    strand: 'argument', moves: ['toulmin'], tier: 1, difficulty: -0.8,
    domain: 'everyday', register: [9, 12],
    title: 'The missing link',
    stimulus: 'Sam says: "We should put a bike rack by the science block. Loads of bikes get left leaning on the fence there."',
    prompt: 'Sam has a **claim** and some **evidence** but has skipped the **warrant** — the rule that makes the evidence matter. Fill in all three.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'claim', label: 'Claim — what Sam wants to be true', required: true, minWords: 4 },
        { id: 'evidence', label: 'Evidence — what Sam has noticed', required: true, minWords: 5 },
        { id: 'warrant', label: 'Warrant — the general rule that links them ("Whenever…")', required: true, minWords: 8 },
      ],
      conceptVocabulary: ['bike', 'rack', 'fence', 'whenever', 'demand', 'need', 'built', 'used'],
    },
    rubric: {
      criteria: [c('warrant', 0.5), c('evidence_fit', 0.25), c('completeness', 0.25)],
      solo: {
        3: 'A warrant stated as a general rule that genuinely licenses the step from "bikes lean on the fence" to "build a rack here".',
        4: 'Notices the warrant could fail (people might lean bikes there because it is on the way, not because they want a rack there) and says so.',
      },
    },
    checks: { requiredFields: ['claim', 'evidence', 'warrant'], capIfMissing: { warrant: 0.5 }, minWords: { warrant: 6 } },
    hints: [
      'Put your evidence and your claim next to each other. What has to be true about the world for the second to follow from the first?',
      'A warrant is a rule, not a fact about this case. Try starting it with "Whenever…" or "In general, if…".',
      'Worked on another case: *Claim: the corridor needs a bin. Evidence: there is litter along it every day. Warrant: whenever litter builds up in one place, it usually means there is nowhere near to put it.* See how the warrant is about litter in general, not about this corridor. Now write Sam\'s.',
    ],
    misconceptions: [
      { signal: 'warrant repeats the evidence', tutorMove: 'Ask what general rule would make that evidence matter to anybody, anywhere.' },
    ],
    bridge: 'Listen for a claim today where the warrant is missing, and say it out loud in your head.',
  },
  {
    id: 'arg-t2-warrant-audit',
    strand: 'argument', moves: ['warrant_audit'], tier: 2, difficulty: 0.2,
    domain: 'social', register: [11, 14],
    title: 'The rule nobody said out loud',
    stimulus: '"The chess club gets the best room because it wins competitions. The knitting club can have the storeroom."',
    prompt: 'Find the **unstated warrant** behind the room decision, state it as a general rule, and then say whether you think that rule holds up. You do not have to disagree with the decision — you have to make the hidden rule visible.',
    mode: 'open_short',
    payload: {
      maxWords: 150,
      answerKey: 'The unstated warrant is something like: "school resources should go to the activities that win things" — or more generally, "space should be allocated in proportion to competitive success / prestige returned to the school". Making it explicit exposes that it is a value choice, not a fact, and invites rival rules: allocate by need, by number of members, by how much the space matters to the activity (knitting needs light and table space; chess needs quiet).',
      conceptVocabulary: ['warrant', 'rule', 'deserve', 'success', 'need', 'value', 'allocate', 'prestige'],
    },
    rubric: {
      criteria: [c('warrant', 0.4), c('beyond_case', 0.3), c('rival_explanations', 0.3, { name: 'Tests whether the rule holds' })],
      solo: {
        3: 'States the hidden rule in general terms and evaluates it rather than just agreeing or disagreeing with the decision.',
        4: 'Offers a rival allocation rule and shows that the argument only works because one rule was silently chosen.',
      },
    },
    checks: { minWords: { response: 35 } },
    hints: [
      'The argument jumps from "wins competitions" to "deserves the best room". What rule would make that jump legal?',
      'Write the rule so it would apply to any club at all, not just chess. Now ask: does the school actually believe that rule everywhere else?',
      'Worked: *"She should go first because she is oldest" → hidden rule: turns should be allocated by age.* Once you say it out loud you can ask whether age is the right basis here. Do the same for the rooms.',
    ],
    misconceptions: [
      { signal: 'argues about chess vs knitting instead of finding the rule', tutorMove: 'Ask them to write a sentence starting "Whenever a school decides who gets a room, it should…".' },
    ],
    bridge: 'Find one decision at home this week and name the rule it silently assumes.',
  },
  {
    id: 'arg-t2-qualifier-fit',
    strand: 'argument', moves: ['qualifier'], tier: 2, difficulty: 0.25,
    domain: 'data', register: [11, 14],
    title: 'Say it as strongly as you can prove it',
    stimulus: 'Evidence: in one class of 28 pupils, 19 said they slept better in the week they stopped using screens after 9pm. No other class was asked. Nobody measured sleep; pupils reported it themselves.',
    prompt: 'Four versions of the same claim. Pick the one whose strength matches this evidence, then in one line say what is wrong with the one directly above it in strength.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'choice', label: 'Which version fits? (A, B, C or D)', required: true, minWords: 1 },
        { id: 'why', label: 'What is wrong with the next-strongest version?', required: true, minWords: 15 },
      ],
      options: [
        { id: 'A', text: 'Screens before bed ruin sleep.' },
        { id: 'B', text: 'Screens before bed usually make sleep worse for teenagers.' },
        { id: 'C', text: 'In one class, most pupils felt they slept better during a week without late screens.' },
        { id: 'D', text: 'Screens have no effect on sleep.' },
      ],
      answerKey: 'C. It matches exactly what was observed: one class, self-reported, one week, "most" not "all". B overreaches — it generalises to all teenagers from a single unrepresentative class with no measurement and no control week.',
      conceptVocabulary: ['sample', 'one class', 'self-reported', 'week', 'most', 'usually', 'all', 'measure', 'control'],
    },
    rubric: {
      criteria: [c('qualifier_fit', 0.5), c('evidence_fit', 0.3), c('specificity', 0.2)],
      solo: {
        3: 'Picks C and names at least two specific limits of the evidence when criticising B.',
        4: 'States the general principle that the words "usually", "most" and "all" are claims about a population, and this evidence only licenses a claim about one sample.',
      },
    },
    checks: { requiredFields: ['choice', 'why'], capIfMissing: { why: 0.5 } },
    hints: [
      'Underline every word in each version that makes a promise: "ruin", "usually", "teenagers", "no effect". Which promises can this evidence keep?',
      'The evidence has four limits: one class, self-reported, one week, and no comparison group. Check each version against all four.',
      'Worked: from *"7 of my 9 friends prefer the new logo"* you may say "most of the people I asked preferred it" — not "people prefer it". The hedge has to survive contact with the sample. Now choose.',
    ],
    bridge: 'Rewrite one thing you believe strongly so the wording matches the evidence you actually have.',
  },
  {
    id: 'arg-t3-toulmin-full',
    strand: 'argument', moves: ['toulmin', 'rebuttal', 'qualifier'], tier: 3, difficulty: 1.0,
    domain: 'social', register: [13, 16],
    title: 'The full six',
    stimulus: 'Proposal on the table: **school should start at 10am for Years 9-11.** Some evidence exists that adolescent sleep cycles shift later; some schools that tried it report mixed results; parents\' working hours have not changed.',
    prompt: 'Build the argument **for** the proposal with all six Toulmin parts: claim, evidence, warrant, backing, qualifier, rebuttal. Your rebuttal must be a case that would genuinely defeat you — not a token one.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'claim', label: 'Claim', required: true, minWords: 5 },
        { id: 'evidence', label: 'Evidence (grounds)', required: true, minWords: 10 },
        { id: 'warrant', label: 'Warrant — the rule linking evidence to claim', required: true, minWords: 10 },
        { id: 'backing', label: 'Backing — why should we accept that rule?', required: true, minWords: 10 },
        { id: 'qualifier', label: 'Qualifier — how strongly does this hold?', required: true, minWords: 6 },
        { id: 'rebuttal', label: 'Rebuttal — when would your own claim fail?', required: true, minWords: 12 },
      ],
      conceptVocabulary: ['sleep', 'adolescent', 'attendance', 'transport', 'parents', 'childcare', 'evidence', 'trial', 'unless', 'however'],
    },
    rubric: {
      criteria: [c('warrant', 0.25), c('evidence_fit', 0.2), c('qualifier_fit', 0.2), c('rebuttal_real', 0.25), c('completeness', 0.1)],
      solo: {
        3: 'Six distinct slots, the warrant is a real general rule, and the rebuttal names a condition that would genuinely defeat the claim.',
        4: 'The qualifier is derived from the weakness in the evidence rather than chosen by taste, and the rebuttal names what evidence would settle it.',
      },
    },
    checks: {
      requiredFields: ['claim', 'evidence', 'warrant', 'backing', 'qualifier', 'rebuttal'],
      capIfMissing: { warrant: 0.5, rebuttal: 0.7, backing: 0.85 },
    },
    hints: [
      'Check whether your backing is doing a different job from your warrant. The warrant is the rule; the backing is why we should trust the rule.',
      'A token rebuttal is "some people might not like it". A real one names the condition under which *you* would drop the claim — for example, if the evidence turned out to come only from schools that also changed three other things.',
      'Worked pair from another case: *Warrant — when a rule stops the people it targets from doing the thing, it is working. Backing — that is how we judge every other school rule, from phones to uniform.* Notice the backing appeals to consistency, which is a reason to accept the rule itself. Now separate yours.',
    ],
    misconceptions: [
      { signal: 'backing repeats the warrant', tutorMove: 'Ask: if someone rejected your rule, what would you say next?' },
      { signal: 'rebuttal is a mild inconvenience', tutorMove: 'Ask what would make them abandon the proposal entirely.' },
    ],
    bridge: 'Take an argument you have had recently and find which of the six parts you never said out loud.',
  },
  {
    id: 'arg-t4-steelman',
    strand: 'argument', moves: ['steelman', 'rebuttal'], tier: 4, difficulty: 2.0,
    domain: 'social', register: [14, 16],
    title: 'Build their best case',
    stimulus: 'You will be given a position you probably disagree with: **"Schools should not teach any subject that a machine can now do better than a person."**',
    prompt: 'First **steelman** it: write the strongest, fairest version of this position — the one its most thoughtful supporter would actually sign. Only then answer it. Your answer must engage with the strong version, not the weak one.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'steelman', label: 'The strongest version of the position', required: true, minWords: 40 },
        { id: 'best_reason', label: 'Its single best reason', required: true, minWords: 12 },
        { id: 'reply', label: 'Your reply to *that* version', required: true, minWords: 40 },
        { id: 'concede', label: 'What does the other side get right?', required: true, minWords: 12 },
      ],
      conceptVocabulary: ['time', 'curriculum', 'skill', 'judgement', 'machine', 'automate', 'value', 'purpose', 'obsolete', 'craft'],
    },
    rubric: {
      criteria: [c('steelman_fair', 0.35), c('warrant', 0.2), c('rebuttal_real', 0.2, { name: 'Reply meets the strong version' }), c('beyond_case', 0.25)],
      solo: {
        3: 'A fair strong version, and a reply that answers *it* rather than a weaker cousin of it.',
        4: 'Identifies the deepest assumption the position rests on (what school is for) and argues at that level, while conceding something real.',
      },
    },
    checks: { requiredFields: ['steelman', 'best_reason', 'reply', 'concede'], capIfMissing: { concede: 0.75, steelman: 0.4 } },
    hints: [
      'Read your steelman back. Is there a sneer anywhere in it? If a supporter would say "that is not quite what I mean", it is not a steelman yet.',
      'The strongest version is not "machines are good". It is about *scarce time*: every hour spent on something automatable is an hour not spent on something that is not.',
      'Worked steelman of a view you may dislike: *"I am not against reading for pleasure — I am against a timetable that pretends there is unlimited time, so that the hour comes out of the only maths lesson some children will ever get."* That version is hard to answer, which is the point. Now sharpen yours.',
    ],
    misconceptions: [
      { signal: 'steelman is a caricature', tutorMove: 'Ask them to write it as if applying for a job with that opinion.' },
      { signal: 'reply attacks the weak version', tutorMove: 'Ask which sentence of their own steelman the reply actually touches.' },
    ],
    bridge: 'Before your next disagreement, write the other side\'s best sentence before you write your own.',
  },
];
