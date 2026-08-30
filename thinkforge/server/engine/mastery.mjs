/**
 * Retention and spaced review (docs/03 §D.1).
 * A held move decays; the scheduler resurfaces the move whose predicted recall
 * is closest to 0.85 — effortful but successful retrieval — rather than
 * whatever happens to be most overdue.
 */
export const H0 = 1.4;            // days
export const TARGET_RECALL = 0.85;
export const MIN_H = 0.5;
export const MAX_H = 120;

export function halfLife({ successes = 0, failures = 0, level = 0 } = {}) {
  const h = H0 * 2 ** (0.6 * successes - 0.9 * failures + 0.4 * level);
  return Math.max(MIN_H, Math.min(MAX_H, h));
}

export function recall(h, daysSince) {
  if (!(h > 0)) return 0;
  return 2 ** (-Math.max(0, daysSince) / h);
}

export function daysBetween(then, now = Date.now()) {
  return Math.max(0, (now - new Date(then).getTime()) / 86400000);
}

/**
 * How badly this move wants revisiting right now, in [0,1].
 *
 * A tent peaking at TARGET_RECALL: something just practised is not urgent
 * (recall 1 -> 0), something at the edge of forgetting is (recall 0.85 -> 1),
 * and something already lost falls away again — a move the student can no
 * longer retrieve needs re-teaching, not a review item.
 */
export function reviewUrgency(state, now = Date.now()) {
  if (!state?.lastSeen) return 0;
  const r = recall(halfLife(state), daysBetween(state.lastSeen, now));
  if (r >= TARGET_RECALL) return Math.max(0, (1 - r) / (1 - TARGET_RECALL));
  return Math.max(0, r / TARGET_RECALL);
}

export function nextReviewAt(state, now = Date.now()) {
  const h = halfLife(state);
  const days = h * Math.log2(1 / TARGET_RECALL);
  return new Date(now + days * 86400000).toISOString();
}

/** A move is "held" once it has been done well twice, in two domains, unaided. */
export function isHeld(state) {
  return !!state && state.unaidedSuccesses >= 2 && (state.domains?.length || 0) >= 2;
}

export function rankReviews(moveStates, now = Date.now()) {
  return [...moveStates]
    .map((s) => ({ move: s.move, urgency: reviewUrgency(s, now), recall: recall(halfLife(s), daysBetween(s.lastSeen, now)) }))
    .sort((a, b) => b.urgency - a.urgency);
}
