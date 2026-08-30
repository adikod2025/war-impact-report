#!/usr/bin/env node
/**
 * Seeds a demo class so the teacher view, the review queue and the growth
 * timeline have something real in them. Responses are generated at three
 * quality levels per learner so the ability estimates spread out the way a
 * class does, rather than everyone sitting on the starting prior.
 *
 *   node scripts/seed.mjs            # add the demo class
 *   THINKFORGE_DB=./data/demo.db node scripts/seed.mjs
 */
// The demo class is seeded deterministically on purpose: with a key present
// this would fire a live marking call per mission and quietly spend real money
// producing data nobody reads. Run the server with the key instead.
delete process.env.ANTHROPIC_API_KEY;
delete process.env.ANTHROPIC_AUTH_TOKEN;

import * as db from '../server/db.mjs';
import { submitAttempt, takeSnapshot, planSession } from '../server/service.mjs';
import { getTask, TASKS } from '../server/content/index.mjs';

const LEARNERS = [
  { displayName: 'Ada', age: 11, skill: 0.85, missions: 22 },
  { displayName: 'Bo', age: 9, skill: 0.55, missions: 16 },
  { displayName: 'Ines', age: 13, skill: 0.7, missions: 18 },
  { displayName: 'Kwame', age: 15, skill: 0.9, missions: 20 },
  { displayName: 'Mira', age: 12, skill: 0.35, missions: 14 },
];

/** Three registers of answer, so the marker has something to discriminate. */
const WRITING = {
  strong: {
    connective: 'Whenever this pattern shows up, it usually means the cause sits outside the thing everyone is looking at',
    detail: 'about seven of them, every morning this term',
    contrast: 'unless the people involved had a reason nobody has asked about yet',
  },
  middling: {
    connective: 'because it happens a lot and that is a reason',
    detail: 'quite a few of them, most days',
    contrast: 'but maybe not always',
  },
  weak: {
    connective: 'because it just is',
    detail: 'some of them sometimes',
    contrast: 'it is fine',
  },
};

function answerFor(task, level) {
  const w = WRITING[level];
  const sentence = (i) => `${['This part matters', 'The next thing here', 'Another angle on it', 'One more consideration'][i % 4]} ${i + 1}: ${w.detail}, ${w.connective}, ${w.contrast}.`;
  const p = task.payload || {};

  switch (task.mode) {
    case 'select':
      return { choice: level === 'weak' ? p.options[0].id : (p.options.find((o) => o.correct)?.id || p.options[0].id) };
    case 'multi_select': {
      const right = p.options.filter((o) => o.correct).map((o) => o.id);
      if (level === 'strong') return { choices: right };
      if (level === 'middling') return { choices: right.slice(0, Math.max(1, right.length - 1)) };
      return { choices: p.options.slice(0, 2).map((o) => o.id) };
    }
    case 'order': {
      const answer = [...p.answer];
      if (level === 'strong') return { order: answer };
      if (level === 'middling') { [answer[0], answer[1]] = [answer[1], answer[0]]; return { order: answer }; }
      return { order: answer.reverse() };
    }
    case 'match': {
      const pairs = { ...p.answer };
      if (level === 'strong') return { pairs };
      const keys = Object.keys(pairs);
      if (level === 'middling') { pairs[keys[0]] = pairs[keys[1]]; return { pairs }; }
      return { pairs: Object.fromEntries(keys.map((k) => [k, pairs[keys[0]]])) };
    }
    case 'structured': {
      const fields = {};
      const dropLast = level === 'weak' && (p.fields || []).length > 3;
      (p.fields || []).forEach((f, i) => {
        // A struggling learner writes something thin everywhere and sometimes
        // leaves the hardest slot empty — which is what the structural cap is for.
        if (dropLast && i === p.fields.length - 1) { fields[f.id] = ''; return; }
        const n = level === 'strong' ? 3 : level === 'middling' ? 2 : 1;
        fields[f.id] = Array.from({ length: n }, (_, k) => sentence(i + k)).join(' ');
      });
      return { fields };
    }
    case 'open_list': {
      const n = level === 'strong' ? (p.minIdeas || 4) + 3 : level === 'middling' ? (p.minIdeas || 4) : 2;
      return { text: Array.from({ length: n }, (_, i) => sentence(i)).join('\n') };
    }
    case 'open_short':
      return { text: Array.from({ length: level === 'strong' ? 5 : level === 'middling' ? 3 : 2 }, (_, i) => sentence(i)).join(' ') };
    case 'probe': {
      const m = p.machine;
      const base = Object.fromEntries(m.inputs.map((inp) => [inp.id, inp.type === 'number' ? inp.min : inp.options[0]]));
      const tests = [{ inputs: { ...base } }];
      // strong learners change one input at a time; weak ones change everything
      m.inputs.forEach((inp, i) => {
        const next = { ...tests[tests.length - 1].inputs };
        next[inp.id] = inp.type === 'number' ? inp.max : inp.options[inp.options.length - 1];
        if (level === 'weak') for (const other of m.inputs) next[other.id] = other.type === 'number' ? Math.round((other.min + other.max) / 2) + i : other.options[i % other.options.length];
        tests.push({ inputs: next });
      });
      const rule = level === 'strong' ? (m.canonicalForms?.[0] || 'it depends on the inputs')
        : level === 'middling' ? `something like ${(m.canonicalForms?.[0] || '').split(' and ')[0]}`
          : 'it turns on sometimes';
      return { tests, rule };
    }
    default:
      return { text: sentence(0) };
  }
}

