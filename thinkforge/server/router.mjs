import { send, readJson } from './http.mjs';
import * as db from './db.mjs';
import * as svc from './service.mjs';
import { getTask, publicTask, TASKS } from './content/index.mjs';
import { STRANDS, TIERS, LEVELS, allMoves } from './content/frameworks.mjs';

const routes = [];
const route = (method, pattern, handler) => routes.push({ method, pattern, handler });

/* ---------------------------------------------------------------- catalogue */

route('GET', /^\/api\/status$/, async (req, res) => send(res, 200, await svc.status()));

route('GET', /^\/api\/curriculum$/, (req, res) => send(res, 200, {
  strands: STRANDS, tiers: TIERS, levels: LEVELS, moves: allMoves(),
  tasks: TASKS.map((t) => ({ id: t.id, title: t.title, strand: t.strand, tier: t.tier, moves: t.moves, domain: t.domain, mode: t.mode, difficulty: t.difficulty })),
}));

route('GET', /^\/api\/tasks\/([\w-]+)$/, (req, res, [id]) => {
  const task = getTask(id);
  return task ? send(res, 200, publicTask(task)) : send(res, 404, { error: 'not_found' });
});

/* ----------------------------------------------------------------- people */

route('GET', /^\/api\/students$/, (req, res) => send(res, 200, { students: db.listStudents() }));

route('POST', /^\/api\/students$/, async (req, res) => {
  const body = await readJson(req);
  const age = Number(body.age);
  const name = String(body.displayName || '').trim().slice(0, 40);
  if (!name || !(age >= 8 && age <= 18)) return send(res, 400, { error: 'displayName and an age between 8 and 18 are required' });
  // Data minimisation: a first name and an age is all the platform ever stores.
  if (!body.consent) return send(res, 400, { error: 'guardian_consent_required' });
  const guardian = body.guardianId || db.createGuardian({ name: String(body.guardianName || 'Class teacher').slice(0, 60) }).id;
  const student = db.createStudent({ displayName: name, age, tier: svc.defaultTierForAge(age), guardianId: guardian, consent: true });
  return send(res, 201, { student });
});

route('GET', /^\/api\/students\/([\w]+)$/, (req, res, [id]) => {
  const p = svc.profile(id);
  return p ? send(res, 200, p) : send(res, 404, { error: 'not_found' });
});

route('DELETE', /^\/api\/students\/([\w]+)$/, (req, res, [id]) => {
  db.deleteStudent(id);
  return send(res, 200, { deleted: true });
});

route('GET', /^\/api\/students\/([\w]+)\/export$/, (req, res, [id]) => send(res, 200, db.exportStudent(id)));

/* -------------------------------------------------------------- the session */

route('GET', /^\/api\/students\/([\w]+)\/session$/, (req, res, [id]) => {
  const plan = svc.planSession(id);
  return plan ? send(res, 200, plan) : send(res, 404, { error: 'not_found' });
});

route('GET', /^\/api\/students\/([\w]+)\/hint$/, (req, res, [id], url) => {
  const task = getTask(url.searchParams.get('taskId'));
  const level = Math.max(1, Math.min(3, Number(url.searchParams.get('level') || 1)));
  if (!task) return send(res, 404, { error: 'not_found' });
  return send(res, 200, { level, hint: task.hints[level - 1], cost: [0, 0.08, 0.18, 0.3][level] });
});

route('POST', /^\/api\/attempts$/, async (req, res) => {
  const body = await readJson(req);
  const result = await svc.submitAttempt(body);
  if (result.error) return send(res, 404, result);
  return send(res, result.valid === false ? 200 : 201, result);
});

/** Run one test on a black-box machine. The rule never leaves the server. */
route('POST', /^\/api\/attempts\/probe-run$/, async (req, res) => {
  const { taskId, inputs } = await readJson(req);
  const task = getTask(taskId);
  if (!task || task.mode !== 'probe') return send(res, 404, { error: 'not_found' });
  const { runMachine } = await import('./engine/probe.mjs');
  return send(res, 200, runMachine(task.payload.machine, inputs || {}));
});

route('POST', /^\/api\/tutor$/, async (req, res) => {
  const body = await readJson(req);
  const turn = await svc.tutor(body);
  return turn.error ? send(res, 404, turn) : send(res, 200, turn);
});

route('GET', /^\/api\/students\/([\w]+)\/transcript$/, (req, res, [id], url) => {
  const taskId = url.searchParams.get('taskId');
  return send(res, 200, { turns: taskId ? db.getTranscript(id, taskId) : db.listTranscripts(id) });
});

