import { h, api, store, go, md, refreshGame } from '../core.js';
import { onboarding } from './learn.js';

/**
 * The Forge-off (docs/04 §4.8): you win by improving someone else's thinking.
 * The peer's name is never fetched, let alone shown.
 */
export async function duel(params) {
  if (!store.studentId) return onboarding();
  const taskId = params[0];
  const data = await api.get(`/api/students/${store.studentId}/duel?taskId=${encodeURIComponent(taskId)}`);

  if (data.error === 'no_opponent') {
    return h('div', { class: 'card' },
      h('h2', {}, 'No opponent yet'),
      h('p', {}, data.message),
      h('button', { class: 'primary', onclick: () => go('session') }, 'Back to the session'));
  }

  const fields = {};
  const outcome = h('div');
  const inputs = data.task.payload.fields.map((f) => h('label', { class: 'field' },
    h('span', {}, f.label),
    h('textarea', { rows: '4', oninput: (e) => { fields[f.id] = e.target.value; } })));

  const submit = h('button', {
    class: 'primary',
    onclick: async () => {
      submit.disabled = true;
      submit.textContent = 'Marking…';
      const res = await api.post('/api/duel', { studentId: store.studentId, taskId, peerAttemptId: data.peerAttemptId, response: { fields } });
      submit.disabled = false;
      submit.textContent = 'Submit critique';
      if (res.valid === false) {
        outcome.replaceChildren(h('div', { class: 'notice' }, h('strong', {}, 'Not marked yet — '), res.repair));
        return;
      }
      await refreshGame();
      outcome.replaceChildren(h('div', { class: 'stack' },
        h('div', { class: 'rewards celebrate' },
          h('div', { class: 'head' }, h('span', { class: 'big' }, `+${res.earned.xp} XP`), h('span', { class: 'tag' }, `✦ ${res.earned.sparks}`)),
          h('p', { style: { margin: '6px 0 0' } }, 'Both of you earned: you for the critique, they for having their work studied. There is no winner and no ranking here.')),
        h('div', { class: 'card' },
          h('h3', {}, `Your critique scored ${Math.round(res.score * 100)}%`),
          h('div', { class: 'stack' }, (res.criteria || []).map((c) => h('div', { class: 'crit' },
            h('div', { class: 'head' }, h('span', {}, c.name), h('span', {}, `${c.score} / 3`)),
            h('small', {}, c.anchor),
            c.evidence ? h('blockquote', {}, `“${c.evidence}”`) : null))),
          h('p', { style: { marginTop: '12px' } }, res.feedback.task),
          h('p', { class: 'muted' }, res.feedback.selfRegulation)),
        h('button', { class: 'primary', onclick: () => go('session') }, 'Back to the session')));
      outcome.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
  }, 'Submit critique');

  return [
    h('div', { class: 'row between' },
      h('div', {}, h('h1', {}, 'Forge-off'), h('p', { class: 'muted' }, 'Someone else answered the same commission. Make their thinking better and you win — there is no loser here.')),
      h('button', { class: 'ghost small', onclick: () => go('session') }, '← back')),

    h('div', { class: 'card tint' },
      h('small', { class: 'muted' }, 'The original commission'),
      h('strong', {}, data.original.title),
      h('p', { class: 'muted', html: md(data.original.prompt) })),

    h('div', { class: 'spacer', style: { height: '14px' } }),
    h('div', { class: 'card' },
      h('h3', {}, 'Their answer'),
      h('small', { class: 'muted' }, 'Anonymous, and it stays that way.'),
      h('div', { class: 'duel-answer', style: { marginTop: '10px' } },
        data.peerAnswer.map((f) => h('div', { class: 'field' }, h('b', {}, f.label), f.text)))),

    h('div', { class: 'spacer', style: { height: '14px' } }),
    h('p', { class: 'prompt', html: md(data.task.prompt) }),
    h('div', {}, inputs),
    h('div', { class: 'row' }, submit),
    h('div', { class: 'spacer' }),
    outcome,
  ];
}
