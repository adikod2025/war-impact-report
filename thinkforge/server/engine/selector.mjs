/**
 * Adaptive selection (docs/03 Part E).
 * Target success probability is 0.75 — not 0.5 — because thinking tasks carry
 * high intrinsic load and the fading evidence favours success-with-effort over
 * maximal information gain.
 */
import { expected } from './elo.mjs';
import { reviewUrgency } from './mastery.mjs';
import { TIERS } from '../content/frameworks.mjs';

export const TARGET_P = 0.75;
export const EPSILON = 0.1;
export const WEIGHTS = { fit: 0.35, review: 0.2, novelty: 0.2, deficit: 0.15, variety: 0.1 };

function registerFit(task, age) {
  if (!task.register) return 1;
  const [lo, hi] = task.register;
  if (age >= lo && age <= hi) return 1;
  const distance = age < lo ? lo - age : age - hi;
  return Math.max(0.25, 1 - distance * 0.25);
}

/**
 * @param {object} args
 * @param {Array}  args.tasks         candidate task records
 * @param {object} args.strandTheta   { strandId: theta }
 * @param {Array}  args.history       recent attempts, newest last
 * @param {Array}  args.moveStates    per-move retention states
 * @param {number} args.age
 * @param {function} [args.random]    injectable for deterministic tests
 */
export function rankTasks({ tasks, strandTheta = {}, history = [], moveStates = [], age = 12, random = Math.random, now = Date.now() }) {
  const done = new Set(history.map((h) => h.taskId));
  const recent = history.slice(-6);
  const lastMoves = new Set((history[history.length - 1]?.moves) || []);
  const domainsByMove = new Map();
  for (const h of history) for (const m of h.moves || []) {
    if (!domainsByMove.has(m)) domainsByMove.set(m, new Set());
    domainsByMove.get(m).add(h.domain);
  }
  const thetas = Object.values(strandTheta);
  const meanTheta = thetas.length ? thetas.reduce((a, b) => a + b, 0) / thetas.length : -1;
  const sessionsSince = (strand) => {
    const idx = [...history].reverse().findIndex((h) => h.strand === strand);
    return idx === -1 ? history.length + 1 : idx;
  };

  const scored = tasks.map((task) => {
    const theta = strandTheta[task.strand] ?? -1.0;
    const p = expected(theta, task.difficulty);
    const fit = 1 - Math.abs(p - TARGET_P) / Math.max(TARGET_P, 1 - TARGET_P);

    const review = Math.max(0, ...task.moves.map((m) => {
      const st = moveStates.find((s) => s.move === m);
      return st ? reviewUrgency(st, now) : 0;
    }), 0);

    const novelty = task.moves.every((m) => !(domainsByMove.get(m)?.has(task.domain))) ? 1 : 0.3;
    const deficit = Math.max(0, Math.min(1, (meanTheta - theta + 0.5) / 1.5));
    const variety = task.moves.some((m) => lastMoves.has(m)) ? 0 : 1;
    const starvation = Math.min(1, sessionsSince(task.strand) / 10);

    const utility = WEIGHTS.fit * Math.max(0, fit)
      + WEIGHTS.review * review
      + WEIGHTS.novelty * novelty
      + WEIGHTS.deficit * deficit
      + WEIGHTS.variety * variety
      + 0.15 * starvation;

    const penalty = done.has(task.id) ? 0.6 : 0;
    const registerPenalty = 1 - registerFit(task, age);

    return {
      task,
      p: Math.round(p * 100) / 100,
      utility: Math.round((utility - penalty - registerPenalty * 0.4) * 1000) / 1000,
      parts: { fit, review, novelty, deficit, variety, starvation },
      repeat: done.has(task.id),
    };
  });

  scored.sort((a, b) => b.utility - a.utility);

  // ε-exploration keeps item difficulty estimates alive rather than letting the
  // bank calcify around whatever the model already believes.
  if (scored.length > 3 && random() < EPSILON) {
    const pick = Math.floor(random() * Math.min(6, scored.length));
    const [chosen] = scored.splice(pick, 1);
    chosen.explored = true;
    scored.unshift(chosen);
  }
  return scored;
}

export function pickTask(args) {
  const ranked = rankTasks(args);
  return ranked[0] || null;
}

export function tierForAge(age) {
  const t = TIERS.find((x) => age >= x.ages[0] && age <= x.ages[1]);
  return t ? t.tier : age < 9 ? 1 : 4;
}
