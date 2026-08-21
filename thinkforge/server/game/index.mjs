/**
 * The game layer orchestrator.
 *
 * Everything here reads the learning model rather than keeping a parallel one,
 * so the deck, the trophies and the quests cannot drift away from what the
 * student can actually do (docs/04 §2 rule 3).
 */
import { awardsFor, rankFor, AWARDS, SPEND, MARKS, RANKS } from './xp.mjs';
import { deckFor, temperedBetween, bossCommissions, isBoss, tierOf } from './cards.mjs';
import { evaluateBadges, badgeCatalogue } from './badges.mjs';
import { generate, progressFor, dayKey, weekKey, getQuest } from './quests.mjs';
import { updateStreak, streakMessage, DEFAULT_FREEZES } from './streak.mjs';

export { AWARDS, SPEND, MARKS, RANKS, rankFor, deckFor, bossCommissions, isBoss, tierOf, badgeCatalogue, dayKey, weekKey, getQuest, streakMessage, DEFAULT_FREEZES, temperedBetween, generate as generateQuests, progressFor };

/**
 * Work out what an attempt earned, given the move state before and after it.
 * Pure: the caller persists whatever comes back.
 */
export function rewardsForAttempt({ task, scored, attempt, beforeMoveStates, afterMoveStates, revisionGain = null }) {
  const before = new Map(beforeMoveStates.map((s) => [s.move, s]));

  const newMoves = task.moves.filter((m) => !before.has(m) || (before.get(m).successes + before.get(m).failures) === 0);
  const newDomains = task.moves.filter((m) => {
    const prior = before.get(m);
    const now = afterMoveStates.find((s) => s.move === m);
    if (!now) return false;
    const had = new Set(prior?.domains || []);
    return (now.domains || []).includes(task.domain) && !had.has(task.domain);
  });
  const tempered = temperedBetween(beforeMoveStates, afterMoveStates);

  const awards = awardsFor({
    task,
    scored,
    confidencePred: attempt.confidencePred ?? null,
    newMoves,
    newDomains,
    tempered: tempered.map((t) => t.name),
    revisionGain,
    isBoss: isBoss(task),
  });

  return {
    ...awards,
    newMoves,
    newDomains,
    tempered,
    isBoss: isBoss(task),
  };
}

/** Everything the game surfaces need, assembled from live state. */
export function gameProfile({ state, moveStates, attempts, indices, quests, unlocks, weekXp, duelsThisWeek = 0 }) {
  const deck = deckFor(moveStates);
  const bosses = bossCommissions(moveStates);
  const held = new Set(unlocks.filter((u) => u.kind === 'badge').map((u) => u.key));
  const rank = rankFor(state.xp);

  const today = dayKey();
  const week = weekKey();
  const todayAttempts = attempts.filter((a) => a.createdAt.slice(0, 10) === today);
  const weekAttempts = attempts.filter((a) => a.createdAt.slice(0, 10) >= week);

  const ctx = questContext({ attempts, deck, bosses, duelsThisWeek, week });

  return {
    xp: state.xp,
    sparks: state.sparks,
    rank,
    streak: { current: state.streak, longest: state.longest, freezes: state.freezes },
    weekXp,
    deck,
    bosses,
    badges: badgeCatalogue(held),
    trophies: unlocks.filter((u) => u.kind === 'badge'),
    marks: MARKS.map((m) => ({ ...m, owned: unlocks.some((u) => u.kind === 'mark' && u.key === m.key) })),
    activeMark: state.mark || null,
    leaderboardOptIn: !!state.leaderboardOptIn,
    quests: quests.map((q) => progressFor(q, q.period === 'day' ? todayAttempts : weekAttempts, ctx)),
    spend: SPEND,
  };
}

/** Shared context for quest counters — the derived facts they all need. */
export function questContext({ attempts, deck, bosses, duelsThisWeek = 0, week = weekKey(), newDomainEvents = [], temperEvents = [] }) {
  const bossIds = new Set(bosses.filter((b) => b.unlocked).map((b) => b.taskId));
  const strandsThisWeek = new Set(attempts.filter((a) => a.createdAt.slice(0, 10) >= week).map((a) => a.strand));
  return { deck, bosses, bossIds, strandsThisWeek, duelsThisPeriod: duelsThisWeek, newDomainEvents, temperEvents };
}

export function checkBadges({ attempts, indices, moveStates, deck, bosses, held }) {
  const bossIds = new Set(bosses.map((b) => b.taskId));
  return evaluateBadges({ attempts, indices, moveStates, deck, bossIds }, held);
}

export { updateStreak };
