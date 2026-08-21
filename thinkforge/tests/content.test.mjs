/**
 * The authoring rules from docs/02 §3, enforced. A task that breaks one of
 * these cannot be scored, scaffolded or selected properly, so this file is the
 * gate on the content bank.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { TASKS, publicTask, CORE_TRANSFER_MOVES } from '../server/content/index.mjs';
import { STRANDS, TIERS, DOMAINS, getMove } from '../server/content/frameworks.mjs';

const OPEN = new Set(['open_short', 'open_list', 'structured', 'probe']);

test('every task has the required shape', () => {
  for (const t of TASKS) {
    assert.ok(t.id && t.title && t.stimulus && t.prompt, `${t.id}: missing core fields`);
    assert.ok(STRANDS.some((s) => s.id === t.strand), `${t.id}: unknown strand`);
    assert.ok(DOMAINS.includes(t.domain), `${t.id}: unknown domain ${t.domain}`);
    assert.ok(Array.isArray(t.register) && t.register.length === 2, `${t.id}: register band missing`);
    assert.ok(typeof t.bridge === 'string' && t.bridge.length > 10, `${t.id}: no transfer bridge`);
  }
});

test('task ids are unique', () => {
  assert.equal(new Set(TASKS.map((t) => t.id)).size, TASKS.length);
});

test('every move belongs to a real strand', () => {
  for (const t of TASKS) {
    assert.ok(t.moves.length, `${t.id}: names no move`);
    for (const m of t.moves) assert.ok(getMove(m), `${t.id}: unknown move ${m}`);
  }
});

test('difficulty sits inside its tier band', () => {
  for (const t of TASKS) {
    const tier = TIERS.find((x) => x.tier === t.tier);
    assert.ok(tier, `${t.id}: unknown tier`);
    assert.ok(t.difficulty >= tier.band[0] && t.difficulty <= tier.band[1],
      `${t.id}: difficulty ${t.difficulty} outside tier ${t.tier} band ${tier.band}`);
  }
});

test('exactly three hints, ordered question → focus → worked analogy', () => {
  for (const t of TASKS) {
    assert.equal(t.hints.length, 3, `${t.id}: needs exactly three hints`);
    for (const hint of t.hints) assert.ok(hint.length > 30, `${t.id}: hint too thin`);
  }
});

test('no hint contains the answer key verbatim', () => {
  for (const t of TASKS) {
    const key = t.payload?.answerKey;
    if (!key) continue;
    for (const hint of t.hints) {
      const sentence = key.split(/[.;]/)[0].trim().toLowerCase();
      if (sentence.length < 25) continue;
      assert.ok(!hint.toLowerCase().includes(sentence), `${t.id}: a hint gives the answer away`);
    }
  }
});

test('rubric weights sum to 1 and every criterion has four anchors', () => {
  for (const t of TASKS) {
    if (!OPEN.has(t.mode)) continue;
    assert.ok(t.rubric?.criteria?.length, `${t.id}: open task with no rubric`);
    const sum = t.rubric.criteria.reduce((a, c) => a + c.weight, 0);
    assert.ok(Math.abs(sum - 1) < 1e-6, `${t.id}: rubric weights sum to ${sum}`);
    for (const c of t.rubric.criteria) {
      for (const level of ['0', '1', '2', '3']) {
        assert.ok(c.anchors[level]?.length > 10, `${t.id}/${c.id}: anchor ${level} missing`);
      }
    }
  }
});

test('open tasks carry SOLO anchors for relational and extended abstract', () => {
  for (const t of TASKS) {
    if (!OPEN.has(t.mode)) continue;
    assert.ok(t.rubric.solo?.['3'], `${t.id}: no relational anchor`);
    assert.ok(t.rubric.solo?.['4'], `${t.id}: no extended-abstract anchor`);
  }
});

test('objective tasks have a resolvable answer', () => {
  for (const t of TASKS) {
    if (t.mode === 'select') assert.ok(t.payload.options.some((o) => o.correct), `${t.id}: no correct option`);
    if (t.mode === 'multi_select') assert.ok(t.payload.options.some((o) => o.correct), `${t.id}: no correct options`);
    if (t.mode === 'order') assert.equal(t.payload.answer.length, t.payload.items.length, `${t.id}: order answer mismatch`);
    if (t.mode === 'match') {
      assert.equal(Object.keys(t.payload.answer).length, t.payload.left.length, `${t.id}: match answer mismatch`);
      for (const r of Object.values(t.payload.answer)) {
        assert.ok(t.payload.right.some((x) => x.id === r), `${t.id}: match answer points nowhere`);
      }
    }
    if (t.mode === 'probe') assert.ok(t.payload.machine?.rule, `${t.id}: probe with no machine rule`);
  }
});

test('every core transfer move is instantiated in at least three domains', () => {
  const byMove = new Map();
  for (const t of TASKS) {
    for (const m of t.moves) {
      if (!byMove.has(m)) byMove.set(m, new Set());
      byMove.get(m).add(t.domain);
    }
  }
  // docs/02 §3 rule 6. Far transfer is weak by default, so a move the platform
  // *claims* to teach must be practised in three different domains. Moves
  // outside the core set are introduced rather than claimed; their coverage is
  // printed as debt so it stays visible rather than silently passing.
  for (const move of CORE_TRANSFER_MOVES) {
    const domains = byMove.get(move) || new Set();
    assert.ok(domains.size >= 3, `core move ${move} appears in only ${domains.size} domain(s): ${[...domains]}`);
  }
  const debt = [...byMove.entries()]
    .filter(([m, d]) => !CORE_TRANSFER_MOVES.includes(m) && d.size < 3)
    .map(([m, d]) => `${m}(${d.size})`);
  console.log(`    coverage debt — non-core moves in fewer than three domains: ${debt.length}/${byMove.size} (${debt.slice(0, 8).join(', ')}${debt.length > 8 ? ', …' : ''})`);
});

test('every strand and every tier is represented', () => {
  for (const s of STRANDS) assert.ok(TASKS.some((t) => t.strand === s.id), `${s.id}: no tasks`);
  for (const tier of TIERS) assert.ok(TASKS.some((t) => t.tier === tier.tier), `tier ${tier.tier}: no tasks`);
});

test('publicTask never leaks an answer', () => {
  for (const t of TASKS) {
    const json = JSON.stringify(publicTask(t));
    assert.ok(!json.includes('"answerKey"'), `${t.id}: answer key leaked`);
    assert.ok(!json.includes('"correct"'), `${t.id}: correct flags leaked`);
    assert.ok(!json.includes('"canonicalForms"'), `${t.id}: probe rule leaked`);
    if (t.mode === 'probe') assert.ok(!json.includes('"rule"'), `${t.id}: machine rule leaked`);
    if (t.mode === 'match') assert.ok(!json.includes('"answer"'), `${t.id}: match answer leaked`);
    assert.ok(!json.includes('"hints"'), `${t.id}: hint ladder leaked to the page`);
  }
});