/* ---------------------------------------------------------------- evolution */

route('POST', /^\/api\/students\/([\w]+)\/snapshot$/, async (req, res, [id]) => {
  const out = await svc.takeSnapshot(id);
  return out ? send(res, 201, out) : send(res, 404, { error: 'not_found' });
});

route('GET', /^\/api\/students\/([\w]+)\/snapshots$/, (req, res, [id]) => send(res, 200, { snapshots: db.listSnapshots(id) }));

/* --------------------------------------------------------------- the forge */

route('GET', /^\/api\/students\/([\w]+)\/game$/, (req, res, [id]) => {
  const out = svc.gameFor(id);
  return out ? send(res, 200, out) : send(res, 404, { error: 'not_found' });
});

route('POST', /^\/api\/students\/([\w]+)\/quests\/reroll$/, async (req, res, [id]) => {
  const { period = 'day' } = await readJson(req);
  if (!['day', 'week'].includes(period)) return send(res, 400, { error: 'bad_period' });
  return send(res, 200, svc.rerollQuests(id, period));
});

route('POST', /^\/api\/students\/([\w]+)\/spend$/, async (req, res, [id]) => {
  const { item } = await readJson(req);
  const out = svc.spendSparks(id, String(item || ''));
  return out.error ? send(res, 400, out) : send(res, 200, out);
});

route('POST', /^\/api\/students\/([\w]+)\/mark$/, async (req, res, [id]) => {
  const { key } = await readJson(req);
  const out = svc.setMark(id, key || null);
  return out.error ? send(res, 400, out) : send(res, 200, out);
});

route('POST', /^\/api\/students\/([\w]+)\/leaderboard-opt-in$/, async (req, res, [id]) => {
  const { optIn } = await readJson(req);
  return send(res, 200, svc.setLeaderboardOptIn(id, !!optIn));
});

route('GET', /^\/api\/leaderboard$/, (req, res) => send(res, 200, svc.leaderboard()));

route('GET', /^\/api\/class-goal$/, (req, res) => send(res, 200, svc.classGoal()));

route('GET', /^\/api\/students\/([\w]+)\/duel$/, (req, res, [id], url) => {
  const out = svc.startDuel({ studentId: id, taskId: url.searchParams.get('taskId') });
  return out.error ? send(res, out.error === 'no_opponent' ? 200 : 404, out) : send(res, 200, out);
});

route('POST', /^\/api\/duel$/, async (req, res) => {
  const body = await readJson(req);
  const out = await svc.submitDuel(body);
  return out.error ? send(res, 404, out) : send(res, 200, out);
});

/* ------------------------------------------------------------------ teacher */

route('GET', /^\/api\/teacher\/cohort$/, (req, res) => send(res, 200, svc.cohort()));

route('POST', /^\/api\/teacher\/override$/, async (req, res) => {
  const body = await readJson(req);
  if (typeof body.score !== 'number' || body.score < 0 || body.score > 1) return send(res, 400, { error: 'score must be 0..1' });
  const out = svc.applyOverride(body);
  return out ? send(res, 200, out) : send(res, 404, { error: 'not_found' });
});

route('GET', /^\/api\/teacher\/flags$/, (req, res) => send(res, 200, { flags: db.listFlags({}) }));

route('POST', /^\/api\/teacher\/flags\/(\d+)\/resolve$/, (req, res, [id]) => {
  db.resolveFlag(Number(id));
  return send(res, 200, { resolved: true });
});

route('GET', /^\/api\/attempts\/([\w]+)$/, (req, res, [id]) => {
  const a = db.getAttempt(id);
  if (!a) return send(res, 404, { error: 'not_found' });
  return send(res, 200, { attempt: a, overrides: db.listOverrides(id), task: publicTask(getTask(a.taskId)) });
});

export async function handleApi(req, res, url) {
  for (const r of routes) {
    if (r.method !== req.method) continue;
    const match = url.pathname.match(r.pattern);
    if (!match) continue;
    try {
      return await r.handler(req, res, match.slice(1), url);
    } catch (err) {
      if (err.message === 'payload_too_large') return send(res, 413, { error: 'payload_too_large' });
      console.error('[thinkforge]', req.method, url.pathname, err);
      return send(res, 500, { error: 'server_error', detail: String(err.message || err) });
    }
  }
  return send(res, 404, { error: 'no_such_route' });
}
