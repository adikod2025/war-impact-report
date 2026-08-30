/**
 * The taught curriculum: eight strands, each owning a set of named "moves".
 * A move is a procedure a 9-15 year-old can perform, that leaves an artefact
 * we can score. See docs/02-learning-architecture.md §1.
 */

export const LEVELS = [
  { level: 0, name: 'Not yet', solo: 'prestructural', blurb: 'The move has not appeared yet.' },
  { level: 1, name: 'Noticing', solo: 'unistructural', blurb: 'Does the move once, on one thing, when asked.' },
  { level: 2, name: 'Listing', solo: 'multistructural', blurb: 'Does it on several things, but they stay separate.' },
  { level: 3, name: 'Connecting', solo: 'relational', blurb: 'Joins the parts into one coherent piece of thinking.' },
  { level: 4, name: 'Extending', solo: 'extended abstract', blurb: 'Goes beyond the case: generalises or moves it to new ground.' },
  { level: 5, name: 'Directing', solo: 'extended abstract +', blurb: 'Picks and combines moves unprompted, and audits their own reasoning.' },
];

/** θ cut-points (logits) for each level. */
export const LEVEL_CUTS = [-1.5, -0.5, 0.5, 1.5, 2.5];

export const TIERS = [
  { tier: 1, name: 'Spark', ages: [9, 10], band: [-1.5, -0.5], register: 'Concrete, one move, familiar ground, example always available.' },
  { tier: 2, name: 'Forge', ages: [11, 12], band: [-0.5, 0.5], register: 'Two moves chained, hypotheticals in familiar content, faded examples.' },
  { tier: 3, name: 'Circuit', ages: [13, 14], band: [0.5, 1.5], register: 'Multi-move, counterfactual, unfamiliar domain, competing evidence.' },
  { tier: 4, name: 'Summit', ages: [15, 18], band: [1.5, 2.5], register: 'Open-ended, student picks the strategy, critiques their own reasoning.' },
];

export const DOMAINS = ['science', 'everyday', 'social', 'design', 'story', 'data'];

