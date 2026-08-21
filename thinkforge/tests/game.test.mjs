/**
 * The game layer's rules (docs/04). These tests exist mostly to stop the
 * mechanic drifting into the version the evidence warns about: paying for
 * correctness, punishing lapses, or awarding things nothing can justify.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { awardsFor, rankFor, AWARDS, RANKS, MARKS, SPEND } from '../server/game/xp.mjs';
import { tierOf, deckFor, temperedBetween, bossCommissions, rarityOf, isBoss } from '../server/game/cards.mjs';
import { evaluateBadges, BADGES } from '../server/game/badges.mjs';
import { generate, progressFor, weekKey, dayKey, CATALOGUE } from '../server/game/quests.mjs';
import { updateStreak, streakMessage, DEFAULT_FREEZES } from '../server/game/streak.mjs';
import { critiqueTask, anonymise } from '../server/game/duel.mjs';
import { getTask } from '../server/content/index.mjs';
import { allMoves } from '../server/content/frameworks.mjs';

const task = { id: 't', moves: ['pmi'], domain: 'social', tier: 1 };
const scored = (over = {}) => ({ score: 0.8, hintLevel: 0, criteria: [{ id: 'a', score: 2 }], ...over });

/* --------------------------------------------------------------------- XP */

test('being right earns nothing on its own', () => {
  const perfect = awardsFor({ task, scored: scored({ score: 1, criteria: [] }), confidencePred: null });
  assert.deepEqual(perfect.lines.map((l) => l.key), ['commission', 'unaided'],
    'a flawless answer with no new ground, no honest prediction and no depth earns only turning up and working unaided');
});

test('honest calibration pays even when the work went badly', () => {
  const badButHonest = awardsFor({ task, scored: scored({ score: 0.2, criteria: [] }), confidencePred: 25 });
  const goodButCocky = awardsFor({ task, scored: scored({ score: 0.6, criteria: [] }), confidencePred: 100 });
  assert.ok(badButHonest.lines.some((l) => l.key === 'calibrated'));
  assert.ok(!goodButCocky.lines.some((l) => l.key === 'calibrated'));
});

test('the biggest single award is carrying a tool to new ground', () => {
  const behaviourAwards = ['new_domain', 'new_tool', 'unaided', 'calibrated', 'revised', 'depth', 'commission'];
  const top = behaviourAwards.reduce((best, k) => (AWARDS[k].xp > AWARDS[best].xp ? k : best), 'commission');
  assert.equal(top, 'new_domain');
});

test('awards add up and are attributable', () => {
  const out = awardsFor({
    task, scored: scored({ criteria: [{ id: 'a', score: 3 }, { id: 'b', score: 2 }] }),
    confidencePred: 75, newMoves: ['pmi'], newDomains: ['pmi'], tempered: ['PMI'], revisionGain: 0.3,
  });
  assert.equal(out.xp, out.lines.reduce((s, l) => s + l.xp, 0));
  for (const line of out.lines) assert.ok(line.certifies.length > 10, `${line.key} must say what it certifies`);
  assert.ok(out.lines.some((l) => l.key === 'revised'));
});

test('ranks are monotone and reachable in order', () => {
  for (let i = 1; i < RANKS.length; i += 1) assert.ok(RANKS[i].at > RANKS[i - 1].at);
  assert.equal(rankFor(0).name, 'Apprentice');
  assert.equal(rankFor(RANKS[2].at).name, RANKS[2].name);
  assert.equal(rankFor(999999).next, null);
  assert.ok(rankFor(RANKS[1].at + 1).progress > 0);
});

test('sparks cannot buy anything that touches learning', () => {
  const buyable = [...Object.keys(SPEND), ...MARKS.map((m) => m.key)];
  for (const key of buyable) {
    assert.ok(!/hint|score|level|answer|xp/i.test(key), `${key} looks like it buys progress`);
  }
});

/* ------------------------------------------------------------------ cards */

test('card tiers follow the platform\'s own mastery definitions', () => {
  assert.equal(tierOf(null), 'locked');
  assert.equal(tierOf({ successes: 1, unaidedSuccesses: 0, domains: ['everyday'] }), 'bronze');
  assert.equal(tierOf({ successes: 2, unaidedSuccesses: 2, domains: ['everyday'] }), 'silver');
  assert.equal(tierOf({ successes: 2, unaidedSuccesses: 0, domains: ['a', 'b'] }), 'silver');
  assert.equal(tierOf({ successes: 3, unaidedSuccesses: 2, domains: ['a', 'b'] }), 'gold',
    'gold is exactly the platform definition of a held move');
});

