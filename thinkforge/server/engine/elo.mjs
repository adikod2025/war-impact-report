/**
 * Ability and difficulty estimation.
 *
 * Elo on the logit scale, with an uncertainty-decayed K factor. Chosen over
 * IRT/BKT because it updates online after every response, needs no item
 * pre-calibration, and performs comparably to Rasch in simulation studies.
 * See docs/03 §A.4 for the reasoning, including the item-freezing mitigation
 * for the known variance-inflation failure mode.
 */

export const STUDENT_K = { a: 0.6, b: 0.05 };
export const ITEM_K = { a: 0.35, b: 0.1 };
export const ITEM_FREEZE_N = 200;
export const SECONDARY_WEIGHT = 0.35;
export const SE_FLOOR = 0.18;

export function expected(theta, difficulty) {
  return 1 / (1 + Math.exp(-(theta - difficulty)));
}

export function kFactor(n, { a, b }) {
  return a / (1 + b * Math.max(0, n));
}

/**
 * @param {object} args
 * @param {number} args.theta      current student ability (logits)
 * @param {number} args.difficulty current item difficulty (logits)
 * @param {number} args.score      scaffold-adjusted score in [0,1]
 * @param {number} args.studentN   observations for this student/strand
 * @param {number} args.itemN      observations for this item
 * @param {number} [args.confidence=1] scoring confidence, scales both updates
 * @param {number} [args.weight=1]     1 for the primary strand, 0.35 for secondary
 */
export function update({ theta, difficulty, score, studentN, itemN, confidence = 1, weight = 1 }) {
  const p = expected(theta, difficulty);
  const err = clamp01(score) - p;
  const ks = kFactor(studentN, STUDENT_K) * confidence * weight;
  const ki = itemN >= ITEM_FREEZE_N ? 0 : kFactor(itemN, ITEM_K) * confidence * weight;
  return {
    expected: p,
    error: err,
    theta: round(theta + ks * err),
    difficulty: round(difficulty - ki * err),
    studentDelta: round(ks * err),
    itemDelta: round(-ki * err),
  };
}

/** SE(θ) ≈ 1/sqrt(Σ p(1-p)), floored so a new learner never looks precise. */
export function standardError(observations) {
  let info = 0;
  for (const o of observations) {
    const p = typeof o === 'number' ? o : expected(o.theta, o.difficulty);
    info += p * (1 - p);
  }
  if (info <= 0) return 1.2;
  return Math.max(SE_FLOOR, Math.min(1.2, 1 / Math.sqrt(info)));
}

/**
 * Level only changes when the whole uncertainty band clears a cut-point, so a
 * displayed level never flickers between sessions.
 */
export function confidentLevel(theta, se, cuts) {
  let lower = 0;
  let upper = 0;
  for (const cut of cuts) {
    if (theta - se >= cut) lower += 1;
    if (theta + se >= cut) upper += 1;
  }
  return { level: lower, provisionalLevel: upper, settled: lower === upper };
}

const clamp01 = (x) => Math.max(0, Math.min(1, x));
const round = (x) => Math.round(x * 1e4) / 1e4;
