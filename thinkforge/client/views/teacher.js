import { h, api, fmtDate } from '../core.js';

const HEAT = ['#d8d4cc', '#b9c7e8', '#8aa8e0', '#5b83d6', '#3b5fc0', '#24408f'];

export async function teacher() {
  const data = await api.get('/api/teacher/cohort');
  const strandIds = data.students[0]?.strands.map((s) => s.strand) || [];

  return [
    h('h1', {}, 'Class view'),
    h('p', { class: 'muted prompt' }, 'Levels, the marking that needs your eyes, and the one thing your class is collectively missing.'),
    h('div', { class: 'spacer' }),

    h('div', { class: 'card' }, h('h3', {}, 'Where the class is'),
      h('div', { class: 'scroll-x' }, h('table', {},
        h('thead', {}, h('tr', {}, h('th', {}, 'Learner'), strandIds.map((s) => h('th', {}, s)), h('th', {}, 'Missions'), h('th', {}, 'Last active'))),
        h('tbody', {}, data.students.length ? data.students.map((s) => h('tr', {},
          h('td', {}, h('strong', {}, s.displayName), h('br'), h('small', {}, `age ${s.age}`)),
          s.strands.map((x) => h('td', {}, h('div', {
            class: 'heat',
            style: { background: HEAT[x.level] || HEAT[0], color: x.level > 1 ? '#fff' : '#16150f' },
            title: `${x.strand}: level ${x.level} (theta ${x.theta}, ${x.n} missions)`,
          }, String(x.level)))),
          h('td', {}, String(s.attempts)),
          h('td', {}, fmtDate(s.lastActive)))) : h('tr', {}, h('td', { colspan: '10', class: 'muted' }, 'No learners yet.')))))),

    h('div', { class: 'spacer' }),
    h('div', { class: 'grid two' },
      h('div', { class: 'card' }, h('h3', {}, 'What the class is missing'),
        data.missingElement.length
          ? h('div', { class: 'stack' }, data.missingElement.map((m) => h('div', {},
            h('div', { class: 'row between' }, h('strong', {}, m.name), h('span', { class: 'tag' }, `${m.students} of ${m.of}`)),
            h('div', { style: { height: '8px', background: 'var(--surface-2)', borderRadius: '999px', overflow: 'hidden' } },
              h('div', { style: { width: `${(m.students / Math.max(1, m.of)) * 100}%`, height: '100%', background: 'var(--accent)' } })))))
          : h('p', { class: 'muted' }, 'Nothing yet — this fills in once the class has submitted work.'),
        h('small', { class: 'muted' }, 'Criteria where a learner scored 0 or 1 at least once. This is the readout that should decide your next lesson.')),

      h('div', { class: 'card' }, h('h3', {}, 'Safety flags'),
        data.safety.length
          ? h('div', { class: 'stack' }, data.safety.map((f) => h('div', { class: 'notice safety' },
            h('strong', {}, f.level), ' — ', fmtDate(f.created_at),
            h('div', {}, h('small', {}, 'The learner was shown a message directing them to a trusted adult; the AI did not attempt to handle it.')),
            h('button', {
              class: 'small',
              onclick: async (e) => { await api.post(`/api/teacher/flags/${f.id}/resolve`); e.target.closest('.notice').remove(); },
            }, 'Mark seen'))))
          : h('p', { class: 'muted' }, 'None. Distress, safeguarding disclosures and off-scope messages are caught before they reach the model and land here.'))),

    h('div', { class: 'spacer' }),
    h('div', { class: 'card' }, h('h3', {}, 'Marking that needs your eyes'),
      h('small', { class: 'muted' }, 'Anything the marker was not confident about, or where the structure and the writing quality disagreed. Your score replaces the machine’s and feeds back into how hard the task is rated.'),
      h('div', { class: 'stack', style: { marginTop: '12px' } },
        data.reviewQueue.length ? data.reviewQueue.map(reviewRow) : h('p', { class: 'muted' }, 'Queue is empty.'))),
  ];
}

function reviewRow(a) {
  const input = h('input', { type: 'number', min: '0', max: '100', step: '5', value: String(Math.round(a.score * 100)), style: { maxWidth: '110px' } });
  const note = h('input', { type: 'text', placeholder: 'why (optional)' });
  const row = h('div', { class: 'card tint' },
    h('div', { class: 'row between' },
      h('strong', {}, a.taskTitle || a.taskId),
      h('div', { class: 'pill-row' },
        h('span', { class: 'tag' }, `${Math.round(a.score * 100)}%`),
        h('span', { class: `tag ${a.confidence < 0.5 ? 'warn' : ''}` }, `confidence ${Math.round(a.confidence * 100)}%`),
        h('span', { class: 'tag' }, a.scorer))),
    h('details', {}, h('summary', {}, 'The learner’s answer'),
      h('pre', { class: 'mono', style: { whiteSpace: 'pre-wrap' } }, JSON.stringify(a.response?.fields || a.response?.text || a.response, null, 1))),
    h('div', { class: 'stack' }, (a.criteria || []).map((c) => h('small', {}, `${c.name}: ${c.score}/3 — ${c.anchor}`))),
    h('div', { class: 'row' }, input, note, h('button', {
      class: 'primary small',
      onclick: async () => {
        await api.post('/api/teacher/override', { attemptId: a.id, score: Number(input.value) / 100, note: note.value });
        row.replaceChildren(h('p', { class: 'muted' }, 'Re-scored. The learner’s level has been recalculated.'));
      },
    }, 'Re-score')));
  return row;
}