function levelFor(skill, i) {
  // deterministic ripple so a learner improves slightly across the term
  const drift = Math.min(0.15, i * 0.012);
  const roll = ((i * 37) % 100) / 100;
  const p = skill + drift;
  if (roll < p - 0.25) return 'strong';
  if (roll < p + 0.2) return 'middling';
  return 'weak';
}

/**
 * Spread the history back over the last six weeks so the review scheduler and
 * the growth timeline have something to work with — everything happening in the
 * same second makes both look broken.
 */
function backdate(studentId, missions) {
  const d = db.getDb();
  const attempts = d.prepare('SELECT id FROM attempts WHERE student_id = ? ORDER BY created_at').all(studentId);
  attempts.forEach((row, i) => {
    const daysAgo = 42 - Math.round((i / Math.max(1, attempts.length - 1)) * 40);
    d.prepare('UPDATE attempts SET created_at = ? WHERE id = ?')
      .run(new Date(Date.now() - daysAgo * 86400000).toISOString(), row.id);
  });
  d.prepare(`UPDATE rewards SET created_at = (SELECT a.created_at FROM attempts a WHERE a.id = rewards.attempt_id)
      WHERE student_id = ? AND attempt_id IS NOT NULL`).run(studentId);
  const days = d.prepare('SELECT COUNT(DISTINCT substr(created_at,1,10)) AS n FROM attempts WHERE student_id = ?').get(studentId)?.n || 1;
  const streak = Math.max(1, Math.min(9, Math.round(days / 2)));
  d.prepare('UPDATE game_state SET streak = ?, longest = ?, last_active_day = ? WHERE student_id = ?')
    .run(streak, streak + 2, new Date().toISOString().slice(0, 10), studentId);
  const moves = d.prepare('SELECT move FROM move_state WHERE student_id = ?').all(studentId);
  moves.forEach((row, i) => {
    const daysAgo = 1 + ((i * 7) % Math.max(2, Math.round(missions / 2)));
    d.prepare('UPDATE move_state SET last_seen = ? WHERE student_id = ? AND move = ?')
      .run(new Date(Date.now() - daysAgo * 86400000).toISOString(), studentId, row.move);
  });
}

const guardian = db.createGuardian({ name: 'Ms Rowe', kind: 'teacher' });
console.log(`Seeding into ${process.env.THINKFORGE_DB || 'data/thinkforge.db'}`);

for (const spec of LEARNERS) {
  const student = db.createStudent({
    displayName: spec.displayName, age: spec.age,
    tier: spec.age <= 10 ? 1 : spec.age <= 12 ? 2 : spec.age <= 14 ? 3 : 4,
    guardianId: guardian.id, consent: true,
  });

  let done = 0;
  const seen = new Set();
  for (let i = 0; i < spec.missions * 2 && done < spec.missions; i += 1) {
    const plan = planSession(student.id);
    const beat = plan.beats.find((b) => !seen.has(b.task.id)) || plan.beats[0];
    if (!beat || seen.has(beat.task.id)) {
      const fallback = TASKS.find((t) => !seen.has(t.id));
      if (!fallback) break;
      seen.add(fallback.id);
      continue;
    }
    seen.add(beat.task.id);
    const task = getTask(beat.task.id);
    const level = levelFor(spec.skill, done);
    const hintLevel = level === 'weak' ? 2 : level === 'middling' ? 1 : 0;
    const confidence = level === 'strong' ? 75 : level === 'weak' ? 90 : 65; // weak learners over-predict
    const response = {
      ...answerFor(task, level),
      meta: { hintLevel, confidence, durationMs: 180000 + (done % 5) * 30000 },
    };
    const out = await submitAttempt({ studentId: student.id, taskId: task.id, response });
    if (out.valid) done += 1;
  }

  // Consolidation pass: revisit moves in a second domain so the strongest
  // learners actually temper cards and open a boss commission — otherwise the
  // demo shows a deck that never advances past bronze.
  if (spec.skill >= 0.65) {
    const teaching = new Map();
    for (const t of TASKS) for (const m of t.moves) teaching.set(m, (teaching.get(m) || 0) + 1);
    const practised = db.getMoveStates(student.id)
      .filter((m) => m.successes > 0)
      .sort((a, b) => (teaching.get(b.move) || 0) - (teaching.get(a.move) || 0));

    let consolidated = 0;
    for (const state of practised) {
      if (consolidated >= 6) break;
      const candidate = TASKS.find((t) => t.moves.includes(state.move) && !seen.has(t.id) && !state.domains.includes(t.domain));
      if (!candidate) continue;
      seen.add(candidate.id);
      const out = await submitAttempt({
        studentId: student.id, taskId: candidate.id,
        response: { ...answerFor(candidate, 'strong'), meta: { hintLevel: 0, confidence: 75, durationMs: 200000 } },
      });
      if (out.valid) { done += 1; consolidated += 1; }
    }
  }

  backdate(student.id, spec.missions);
  await takeSnapshot(student.id);
  const profile = db.getStrandStates(student.id);
  console.log(`  ${student.displayName.padEnd(6)} age ${student.age}  ${done} missions  strands touched: ${profile.length}`);
}

console.log('\nDone. Start the server and open the teacher view.');
