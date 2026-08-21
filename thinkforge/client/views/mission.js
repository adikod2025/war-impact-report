import { h, api, store, go, md, refreshGame } from '../core.js';

const strandColour = (id) => (store.status?.strands || []).find((x) => x.id === id)?.colour || 'var(--accent)';
const moveInfo = (id) => {
  for (const s of store.status?.strands || []) {
    const m = (s.moves || []).find((x) => x.id === id);
    if (m) return { ...m, strandName: s.name, colour: s.colour };
  }
  return null;
};

export function missionCard(task) {
  const state = { response: {}, hintLevel: 0, startedAt: Date.now(), confidence: 60, attemptId: null, firstScore: null };
  const wrap = h('div', { style: { '--strand': strandColour(task.strand) } });
  const widget = buildWidget(task, state);
  const hintBox = h('div', { class: 'stack' });
  const outcome = h('div');

  const confidence = h('input', { type: 'range', min: '50', max: '100', step: '5', value: '60', oninput: (e) => { state.confidence = Number(e.target.value); confLabel.textContent = `${e.target.value}%`; } });
  const confLabel = h('strong', {}, '60%');

  const submitBtn = h('button', { class: 'primary', onclick: () => submit() }, 'Submit');

  async function submit() {
    const revisionOf = state.attemptId;   // a second submit is a revision, scored separately
    submitBtn.disabled = true;
    submitBtn.textContent = 'Marking…';
    const response = { ...widget.read(), meta: { hintLevel: state.hintLevel, confidence: state.confidence, durationMs: Date.now() - state.startedAt } };
    let result;
    try {
      result = await api.post('/api/attempts', { studentId: store.studentId, taskId: task.id, response, revisionOf });
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = state.attemptId ? 'Submit revision' : 'Submit';
    }
    if (result.safety) {
      outcome.replaceChildren(h('div', { class: 'notice safety' }, result.safety.message));
      return;
    }
    if (result.valid === false) {
      outcome.replaceChildren(h('div', { class: 'notice' },
        h('strong', {}, 'Not marked yet — '), result.repair,
        h('p', { class: 'muted', style: { margin: '8px 0 0' } }, 'Nothing was recorded against you. Edit and submit again.')));
      return;
    }
    if (!revisionOf) { state.attemptId = result.attempt.id; state.firstScore = result.scored.score; }
    submitBtn.textContent = 'Submit revision';
    outcome.replaceChildren(feedbackPanel(task, result, state, revisionOf));
    refreshGame();
    outcome.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function showHint() {
    if (state.hintLevel >= 3) return;
    state.hintLevel += 1;
    api.get(`/api/students/${store.studentId}/hint?taskId=${task.id}&level=${state.hintLevel}`).then(({ level, hint, cost }) => {
      hintBox.append(h('div', { class: 'hint-step' },
        h('b', {}, `Nudge ${level} of 3 · costs ${Math.round(cost * 100)} points of the score`),
        h('span', { html: md(hint) })));
      if (state.hintLevel >= 3) hintBtn.disabled = true;
    });
  }
  const hintBtn = h('button', { onclick: showHint }, 'I need a nudge');

  wrap.append(
    h('div', { class: 'row between' },
      h('div', { class: 'pill-row' },
        h('span', { class: 'tag solid', style: { '--strand': strandColour(task.strand) } }, task.strand.replace('_', ' ')),
        h('span', { class: 'tag' }, `tier ${task.tier}`),
        h('span', { class: 'tag' }, task.domain)),
      h('button', { class: 'ghost small', onclick: () => go('session') }, '← back to session')),
    h('h1', {}, task.title),
    h('div', {}, task.moves.map((m) => moveCard(m))),
    h('div', { class: 'stimulus', html: md(task.stimulus) }),
    h('div', { class: 'spacer', style: { height: '14px' } }),
    h('p', { class: 'prompt', html: md(task.prompt) }),
    widget.el,
    hintBox,
    h('div', { class: 'card tint' },
      h('label', { class: 'field' },
        h('span', {}, 'Before you submit: how well do you think this went?'),
        h('small', {}, 'Guessing high when you are wrong is the most fixable thinking fault there is — this trains it.')),
      h('div', { class: 'slider-row' }, confidence, confLabel)),
    h('div', { class: 'row' }, submitBtn, hintBtn),
    h('div', { class: 'spacer' }),
    outcome,
  );
  return wrap;
}

function moveCard(id) {
  const m = moveInfo(id);
  if (!m) return null;
  return h('div', { class: 'card tint strand-edge', style: { '--strand': m.colour, marginBottom: '14px' } },
    h('div', { class: 'row between' }, h('strong', {}, `The move: ${m.name}`), h('small', {}, m.origin)),
    h('p', { style: { margin: '6px 0 0' }, html: md(m.how) }),
    h('small', {}, `What it should leave behind: ${m.artefact}`));
}

/* ------------------------------------------------------------- widgets */

function buildWidget(task, state) {
  const p = task.payload || {};
  switch (task.mode) {
    case 'select': {
      let choice = null;
      const opts = p.options.map((o) => {
        const el = h('label', { class: 'choice', onclick: () => { choice = o.id; [...el.parentElement.children].forEach((c) => c.classList.remove('picked')); el.classList.add('picked'); } },
          h('input', { type: 'radio', name: 'sel' }), h('span', {}, o.text));
        return el;
      });
      return { el: h('div', { class: 'stack' }, opts), read: () => ({ choice }) };
    }
    case 'multi_select': {
      const chosen = new Set();
      const opts = p.options.map((o) => {
        const box = h('input', { type: 'checkbox' });
        const el = h('label', { class: 'choice', onclick: () => { setTimeout(() => { box.checked ? chosen.add(o.id) : chosen.delete(o.id); el.classList.toggle('picked', box.checked); }); } }, box, h('span', {}, o.text));
        return el;
      });
      return { el: h('div', { class: 'stack' }, h('small', { class: 'muted' }, 'Pick every one that applies.'), opts), read: () => ({ choices: [...chosen] }) };
    }
    case 'order': {
      const order = [...p.items];
      const list = h('div', {});
      const paint = () => list.replaceChildren(...order.map((item, i) => h('div', { class: 'order-item' },
        h('span', { class: 'grip' }, `${i + 1}.`),
        h('span', { style: { flex: '1' } }, item.text),
        h('button', { class: 'small', disabled: i === 0, onclick: () => { [order[i - 1], order[i]] = [order[i], order[i - 1]]; paint(); } }, '↑'),
        h('button', { class: 'small', disabled: i === order.length - 1, onclick: () => { [order[i + 1], order[i]] = [order[i], order[i + 1]]; paint(); } }, '↓'))));
      paint();
      return { el: h('div', {}, h('small', { class: 'muted' }, p.direction === 'backwards' ? 'Put the goal first, then what had to happen just before it.' : 'Put them in order.'), list), read: () => ({ order: order.map((i) => i.id) }) };
    }
    case 'match': {
      const pairs = {};
      const rows = p.left.map((l) => h('div', { class: 'match-row' },
        h('span', { style: { flex: '1' } }, l.text),
        h('span', { class: 'muted' }, '→'),
        h('select', { onchange: (e) => { pairs[l.id] = e.target.value; } },
          h('option', { value: '' }, 'choose…'),
          p.right.map((r) => h('option', { value: r.id }, r.text)))));
      return { el: h('div', {}, rows), read: () => ({ pairs }) };
    }
    case 'structured': {
      const fields = {};
      const els = p.fields.map((f) => {
        const input = h('textarea', { placeholder: f.hint || '', oninput: (e) => { fields[f.id] = e.target.value; counter.textContent = `${words(e.target.value)} words${f.minWords ? ` — aim for ${f.minWords}+` : ''}`; } });
        const counter = h('small', { class: 'muted' }, f.minWords ? `0 words — aim for ${f.minWords}+` : '');
        return h('label', { class: 'field' }, h('span', {}, f.label), input, counter);
      });
      return { el: h('div', {}, els), read: () => ({ fields }) };
    }
    case 'open_list': {
      const ta = h('textarea', { rows: '8', placeholder: p.lineFormat ? `One per line — ${p.lineFormat}` : 'One idea per line', oninput: (e) => { count.textContent = `${lines(e.target.value)} of at least ${p.minIdeas} ideas`; } });
      const count = h('small', { class: 'muted' }, `0 of at least ${p.minIdeas} ideas`);
      return { el: h('label', { class: 'field' }, ta, count), read: () => ({ text: ta.value }) };
    }
    case 'open_short': {
      const ta = h('textarea', { rows: '7', oninput: (e) => { count.textContent = `${words(e.target.value)} words${p.maxWords ? ` (aim for under ${p.maxWords})` : ''}`; } });
      const count = h('small', { class: 'muted' }, '0 words');
      return { el: h('label', { class: 'field' }, ta, count), read: () => ({ text: ta.value }) };
    }
    case 'probe':
      return probeWidget(task, state);
    default:
      return { el: h('p', {}, 'Unsupported task type.'), read: () => ({}) };
  }
}

function probeWidget(task) {
  const m = task.payload.machine;
  const tests = [];
  const inputs = {};
  const controls = m.inputs.map((inp) => {
    if (inp.type === 'number') {
      inputs[inp.id] = inp.min;
      return h('label', { class: 'field' }, h('span', {}, `${inp.label} (${inp.min}–${inp.max})`),
        h('input', { type: 'number', min: inp.min, max: inp.max, value: inp.min, oninput: (e) => { inputs[inp.id] = Number(e.target.value); } }));
    }
    inputs[inp.id] = inp.options[0];
    return h('label', { class: 'field' }, h('span', {}, inp.label),
      h('select', { onchange: (e) => { inputs[inp.id] = e.target.value; } }, inp.options.map((o) => h('option', { value: o }, o))));
  });

  const readout = h('div', { class: 'readout' }, 'run a test');
  const log = h('div', { class: 'tests' });
  const ruleBox = h('textarea', { rows: '3', placeholder: 'The rule is…' });

  const run = async () => {
    const snapshot = { ...inputs };
    // The machine is evaluated on the server so the rule never reaches the page.
    const res = await api.post('/api/attempts/probe-run', { taskId: task.id, inputs: snapshot }).catch(() => null);
    const on = res ? res.on : null;
    tests.push({ inputs: snapshot, on });
    readout.textContent = res ? res.text : '—';
    readout.classList.toggle('on', !!on);
    const controlled = tests.length > 1 && Object.keys(snapshot).filter((k) => String(tests[tests.length - 2].inputs[k]) !== String(snapshot[k])).length === 1;
    log.prepend(h('div', {}, `${Object.entries(snapshot).map(([k, v]) => `${k}=${v}`).join(' ')} → ${res ? res.text : '?'}${controlled ? '  · one thing changed ✓' : tests.length > 1 ? '  · several things changed' : ''}`));
  };

  return {
    el: h('div', { class: 'grid two' },
      h('div', { class: 'card' }, h('h3', {}, m.label), controls,
        h('button', { class: 'primary', onclick: run }, 'Run test'),
        h('div', { class: 'spacer', style: { height: '12px' } }), readout),
      h('div', { class: 'card' }, h('h3', {}, 'Your tests'),
        h('small', { class: 'muted' }, `Most people need about ${m.minTests}. Changing one thing at a time is what makes a test worth running.`),
        log, h('div', { class: 'spacer', style: { height: '10px' } }),
        h('label', { class: 'field' }, h('span', {}, 'State the rule'), ruleBox))),
    read: () => ({ tests, rule: ruleBox.value }),
  };
}

const words = (s) => (String(s || '').match(/\S+/g) || []).length;
const lines = (s) => String(s || '').split('\n').filter((l) => l.trim().length > 1).length;

/* ------------------------------------------------------------ feedback */

function feedbackPanel(task, result, state, wasRevision) {
  const { scored, feedback, ability, calibration } = result;
  const pct = Math.round(scored.score * 100);
  const tone = pct >= 75 ? 'good' : pct >= 45 ? 'warn' : 'bad';

  const panel = h('div', { class: 'stack' },
    result.rewards ? rewardsPanel(result.rewards) : null,
    h('div', { class: 'card' },
      h('div', { class: 'row between' },
        h('h2', { style: { margin: 0 } }, `${pct}%`),
        h('div', { class: 'pill-row' },
          h('span', { class: `tag ${tone}` }, `${ability.strand} · level ${ability.level} ${ability.levelName}`),
          scored.hintPenalty ? h('span', { class: 'tag warn' }, `−${Math.round(scored.hintPenalty * 100)} for nudges taken`) : null,
          h('span', { class: 'tag' }, scored.scorer === 'ai' ? 'marked by AI + rules' : scored.scorer === 'human' ? 'marked by your teacher' : 'marked by rules only'))),
      ability.levelUp ? h('div', { class: 'notice' }, `That moved you up to level ${ability.level} — ${ability.levelName} — in ${ability.strand}.`) : null,
      scored.capsApplied?.length
        ? h('div', { class: 'notice' }, `Capped at ${Math.round(scored.capsApplied[0].cap * 100)}% because "${scored.capsApplied.map((c) => c.field).join('", "')}" was missing. That part is what the rest rests on.`)
        : null,
      h('div', { class: 'spacer', style: { height: '10px' } }),
      h('div', { class: 'stack' },
        fbLine('What this answer did', feedback.task),
        fbLine('The thinking behind it', feedback.process),
        fbLine('Check it yourself next time', feedback.selfRegulation))),

    calibration ? h('div', { class: 'card tint' },
      h('h3', {}, 'Your prediction'),
      h('p', {}, `You said ${calibration.predicted}%. It came out at ${calibration.actual}%. ${Math.abs(calibration.gap) <= 10 ? 'That is well calibrated — you know what you know.' : calibration.gap > 0 ? 'You were more confident than the work was. What check would have told you?' : 'You were harder on yourself than the work deserved.'}`)) : null,

    scored.criteria?.length ? h('div', { class: 'card' },
      h('h3', {}, 'Against the rubric'),
      h('div', { class: 'stack' }, scored.criteria.map((c) => h('div', { class: 'crit' },
        h('div', { class: 'head' }, h('span', {}, c.name), h('span', {}, `${c.score} / 3`)),
        h('small', {}, c.anchor),
        c.evidence ? h('blockquote', {}, `“${c.evidence}”`) : null,
        c.rationale ? h('small', { class: 'muted' }, c.rationale) : null))),
      scored.scorer === 'offline'
        ? h('div', { class: 'notice ai' }, 'No AI marker is configured, so these are rule-based estimates from the structure and language of your answer. They are rougher than a human or AI marker and count for less in your level.')
        : null) : null,

    scored.detail?.process ? h('div', { class: 'card tint' },
      h('h3', {}, 'How you investigated'),
      h('p', {}, `${scored.detail.process.tests} tests · ${Math.round(scored.detail.process.control * 100)}% of them changed one thing at a time · ${scored.detail.process.discrimination ? 'you got both outcomes, so your tests could tell things apart' : 'every test gave the same outcome, so none of them could rule anything out'}.`)) : null,

    scored.detail?.perOption ? h('div', { class: 'card' }, h('h3', {}, 'Each option'),
      h('div', { class: 'stack' }, scored.detail.perOption.map((o) => h('div', { class: `choice ${o.correct ? 'correct' : o.chosen ? 'wrong' : ''}` },
        h('span', {}, h('strong', {}, o.correct ? '✓ ' : o.chosen ? '✗ ' : '· '), o.why || ''))))) : null,

    scored.detail?.why ? h('div', { class: 'notice' }, scored.detail.why) : null,

    tutorPanel(task, state),

    wasRevision && state.firstScore !== null
      ? h('div', { class: 'card tint' }, h('h3', {}, 'Revision'),
        h('p', {}, `First attempt ${Math.round(state.firstScore * 100)}% → revision ${Math.round(result.scored.score * 100)}%. Your first attempt still counts for your level; the change is recorded separately as revision gain.`))
      : h('div', { class: 'notice' }, 'You can edit your answer above and submit once more. The revision is scored separately — your first attempt is what counts towards your level.'),

    h('div', { class: 'card tint' },
      h('h3', {}, 'Where else this works'),
      h('p', {}, result.bridge),
      h('div', { class: 'row' },
        h('button', { class: 'primary', onclick: () => go('session') }, 'Next mission'),
        h('button', { onclick: () => go(`duel/${task.id}`) }, 'Forge-off on this one'),
        h('button', { onclick: () => go('growth') }, 'See what changed'))),
  );
  return panel;
}

/** What this attempt earned, and — more importantly — what each line certifies. */
function rewardsPanel(rewards) {
  const grouped = new Map();
  for (const line of rewards.lines) {
    const cur = grouped.get(line.key) || { ...line, xp: 0, sparks: 0, count: 0, details: [] };
    cur.xp += line.xp; cur.sparks += line.sparks; cur.count += 1;
    if (line.detail) cur.details.push(line.detail);
    grouped.set(line.key, cur);
  }
  return h('div', { class: 'rewards celebrate' },
    h('div', { class: 'head' },
      h('span', { class: 'big' }, `+${rewards.xp} XP`),
      h('div', { class: 'pill-row' },
        h('span', { class: 'tag' }, `✦ ${rewards.sparks}`),
        h('span', { class: 'tag' }, `🔥 ${rewards.streak.streak}`),
        h('span', { class: 'tag' }, `${rewards.rank.mark} ${rewards.rank.name}`))),
    h('ul', {}, [...grouped.values()].map((l) => h('li', {},
      h('b', {}, `+${l.xp}`),
      h('span', {}, h('strong', {}, l.label + (l.count > 1 ? ` ×${l.count}` : '')), ' — ', l.certifies,
        l.details.length ? h('small', { class: 'muted' }, ` (${l.details.join('; ')})`) : null)))),
    rewards.quests?.length
      ? h('p', { style: { marginTop: '10px' } }, '🎯 Quest complete: ', rewards.quests.map((q) => `${q.label} (+${q.xp} XP)`).join(', '))
      : null,
    rewards.tempered?.length
      ? h('p', { style: { marginTop: '6px' } }, '🔨 Tempered: ', rewards.tempered.map((t) => `${t.name} ${t.from} → ${t.to}`).join(', '))
      : null,
    rewards.badges?.length
      ? h('p', { style: { marginTop: '6px' } }, '🏅 Trophy: ', rewards.badges.map((b) => `${b.glyph} ${b.name} — ${b.blurb}`).join(' · '))
      : null,
    rewards.rankUp
      ? h('p', { style: { marginTop: '6px' } }, `${rewards.rankUp.mark} You are now a ${rewards.rankUp.name}.`)
      : null,
    h('small', { class: 'muted', style: { display: 'block', marginTop: '8px' } }, rewards.streak.message),
    h('small', { class: 'muted', style: { display: 'block' } }, 'None of this is paid for being right — every line above is a behaviour.'));
}

function fbLine(label, text) {
  return h('div', {}, h('small', { class: 'muted' }, label), h('p', { style: { margin: '2px 0 0' }, html: md(text) }));
}

function tutorPanel(task, state) {
  const chat = h('div', { class: 'chat' },
    h('div', { class: 'bubble system' }, 'This coach is an AI, not a person. It will not give you the answer — it asks, then narrows, then shows you a different case worked through.'));
  const input = h('input', { type: 'text', placeholder: 'Ask about your answer…' });
  let busy = false;

  const send = async (message) => {
    if (busy || !message.trim()) return;
    busy = true;
    chat.append(h('div', { class: 'bubble student' }, message));
    input.value = '';
    const thinking = h('div', { class: 'bubble tutor muted' }, '…');
    chat.append(thinking);
    chat.scrollTop = chat.scrollHeight;
    try {
      const turn = await api.post('/api/tutor', { studentId: store.studentId, taskId: task.id, message, attemptId: state.attemptId });
      thinking.replaceChildren(document.createTextNode(turn.reply));
      thinking.classList.remove('muted');
      if (turn.mode === 'safety') thinking.classList.add('system');
    } catch (e) {
      thinking.textContent = 'The coach is unavailable right now.';
    } finally {
      busy = false;
      chat.scrollTop = chat.scrollHeight;
    }
  };

  // Open the dialogue with a coaching turn on the submitted work.
  send('I have just submitted — what should I look at?');

  return h('div', { class: 'card' },
    h('h3', {}, 'Talk it through'),
    chat,
    h('div', { class: 'row', style: { marginTop: '10px' } },
      h('div', { style: { flex: '1' } }, input),
      h('button', { onclick: () => send(input.value) }, 'Send')),
    h('small', { class: 'muted' }, 'Your teacher can see this conversation.'));
}
