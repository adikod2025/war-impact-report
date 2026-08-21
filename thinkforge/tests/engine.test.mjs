import test from 'node:test';
import assert from 'node:assert/strict';
import { expected, update, kFactor, standardError, confidentLevel, ITEM_FREEZE_N } from '../server/engine/elo.mjs';
import { evaluateRule, runMachine, isControlledPair, scoreProcess, ruleMatches } from '../server/engine/probe.mjs';
import { extractFeatures, verbatimShare, clusters, progression } from '../server/engine/text.mjs';
import { validityGate, objectiveScore, scoreCap } from '../server/engine/deterministic.mjs';
import { scoreResponse, hintPenalty } from '../server/engine/scoring.mjs';
import { halfLife, recall, reviewUrgency, isHeld } from '../server/engine/mastery.mjs';
import { transferIndex, calibrationIndex, independenceIndex, revisionGainIndex } from '../server/engine/growth.mjs';
import { rankTasks, TARGET_P } from '../server/engine/selector.mjs';
import { getTask, TASKS } from '../server/content/index.mjs';
import { levelForTheta } from '../server/content/frameworks.mjs';

/* ------------------------------------------------------------------ Elo */

test('expected success rises with ability and falls with difficulty', () => {
  assert.ok(expected(1, 0) > expected(0, 0));
  assert.ok(expected(0, 1) < expected(0, 0));
  assert.equal(Math.round(expected(0, 0) * 100), 50);
});

test('a win raises ability, a loss lowers it, and the item moves the other way', () => {
  const win = update({ theta: 0, difficulty: 0, score: 1, studentN: 0, itemN: 0 });
  const loss = update({ theta: 0, difficulty: 0, score: 0, studentN: 0, itemN: 0 });
  assert.ok(win.theta > 0 && win.difficulty < 0);
  assert.ok(loss.theta < 0 && loss.difficulty > 0);
});

test('K decays with observations, so later evidence moves the estimate less', () => {
  assert.ok(kFactor(0, { a: 0.6, b: 0.05 }) > kFactor(50, { a: 0.6, b: 0.05 }));
  const early = update({ theta: 0, difficulty: 0, score: 1, studentN: 0, itemN: 0 });
  const late = update({ theta: 0, difficulty: 0, score: 1, studentN: 100, itemN: 0 });
  assert.ok(Math.abs(early.studentDelta) > Math.abs(late.studentDelta) * 3);
});

test('item difficulty freezes once it has enough observations', () => {
  const frozen = update({ theta: 0, difficulty: 0.5, score: 1, studentN: 5, itemN: ITEM_FREEZE_N });
  assert.equal(frozen.difficulty, 0.5);
  assert.notEqual(frozen.theta, 0);
});

test('low confidence dampens the update', () => {
  const sure = update({ theta: 0, difficulty: 0, score: 1, studentN: 3, itemN: 3, confidence: 1 });
  const unsure = update({ theta: 0, difficulty: 0, score: 1, studentN: 3, itemN: 3, confidence: 0.5 });
  assert.ok(Math.abs(unsure.studentDelta) < Math.abs(sure.studentDelta));
});

test('a level only changes when the whole uncertainty band clears the cut', () => {
  const cuts = [-1.5, -0.5, 0.5, 1.5, 2.5];
  const wobbly = confidentLevel(0.55, 0.4, cuts);
  assert.equal(wobbly.settled, false, 'a band straddling a cut must not settle');
  const settled = confidentLevel(1.1, 0.2, cuts);
  assert.equal(settled.settled, true);
  assert.equal(settled.level, levelForTheta(1.1));
});

test('standard error shrinks as observations accumulate', () => {
  const few = standardError([{ theta: 0, difficulty: 0 }, { theta: 0, difficulty: 0 }]);
  const many = standardError(Array.from({ length: 40 }, () => ({ theta: 0, difficulty: 0 })));
  assert.ok(many < few);
});

/* ---------------------------------------------------------------- probe */

test('rule trees evaluate and/or/not correctly', () => {
  const rule = { op: 'and', terms: [{ var: 'w', cmp: '>=', val: 3 }, { op: 'or', terms: [{ var: 'k', cmp: '==', val: 'in' }, { var: 'l', cmp: '==', val: 'day' }] }] };
  assert.equal(evaluateRule(rule, { w: 5, k: 'out', l: 'day' }), true);
  assert.equal(evaluateRule(rule, { w: 5, k: 'out', l: 'night' }), false);
  assert.equal(evaluateRule(rule, { w: 2, k: 'in', l: 'day' }), false);
  assert.equal(evaluateRule({ op: 'not', terms: [{ var: 'a', cmp: '==', val: 1 }] }, { a: 2 }), true);
});

