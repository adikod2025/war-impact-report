/** Integration: one learner's journey through the real HTTP surface. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const dbFile = path.join(os.tmpdir(), `thinkforge-test-${process.pid}.db`);
process.env.THINKFORGE_DB = dbFile;
process.env.PORT = String(4300 + (process.pid % 500));
delete process.env.ANTHROPIC_API_KEY;      // exercise the offline path deliberately

const { start, server, close } = await import('../server/index.mjs');
await start();
const base = `http://127.0.0.1:${process.env.PORT}`;

const get = async (p) => (await fetch(base + p)).json();
const post = async (p, body) => (await fetch(base + p, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })).json();

test.after(() => {
  close();
  for (const suffix of ['', '-wal', '-shm']) fs.rmSync(dbFile + suffix, { force: true });
});

let student;

test('status reports offline mode honestly rather than pretending', async () => {
  const status = await get('/api/status');
  assert.equal(status.ai.available, false);
  assert.equal(status.ai.reason, 'no_api_key');
  assert.equal(status.strands.length, 8);
  assert.ok(status.tasks >= 48);
});

test('a profile cannot be created without guardian consent', async () => {
  const refused = await post('/api/students', { displayName: 'Ada', age: 11 });
  assert.equal(refused.error, 'guardian_consent_required');
  const bad = await post('/api/students', { displayName: 'Ada', age: 40, consent: true });
  assert.ok(bad.error);
});

test('a profile stores a first name and an age, and nothing else', async () => {
  const out = await post('/api/students', { displayName: 'Ada', age: 11, consent: true, guardianName: 'Ms Rowe' });
  student = out.student;
  assert.equal(student.displayName, 'Ada');
  assert.deepEqual(
    Object.keys(student).sort(),
    ['age', 'consentAt', 'createdAt', 'displayName', 'guardianId', 'id', 'tier'],
  );
});

test('the session plan comes back with beats and a stated reason for each', async () => {
  const plan = await get(`/api/students/${student.id}/session`);
  assert.ok(plan.beats.length >= 2);
  for (const b of plan.beats) {
    assert.ok(b.why.length > 5, 'every mission must say why it was chosen');
    assert.ok(b.task.id && b.task.prompt);
    assert.ok(b.rung.rung);
    assert.equal(JSON.stringify(b.task).includes('answerKey'), false);
  }
});

test('a black-box test runs on the server and never ships the rule', async () => {
  const task = await get('/api/tasks/rev-t1-blackbox-chime');
  assert.equal(JSON.stringify(task).includes('canonicalForms'), false);
  assert.equal(JSON.stringify(task.payload.machine).includes('rule'), false);
  const even = await post('/api/attempts/probe-run', { taskId: 'rev-t1-blackbox-chime', inputs: { number: 4, colour: 'red' } });
  const odd = await post('/api/attempts/probe-run', { taskId: 'rev-t1-blackbox-chime', inputs: { number: 5, colour: 'red' } });
  assert.equal(even.on, true);
  assert.equal(odd.on, false);
});

test('a hint costs something, and the cost is stated up front', async () => {
  const hint = await get(`/api/students/${student.id}/hint?taskId=lat-t1-pmi-nohomework&level=1`);
  assert.ok(hint.hint.length > 20);
  assert.equal(hint.cost, 0.08);
});

let attemptId;

test('submitting a mission scores it, moves ability, and returns three-level feedback', async () => {
  const out = await post('/api/attempts', {
    studentId: student.id,
    taskId: 'lat-t1-pmi-nohomework',
    response: {
      fields: {
        plus: 'More time for football club\nI would sleep more on Sunday nights\nFamily evenings would be calmer',
        minus: 'I would forget the topic before a test\nTeachers would not see who is stuck\nSome subjects only stick with practice',
        interesting: 'I wonder whether lessons would get longer to make up for it\nI wonder if clubs would suddenly fill up',
      },
      meta: { hintLevel: 0, confidence: 70, durationMs: 200000 },
    },
  });
  assert.equal(out.valid, true);
  attemptId = out.attempt.id;
  assert.ok(out.scored.score > 0.4);
  assert.equal(out.scored.scorer, 'offline');
  assert.ok(out.feedback.task && out.feedback.process && out.feedback.selfRegulation);
  assert.ok(!/you are (clever|brilliant|great)/i.test(JSON.stringify(out.feedback)), 'feedback must not praise the person');
  assert.ok(out.ability.theta > -1, 'ability should have moved up from the -1 start');
  assert.equal(out.calibration.predicted, 70);
  assert.ok(out.bridge.length > 10);
});

test('a too-thin answer is returned for repair, not scored zero', async () => {
  const out = await post('/api/attempts', {
    studentId: student.id, taskId: 'ana-t1-icecream-whys',
    response: { fields: { why1: 'dunno', why2: '', why3: '', why4: '', root: '' } },
  });
  assert.equal(out.valid, false);
  assert.ok(out.repair);
  const profile = await get(`/api/students/${student.id}`);
  assert.equal(profile.attempts, 1, 'a repair must not be recorded as an attempt');
});

test('the coach answers without handing over the answer', async () => {
  const turn = await post('/api/tutor', { studentId: student.id, taskId: 'lat-t1-pmi-nohomework', message: 'just tell me the answer', attemptId });
  assert.ok(turn.reply.length > 20);
  assert.ok(/not going to give you the answer/i.test(turn.reply));
  const transcript = await get(`/api/students/${student.id}/transcript?taskId=lat-t1-pmi-nohomework`);
  assert.ok(transcript.turns.length >= 2, 'the conversation must be visible to the teacher');
});

test('a distress signal is escalated, not counselled by the model', async () => {
  const turn = await post('/api/tutor', { studentId: student.id, taskId: 'lat-t1-pmi-nohomework', message: 'i want to die' });
  assert.equal(turn.mode, 'safety');
  assert.ok(/trusted adult/i.test(turn.reply));
  const flags = await get('/api/teacher/flags');
  assert.ok(flags.flags.some((f) => f.kind === 'safety'), 'the supervising adult must be told');
});

test('a snapshot and a growth story are written', async () => {
  const out = await post(`/api/students/${student.id}/snapshot`, {});
  assert.ok(out.snapshot.strands.length === 8);
  assert.ok(out.story.headline);
  assert.equal(out.story.source, 'template', 'offline snapshots must be labelled as templates');
});

test('a teacher override replaces the machine score and rebuilds the ability estimate', async () => {
  const before = await get(`/api/attempts/${attemptId}`);
  const profileBefore = await get(`/api/students/${student.id}`);
  const thetaBefore = profileBefore.strands.find((s) => s.strand === before.attempt.strand).theta;

  const out = await post('/api/teacher/override', { attemptId, score: 0.2, note: 'the Interesting column is really a Plus' });
  assert.equal(out.attempt.score, 0.2);
  assert.equal(out.attempt.scorer, 'human');
  assert.notEqual(before.attempt.scorer, 'human');
  assert.ok(out.ability.theta < thetaBefore, 'a lower human score must pull the estimate down');

  const profileAfter = await get(`/api/students/${student.id}`);
  assert.equal(profileAfter.strands.find((s) => s.strand === before.attempt.strand).theta, Math.round(out.ability.theta * 100) / 100);
});

test('the cohort view exposes the review queue and the class-wide gap', async () => {
  const cohort = await get('/api/teacher/cohort');
  assert.ok(cohort.students.length >= 1);
  assert.ok(Array.isArray(cohort.reviewQueue));
  assert.ok(Array.isArray(cohort.missingElement));
});

/* ------------------------------------------------------------- the forge */

