import { h, api, store, go, dial, fmtDate, LEVEL_NAMES } from '../core.js';
import { indexPanel, onboarding } from './learn.js';

export async function growth() {
  if (!store.studentId) return onboarding();
  const [profile, snaps] = await Promise.all([
    api.get(`/api/students/${store.studentId}`),
    api.get(`/api/students/${store.studentId}/snapshots`),
  ]);
  const latest = snaps.snapshots[0];

  const takeSnapshot = h('button', {
    class: 'primary',
    onclick: async (e) => { e.target.disabled = true; e.target.textContent = 'Writing…'; await api.post(`/api/students/${store.studentId}/snapshot`); go('growth'); },
  }, 'Save this week’s snapshot');

  return [
    h('div', { class: 'row between' },
      h('div', {}, h('h1', {}, 'How your thinking is changing'),
        h('p', { class: 'muted' }, 'Not points. Six things that can only move for the right reason.')),
      takeSnapshot),
    h('div', { class: 'spacer' }),

    latest?.story ? h('div', { class: 'card strand-edge', style: { '--strand': 'var(--accent)' } },
      h('h3', {}, latest.story.headline),
      h('p', {}, latest.story.body),
      h('p', {}, h('strong', {}, 'Next: '), latest.story.next),
      h('small', { class: 'muted' }, latest.story.source === 'ai'
        ? 'Written by the AI from your own work and your own numbers.'
        : 'Written from your numbers by a fixed template (no AI configured).')) : null,

    h('div', { class: 'spacer' }),
    indexPanel(profile.indices, { title: 'The six growth indices' }),
    h('div', { class: 'spacer' }),

    h('div', { class: 'grid two' },
      h('div', { class: 'card' }, h('h3', {}, 'Strand by strand'),
        h('div', { class: 'stack' }, profile.strands.map((s) => dial({ ...s, levelName: LEVEL_NAMES[s.level] })))),
      h('div', { class: 'card' }, h('h3', {}, 'Your moves'),
        h('div', { class: 'scroll-x' }, h('table', {},
          h('thead', {}, h('tr', {}, h('th', {}, 'Move'), h('th', {}, 'Done'), h('th', {}, 'Unaided'), h('th', {}, 'Domains'), h('th', {}, 'Due'))),
          h('tbody', {}, profile.moves.length ? profile.moves.map((m) => h('tr', {},
            h('td', {}, m.name, m.held ? h('span', { class: 'tag good', style: { marginLeft: '6px' } }, 'held') : null),
            h('td', {}, String(m.successes + m.failures)),
            h('td', {}, String(m.unaidedSuccesses)),
            h('td', {}, (m.domains || []).join(', ') || '—'),
            h('td', {}, fmtDate(m.dueAt)))) : h('tr', {}, h('td', { colspan: '5', class: 'muted' }, 'Nothing yet.'))))))),

    h('div', { class: 'spacer' }),
    h('div', { class: 'card' }, h('h3', {}, 'Snapshots'),
      snaps.snapshots.length
        ? h('div', { class: 'timeline' }, snaps.snapshots.map((s) => h('div', { class: 'entry' },
          h('div', { class: 'when' }, fmtDate(s.at)),
          h('div', {},
            h('strong', {}, s.story?.headline || 'Snapshot'),
            h('div', { class: 'pill-row', style: { marginTop: '6px' } },
              s.strands.filter((x) => x.n).map((x) => h('span', { class: 'tag' }, `${x.strand} L${x.level}`))),
            h('small', { class: 'muted' }, `${s.attempts} missions · ${s.movesHeld} moves held`)))))
        : h('p', { class: 'muted' }, 'No snapshots yet. Save one at the end of a week and this becomes a timeline.')),

    h('div', { class: 'spacer' }),
    h('div', { class: 'card tint' },
      h('h3', {}, 'Your data'),
      h('p', { class: 'muted' }, 'Everything Thinkforge holds about you is a first name, an age, your answers and your coach conversations.'),
      h('div', { class: 'row' },
        h('a', { class: 'btn', href: `/api/students/${store.studentId}/export`, download: 'thinkforge-export.json' }, 'Download everything'),
        h('button', {
          onclick: async () => {
            if (!confirm('Delete this profile and every answer in it? This cannot be undone.')) return;
            await api.del(`/api/students/${store.studentId}`);
            store.studentId = null;
            go('home');
          },
        }, 'Delete this profile'))),
  ];
}

