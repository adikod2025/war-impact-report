/**
 * The deck (docs/04 §4.3).
 *
 * A card is not a collectible awarded for playing; it is the student's mastery
 * of one move, rendered. The tier conditions are the platform's existing
 * definitions, so a card cannot be farmed without the learning happening.
 */
import { STRANDS, allMoves, getMove } from '../content/frameworks.mjs';
import { TASKS } from '../content/index.mjs';

export const TIERS = ['locked', 'bronze', 'silver', 'gold'];

const TEACHING_COUNT = new Map();
for (const t of TASKS) for (const m of t.moves) TEACHING_COUNT.set(m, (TEACHING_COUNT.get(m) || 0) + 1);

export function rarityOf(moveId) {
  const n = TEACHING_COUNT.get(moveId) || 0;
  if (n >= 3) return 'common';
  if (n === 2) return 'uncommon';
  return 'rare';
}

export function tierOf(state) {
  if (!state || (state.successes || 0) === 0) return 'locked';
  const unaided = state.unaidedSuccesses || 0;
  const domains = (state.domains || []).length;
  if (unaided >= 2 && domains >= 2) return 'gold';
  if (unaided >= 2 || domains >= 2) return 'silver';
  return 'bronze';
}

export function nextTierCondition(state) {
  const tier = tierOf(state);
  const unaided = state?.unaidedSuccesses || 0;
  const domains = (state?.domains || []).length;
  switch (tier) {
    case 'locked': return 'Clear a commission using this tool.';
    case 'bronze': return unaided < 2
      ? `Clear it unaided ${2 - unaided} more time${2 - unaided === 1 ? '' : 's'}, or use it in another kind of situation.`
      : 'Use it in another kind of situation.';
    case 'silver': return unaided < 2
      ? `Clear it unaided ${2 - unaided} more time${2 - unaided === 1 ? '' : 's'}.`
      : `Use it in ${2 - domains} more kind${2 - domains === 1 ? '' : 's'} of situation.`;
    default: return 'Fully tempered. Take it into a boss commission.';
  }
}

/** The whole deck for one student, grouped by hall (strand). */
export function deckFor(moveStates = []) {
  const byMove = new Map(moveStates.map((s) => [s.move, s]));
  const cards = allMoves().map((move) => {
    const state = byMove.get(move.id);
    const tier = tierOf(state);
    return {
      id: move.id,
      name: move.name,
      strand: move.strand,
      origin: move.origin,
      how: move.how,
      artefact: move.artefact,
      rarity: rarityOf(move.id),
      tier,
      tierIndex: TIERS.indexOf(tier),
      unaided: state?.unaidedSuccesses || 0,
      domains: state?.domains || [],
      uses: (state?.successes || 0) + (state?.failures || 0),
      next: nextTierCondition(state),
      teachingTasks: TEACHING_COUNT.get(move.id) || 0,
    };
  });
  return {
    cards,
    halls: STRANDS.map((s) => ({
      strand: s.id, name: s.name, colour: s.colour,
      owned: cards.filter((c) => c.strand === s.id && c.tier !== 'locked').length,
      total: cards.filter((c) => c.strand === s.id).length,
      gold: cards.filter((c) => c.strand === s.id && c.tier === 'gold').length,
    })),
    owned: cards.filter((c) => c.tier !== 'locked').length,
    gold: cards.filter((c) => c.tier === 'gold').length,
    total: cards.length,
  };
}

/** Cards that advanced a tier between two snapshots of move state. */
export function temperedBetween(before = [], after = []) {
  const beforeMap = new Map(before.map((s) => [s.move, tierOf(s)]));
  const out = [];
  for (const state of after) {
    const was = beforeMap.get(state.move) || 'locked';
    const now = tierOf(state);
    if (TIERS.indexOf(now) > TIERS.indexOf(was)) {
      out.push({ move: state.move, name: getMove(state.move)?.name || state.move, from: was, to: now });
    }
  }
  return out;
}

/**
 * A boss commission is a top-tier task that combines moves. It unlocks once the
 * student holds about half of them at silver or better, so it is a culmination
 * of work already done rather than a wall to grind against.
 */
export const bossRequirement = (task) => Math.max(1, Math.ceil(task.moves.length / 2));

export function bossCommissions(moveStates = []) {
  const held = new Set(moveStates.filter((s) => ['gold', 'silver'].includes(tierOf(s))).map((s) => s.move));
  return TASKS.filter(isBoss).map((t) => {
    const have = t.moves.filter((m) => held.has(m));
    const need = bossRequirement(t);
    return {
      taskId: t.id, title: t.title, strand: t.strand, moves: t.moves,
      moveNames: t.moves.map((m) => getMove(m)?.name || m),
      have: have.length, need,
      unlocked: have.length >= need,
      missing: t.moves.filter((m) => !held.has(m)).map((m) => getMove(m)?.name || m),
    };
  });
}

export function isBoss(task) {
  return task.tier === 4 && task.moves.length >= 2;
}
