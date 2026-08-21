/**
 * Quests (docs/04 §4.5): three daily, one weekly, chosen from behaviours that
 * are worth doing anyway. Re-rollable, because choosing what to work on is the
 * autonomy lever, and never time-limited within the day.
 */

export const CATALOGUE = [
  {
    key: 'new_ground', period: 'day', goal: 1, xp: 40,
    label: 'New ground', blurb: 'Use a tool in a kind of situation you have not used it in before.',
    count: (attempts, ctx) => attempts.filter((a) => (a.moves || []).some((m) => ctx.newDomainEvents.some((e) => e.attemptId === a.id && e.move === m))).length,
    eligible: (ctx) => ctx.deck.owned >= 1,
  },
  {
    key: 'call_it', period: 'day', goal: 2, xp: 30,
    label: 'Call it', blurb: 'Predict your own score within 10 points — twice. Being right about a low score counts.',
    count: (attempts) => attempts.filter((a) => a.confidencePred !== null && Math.abs(a.confidencePred - a.score * 100) <= 10).length,
  },
  {
    key: 'second_draft', period: 'day', goal: 1, xp: 30,
    label: 'Second draft', blurb: 'Talk one answer through with the coach, then revise it.',
    count: (attempts) => attempts.filter((a) => a.revisionOf).length,
  },
  {
    key: 'own_two_hands', period: 'day', goal: 2, xp: 30,
    label: 'Own two hands', blurb: 'Clear two commissions without taking a nudge.',
    count: (attempts) => attempts.filter((a) => !a.hintLevel && a.score >= 0.6).length,
  },
  {
    key: 'other_hall', period: 'day', goal: 1, xp: 25,
    label: 'Another hall', blurb: 'Work in a hall you have not visited this week.',
    count: (attempts, ctx) => attempts.filter((a) => !ctx.strandsThisWeek.has(a.strand)).length,
  },
  {
    key: 'temper', period: 'day', goal: 1, xp: 45,
    label: 'Temper a tool', blurb: 'Advance one card a tier.',
    count: (attempts, ctx) => ctx.temperEvents.filter((e) => attempts.some((a) => a.id === e.attemptId)).length,
    eligible: (ctx) => ctx.deck.owned >= 1,
  },
  {
    key: 'deep_work', period: 'day', goal: 1, xp: 35,
    label: 'Deep work', blurb: 'Score at least 2 of 3 on every part of one rubric.',
    count: (attempts) => attempts.filter((a) => (a.criteria || []).length && a.criteria.every((c) => c.score >= 2)).length,
  },
  {
    key: 'forge_off', period: 'week', goal: 1, xp: 60,
    label: 'Forge-off', blurb: 'Take on one peer critique — win it by improving someone else’s thinking.',
    count: (attempts, ctx) => ctx.duelsThisPeriod,
  },
  {
    key: 'five_days', period: 'week', goal: 4, xp: 80,
    label: 'Keep the forge lit', blurb: 'Work on four different days this week.',
    count: (attempts) => new Set(attempts.map((a) => a.createdAt.slice(0, 10))).size,
  },
  {
    key: 'three_halls', period: 'week', goal: 3, xp: 70,
    label: 'Three halls', blurb: 'Work in three different halls this week.',
    count: (attempts) => new Set(attempts.map((a) => a.strand)).size,
  },
  {
    key: 'boss', period: 'week', goal: 1, xp: 120,
    label: 'Take a boss commission', blurb: 'Clear a three-move commission at the top tier.',
    count: (attempts, ctx) => attempts.filter((a) => ctx.bossIds.has(a.taskId) && a.score >= 0.6).length,
    eligible: (ctx) => ctx.bosses.some((b) => b.unlocked),
  },
];

const BY_KEY = new Map(CATALOGUE.map((q) => [q.key, q]));
export const getQuest = (key) => BY_KEY.get(key) || null;

export const dayKey = (d = new Date()) => new Date(d).toISOString().slice(0, 10);
export function weekKey(d = new Date()) {
  const date = new Date(d);
  const day = (date.getUTCDay() + 6) % 7;                       // Monday = 0
  date.setUTCDate(date.getUTCDate() - day);
  return date.toISOString().slice(0, 10);
}

/** Deterministic per student per period, so a refresh cannot reroll for free. */
function pick(pool, seed, n) {
  const scored = pool.map((q, i) => ({ q, r: hash(`${seed}:${q.key}:${i}`) })).sort((a, b) => a.r - b.r);
  return scored.slice(0, n).map((x) => x.q);
}

function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i += 1) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return (h >>> 0) / 4294967295;
}

export function generate({ studentId, period, ctx, rerolls = 0, now = new Date() }) {
  const pool = CATALOGUE.filter((q) => q.period === period && (!q.eligible || q.eligible(ctx)));
  const key = period === 'day' ? dayKey(now) : weekKey(now);
  return pick(pool, `${studentId}:${key}:${rerolls}`, period === 'day' ? 3 : 1)
    .map((q) => ({ key: q.key, period, label: q.label, blurb: q.blurb, goal: q.goal, xp: q.xp, periodKey: key }));
}

export function progressFor(quest, attempts, ctx) {
  const def = BY_KEY.get(quest.key);
  if (!def) return { ...quest, progress: 0, done: false };
  // A claimed quest stays done: its evidence was the moment it was awarded, and
  // recomputing it later from a different context would make it flicker.
  if (quest.claimed) return { ...quest, progress: quest.goal, done: true };
  let progress = 0;
  try {
    progress = def.count(attempts, ctx) || 0;
  } catch {
    progress = 0;
  }
  return { ...quest, progress: Math.min(progress, quest.goal), done: progress >= quest.goal };
}