export async function moves() {
  const curriculum = await api.get('/api/curriculum');
  return [
    h('h1', {}, 'The moves'),
    h('p', { class: 'muted prompt' }, 'Every strand is a claim about what you can do. Every move is a procedure you can actually run, on purpose, and it leaves something behind that can be looked at.'),
    h('div', { class: 'spacer' }),
    h('div', { class: 'stack' }, curriculum.strands.map((s) => h('div', { class: 'card strand-edge', style: { '--strand': s.colour } },
      h('div', { class: 'row between' }, h('h3', { style: { margin: 0 } }, s.name), h('span', { class: 'tag' }, `${s.moves.length} moves`)),
      h('p', { class: 'muted' }, s.claim),
      h('div', { class: 'stack' }, s.moves.map((m) => h('div', { class: 'card tint flat' },
        h('div', { class: 'row between' }, h('strong', {}, m.name), h('small', {}, m.origin)),
        h('p', { style: { margin: '4px 0 2px' } }, m.how),
        h('small', { class: 'muted' }, `Leaves behind: ${m.artefact}`))))))),
  ];
}

export async function about() {
  const status = store.status || await api.get('/api/status');
  return [
    h('h1', {}, 'How Thinkforge works'),
    h('div', { class: 'grid two' },
      h('div', { class: 'card' }, h('h3', {}, 'The session'),
        h('ol', {},
          h('li', {}, h('strong', {}, 'Warm-up. '), 'One thing you met before, brought back just as you were about to forget it.'),
          h('li', {}, h('strong', {}, 'Move of the day. '), 'A named move, shown worked, then half-worked, then yours — the help fades as you stop needing it.'),
          h('li', {}, h('strong', {}, 'Mission. '), 'A real problem, in a situation you have not used this move in before.'),
          h('li', {}, h('strong', {}, 'Dialogue. '), 'The coach asks; you may revise once.'),
          h('li', {}, h('strong', {}, 'Close. '), 'Was your prediction right? Where else does this move work?'))),
      h('div', { class: 'card' }, h('h3', {}, 'How marking works'),
        h('p', {}, 'Four layers. First a check that there is something to mark. Then the parts a computer can count — are the slots filled, was the choice right, did your tests change one thing at a time. Then a rubric, judged line by line, where any score above zero has to quote your own words back to you. Then the layers are combined, with a ceiling: a missing warrant caps the score however well it is written.'),
        h('p', { class: 'muted' }, status?.ai?.available
          ? `The rubric layer is currently marked by ${status.ai.model}, bounded by the rules.`
          : 'No AI marker is configured right now, so the rubric layer is estimated from the structure and language of your answer, and counts for less.')),
      h('div', { class: 'card' }, h('h3', {}, 'What the coach will not do'),
        h('ul', {},
          h('li', {}, 'Give you the answer, however you ask.'),
          h('li', {}, 'Praise you rather than the work.'),
          h('li', {}, 'Talk about anything other than the task.'),
          h('li', {}, 'Keep a secret from your teacher — every conversation is visible to them.'))),
      h('div', { class: 'card' }, h('h3', {}, 'What we do not claim'),
        h('p', {}, 'Thinking skills do not automatically transfer to new situations — the research is clear about that. So Thinkforge does not claim to raise your general intelligence. It teaches specific moves, makes you use them in several different kinds of situation on purpose, and then measures whether they held up somewhere new. That number is the Transfer index, and it is allowed to be low.')),
      h('div', { class: 'card' }, h('h3', {}, 'Where this comes from'),
        h('p', { class: 'muted' }, 'De Bono’s CoRT tools, Toulmin’s model of argument, Biggs & Collis’s SOLO taxonomy, Paul and Elder’s elements of reasoning, Pólya, Meadows’ systems primer, TRIZ, and the evidence base on worked examples, spacing, feedback and metacognition. The reasoning behind each choice — including what was left out — is written up in the project’s docs folder.')),
      h('div', { class: 'card' }, h('h3', {}, 'Privacy'),
        h('p', {}, 'A first name and an age. No email, no photo, no profile, no open chat. Personal details are stripped out of anything sent to the AI. Nothing is used to train a model. Everything can be exported or deleted in one click.'))),
  ];
}
