/**
 * The offline rubric estimator (docs/03 §A.1, "offline path").
 *
 * When no AI key is configured the platform must still work, so every rubric
 * criterion carries a `heuristic` descriptor that this module turns into a
 * 0-3 score from the deterministic feature vector. It approximates the anchors;
 * it does not pretend to reproduce them. Everything it produces is stamped
 * `scorer: "offline"` and carries lower confidence, which widens the ability
 * band rather than faking precision.
 */
import { wordCount, extractFeatures } from './text.mjs';

export const OFFLINE_CEILING = 2.5;

const band = (value, stops) => {
  // stops = [s1, s2, s3]; returns 0..3 with linear interpolation inside a band
  const [s1, s2, s3] = stops;
  if (value <= 0) return 0;
  if (value < s1) return (value / s1) * 1;
  if (value < s2) return 1 + ((value - s1) / (s2 - s1));
  if (value < s3) return 2 + ((value - s2) / (s3 - s2));
  return 3;
};

function slotsScore(task, response, features) {
  const p = task.payload || {};
  const required = task.checks?.requiredFields || (p.fields || []).filter((f) => f.required).map((f) => f.id);
  if (!required.length) return band(features.items, [1, 3, 5]);
  const fields = response.fields || {};
  let filled = 0;
  let substantial = 0;
  for (const id of required) {
    const min = (p.fields || []).find((f) => f.id === id)?.minWords ?? 3;
    const w = wordCount(fields[id]);
    if (w >= min) filled += 1;
    if (w >= min * 1.8) substantial += 1;
  }
  const base = (filled / required.length) * 2.4;
  const bonus = (substantial / required.length) * 0.6;
  return Math.min(3, base + bonus);
}

export function scoreCriterionOffline(criterion, { task, response, features }) {
  const h = criterion.heuristic || {};
  const density = features.words ? (n) => (n * 100) / Math.max(20, features.words) : () => 0;

  switch (h.type) {
    case 'slots':
      return slotsScore(task, response, features);
    case 'count': {
      const target = h.target || task.payload?.minIdeas || 4;
      const n = features.listItems ?? features.items;
      return band(n, [target * 0.5, target * 0.85, target * 1.25]);
    }
    case 'distinct': {
      const target = h.target || 4;
      const spread = features.clusters;
      const dupPenalty = features.items > 0 ? features.clusters / features.items : 1;
      return Math.min(3, band(spread, [target * 0.5, target * 0.8, target]) * (0.6 + 0.4 * dupPenalty));
    }
    case 'depth': {
      const n = Math.max(features.items, Object.keys(features.perField || {}).length);
      const min = h.min || 3;
      const depthish = features.progression * Math.min(1, n / min);
      return band(depthish, [0.3, 0.6, 0.85]);
    }
    case 'connective':
      return band(density(features.connectives), [1.2, 3, 6]);
    case 'hedge': {
      const hedged = band(density(features.hedges), [1, 2.5, 5]);
      const penalty = Math.min(1.5, features.absolutes * 0.75);
      return Math.max(0, hedged - penalty);
    }
    case 'contrast':
      return band(density(features.contrast), [1, 2.5, 5]);
    case 'novelty': {
      const fresh = 1 - features.commonIdeaShare;
      const relevant = features.conceptVocabHits > 0 || features.words > 25 ? 1 : 0.6;
      return Math.min(3, band(fresh, [0.3, 0.6, 0.85]) * relevant);
    }
    case 'specific': {
      const concrete = features.numbers + features.properNouns + features.conceptVocabHits;
      const vagueness = Math.min(1.2, features.vague * 0.4);
      return Math.max(0, band(concrete, [1, 3, 5]) - vagueness);
    }
    case 'generality': {
      const general = features.generality * 1.5 + features.connectives * 0.5;
      const copied = features.stimulusVerbatim > 0.3 ? 1 : 0;
      return Math.max(0, band(general, [0.8, 2, 3.5]) - copied);
    }
    default:
      return band(features.contentWords, [8, 25, 60]);
  }
}

/**
 * Criteria that name a slot ("warrant", "evidence_fit") are estimated against
 * that slot's own text, not the whole response — otherwise a long answer
 * dilutes the very signal the criterion is looking for.
 */
function scopedFeatures(crit, task, response, features) {
  const fields = response.fields || {};
  const explicit = crit.heuristic?.field;
  const byId = Object.prototype.hasOwnProperty.call(fields, crit.id) ? crit.id : null;
  const field = explicit || byId;
  if (!field || !fields[field]) return { features, field: null };
  const p = task.payload || {};
  const scoped = extractFeatures(fields[field], {
    stimulus: task.stimulus,
    commonIdeas: p.commonIdeas || [],
    conceptVocabulary: p.conceptVocabulary || [],
  });
  return { features: { ...scoped, perField: features.perField }, field };
}

export function scoreRubricOffline(task, response, features) {
  const criteria = task.rubric?.criteria || [];
  if (!criteria.length) return { criteria: [], rubricScore: null };
  const scored = criteria.map((crit) => {
    const scope = ['slots', 'count', 'distinct', 'depth'].includes(crit.heuristic?.type)
      ? { features, field: null }
      : scopedFeatures(crit, task, response, features);
    const raw = scoreCriterionOffline(crit, { task, response, features: scope.features });
    // The top anchor always asks for a judgement the heuristics cannot make
    // (is the warrant *really* general? is the exception *really* a threat?).
    // Offline marking is therefore capped below 3 rather than claiming it.
    const score = Math.max(0, Math.min(OFFLINE_CEILING, Math.round(raw * 10) / 10));
    return {
      id: crit.id,
      name: crit.name,
      weight: crit.weight,
      score,
      anchor: crit.anchors[String(Math.round(score))],
      anchors: crit.anchors,
      rationale: `Estimated offline from ${crit.heuristic?.type || 'text'} features${scope.field ? ` in "${scope.field}"` : ''} — no AI marker was available.`,
      evidence: null,
    };
  });
  const rubricScore = scored.reduce((sum, c) => sum + c.weight * (c.score / 3), 0);
  return { criteria: scored, rubricScore: Math.max(0, Math.min(1, rubricScore)) };
}
