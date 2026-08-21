import { h, api, store, go, dial, aiBadge, LEVEL_NAMES } from '../core.js';
import { missionCard } from './mission.js';

export async function home() {
  if (!store.studentId) return onboarding();
  const profile = await api.get(`/api/students/${store.studentId}`);
  store.profile = profile;
  const { student, strands, indices, heldMoves, moves } = profile;
  const weakest = [...strands].sort((a, b) => a.theta - b.theta)[0];
  const due = moves.filter((m) => m.dueAt && new Date(m.dueAt) <= new Date()).length;

  return [
    h('div', { class: 'row between' },
      h('div', {},
        h('h1', {}, `Hello, ${student.displayName}`),
        h('p', { class: 'muted' }, `${profile.attempts} missions done · ${heldMoves.length} moves held · ${student.tier === 1 ? 'Spark' : student.tier === 2 ? 'Forge' : student.tier === 3 ? 'Circuit' : 'Summit'} tier`)),
      h('div', { class: 'row' }, aiBadge(store.status),
        h('button', { class: 'primary', onclick: () => go('session') }, 'Start today’s session →'))),

    h('div', { class: 'spacer' }),
    h('div', { class: 'grid two' },
      h('div', { class: 'card' },
        h('h3', {}, 'Where your thinking is'),
        h('p', { class: 'muted' }, 'The pale band is how sure we are. It narrows as you do more.'),
        h('div', { class: 'stack' }, strands.map((s) => dial({ ...s, levelName: LEVEL_NAMES[s.level] })))),
      h('div', { class: 'stack' },
        h('div', { class: 'card' },
          h('h3', {}, 'Next best thing to do'),
          h('p', {}, due
            ? `${due} move${due === 1 ? '' : 's'} ${due === 1 ? 'is' : 'are'} due for a review — that is where a session pays most today.`
            : `Your thinnest strand is ${weakest.name}. Today’s session will lean there.`),
          h('button', { class: 'primary', onclick: () => go('session') }, 'Open the session')),
        indexPanel(indices),
        h('div', { class: 'card tint' },
          h('h3', {}, 'Moves you hold'),
          heldMoves.length
            ? h('div', { class: 'pill-row' }, moves.filter((m) => m.held).map((m) => h('span', { class: 'tag' }, m.name)))
            : h('p', { class: 'muted' }, 'None yet. A move counts as held once you have done it well twice, in two different situations, with no hints.'))),
    ),
  ];
}

export function indexPanel(indices, { title = 'How you are growing' } = {}) {
  const labels = {
    transfer: ['Transfer', 'Does it work in a new situation?'],
    independence: ['Independence', 'Score with no help taken'],
    calibration: ['Calibration', 'Do you know when you are right?'],
    flexibility: ['Flexibility', 'Do you use the whole toolkit?'],
    originality: ['Originality', 'Non-obvious but still relevant'],
    revisionGain: ['Revision gain', 'How much you improve after coaching'],
  };
  return h('div', { class: 'card' },
    h('h3', {}, title),
    h('div', { class: 'index-grid' }, Object.entries(indices).map(([key, v]) => {
      const [name, note] = labels[key] || [key, ''];
      return h('div', { class: 'index' },
        v.available
          ? h('div', { class: 'val' }, String(v.value))
          : h('div', { class: 'val na' }, 'not enough evidence yet'),
        h('div', { class: 'name' }, name),
        h('div', { class: 'note' }, v.available && v.reading ? v.reading : note));
    })));
}