test('a card can only advance when the mastery advanced', () => {
  const before = [{ move: 'pmi', successes: 1, unaidedSuccesses: 1, domains: ['everyday'] }];
  const same = temperedBetween(before, before);
  assert.equal(same.length, 0);
  const after = [{ move: 'pmi', successes: 2, unaidedSuccesses: 2, domains: ['everyday', 'social'] }];
  const moved = temperedBetween(before, after);
  assert.equal(moved.length, 1);
  assert.equal(moved[0].to, 'gold');
});

test('every move has a card, and rarity reflects real practice opportunities', () => {
  const deck = deckFor([]);
  assert.equal(deck.total, allMoves().length);
  assert.equal(deck.owned, 0);
  assert.ok(['common', 'uncommon', 'rare'].includes(rarityOf('pmi')));
});

test('boss commissions gate on tools already held, and open once enough are', () => {
  const locked = bossCommissions([]);
  assert.ok(locked.length >= 3);
  assert.ok(locked.every((b) => !b.unlocked));
  const boss = locked[0];
  const held = boss.moves.map((m) => ({ move: m, successes: 3, unaidedSuccesses: 2, domains: ['a', 'b'] }));
  const opened = bossCommissions(held).find((b) => b.taskId === boss.taskId);
  assert.equal(opened.unlocked, true);
  assert.ok(isBoss(getTask(boss.taskId)));
});

/* ----------------------------------------------------------------- badges */

test('a badge is only awarded with the evidence that earned it', () => {
  const attempts = [1, 2, 3].map((i) => ({
    id: `a${i}`, taskId: `t${i}`, strand: 'argument', score: 0.8, hintLevel: 0,
    criteria: [{ id: 'warrant', score: 2 }], createdAt: `2026-08-0${i}`,
  }));
  const ctx = { attempts, indices: { calibration: { available: false } }, moveStates: [], deck: { cards: [] }, bossIds: new Set() };
  const earned = evaluateBadges(ctx);
  const warrant = earned.find((b) => b.key === 'warrant_smith');
  assert.ok(warrant, 'three warrants in three commissions should earn it');
  assert.equal(warrant.evidence.length, 3);
  for (const e of warrant.evidence) assert.ok(e.attemptId && e.taskId);
});

test('the same badge is never awarded twice', () => {
  const attempts = [1, 2, 3].map((i) => ({ id: `a${i}`, taskId: `t${i}`, strand: 'argument', score: 0.8, hintLevel: 0, criteria: [{ id: 'warrant', score: 3 }] }));
  const ctx = { attempts, indices: { calibration: { available: false } }, moveStates: [], deck: { cards: [] }, bossIds: new Set() };
  assert.equal(evaluateBadges(ctx, new Set(['warrant_smith'])).some((b) => b.key === 'warrant_smith'), false);
});

test('no badge can be earned by an empty history', () => {
  const ctx = { attempts: [], indices: { calibration: { available: false } }, moveStates: [], deck: { cards: [] }, bossIds: new Set() };
  assert.deepEqual(evaluateBadges(ctx), []);
});

test('every badge explains itself', () => {
  for (const b of BADGES) {
    assert.ok(b.blurb.length > 20, `${b.key} has no explanation`);
    assert.equal(typeof b.test, 'function');
  }
});

/* ----------------------------------------------------------------- quests */

test('quests are stable within a period and change on a re-roll', () => {
  const ctx = { deck: { owned: 3 }, newDomainEvents: [], temperEvents: [], strandsThisWeek: new Set(), bossIds: new Set(), bosses: [], duelsThisPeriod: 0 };
  const a = generate({ studentId: 's1', period: 'day', ctx }).map((q) => q.key);
  const b = generate({ studentId: 's1', period: 'day', ctx }).map((q) => q.key);
  const rerolled = generate({ studentId: 's1', period: 'day', ctx, rerolls: 1 }).map((q) => q.key);
  assert.deepEqual(a, b, 'a refresh must not reroll the quests');
  assert.notDeepEqual(a, rerolled);
  assert.equal(a.length, 3);
});

test('quests only offer what the student can actually do', () => {
  const ctx = { deck: { owned: 0 }, newDomainEvents: [], temperEvents: [], strandsThisWeek: new Set(), bossIds: new Set(), bosses: [], duelsThisPeriod: 0 };
  const keys = generate({ studentId: 's2', period: 'day', ctx }).map((q) => q.key);
  assert.ok(!keys.includes('temper'), 'you cannot be asked to temper a tool you have not forged');
  assert.ok(!keys.includes('new_ground'));
});