test('parity works on the authored chime box', () => {
  const task = getTask('rev-t1-blackbox-chime');
  assert.equal(runMachine(task.payload.machine, { number: 4, colour: 'red' }).on, true);
  assert.equal(runMachine(task.payload.machine, { number: 5, colour: 'blue' }).on, false);
});

test('control of variables is detected only when one input changed', () => {
  assert.equal(isControlledPair({ a: 1, b: 'x' }, { a: 2, b: 'x' }), true);
  assert.equal(isControlledPair({ a: 1, b: 'x' }, { a: 2, b: 'y' }), false);
});

test('a controlled, discriminating investigation outscores a scattergun one', () => {
  const machine = { minTests: 3, maxUseful: 9 };
  const careful = scoreProcess([
    { inputs: { a: 1, b: 'x' }, on: false },
    { inputs: { a: 2, b: 'x' }, on: true },
    { inputs: { a: 2, b: 'y' }, on: true },
  ], machine);
  const scattergun = scoreProcess(Array.from({ length: 8 }, (_, i) => ({ inputs: { a: i, b: i % 2 ? 'x' : 'y' }, on: true })), machine);
  assert.ok(careful.process > scattergun.process);
  assert.equal(careful.discrimination, 1);
  assert.equal(scattergun.discrimination, 0, 'all-identical outcomes cannot rule anything out');
});

test('rule matching tolerates paraphrase but not a different rule', () => {
  const machine = { canonicalForms: ['weight at least 3 and (key in or daytime)'] };
  assert.ok(ruleMatches('it needs a weight of at least 3 plus either the key or daytime', machine) > 0.5);
  assert.ok(ruleMatches('it opens at random', machine) < 0.3);
});

/* ----------------------------------------------------------------- text */

test('whole-word matching does not read "never" inside "whenever"', () => {
  const f = extractFeatures('Whenever this happens, it usually means something.');
  assert.equal(f.absolutes, 0);
  assert.ok(f.generality > 0);
});

test('copying is measured by verbatim runs, not shared vocabulary', () => {
  const source = 'Loads of bikes get left leaning on the fence by the science block every single day.';
  const own = 'Around seven bicycles are propped against the railings each morning.';
  const copied = 'Loads of bikes get left leaning on the fence by the science block.';
  assert.ok(verbatimShare(own, source) < 0.2);
  assert.ok(verbatimShare(copied, source) > 0.7);
});

test('near-duplicate ideas collapse into one cluster', () => {
  assert.equal(clusters(['more bins', 'add more bins please', 'pay a cleaner']).length, 2);
});

test('progression rewards lines that add something new', () => {
  const advancing = progression(['the van stopped coming', 'because too few children bought ice cream', 'because the primary school moved']);
  const stalling = progression(['the van stopped coming', 'the van does not come any more', 'the van stopped coming here']);
  assert.ok(advancing > stalling);
});

/* -------------------------------------------------------- gate and caps */

test('the validity gate refuses empty, copied and degenerate answers without scoring them', async () => {
  const task = getTask('arg-t1-toulmin-lite');
  const short = validityGate(task, { fields: { claim: 'dunno', evidence: '', warrant: '' } });
  assert.equal(short.valid, false);
  assert.ok(short.repair.length > 10, 'a rejected response must come back with a repair prompt');

  const copied = validityGate(task, { fields: { claim: task.stimulus, evidence: task.stimulus, warrant: task.stimulus } });
  assert.equal(copied.reason, 'copied');

  const mash = validityGate(task, { fields: { claim: 'aaa aaa aaa aaa aaa aaa aaa aaa aaa aaa', evidence: 'aaa', warrant: 'aaa' } });
  assert.equal(mash.valid, false);
});

test('an invalid response is never scored zero — it is not scored at all', async () => {
  const task = getTask('arg-t1-toulmin-lite');
  const out = await scoreResponse(task, { fields: { claim: 'no', evidence: '', warrant: '' } });
  assert.equal(out.valid, false);
  assert.equal(out.score, null);
});