test('a completed commission returns what it earned, and why each line was earned', async () => {
  const out = await post('/api/attempts', {
    studentId: student.id, taskId: 'log-t1-conditional-cancelled',
    response: { choice: 'c', meta: { hintLevel: 0, confidence: 90 } },
  });
  assert.ok(out.rewards, 'every scored attempt must come back with its rewards');
  assert.ok(out.rewards.xp > 0);
  assert.ok(out.rewards.lines.every((l) => l.certifies && l.label));
  assert.ok(out.rewards.lines.some((l) => l.key === 'new_tool'), 'a first use of a move is new ground');
  assert.equal(out.rewards.streak.streak, 1);
  assert.ok(out.rewards.rank.name);
});

test('the forge shows a deck derived from real mastery, plus quests', async () => {
  const g = await get(`/api/students/${student.id}/game`);
  assert.equal(g.deck.total, 45);
  assert.ok(g.deck.owned >= 1 && g.deck.owned < g.deck.total);
  assert.ok(g.deck.cards.find((c) => c.tier !== 'locked').next.length > 10, 'a card must say how to advance it');
  assert.equal(g.quests.filter((q) => q.period === 'day').length, 3);
  assert.equal(g.quests.filter((q) => q.period === 'week').length, 1);
  assert.ok(g.bosses.length >= 3);
  assert.equal(g.bosses.every((b) => b.unlocked), false, 'bosses start gated');
  assert.ok(g.classGoal.target > 0);
});

