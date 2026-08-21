/**
 * Streaks (docs/04 §4.6).
 *
 * The commitment device stays; the loss aversion is defanged. Freezes are
 * consumed automatically for missed days, nothing already earned is ever taken
 * away, and a lapse is described as a forge relit rather than a failure. There
 * are no notifications and no countdowns anywhere in the product.
 */
export const DEFAULT_FREEZES = 2;
export const MAX_FREEZES = 5;

const DAY = 86400000;
export const dayKey = (d = new Date()) => new Date(d).toISOString().slice(0, 10);
const daysApart = (a, b) => Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / DAY);

/**
 * @param {{streak:number, longest:number, freezes:number, lastActiveDay:string|null}} state
 * @param {string} today  ISO date key
 */
export function updateStreak(state, today = dayKey()) {
  const streak = state.streak || 0;
  const freezes = state.freezes ?? DEFAULT_FREEZES;
  const longest = state.longest || 0;
  const last = state.lastActiveDay;

  if (last === today) {
    return { streak, longest, freezes, lastActiveDay: today, changed: false, usedFreezes: 0, relit: false };
  }
  if (!last) {
    return { streak: 1, longest: Math.max(1, longest), freezes, lastActiveDay: today, changed: true, usedFreezes: 0, relit: false };
  }

  const gap = daysApart(last, today);
  const missed = Math.max(0, gap - 1);

  if (missed === 0) {
    const next = streak + 1;
    return { streak: next, longest: Math.max(next, longest), freezes, lastActiveDay: today, changed: true, usedFreezes: 0, relit: false };
  }
  if (missed <= freezes) {
    const next = streak + 1;
    return {
      streak: next, longest: Math.max(next, longest), freezes: freezes - missed,
      lastActiveDay: today, changed: true, usedFreezes: missed, relit: false,
    };
  }
  return { streak: 1, longest, freezes, lastActiveDay: today, changed: true, usedFreezes: 0, relit: true };
}

export function streakMessage(result) {
  if (!result.changed) return 'The forge is lit today.';
  if (result.relit) return 'The forge had gone cold — it is lit again. Nothing you earned was lost.';
  if (result.usedFreezes) return `A freeze covered ${result.usedFreezes} missed day${result.usedFreezes === 1 ? '' : 's'}. Streak intact: ${result.streak}.`;
  return `${result.streak} day${result.streak === 1 ? '' : 's'} in a row.`;
}