test('a missing required slot caps the score however well it is written', async () => {
  const task = getTask('arg-t1-toulmin-lite');
  const fluent = {
    claim: 'The school should install a covered bicycle rack immediately outside the science block',
    evidence: 'Seven or eight bicycles are propped against the railings there every single morning this term',
    warrant: '',
  };
  const { cap } = scoreCap(task, { fields: fluent });
  assert.equal(cap, 0.5);
  const scored = await scoreResponse(task, { fields: fluent });
  assert.ok(scored.score <= 0.5, `capped score expected, got ${scored.score}`);
});

test('objective scoring: partial credit, over-selection penalty, order distance', () => {
  const wason = getTask('log-t2-selection-task');
  assert.equal(objectiveScore(wason, { choices: ['a', 'c'] }).score, 1);
  assert.equal(objectiveScore(wason, { choices: ['a', 'c', 'd'] }).score, 0.5);
  assert.equal(objectiveScore(wason, { choices: ['b', 'd'] }).score, 0);

  const order = getTask('rev-t1-workbackwards-bus');
  assert.equal(objectiveScore(order, { order: order.payload.answer }).score, 1);
  assert.equal(objectiveScore(order, { order: [...order.payload.answer].reverse() }).score, 0);
});

test('better reasoning scores higher than weaker reasoning, offline', async () => {
  const task = getTask('arg-t1-toulmin-lite');
  const weak = await scoreResponse(task, { fields: { claim: 'We should get a bike rack there', evidence: 'Lots of bikes are near the fence', warrant: 'Because bikes are near the fence' } });
  const strong = await scoreResponse(task, {
    fields: {
      claim: 'The school should install a bike rack by the science block',
      evidence: 'Seven bicycles are propped against the railings every morning',
      warrant: 'Whenever people repeatedly leave something in the same spot, it usually means that spot is where they need somewhere to put it',
    },
  });
  assert.ok(strong.score > weak.score, `${strong.score} should beat ${weak.score}`);
});

test('offline marking never claims the top anchor', async () => {
  const task = getTask('lat-t1-pmi-nohomework');
  const out = await scoreResponse(task, {
    fields: {
      plus: 'More time for football club\nI would sleep more on Sunday nights\nFamily evenings would be calmer',
      minus: 'I would forget the topic before the test\nTeachers would not see who is stuck\nSome subjects only stick with practice',
      interesting: 'I wonder whether lessons would get longer to make up for it\nI wonder if clubs would suddenly fill up',
    },
  });
  assert.equal(out.scorer, 'offline');
  for (const c of out.criteria) assert.ok(c.score <= 2.5, `${c.id} scored ${c.score} offline`);
  assert.ok(out.confidence < 0.8, 'offline marking must carry lower confidence');
});

test('help taken is discounted from the ability update but not from the feedback', async () => {
  const task = getTask('lat-t1-pmi-nohomework');
  const fields = {
    plus: 'More time for football club\nI would sleep more\nFamily evenings calmer',
    minus: 'I would forget things before tests\nTeachers cannot see who is stuck\nSome subjects need practice',
    interesting: 'I wonder whether lessons would get longer\nI wonder if clubs would fill up',
  };
  const clean = await scoreResponse(task, { fields, meta: { hintLevel: 0 } });
  const helped = await scoreResponse(task, { fields, meta: { hintLevel: 2 } });
  assert.equal(clean.score, helped.score, 'the raw score is the same work');
  assert.ok(helped.adjustedScore < clean.adjustedScore);
  assert.ok(Math.abs((clean.adjustedScore - helped.adjustedScore) - hintPenalty(2)) < 1e-9);
});

/* -------------------------------------------------------------- mastery */

test('half-life grows with success and collapses with failure', () => {
  assert.ok(halfLife({ successes: 4, failures: 0, level: 3 }) > halfLife({ successes: 1, failures: 0, level: 1 }));
  assert.ok(halfLife({ successes: 1, failures: 3, level: 1 }) < halfLife({ successes: 1, failures: 0, level: 1 }));
});

test('review urgency peaks near the target recall, not at total forgetting', () => {
  const state = { successes: 2, failures: 0, level: 2, lastSeen: new Date(Date.now() - 3 * 86400000).toISOString() };
  const fresh = { ...state, lastSeen: new Date().toISOString() };
  const ancient = { ...state, lastSeen: new Date(Date.now() - 400 * 86400000).toISOString() };
  assert.ok(reviewUrgency(state) > reviewUrgency(fresh));
  assert.ok(reviewUrgency(state) > reviewUrgency(ancient));
  assert.ok(recall(halfLife(state), 0) === 1);
});