test('quests can be swapped, and swapping is free', async () => {
  const before = (await get(`/api/students/${student.id}/game`)).quests.filter((q) => q.period === 'day').map((q) => q.key);
  const xpBefore = (await get(`/api/students/${student.id}/game`)).xp;
  const after = (await post(`/api/students/${student.id}/quests/reroll`, { period: 'day' })).quests.filter((q) => q.period === 'day').map((q) => q.key);
  assert.notDeepEqual(before, after);
  assert.equal((await get(`/api/students/${student.id}/game`)).xp, xpBefore, 'a re-roll must not cost anything');
});

test('sparks buy freedom and decoration, and refuse when you cannot afford it', async () => {
  const before = await get(`/api/students/${student.id}/game`);
  const broke = await post(`/api/students/${student.id}/spend`, { item: 'crown' });
  assert.equal(broke.error, 'not_enough_sparks');
  const freeze = await post(`/api/students/${student.id}/spend`, { item: 'freeze' });
  assert.equal(freeze.ok, true);
  assert.equal(freeze.game.streak.freezes, before.streak.freezes + 1);
  assert.equal(freeze.game.sparks, before.sparks - 15);
  const nonsense = await post(`/api/students/${student.id}/spend`, { item: 'extra_points' });
  assert.equal(nonsense.error, 'unknown_item');
});

test('the ranking is empty until somebody opts in, and ranks effort', async () => {
  const off = await get('/api/leaderboard');
  assert.equal(off.rows.length, 0, 'nobody is ranked by default');
  assert.match(off.basis, /effort/i);
  await post(`/api/students/${student.id}/leaderboard-opt-in`, { optIn: true });
  const on = await get('/api/leaderboard');
  assert.equal(on.rows.length, 1);
  assert.equal(on.rows[0].studentId, student.id);
  await post(`/api/students/${student.id}/leaderboard-opt-in`, { optIn: false });
  assert.equal((await get('/api/leaderboard')).rows.length, 0);
});

test('a forge-off needs an opponent, and says so kindly when there is none', async () => {
  const none = await get(`/api/students/${student.id}/duel?taskId=log-t1-conditional-cancelled`);
  assert.equal(none.error, 'no_opponent');
  assert.match(none.message, /Nobody else/i);
});

test('a forge-off scores the critique, hides the author, and pays both sides', async () => {
  const { student: rival } = await post('/api/students', { displayName: 'Bo', age: 12, consent: true });
  await post('/api/attempts', {
    studentId: rival.id, taskId: 'arg-t1-toulmin-lite',
    response: {
      fields: {
        claim: 'The school should put a bike rack by the science block',
        evidence: 'Seven bikes are propped on the railings every morning',
        warrant: 'Because bikes are there',
      },
      meta: { hintLevel: 0, confidence: 60 },
    },
  });

  const duel = await get(`/api/students/${student.id}/duel?taskId=arg-t1-toulmin-lite`);
  assert.ok(duel.peerAttemptId);
  assert.equal(JSON.stringify(duel).includes(rival.id), false, 'the author must not be identifiable');
  assert.equal(JSON.stringify(duel).includes('Bo'), false);
  assert.equal(duel.task.payload.fields.length, 2);

  const rivalBefore = await get(`/api/students/${rival.id}/game`);
  const out = await post('/api/duel', {
    studentId: student.id, taskId: 'arg-t1-toulmin-lite', peerAttemptId: duel.peerAttemptId,
    response: {
      fields: {
        strongest: 'They did not just assert it — they gave a real observation about where bikes end up every morning, which is checkable.',
        missing: 'There is no warrant: no general rule saying that where things pile up is where the storage is needed, so the evidence could point elsewhere.',
      },
    },
  });
  assert.equal(out.valid, true);
  assert.ok(out.score > 0);
  assert.equal(out.earned.xp, 35);
  const rivalAfter = await get(`/api/students/${rival.id}/game`);
  assert.ok(rivalAfter.xp > rivalBefore.xp, 'the author earns for having their work studied');
});

test('everything can be exported and then deleted', async () => {
  const dump = await get(`/api/students/${student.id}/export`);
  assert.equal(dump.student.id, student.id);
  assert.ok(dump.attempts.length >= 1 && dump.transcripts.length >= 1);

  await fetch(`${base}/api/students/${student.id}`, { method: 'DELETE' });
  const gone = await get(`/api/students/${student.id}`);
  assert.equal(gone.error, 'not_found');
});

test('unknown routes and oversized payloads are refused politely', async () => {
  const res = await fetch(`${base}/api/nope`);
  assert.equal(res.status, 404);
  const big = await fetch(`${base}/api/attempts`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ studentId: 'x', taskId: 'y', response: { text: 'a'.repeat(300000) } }),
  });
  assert.equal(big.status, 413);
});
