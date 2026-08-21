/**
 * Evolution tracking (docs/03 Part D).
 *
 * Six indices, each defined so it can only move for the right reason. Every one
 * reports how much evidence it rests on; an index with too little evidence
 * returns `available:false` rather than a reassuring number.
 */
import { hintPenalty } from './scoring.mjs';
import { LEVEL_CUTS, STRANDS } from '../content/frameworks.mjs';
import { confidentLevel, standardError } from './elo.mjs';

const pct = (x) => Math.round(Math.max(0, Math.min(1, x)) * 100);
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);

/**
 * Transfer: how performance holds up the first time a move is used in a domain
 * the student has not practised it in. The honest answer to "is this
 * generalising?", given that far transfer is weak by default.
 */
export function transferIndex(attempts) {
  const byMove = new Map();
  for (const a of attempts) {
    for (const move of a.moves || []) {
      if (!byMove.has(move)) byMove.set(move, []);
      byMove.get(move).push(a);
    }
  }
  const novel = [];
  const practised = [];
  for (const list of byMove.values()) {
    const ordered = [...list].sort((x, y) => new Date(x.createdAt) - new Date(y.createdAt));
    const seen = new Map();
    for (const a of ordered) {
      const n = seen.get(a.domain) || 0;
      if (n === 0 && seen.size > 0) novel.push(a.score);
      else if (n > 0) practised.push(a.score);
      seen.set(a.domain, n + 1);
    }
  }
  if (novel.length < 2 || practised.length < 2) {
    return { value: null, available: false, n: novel.length, note: 'Needs the same move used in at least two domains.' };
  }
  const ratio = mean(novel) / Math.max(0.05, mean(practised));
  return { value: pct(Math.min(1.2, ratio) / 1.2), available: true, n: novel.length, novel: mean(novel), practised: mean(practised) };
}

/** Independence: what the score would have been with no help taken. */
export function independenceIndex(attempts, window = 20) {
  const recent = attempts.slice(-window);
  if (recent.length < 3) return { value: null, available: false, n: recent.length };
  const unaided = recent.map((a) => Math.max(0, a.score - hintPenalty(a.hintLevel || 0)));
  const helpRate = mean(recent.map((a) => (a.hintLevel ? 1 : 0)));
  return { value: pct(mean(unaided)), available: true, n: recent.length, helpRate: pct(helpRate) };
}

/** Calibration: 1 − mean Brier, plus the signed over/under-confidence bias. */
export function calibrationIndex(attempts, window = 20) {
  const withPred = attempts.filter((a) => typeof a.confidencePred === 'number').slice(-window);
  if (withPred.length < 3) return { value: null, available: false, n: withPred.length };
  const briers = withPred.map((a) => ((a.confidencePred / 100) - a.score) ** 2);
  const bias = mean(withPred.map((a) => (a.confidencePred / 100) - a.score));
  return {
    value: pct(1 - mean(briers)),
    available: true,
    n: withPred.length,
    bias: Math.round(bias * 100),
    reading: bias > 0.12 ? 'over-confident' : bias < -0.12 ? 'under-confident' : 'well calibrated',
  };
}

/** Flexibility: is the whole toolkit in use, or one favourite tool? */
export function flexibilityIndex(attempts, heldMoves, window = 20) {
  const recent = attempts.slice(-window);
  if (recent.length < 4 || heldMoves.length < 2) return { value: null, available: false, n: recent.length };
  const used = new Set();
  for (const a of recent) for (const m of a.moves || []) used.add(m);
  const spread = used.size / Math.max(2, heldMoves.length);
  let switches = 0;
  let opportunities = 0;
  for (let i = 1; i < recent.length; i += 1) {
    if (recent[i - 1].score < 0.5) {
      opportunities += 1;
      const prev = new Set(recent[i - 1].moves || []);
      if ((recent[i].moves || []).some((m) => !prev.has(m))) switches += 1;
    }
  }
  const switchRate = opportunities ? switches / opportunities : 0.5;
  return { value: pct(0.7 * Math.min(1, spread) + 0.3 * switchRate), available: true, n: recent.length, movesUsed: used.size };
}