export async function onboarding() {
  const students = (await api.get('/api/students')).students;
  const form = h('div', { class: 'card' },
    h('h3', {}, 'Make a learner profile'),
    h('label', { class: 'field' }, h('span', {}, 'First name only'), h('input', { type: 'text', id: 'nm', maxlength: '40', placeholder: 'e.g. Ada' })),
    h('label', { class: 'field' }, h('span', {}, 'Age'), h('input', { type: 'number', id: 'age', min: '8', max: '18', value: '11' })),
    h('label', { class: 'field' }, h('span', {}, 'Supervising adult (teacher or parent)'), h('input', { type: 'text', id: 'guardian', placeholder: 'e.g. Ms Rowe' })),
    h('label', { class: 'choice' },
      h('input', { type: 'checkbox', id: 'consent' }),
      h('span', {}, h('strong', {}, 'A grown-up has said yes.'),
        h('br'), h('small', {}, 'We store a first name and an age. Nothing else. No email, no photo, no free chat. Everything written here can be exported or deleted in one click, and is never used to train a model.'))),
    h('button', {
      class: 'primary',
      onclick: async (e) => {
        const displayName = document.getElementById('nm').value.trim();
        const age = Number(document.getElementById('age').value);
        const consent = document.getElementById('consent').checked;
        const guardianName = document.getElementById('guardian').value.trim();
        if (!displayName || !consent) return alert('A name and a grown-up’s consent are both needed.');
        e.target.disabled = true;
        const { student } = await api.post('/api/students', { displayName, age, consent, guardianName });
        store.studentId = student.id;
        go('home');
      },
    }, 'Create profile'));

  return [
    h('h1', {}, 'Learn to think on purpose.'),
    h('p', { class: 'prompt muted' }, 'Thinkforge teaches named thinking moves — the ones behind good arguments, good inventions and good decisions — then makes you use them on problems that actually matter, and shows you what changed.'),
    h('div', { class: 'spacer' }),
    h('div', { class: 'grid two' },
      form,
      h('div', { class: 'stack' },
        students.length ? h('div', { class: 'card tint' },
          h('h3', {}, 'Or carry on as'),
          h('div', { class: 'pill-row' }, students.map((s) => h('button', {
            class: 'small', onclick: () => { store.studentId = s.id; go('home'); },
          }, `${s.displayName}, ${s.age}`)))) : null,
        h('div', { class: 'card' },
          h('h3', {}, 'What you actually get'),
          h('ul', {},
            h('li', {}, h('strong', {}, '8 strands of thinking'), ' — breaking down, building up, sideways, logic, argument, reverse engineering, systems, and thinking about thinking.'),
            h('li', {}, h('strong', {}, 'A coach that will not tell you the answer'), ' — it asks, then narrows, then shows you a different case worked out.'),
            h('li', {}, h('strong', {}, 'Marking you can argue with'), ' — every score points at the rubric line and quotes your own words.'),
            h('li', {}, h('strong', {}, 'Growth measured honestly'), ' — including whether it works in situations you have never practised.')))),
    ),
  ];
}

export async function session() {
  if (!store.studentId) return onboarding();
  const plan = await api.get(`/api/students/${store.studentId}/session`);
  return [
    h('div', { class: 'row between' },
      h('div', {}, h('h1', {}, 'Today’s session'), h('p', { class: 'muted' }, 'Three beats, about twenty minutes. Warm up, learn a move, then use it on something real.')),
      aiBadge(store.status)),
    h('div', { class: 'spacer' }),
    h('div', { class: 'grid three' }, plan.beats.map((b, i) => beatCard(b, i))),
    h('div', { class: 'spacer' }),
    h('div', { class: 'card tint' },
      h('h3', {}, 'Why these three?'),
      h('p', { class: 'muted' }, 'Missions are picked so you have roughly a 75% chance of succeeding — hard enough to be worth doing, not so hard you stall. Reviews come back when you are about to forget them, not on a fixed timetable.')),
  ];
}

function beatCard(beat, i) {
  const t = beat.task;
  return h('div', { class: 'card strand-edge', style: { '--strand': strandColour(t.strand) } },
    h('div', { class: 'row between' },
      h('span', { class: 'tag solid', style: { '--strand': strandColour(t.strand) } }, beat.beat),
      h('span', { class: 'tag' }, `${Math.round(beat.successChance * 100)}% likely`)),
    h('h3', { style: { marginTop: '12px' } }, t.title),
    h('p', { class: 'muted' }, beat.why),
    h('div', { class: 'row' }, h('span', { class: 'tag' }, beat.rung.rung), h('small', {}, beat.rung.label)),
    h('div', { class: 'spacer', style: { height: '10px' } }),
    h('button', { class: i === 0 ? 'primary' : '', onclick: () => go(`mission/${t.id}`) }, 'Start'));
}

export function strandColour(id) {
  const s = (store.status?.strands || []).find((x) => x.id === id);
  return s?.colour || 'var(--accent)';
}

export async function mission(params) {
  if (!store.studentId) return onboarding();
  const task = await api.get(`/api/tasks/${params[0]}`);
  return missionCard(task);
}