test('a claimed quest stays done even when the context moves on', () => {
  const quest = { key: 'temper', goal: 1, claimed: true, period: 'day' };
  const out = progressFor(quest, [], { temperEvents: [], deck: { owned: 0 } });
  assert.equal(out.done, true);
  assert.equal(out.progress, 1);
});

test('no quest pays more for a better score', () => {
  // The property that matters: above the pass bar, scoring higher must not
  // earn more. Quests may require clearing something; none may reward polish.
  const base = (score) => [{
    id: 'a1', taskId: 'lat-t1-pmi-nohomework', strand: 'lateral', domain: 'everyday', moves: ['pmi'],
    score, hintLevel: 0, confidencePred: null, revisionOf: null, createdAt: '2026-08-21T10:00:00.000Z',
    criteria: [{ id: 'x', score: 2 }],
  }];
  const ctx = { deck: { owned: 2 }, newDomainEvents: [], temperEvents: [], strandsThisWeek: new Set(), bossIds: new Set(), bosses: [], duelsThisPeriod: 0 };
  for (const q of CATALOGUE) {
    assert.ok(q.xp > 0 && q.goal > 0, `${q.key} is not worth doing`);
    const modest = q.count(base(0.65), ctx);
    const flawless = q.count(base(1), ctx);
    assert.equal(modest, flawless, `${q.key} pays more for a higher score`);
  }
});

test('period keys roll over on the right boundaries', () => {
  assert.equal(weekKey(new Date('2026-08-21T12:00:00Z')), '2026-08-17');   // Monday of that week
  assert.equal(weekKey(new Date('2026-08-17T00:00:00Z')), '2026-08-17');
  assert.equal(dayKey(new Date('2026-08-21T23:59:00Z')), '2026-08-21');
});

/* ----------------------------------------------------------------- streak */

test('a streak grows on consecutive days and holds on the same day', () => {
  const first = updateStreak({ streak: 0, longest: 0, freezes: 2, lastActiveDay: null }, '2026-08-20');
  assert.equal(first.streak, 1);
  const same = updateStreak({ ...first }, '2026-08-20');
  assert.equal(same.changed, false);
  const next = updateStreak({ ...first }, '2026-08-21');
  assert.equal(next.streak, 2);
});

test('freezes cover missed days automatically, and are spent one per day', () => {
  const out = updateStreak({ streak: 5, longest: 5, freezes: 2, lastActiveDay: '2026-08-18' }, '2026-08-20');
  assert.equal(out.streak, 6);
  assert.equal(out.usedFreezes, 1);
  assert.equal(out.freezes, 1);
  assert.match(streakMessage(out), /freeze/i);
});

test('losing a streak costs nothing but the streak, and the copy does not scold', () => {
  const before = { streak: 9, longest: 12, freezes: 0, lastActiveDay: '2026-08-01' };
  const out = updateStreak(before, '2026-08-21');
  assert.equal(out.streak, 1);
  assert.equal(out.relit, true);
  assert.equal(out.longest, 12, 'the record stands');
  const message = streakMessage(out);
  assert.match(message, /nothing you earned was lost/i);
  assert.ok(!/fail|lost your|broke|don't lose/i.test(message));
});

test('the default position is two freezes in hand', () => {
  assert.equal(DEFAULT_FREEZES, 2);
});

/* ------------------------------------------------------------------- duel */

test('the duel is scored on the critique, not on who was better', () => {
  const critique = critiqueTask(getTask('arg-t1-toulmin-lite'));
  assert.equal(critique.mode, 'structured');
  assert.deepEqual(critique.payload.fields.map((f) => f.id), ['strongest', 'missing']);
  const ids = critique.rubric.criteria.map((c) => c.id);
  assert.ok(ids.includes('steelman_fair'), 'fairness to the other person is the main criterion');
  assert.equal(Math.round(critique.rubric.criteria.reduce((s, c) => s + c.weight, 0) * 100) / 100, 1);
});

test('a peer answer is anonymised to its content', () => {
  const t = getTask('arg-t1-toulmin-lite');
  const fields = anonymise({ studentId: 'someone', response: { fields: { claim: 'a claim', evidence: 'some evidence', warrant: '' } } }, t);
  const json = JSON.stringify(fields);
  assert.ok(!json.includes('someone'));
  assert.equal(fields.length, 2, 'empty slots are not shown');
  assert.ok(fields.every((f) => f.label && f.text));
});

test('both sides of a duel earn, and neither can lose anything', () => {
  assert.ok(AWARDS.duel.xp > 0 && AWARDS.reviewed.xp > 0);
  for (const a of Object.values(AWARDS)) assert.ok(a.xp >= 0 && a.sparks >= 0, 'no award may be negative');
});