/** Originality: non-obvious *and* relevant, taken from the originality criterion. */
export function originalityIndex(attempts) {
  const scores = [];
  for (const a of attempts) {
    for (const c of a.criteria || []) if (c.id === 'originality') scores.push(c.score / 3);
  }
  if (scores.length < 2) return { value: null, available: false, n: scores.length };
  return { value: pct(mean(scores)), available: true, n: scores.length };
}

/** Revision gain: responsiveness to teaching — with a dependency warning. */
export function revisionGainIndex(attempts) {
  const pairs = [];
  const byId = new Map(attempts.map((a) => [a.id, a]));
  for (const a of attempts) {
    if (a.revisionOf && byId.has(a.revisionOf)) pairs.push([byId.get(a.revisionOf), a]);
  }
  if (pairs.length < 2) return { value: null, available: false, n: pairs.length };
  const gains = pairs.map(([first, rev]) => rev.score - first.score);
  const firstAttempts = mean(pairs.map(([first]) => first.score));
  const gain = mean(gains);
  return {
    value: pct(0.5 + gain / 2),
    available: true,
    n: pairs.length,
    rawGain: Math.round(gain * 100),
    dependency: gain > 0.25 && firstAttempts < 0.45,
  };
}

export function indices(attempts, heldMoves = []) {
  return {
    transfer: transferIndex(attempts),
    independence: independenceIndex(attempts),
    calibration: calibrationIndex(attempts),
    flexibility: flexibilityIndex(attempts, heldMoves),
    originality: originalityIndex(attempts),
    revisionGain: revisionGainIndex(attempts),
  };
}

/** Per-strand level with its uncertainty band. */
export function strandProfile(strandStates, attemptsByStrand = {}) {
  return STRANDS.map((s) => {
    const st = strandStates.find((x) => x.strand === s.id) || { theta: -1.0, n: 0 };
    const obs = (attemptsByStrand[s.id] || []).map((a) => ({ theta: st.theta, difficulty: a.difficulty ?? 0 }));
    const se = st.n ? standardError(obs.length ? obs : [{ theta: st.theta, difficulty: st.theta }]) : 1.2;
    const lvl = confidentLevel(st.theta, se, LEVEL_CUTS);
    return {
      strand: s.id, name: s.name, colour: s.colour, claim: s.claim,
      theta: Math.round(st.theta * 100) / 100,
      se: Math.round(se * 100) / 100,
      n: st.n || 0,
      ...lvl,
    };
  });
}

export function buildSnapshot({ strandStates, attempts, heldMoves, minutes = 0, attemptsByStrand }) {
  const profile = strandProfile(strandStates, attemptsByStrand);
  return {
    at: new Date().toISOString(),
    strands: profile.map((p) => ({ strand: p.strand, theta: p.theta, se: p.se, level: p.level, n: p.n })),
    indices: indices(attempts, heldMoves),
    movesHeld: heldMoves.length,
    attempts: attempts.length,
    minutes,
  };
}

/** Deterministic growth story, used when no AI key is configured. */
export function templateNarrative(current, previous) {
  if (!previous) {
    return {
      headline: 'First snapshot saved.',
      body: 'There is nothing to compare against yet. Come back after a few sessions and this will show what moved.',
      next: 'Do one session in a strand you have not touched.',
      source: 'template',
    };
  }
  const deltas = current.strands.map((s) => {
    const before = previous.strands.find((p) => p.strand === s.strand);
    return { strand: s.strand, delta: s.theta - (before?.theta ?? s.theta), level: s.level };
  }).sort((a, b) => b.delta - a.delta);
  const top = deltas[0];
  const bottom = deltas[deltas.length - 1];
  const name = (id) => STRANDS.find((s) => s.id === id)?.name || id;
  return {
    headline: top && top.delta > 0.05
      ? `${name(top.strand)} moved the most this week.`
      : 'Steady week — nothing moved much in either direction.',
    body: `${name(top.strand)} is at level ${top.level}. ${bottom && bottom.delta < -0.05 ? `${name(bottom.strand)} slipped a little — worth a review session.` : 'Nothing slipped.'}`,
    next: bottom ? `Next: a session in ${name(bottom.strand)}.` : 'Next: keep going.',
    source: 'template',
  };
}
