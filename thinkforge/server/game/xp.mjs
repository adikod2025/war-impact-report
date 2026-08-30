/**
 * XP, ranks and sparks (docs/04 §4.1-4.2).
 *
 * The whole table is built on one rule: nothing pays for being right. Awards
 * are attached to the behaviours the platform exists to build, so the cheapest
 * route to XP is also the most useful thing the student could be doing.
 */

export const AWARDS = {
  commission: { xp: 10, sparks: 2, label: 'Commission completed', certifies: 'You produced something markable.' },
  new_tool: { xp: 25, sparks: 2, label: 'New tool used', certifies: 'A move you had never used before.' },
  new_domain: { xp: 30, sparks: 3, label: 'Tool carried somewhere new', certifies: 'You used a move in a kind of situation you had never used it in.' },
  unaided: { xp: 15, sparks: 1, label: 'Unaided clear', certifies: 'You cleared it without taking a nudge.' },
  calibrated: { xp: 20, sparks: 2, label: 'Honest dial', certifies: 'Your prediction was within 10 points of the outcome.' },
  revised: { xp: 20, sparks: 2, label: 'Revised and improved', certifies: 'Your revision was meaningfully better than your first attempt.' },
  depth: { xp: 15, sparks: 1, label: 'Depth reached', certifies: 'Every part of the rubric was doing work.' },
  tempered: { xp: 40, sparks: 4, label: 'Tool tempered', certifies: 'A card advanced a tier — that is real mastery, not a purchase.' },
  boss: { xp: 100, sparks: 10, label: 'Boss commission cleared', certifies: 'A multi-move commission at the top tier.' },
  quest: { xp: 0, sparks: 3, label: 'Quest completed', certifies: 'A behaviour you chose to go after.' },
  duel: { xp: 35, sparks: 4, label: 'Forge-off', certifies: 'You improved someone else’s thinking.' },
  reviewed: { xp: 10, sparks: 1, label: 'Work reviewed', certifies: 'Another apprentice studied your answer.' },
};

export const RANKS = [
  { key: 'apprentice', name: 'Apprentice', at: 0, mark: '◇' },
  { key: 'smith', name: 'Smith', at: 500, mark: '◆' },
  { key: 'journeyman', name: 'Journeyman', at: 1500, mark: '❖' },
  { key: 'artisan', name: 'Artisan', at: 3500, mark: '✦' },
  { key: 'master', name: 'Master', at: 7000, mark: '✧' },
  { key: 'forgemaster', name: 'Forgemaster', at: 12000, mark: '✶' },
];

export const CALIBRATION_WINDOW = 10;   // percentage points
export const REVISION_THRESHOLD = 0.15;
export const UNAIDED_SCORE = 0.6;
export const DEPTH_CRITERION = 2;

export function rankFor(xp) {
  let current = RANKS[0];
  for (const r of RANKS) if (xp >= r.at) current = r;
  const next = RANKS[RANKS.indexOf(current) + 1] || null;
  const span = next ? next.at - current.at : 1;
  return {
    ...current,
    next: next ? { name: next.name, at: next.at, mark: next.mark } : null,
    toNext: next ? next.at - xp : 0,
    progress: next ? Math.max(0, Math.min(1, (xp - current.at) / span)) : 1,
  };
}

/**
 * Decide what a completed attempt earned.
 *
 * @param {object} ctx
 * @param {object} ctx.task
 * @param {object} ctx.scored           result of engine/scoring
 * @param {number|null} ctx.confidencePred
 * @param {string[]} ctx.newMoves       moves used for the very first time
 * @param {string[]} ctx.newDomains     moves used in a domain new for that move
 * @param {string[]} ctx.tempered       cards that advanced a tier
 * @param {number|null} ctx.revisionGain
 * @param {boolean} ctx.isBoss
 * @returns {{lines: Array, xp: number, sparks: number}}
 */
export function awardsFor({ task, scored, confidencePred = null, newMoves = [], newDomains = [], tempered = [], revisionGain = null, isBoss = false }) {
  const lines = [];
  const add = (key, detail = null, times = 1) => {
    const a = AWARDS[key];
    for (let i = 0; i < times; i += 1) lines.push({ key, xp: a.xp, sparks: a.sparks, label: a.label, certifies: a.certifies, detail });
  };

  add('commission');
  for (const m of newMoves) add('new_tool', m);
  for (const m of newDomains) add('new_domain', `${m} → ${task.domain}`);
  for (const m of tempered) add('tempered', m);

  if (!scored.hintLevel && scored.score >= UNAIDED_SCORE) add('unaided');

  // Calibration pays whether the score was high or low: the thing being
  // rewarded is honesty about your own performance, not the performance.
  if (confidencePred !== null && Math.abs(confidencePred - scored.score * 100) <= CALIBRATION_WINDOW) {
    add('calibrated', `predicted ${confidencePred}%, scored ${Math.round(scored.score * 100)}%`);
  }

  if (revisionGain !== null && revisionGain >= REVISION_THRESHOLD) {
    add('revised', `+${Math.round(revisionGain * 100)} points on the revision`);
  }

  const criteria = scored.criteria || [];
  if (criteria.length && criteria.reduce((s, c) => s + c.score, 0) / criteria.length >= DEPTH_CRITERION) add('depth');

  if (isBoss && scored.score >= UNAIDED_SCORE) add('boss');

  return {
    lines,
    xp: lines.reduce((s, l) => s + l.xp, 0),
    sparks: lines.reduce((s, l) => s + l.sparks, 0),
  };
}

export const SPEND = {
  freeze: { cost: 15, label: 'Streak freeze', blurb: 'Keeps the forge lit on a day you miss.' },
  free_choice: { cost: 12, label: 'Free choice', blurb: 'Pick any commission you like, outside today’s session.' },
};

export const MARKS = [
  { key: 'ember', name: 'Ember', cost: 60, glyph: '🔥', colour: '#f59e0b' },
  { key: 'anvil', name: 'Anvil', cost: 60, glyph: '⚒️', colour: '#64748b' },
  { key: 'prism', name: 'Prism', cost: 90, glyph: '🔷', colour: '#3b82f6' },
  { key: 'loop', name: 'Loop', cost: 90, glyph: '🌀', colour: '#14b8a6' },
  { key: 'quill', name: 'Quill', cost: 140, glyph: '🪶', colour: '#a855f7' },
  { key: 'crown', name: 'Crown', cost: 140, glyph: '👑', colour: '#eab308' },
];
