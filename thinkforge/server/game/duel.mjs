/**
 * The Forge-off (docs/04 §4.8).
 *
 * The competition-plus-collaboration combination is the moderator that actually
 * moved behavioural outcomes in the meta-analysis, so the duel is built so that
 * the only way to win is to improve someone else's thinking. Both sides earn.
 * Names are never shown.
 */
import { c } from '../content/rubrics.mjs';

export function critiqueTask(task) {
  return {
    id: `duel-${task.id}`,
    strand: task.strand,
    moves: ['steelman', 'warrant_audit'],
    tier: task.tier,
    difficulty: task.difficulty,
    domain: task.domain,
    title: `Forge-off: ${task.title}`,
    stimulus: task.stimulus,
    prompt: 'Read another apprentice’s answer to the same commission. First say the strongest thing about it — fairly enough that they would agree. Then name the one element that is missing, and why it matters.',
    mode: 'structured',
    payload: {
      fields: [
        { id: 'strongest', label: 'The strongest thing about their answer', required: true, minWords: 15 },
        { id: 'missing', label: 'The one element that is missing, and why it matters', required: true, minWords: 15 },
      ],
      conceptVocabulary: task.payload?.conceptVocabulary || [],
    },
    rubric: {
      criteria: [
        c('steelman_fair', 0.45, { name: 'You gave them their best point, not their weakest' }),
        c('warrant', 0.35, { name: 'You named a real missing element, not a style note' }),
        c('specificity', 0.2),
      ],
      solo: {
        3: 'A strength its author would recognise, plus a specific missing element with a reason.',
        4: 'The missing element is named at the level of the move — what kind of thinking is absent — rather than as a fix to one sentence.',
      },
    },
    checks: { requiredFields: ['strongest', 'missing'], capIfMissing: { missing: 0.55 } },
    hints: [
      'Read their answer twice before you write anything. What is the best sentence in it?',
      'A missing element is a kind of thinking, not a typo: an unstated warrant, no other point of view, no consequence traced, no exception admitted.',
      'Worked shape: *Strongest — "you did not just say the bus should be free, you said who it would move onto the bus." Missing — there is no rule connecting that to the claim; without it, the evidence could point either way.*',
    ],
    bridge: 'Do this to your own answer before you submit next time.',
  };
}

/** Anonymise a peer answer for display: fields only, no name, no score. */
export function anonymise(attempt, task) {
  const response = attempt.response || {};
  if (task.mode === 'structured') {
    return (task.payload?.fields || []).map((f) => ({ label: f.label, text: response.fields?.[f.id] || '' })).filter((x) => x.text);
  }
  return [{ label: 'Their answer', text: response.text || response.rule || '' }];
}
