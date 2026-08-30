/**
 * Trophies (docs/04 §4.4).
 *
 * Every badge is a predicate over evidence the platform already holds, and it
 * carries the attempts that earned it. If a badge cannot point at the work that
 * proves it, it is not a credential — it is a sticker, and we do not award it.
 */

const criterionHits = (attempts, id, min = 2) =>
  attempts.filter((a) => (a.criteria || []).some((c) => c.id === id && c.score >= min));

const distinctTasks = (list) => new Set(list.map((a) => a.taskId)).size;

export const BADGES = [
  {
    key: 'warrant_smith', name: 'Warrant Smith', glyph: '🔗',
    blurb: 'Stated the rule that links evidence to claim — three times, in three different commissions.',
    test: ({ attempts }) => {
      const hits = criterionHits(attempts, 'warrant');
      return distinctTasks(hits) >= 3 ? hits.slice(0, 3) : null;
    },
  },
  {
    key: 'steelmaker', name: 'Steelmaker', glyph: '🛡️',
    blurb: 'Built the strongest version of a view you disagreed with.',
    test: ({ attempts }) => {
      const hits = criterionHits(attempts, 'steelman_fair');
      return hits.length >= 1 ? hits.slice(0, 2) : null;
    },
  },
  {
    key: 'one_thing', name: 'One Thing at a Time', glyph: '🎛️',
    blurb: 'Ran an investigation where at least four in five tests changed exactly one thing.',
    test: ({ attempts }) => {
      const hits = attempts.filter((a) => (a.detail?.process?.control ?? 0) >= 0.8 && (a.detail?.process?.tests ?? 0) >= 3);
      return hits.length ? hits.slice(0, 1) : null;
    },
  },
  {
    key: 'breaker', name: 'Breaker', glyph: '🔨',
    blurb: 'Designed tests that could have proved you wrong, and ran them.',
    test: ({ attempts }) => {
      const hits = attempts.filter((a) => a.detail?.process?.discrimination === 1 && (a.detail?.process?.tests ?? 0) >= 4);
      return hits.length ? hits.slice(0, 1) : null;
    },
  },
  {
    key: 'root_finder', name: 'Root Finder', glyph: '🌳',
    blurb: 'Went past the symptom to something you could actually change — twice.',
    test: ({ attempts }) => {
      const hits = criterionHits(attempts, 'root_vs_symptom');
      return hits.length >= 2 ? hits.slice(0, 2) : null;
    },
  },
  {
    key: 'long_view', name: 'The Long View', glyph: '🔭',
    blurb: 'Followed a consequence three steps out, including one that worked against the plan.',
    test: ({ attempts }) => {
      const hits = criterionHits(attempts, 'second_order_chain');
      return hits.length >= 2 ? hits.slice(0, 2) : null;
    },
  },
  {
    key: 'sideways', name: 'Sideways', glyph: '↔️',
    blurb: 'Produced ideas outside the obvious set — and they still answered the question.',
    test: ({ attempts }) => {
      const hits = criterionHits(attempts, 'originality');
      return distinctTasks(hits) >= 3 ? hits.slice(0, 3) : null;
    },
  },
  {
    key: 'honest_dial', name: 'Honest Dial', glyph: '🎯',
    blurb: 'Knew how well you had done before you were told — across at least eight predictions.',
    test: ({ indices }) => (indices.calibration.available && indices.calibration.n >= 8 && indices.calibration.value >= 80 ? [] : null),
  },
  {
    key: 'traveller', name: 'Traveller', glyph: '🧭',
    blurb: 'Took one tool into three different kinds of situation. This is the hard one.',
    test: ({ moveStates }) => {
      const hit = moveStates.find((m) => (m.domains || []).length >= 3);
      return hit ? [] : null;
    },
  },
  {
    key: 'unaided', name: 'Own Two Hands', glyph: '✋',
    blurb: 'Five commissions in a row cleared without taking a nudge.',
    test: ({ attempts }) => {
      let run = 0;
      for (const a of attempts) {
        run = (!a.hintLevel && a.score >= 0.6) ? run + 1 : 0;
        if (run >= 5) return [a];
      }
      return null;
    },
  },
  {
    key: 'phoenix', name: 'Second Draft', glyph: '🪶',
    blurb: 'Took the coaching and made the answer genuinely better — three times.',
    test: ({ attempts }) => {
      const byId = new Map(attempts.map((a) => [a.id, a]));
      const gains = attempts.filter((a) => a.revisionOf && byId.has(a.revisionOf) && a.score - byId.get(a.revisionOf).score >= 0.15);
      return gains.length >= 3 ? gains.slice(0, 3) : null;
    },
  },
  {
    key: 'cartographer', name: 'Cartographer', glyph: '🗺️',
    blurb: 'Worked in all eight halls of the forge.',
    test: ({ attempts }) => (new Set(attempts.map((a) => a.strand)).size >= 8 ? [] : null),
  },
  {
    key: 'deck_builder', name: 'Toolmaker', glyph: '🧰',
    blurb: 'Ten tools tempered to silver or better.',
    test: ({ deck }) => (deck.cards.filter((c) => c.tierIndex >= 2).length >= 10 ? [] : null),
  },
  {
    key: 'boss_slayer', name: 'Master Commission', glyph: '🏆',
    blurb: 'Cleared a boss commission — three moves at once, at the top tier.',
    test: ({ attempts, bossIds }) => {
      const hits = attempts.filter((a) => bossIds.has(a.taskId) && a.score >= 0.6);
      return hits.length ? hits.slice(0, 1) : null;
    },
  },
];

/**
 * @returns {Array<{key,name,glyph,blurb,evidence:string[]}>} newly satisfied badges
 */
export function evaluateBadges(ctx, alreadyHeld = new Set()) {
  const earned = [];
  for (const badge of BADGES) {
    if (alreadyHeld.has(badge.key)) continue;
    let evidence;
    try {
      evidence = badge.test(ctx);
    } catch {
      evidence = null;
    }
    if (evidence) {
      earned.push({
        key: badge.key, name: badge.name, glyph: badge.glyph, blurb: badge.blurb,
        evidence: (evidence || []).map((a) => ({ attemptId: a.id, taskId: a.taskId })),
      });
    }
  }
  return earned;
}

export function badgeCatalogue(held = new Set()) {
  return BADGES.map((b) => ({ key: b.key, name: b.name, glyph: b.glyph, blurb: b.blurb, held: held.has(b.key) }));
}
