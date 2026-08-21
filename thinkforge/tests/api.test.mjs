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

const { start, server } = await import('../server/index.mjs');
await start();
const base = `http://127.0.0.1:${process.env.PORT}`;

const get = async (p) => (await fetch(base + p)).json();
const post = async (p, body) => (await fetch(base + p, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })).json();

test.after(() => {
  server.close();
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