test('a move is held only after unaided success in two domains', () => {
  assert.equal(isHeld({ unaidedSuccesses: 2, domains: ['everyday', 'social'] }), true);
  assert.equal(isHeld({ unaidedSuccesses: 2, domains: ['everyday'] }), false);
  assert.equal(isHeld({ unaidedSuccesses: 1, domains: ['everyday', 'social'] }), false);
});

/* --------------------------------------------------------------- growth */

test('transfer index compares novel domains against practised ones', () => {
  const day = (n) => new Date(2026, 0, n).toISOString();
  const holds = transferIndex([
    { moves: ['pmi'], domain: 'everyday', score: 0.8, createdAt: day(1) },
    { moves: ['pmi'], domain: 'everyday', score: 0.9, createdAt: day(2) },
    { moves: ['pmi'], domain: 'social', score: 0.85, createdAt: day(3) },
    { moves: ['pmi'], domain: 'design', score: 0.8, createdAt: day(4) },
    { moves: ['pmi'], domain: 'design', score: 0.9, createdAt: day(5) },
  ]);
  const collapses = transferIndex([
    { moves: ['pmi'], domain: 'everyday', score: 0.9, createdAt: day(1) },
    { moves: ['pmi'], domain: 'everyday', score: 0.95, createdAt: day(2) },
    { moves: ['pmi'], domain: 'social', score: 0.2, createdAt: day(3) },
    { moves: ['pmi'], domain: 'design', score: 0.25, createdAt: day(4) },
    { moves: ['pmi'], domain: 'design', score: 0.9, createdAt: day(5) },
  ]);
  assert.ok(holds.available && collapses.available);
  assert.ok(holds.value > collapses.value, 'transfer must fall when the move fails in new domains');
});

test('growth indices refuse to report on too little evidence', () => {
  assert.equal(transferIndex([]).available, false);
  assert.equal(independenceIndex([{ score: 1, hintLevel: 0 }]).available, false);
  assert.equal(calibrationIndex([{ score: 1, confidencePred: 90 }]).available, false);
});

test('calibration rewards accurate self-prediction and names the bias', () => {
  const good = calibrationIndex(Array.from({ length: 6 }, () => ({ score: 0.8, confidencePred: 80 })));
  const cocky = calibrationIndex(Array.from({ length: 6 }, () => ({ score: 0.3, confidencePred: 95 })));
  assert.ok(good.value > cocky.value);
  assert.equal(cocky.reading, 'over-confident');
});

test('revision gain flags dependency when first attempts stay weak', () => {
  const attempts = [
    { id: 1, score: 0.2 }, { id: 2, score: 0.8, revisionOf: 1 },
    { id: 3, score: 0.25 }, { id: 4, score: 0.85, revisionOf: 3 },
  ];
  const out = revisionGainIndex(attempts);
  assert.equal(out.available, true);
  assert.equal(out.dependency, true);
});

/* ------------------------------------------------------------- selector */

test('selection targets a success chance near 0.75 and avoids repeats', () => {
  const theta = { logic: 0.3 };
  const ranked = rankTasks({ tasks: TASKS.filter((t) => t.strand === 'logic'), strandTheta: theta, history: [], age: 12, random: () => 0.99 });
  const top = ranked[0];
  assert.ok(Math.abs(top.p - TARGET_P) < 0.35, `picked p=${top.p}`);

  const withHistory = rankTasks({
    tasks: TASKS.filter((t) => t.strand === 'logic'), strandTheta: theta, age: 12, random: () => 0.99,
    history: [{ taskId: top.task.id, strand: 'logic', moves: top.task.moves, domain: top.task.domain, score: 0.9 }],
  });
  assert.notEqual(withHistory[0].task.id, top.task.id, 'a just-completed task should not come straight back');
});

test('a starved strand is pulled forward', () => {
  const history = Array.from({ length: 12 }, () => ({ taskId: 'x', strand: 'logic', moves: ['conditional'], domain: 'data', score: 0.8 }));
  const ranked = rankTasks({ tasks: TASKS, strandTheta: { logic: 0.5 }, history, age: 12, random: () => 0.99 });
  assert.notEqual(ranked[0].task.strand, 'logic');
});