export const STRANDS = [
  {
    id: 'analysis',
    name: 'Break It Down',
    claim: 'Decomposes a whole into parts, finds the structure, and separates cause from coincidence.',
    colour: '#3b82f6',
    icon: 'grid',
    moves: [
      { id: 'first_principles', name: 'First principles', origin: 'Aristotle / Descartes / modern engineering practice',
        how: 'Strip the thing back to the parts you are sure of, then rebuild only from those.',
        artefact: 'A list of things known to be true, separated from things assumed.' },
      { id: 'part_whole', name: 'Part / whole map', origin: 'Structural analysis',
        how: 'Name the parts, then say what each one does for the whole.',
        artefact: 'Parts with their jobs.' },
      { id: 'five_whys', name: 'Five whys', origin: 'Toyota Production System',
        how: 'Ask "why?" of your own answer, five times, until you stop finding a deeper cause.',
        artefact: 'A why-chain from surface symptom to root cause.' },
      { id: 'cause_vs_correlate', name: 'Cause or coincidence', origin: 'Scientific method / statistics',
        how: 'Before calling A the cause of B, ask: could B cause A? Could C cause both? Could it be chance?',
        artefact: 'Three rival explanations ranked.' },
      { id: 'criteria', name: 'Criteria extraction', origin: 'Decision analysis',
        how: 'Say what "good" means here before you judge anything.',
        artefact: 'Named criteria, ideally weighted.' },
    ],
  },
  {
    id: 'synthesis',
    name: 'Build It Up',
    claim: 'Combines parts, carries structure across domains, and invents under constraint.',
    colour: '#8b5cf6',
    icon: 'spark',
    moves: [
      { id: 'analogy_map', name: 'Structure mapping', origin: 'Gentner, analogical reasoning',
        how: 'Match the *relationships* between two things, not what they look like.',
        artefact: 'A mapping table: this↔that, and the relation that carries over.' },
      { id: 'contradiction', name: 'TRIZ contradiction', origin: 'Altshuller, TRIZ',
        how: 'Write the problem as "we want X and also not-X", then attack the contradiction instead of compromising.',
        artefact: 'A stated contradiction plus a resolution that keeps both sides.' },
      { id: 'ideality', name: 'Ideal final result', origin: 'TRIZ',
        how: 'Describe the perfect outcome where the job gets done with no machine, cost or harm — then work back toward it.',
        artefact: 'An IFR statement and the nearest reachable version.' },
      { id: 'scamper', name: 'SCAMPER', origin: 'Osborn / Eberle',
        how: 'Substitute, Combine, Adapt, Modify, Put to other use, Eliminate, Reverse.',
        artefact: 'One idea per operator.' },
      { id: 'hmw_frame', name: 'How might we…', origin: 'Stanford d.school design thinking',
        how: 'Turn a complaint into a question with a user, a need and an insight in it.',
        artefact: 'A HMW question that is neither too broad nor a hidden solution.' },
      { id: 'concept_fan', name: 'Concept fan', origin: 'de Bono',
        how: 'Climb from your idea up to the concept behind it, then fan back down to other ideas.',
        artefact: 'Idea → concept → three new ideas.' },
    ],
  },
  {
    id: 'lateral',
    name: 'Sideways',
    claim: 'Escapes the first idea, and generates and shapes alternatives on purpose.',
    colour: '#f59e0b',
    icon: 'zigzag',
    moves: [
      { id: 'pmi', name: 'PMI', origin: 'de Bono, CoRT 1',
        how: 'Before judging: list the Pluses, the Minuses, and the Interesting (neither good nor bad, but worth noticing).',
        artefact: 'Three columns, all non-empty.' },
      { id: 'caf', name: 'Consider all factors', origin: 'de Bono, CoRT 1',
        how: 'List everything that has to be taken into account — then find the ones everybody forgets.',
        artefact: 'A factor list with at least one non-obvious factor.' },
      { id: 'cns', name: 'Consequence & sequel', origin: 'de Bono, CoRT 1',
        how: 'Trace effects at four ranges: right now, soon, in a year, in ten years.',
        artefact: 'Four time bands, each with an effect.' },
      { id: 'apc', name: 'Alternatives', origin: 'de Bono, CoRT 1',
        how: 'Force at least three genuine options before choosing, including one you dislike.',
        artefact: 'Three distinct options, not variations of one.' },
      { id: 'opv', name: 'Other people\'s views', origin: 'de Bono, CoRT 1',
        how: 'Name everyone affected and state their view in their own terms — fairly enough that they would agree.',
        artefact: 'Stakeholders with their actual interests.' },
      { id: 'po', name: 'Provocation (PO)', origin: 'de Bono, lateral thinking',
        how: 'Say something deliberately impossible, then *move* from it to something usable.',
        artefact: 'A provocation plus the movement that rescued a real idea from it.' },
      { id: 'random_entry', name: 'Random entry', origin: 'de Bono',
        how: 'Take an unrelated word and force a connection to your problem.',
        artefact: 'Word → link → new idea.' },
      { id: 'six_hats', name: 'Six thinking hats', origin: 'de Bono',
        how: 'Everyone thinks in the same direction at once: facts, feelings, cautions, benefits, new ideas, process.',
        artefact: 'A contribution under each hat that stays in role.' },
    ],
  },
  {
    id: 'logic',
    name: 'Straight Lines',
    claim: 'Tells valid inference from invalid, and truth from validity.',
    colour: '#10b981',
    icon: 'arrow',
    moves: [
      { id: 'validity', name: 'Valid vs true', origin: 'Formal logic',
        how: 'Ask two separate questions: are the premises true, and does the conclusion actually follow?',
        artefact: 'A verdict on each question separately.' },
      { id: 'conditional', name: 'If-then reasoning', origin: 'Propositional logic / Wason',
        how: 'From "if P then Q": P tells you Q, and not-Q tells you not-P. Q tells you nothing. Not-P tells you nothing.',
        artefact: 'The correct check, and the case that could disprove the rule.' },
      { id: 'necessary_sufficient', name: 'Necessary or sufficient', origin: 'Logic / causal analysis',
        how: 'Needed for it to happen, or enough on its own? They are different jobs.',
        artefact: 'A condition correctly labelled, with a counter-case.' },
      { id: 'quantifier', name: 'All, some, none', origin: 'Syllogistic logic',
        how: 'Draw the circles. "Some A are B" never gives you "all".',
        artefact: 'A diagram or a counterexample.' },
      { id: 'falsification', name: 'What would change my mind', origin: 'Popper',
        how: 'Name the observation that would prove you wrong. If there isn\'t one, you aren\'t making a claim.',
        artefact: 'A stated disconfirming observation.' },
      { id: 'fallacy', name: 'Fallacy spotting', origin: 'Informal logic',
        how: 'Name the flaw: attacking the person, false choice, jumping from few cases, after-therefore-because, popularity, straw man, survivor stories.',
        artefact: 'The fallacy named and located in the text.' },
    ],
  },
  {
    id: 'argument',
    name: 'Make the Case',
    claim: 'Builds and audits arguments with explicit warrants and honest limits.',
    colour: '#ef4444',
    icon: 'scale',
    moves: [
      { id: 'toulmin', name: 'Toulmin six', origin: 'Stephen Toulmin, The Uses of Argument',
        how: 'Claim, evidence, warrant (the rule that links them), backing, qualifier (how strongly), rebuttal (when it fails).',
        artefact: 'Six named slots, filled honestly.' },
      { id: 'warrant_audit', name: 'Warrant audit', origin: 'Toulmin applied',
        how: 'Find the unstated rule somebody is relying on, and ask whether it holds in general.',
        artefact: 'The hidden warrant, stated out loud.' },
      { id: 'steelman', name: 'Steelman', origin: 'Argumentation ethics',
        how: 'Build the strongest version of the view you disagree with, before answering it.',
        artefact: 'An opposing case its holder would sign.' },
      { id: 'qualifier', name: 'Qualify honestly', origin: 'Toulmin',
        how: 'Match the strength of your words to the strength of your evidence: always / usually / sometimes / in this case.',
        artefact: 'A claim whose hedging fits its support.' },
      { id: 'rebuttal', name: 'Rebuttal', origin: 'Toulmin',
        how: 'State the conditions under which your own claim would fail.',
        artefact: 'A real exception, not a token one.' },
    ],
  },
  {
    id: 'reverse',
    name: 'Reverse Engineer',
    claim: 'Infers hidden mechanism, rule or intent from what can be observed.',
    colour: '#06b6d4',
    icon: 'gear',
    moves: [
      { id: 'work_backwards', name: 'Work backwards', origin: 'Pólya, How to Solve It',
        how: 'Start at the goal and ask what must have happened immediately before it.',
        artefact: 'A chain built end-first.' },
      { id: 'blackbox', name: 'Black-box probing', origin: 'Cybernetics / scientific inquiry',
        how: 'Feed the box inputs and watch outputs until you can predict it.',
        artefact: 'A stated rule that predicts unseen cases.' },
      { id: 'cvs', name: 'Change one thing', origin: 'Control-of-variables strategy',
        how: 'Between two tests, change exactly one thing. Otherwise you learn nothing.',
        artefact: 'A pair of tests differing in one input.' },
      { id: 'disconfirm', name: 'Try to break it', origin: 'Falsification in practice',
        how: 'Design the test that would prove your own guess wrong — that\'s the one worth running.',
        artefact: 'A test whose failure would kill the hypothesis.' },
      { id: 'design_intent', name: 'Recover the intent', origin: 'Reverse engineering / design forensics',
        how: 'Ask what problem this was built to solve, and what the builder could not afford.',
        artefact: 'The original problem and constraint, reconstructed.' },
    ],
  },
  {
    id: 'systems',
    name: 'Whole Machine',
    claim: 'Reasons about loops, delays and effects that arrive later or elsewhere.',
    colour: '#14b8a6',
    icon: 'loop',
    moves: [
      { id: 'causal_loop', name: 'Causal loop', origin: 'Systems dynamics / Meadows',
        how: 'Draw arrows between the things that change each other, and mark each + or −.',
        artefact: 'A loop with signed links.' },
      { id: 'loop_type', name: 'Reinforcing or balancing', origin: 'Systems dynamics',
        how: 'Even number of minus links → reinforcing (runs away). Odd → balancing (settles).',
        artefact: 'A loop correctly typed, with what it does over time.' },
      { id: 'second_order', name: 'And then what?', origin: 'Second-order thinking',
        how: 'Take your solution and ask "and then what happens?" three times.',
        artefact: 'A three-step consequence chain, including one backfire.' },
      { id: 'delay', name: 'Find the delay', origin: 'Systems dynamics',
        how: 'Find where the effect arrives late — that is usually where people overreact.',
        artefact: 'A named delay and what it causes people to do wrong.' },
      { id: 'leverage', name: 'Leverage point', origin: 'Donella Meadows',
        how: 'Rank where to push: numbers < buffers < loops < rules < goals < the idea behind it all.',
        artefact: 'An intervention placed on the leverage ladder, with a reason.' },
    ],
  },
  {
    id: 'metacog',
    name: 'Think About Thinking',
    claim: 'Plans, monitors, evaluates and calibrates their own thinking.',
    colour: '#a855f7',
    icon: 'mirror',
    moves: [
      { id: 'plan_monitor_evaluate', name: 'Plan, monitor, evaluate', origin: 'Self-regulated learning (EEF)',
        how: 'Before: what am I doing and with what tool? During: is it working? After: what would I do differently?',
        artefact: 'Three statements, one per phase.' },
      { id: 'strategy_select', name: 'Pick the tool', origin: 'Metacognitive strategy knowledge',
        how: 'Name the move you will use and say why this problem calls for it.',
        artefact: 'A named move and a fitting reason.' },
      { id: 'calibration', name: 'Calibration', origin: 'Judgement research / Brier scoring',
        how: 'Predict your score before you find out, then compare.',
        artefact: 'A prediction, and an honest read of the gap.' },
      { id: 'error_autopsy', name: 'Error autopsy', origin: 'Deliberate practice',
        how: 'Classify the mistake: misread it / missed a step / wrong tool / stopped too early / never checked an assumption.',
        artefact: 'The error type named, plus the fix.' },
      { id: 'bridging', name: 'Bridging', origin: 'Transfer research (Perkins & Salomon)',
        how: 'Name two other places this exact move would work.',
        artefact: 'Two concrete transfer targets in different domains.' },
    ],
  },
];

export const STRAND_IDS = STRANDS.map((s) => s.id);

const MOVE_INDEX = new Map();
for (const strand of STRANDS) {
  for (const move of strand.moves) MOVE_INDEX.set(move.id, { ...move, strand: strand.id });
}

export function getMove(id) {
  return MOVE_INDEX.get(id) || null;
}
export function allMoves() {
  return [...MOVE_INDEX.values()];
}
export function getStrand(id) {
  return STRANDS.find((s) => s.id === id) || null;
}
export function levelForTheta(theta) {
  let level = 0;
  for (const cut of LEVEL_CUTS) if (theta >= cut) level += 1;
  return level;
}
export function tierForTheta(theta) {
  for (const t of TIERS) if (theta < t.band[1]) return t.tier;
  return 4;
}
export function defaultTierForAge(age) {
  const t = TIERS.find((x) => age >= x.ages[0] && age <= x.ages[1]);
  return t ? t.tier : age < 9 ? 1 : 4;
}
