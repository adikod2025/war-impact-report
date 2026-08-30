/**
 * L3 reconciliation — the only place a final score is produced.
 * Orchestrates: validity gate → deterministic evidence → rubric judgement
 * (AI when configured, offline otherwise) → blend, cap, confidence, flags.
 */
import { validityGate, objectiveScore, scoreCap, blendWeight, responseText, isOpenMode } from './deterministic.mjs';
import { scoreRubricOffline } from './offline-scorer.mjs';
import { RUBRIC_VERSION } from '../content/rubrics.mjs';

export const HINT_PENALTY = [0, 0.08, 0.18, 0.3];

export function hintPenalty(level) {
  return HINT_PENALTY[Math.max(0, Math.min(3, level | 0))];
}

/**
 * @param {object} task
 * @param {object} response
 * @param {object} [opts]
 * @param {function} [opts.aiRubric] async (task, response, features) => {criteria, rubricScore, model, promptHash}
 */
export async function scoreResponse(task, response = {}, opts = {}) {
  const gate = validityGate(task, response);
  if (!gate.valid) {
    return {
      valid: false, reason: gate.reason, repair: gate.repair,
      score: null, scorer: 'gate', rubricVersion: RUBRIC_VERSION,
    };
  }

  const { score: objective, detail, features } = objectiveScore(task, response);
  const { cap, applied } = scoreCap(task, response);

  let rubric = { criteria: [], rubricScore: null };
  let scorer = 'deterministic';
  let model = null;
  let promptHash = null;

  if (isOpenMode(task.mode) && task.rubric?.criteria?.length) {
    if (opts.aiRubric) {
      try {
        const ai = await opts.aiRubric(task, response, features);
        if (ai && Array.isArray(ai.criteria) && ai.criteria.length) {
          rubric = ai;
          scorer = 'ai';
          model = ai.model || null;
          promptHash = ai.promptHash || null;
        }
      } catch (err) {
        rubric = { ...scoreRubricOffline(task, response, features), error: String(err.message || err) };
        scorer = 'offline';
      }
    }
    if (scorer === 'deterministic') {
      rubric = scoreRubricOffline(task, response, features);
      scorer = 'offline';
    }
  }

  const beta = rubric.rubricScore === null ? 0 : blendWeight(task.mode);
  const objectivePart = objective === null ? rubric.rubricScore ?? 0 : objective;
  const blended = beta * (rubric.rubricScore ?? objectivePart) + (1 - beta) * objectivePart;
  const raw = Math.max(0, Math.min(cap, blended));

  // Asymmetric on purpose. A structurally complete answer that is written
  // poorly is a normal pattern, not a marking failure; the reliability concern
  // is a judge crediting quality that the structure cannot support.
  const overCredit = rubric.rubricScore !== null && objective !== null
    ? Math.max(0, rubric.rubricScore - objective) : 0;
  const underCredit = rubric.rubricScore !== null && objective !== null
    ? Math.max(0, objective - rubric.rubricScore) : 0;
  const disagreement = Math.max(overCredit, Math.max(0, underCredit - 0.35));
  const flagged = overCredit > 0.35 || underCredit > 0.6;

  const lengthAdequacy = isOpenMode(task.mode)
    ? Math.min(1, features.words / Math.max(12, (task.checks?.minWords?.response ?? 15) * 1.5))
    : 1;
  const confidence = Math.max(0.3, Math.min(1,
    (scorer === 'ai' ? 1 : scorer === 'offline' ? 0.6 : 0.95)
    * (1 - Math.min(0.3, disagreement))
    * (0.7 + 0.3 * lengthAdequacy)));

  const hintLevel = response.meta?.hintLevel || 0;
  const adjusted = Math.max(0, raw - hintPenalty(hintLevel));

  return {
    valid: true,
    score: round(raw),
    adjustedScore: round(adjusted),
    objective: objective === null ? null : round(objective),
    rubricScore: rubric.rubricScore === null ? null : round(rubric.rubricScore),
    criteria: rubric.criteria,
    cap, capsApplied: applied,
    confidence: round(confidence),
    disagreement: round(disagreement),
    flagged,
    hintLevel,
    hintPenalty: hintPenalty(hintLevel),
    aiFeedback: rubric.feedback || null,
    soloLevel: rubric.soloLevel ?? null,
    scorer, model, promptHash,
    rubricVersion: RUBRIC_VERSION,
    features,
    detail,
    text: responseText(task, response),
  };
}

const round = (x) => Math.round(x * 1e4) / 1e4;
