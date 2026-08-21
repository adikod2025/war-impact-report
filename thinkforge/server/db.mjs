/**
 * Storage. node:sqlite (Node >= 22.5) keeps the platform dependency-free while
 * still giving us real transactions and a file a school can back up or delete
 * in one move — which matters, because deletion is a right here, not a feature.
 */
import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import path from 'node:path';

const DB_PATH = process.env.THINKFORGE_DB || path.join(process.cwd(), 'data', 'thinkforge.db');

let db;

export function getDb() {
  if (db) return db;
  fs.mkdirSync(path.dirname(DB_PATH), { recursive: true });
  db = new DatabaseSync(DB_PATH);
  db.exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;');
  migrate(db);
  return db;
}

function migrate(d) {
  d.exec(`
    CREATE TABLE IF NOT EXISTS guardians (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'teacher',
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS students (
      id TEXT PRIMARY KEY,
      display_name TEXT NOT NULL,
      age INTEGER NOT NULL,
      tier INTEGER NOT NULL,
      guardian_id TEXT REFERENCES guardians(id),
      consent_at TEXT,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS strand_state (
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      strand TEXT NOT NULL, theta REAL NOT NULL, n INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (student_id, strand)
    );
    CREATE TABLE IF NOT EXISTS move_state (
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      move TEXT NOT NULL, successes INTEGER DEFAULT 0, failures INTEGER DEFAULT 0,
      unaided_successes INTEGER DEFAULT 0, domains TEXT DEFAULT '[]',
      level INTEGER DEFAULT 0, last_seen TEXT,
      PRIMARY KEY (student_id, move)
    );
    CREATE TABLE IF NOT EXISTS item_state (
      task_id TEXT PRIMARY KEY, difficulty REAL NOT NULL, n INTEGER NOT NULL DEFAULT 0,
      seeded REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS attempts (
      id TEXT PRIMARY KEY,
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      task_id TEXT NOT NULL, strand TEXT NOT NULL, moves TEXT NOT NULL, domain TEXT NOT NULL,
      difficulty REAL, score REAL, adjusted_score REAL, objective REAL, rubric_score REAL,
      criteria TEXT, feedback TEXT, response TEXT, features TEXT, detail TEXT,
      confidence REAL, confidence_pred INTEGER, hint_level INTEGER DEFAULT 0,
      scorer TEXT, model TEXT, prompt_hash TEXT, rubric_version TEXT,
      flagged INTEGER DEFAULT 0, revision_of TEXT, duration_ms INTEGER,
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS attempts_student ON attempts(student_id, created_at);
    CREATE TABLE IF NOT EXISTS transcripts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      attempt_id TEXT, task_id TEXT, role TEXT NOT NULL, text TEXT NOT NULL,
      element TEXT, rung INTEGER, mode TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS snapshots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      at TEXT NOT NULL, payload TEXT NOT NULL, story TEXT
    );
    CREATE TABLE IF NOT EXISTS flags (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      kind TEXT NOT NULL, level TEXT, detail TEXT, attempt_id TEXT,
      resolved INTEGER DEFAULT 0, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS game_state (
      student_id TEXT PRIMARY KEY REFERENCES students(id) ON DELETE CASCADE,
      xp INTEGER NOT NULL DEFAULT 0, sparks INTEGER NOT NULL DEFAULT 0,
      streak INTEGER NOT NULL DEFAULT 0, longest INTEGER NOT NULL DEFAULT 0,
      freezes INTEGER NOT NULL DEFAULT 2, last_active_day TEXT,
      mark TEXT, leaderboard_opt_in INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS rewards (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      attempt_id TEXT, source TEXT NOT NULL, xp INTEGER NOT NULL, sparks INTEGER NOT NULL,
      lines TEXT, created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS rewards_student ON rewards(student_id, created_at);
    CREATE TABLE IF NOT EXISTS unlocks (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      kind TEXT NOT NULL, key TEXT NOT NULL, meta TEXT, created_at TEXT NOT NULL,
      UNIQUE (student_id, kind, key)
    );
    CREATE TABLE IF NOT EXISTS quests (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      period TEXT NOT NULL, period_key TEXT NOT NULL, quest_key TEXT NOT NULL,
      goal INTEGER NOT NULL, xp INTEGER NOT NULL, rerolls INTEGER NOT NULL DEFAULT 0,
      claimed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
      UNIQUE (student_id, period, period_key, quest_key)
    );
    CREATE TABLE IF NOT EXISTS duels (
      id TEXT PRIMARY KEY,
      student_id TEXT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
      task_id TEXT NOT NULL, peer_attempt_id TEXT, peer_student_id TEXT,
      score REAL, response TEXT, criteria TEXT, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS overrides (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      attempt_id TEXT NOT NULL, guardian_id TEXT, score REAL NOT NULL,
      note TEXT, created_at TEXT NOT NULL
    );
  `);
}

export const now = () => new Date().toISOString();
export const uid = (prefix) => `${prefix}_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`;

const j = (v) => JSON.stringify(v ?? null);
const p = (v, d = null) => { try { return v ? JSON.parse(v) : d; } catch { return d; } };

/* ---------- students ---------- */

export function createGuardian({ name, kind = 'teacher' }) {
  const d = getDb();
  const id = uid('g');
  d.prepare('INSERT INTO guardians (id,name,kind,created_at) VALUES (?,?,?,?)').run(id, name, kind, now());
  return { id, name, kind };
}

export function createStudent({ displayName, age, tier, guardianId = null, consent = false }) {
  const d = getDb();
  const id = uid('s');
  d.prepare('INSERT INTO students (id,display_name,age,tier,guardian_id,consent_at,created_at) VALUES (?,?,?,?,?,?,?)')
    .run(id, displayName, age, tier, guardianId, consent ? now() : null, now());
  return getStudent(id);
}

export function getStudent(id) {
  const row = getDb().prepare('SELECT * FROM students WHERE id = ?').get(id);
  return row ? mapStudent(row) : null;
}

export function listStudents() {
  return getDb().prepare('SELECT * FROM students ORDER BY created_at').all().map(mapStudent);
}

function mapStudent(r) {
  return { id: r.id, displayName: r.display_name, age: r.age, tier: r.tier, guardianId: r.guardian_id, consentAt: r.consent_at, createdAt: r.created_at };
}

export function deleteStudent(id) {
  getDb().prepare('DELETE FROM students WHERE id = ?').run(id);
}

/* ---------- ability ---------- */

export function getStrandStates(studentId) {
  return getDb().prepare('SELECT strand, theta, n FROM strand_state WHERE student_id = ?').all(studentId);
}

export function upsertStrandState(studentId, strand, theta, n) {
  getDb().prepare(`INSERT INTO strand_state (student_id,strand,theta,n,updated_at) VALUES (?,?,?,?,?)
    ON CONFLICT(student_id,strand) DO UPDATE SET theta=excluded.theta, n=excluded.n, updated_at=excluded.updated_at`)
    .run(studentId, strand, theta, n, now());
}

export function getItemState(taskId, seedDifficulty) {
  const d = getDb();
  const row = d.prepare('SELECT * FROM item_state WHERE task_id = ?').get(taskId);
  if (row) return { taskId: row.task_id, difficulty: row.difficulty, n: row.n, seeded: row.seeded };
  d.prepare('INSERT INTO item_state (task_id,difficulty,n,seeded) VALUES (?,?,0,?)').run(taskId, seedDifficulty, seedDifficulty);
  return { taskId, difficulty: seedDifficulty, n: 0, seeded: seedDifficulty };
}

export function updateItemState(taskId, difficulty, n) {
  getDb().prepare('UPDATE item_state SET difficulty = ?, n = ? WHERE task_id = ?').run(difficulty, n, taskId);
}

/* ---------- moves ---------- */

export function getMoveStates(studentId) {
  return getDb().prepare('SELECT * FROM move_state WHERE student_id = ?').all(studentId).map((r) => ({
    move: r.move, successes: r.successes, failures: r.failures, unaidedSuccesses: r.unaided_successes,
    domains: p(r.domains, []), level: r.level, lastSeen: r.last_seen,
  }));
}

export function upsertMoveState(studentId, state) {
  getDb().prepare(`INSERT INTO move_state (student_id,move,successes,failures,unaided_successes,domains,level,last_seen)
    VALUES (?,?,?,?,?,?,?,?)
    ON CONFLICT(student_id,move) DO UPDATE SET successes=excluded.successes, failures=excluded.failures,
      unaided_successes=excluded.unaided_successes, domains=excluded.domains, level=excluded.level, last_seen=excluded.last_seen`)
    .run(studentId, state.move, state.successes, state.failures, state.unaidedSuccesses, j(state.domains), state.level, state.lastSeen);
}

/* ---------- attempts ---------- */

export function insertAttempt(a) {
  const d = getDb();
  d.prepare(`INSERT INTO attempts (id,student_id,task_id,strand,moves,domain,difficulty,score,adjusted_score,objective,
      rubric_score,criteria,feedback,response,features,detail,confidence,confidence_pred,hint_level,scorer,model,
      prompt_hash,rubric_version,flagged,revision_of,duration_ms,created_at)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
    .run(a.id, a.studentId, a.taskId, a.strand, j(a.moves), a.domain, a.difficulty, a.score, a.adjustedScore,
      a.objective, a.rubricScore, j(a.criteria), j(a.feedback), j(a.response), j(a.features), j(a.detail),
      a.confidence, a.confidencePred ?? null, a.hintLevel || 0, a.scorer, a.model, a.promptHash, a.rubricVersion,
      a.flagged ? 1 : 0, a.revisionOf || null, a.durationMs || null, a.createdAt || now());
  return getAttempt(a.id);
}

function mapAttempt(r) {
  return {
    id: r.id, studentId: r.student_id, taskId: r.task_id, strand: r.strand, moves: p(r.moves, []),
    domain: r.domain, difficulty: r.difficulty, score: r.score, adjustedScore: r.adjusted_score,
    objective: r.objective, rubricScore: r.rubric_score, criteria: p(r.criteria, []), feedback: p(r.feedback),
    response: p(r.response), features: p(r.features), detail: p(r.detail), confidence: r.confidence,
    confidencePred: r.confidence_pred, hintLevel: r.hint_level, scorer: r.scorer, model: r.model,
    promptHash: r.prompt_hash, rubricVersion: r.rubric_version, flagged: !!r.flagged, revisionOf: r.revision_of,
    durationMs: r.duration_ms, createdAt: r.created_at,
  };
}

export function getAttempt(id) {
  const r = getDb().prepare('SELECT * FROM attempts WHERE id = ?').get(id);
  return r ? mapAttempt(r) : null;
}

export function listAttempts(studentId, limit = 500) {
  return getDb().prepare('SELECT * FROM attempts WHERE student_id = ? ORDER BY created_at LIMIT ?')
    .all(studentId, limit).map(mapAttempt);
}

export function listFlaggedAttempts(limit = 50) {
  return getDb().prepare('SELECT * FROM attempts WHERE flagged = 1 OR confidence < 0.5 ORDER BY created_at DESC LIMIT ?')
    .all(limit).map(mapAttempt);
}

export function overrideScore({ attemptId, guardianId = null, score, note = null }) {
  const d = getDb();
  d.prepare('INSERT INTO overrides (attempt_id,guardian_id,score,note,created_at) VALUES (?,?,?,?,?)')
    .run(attemptId, guardianId ?? null, score, note || null, now());
  d.prepare('UPDATE attempts SET score = ?, adjusted_score = ?, scorer = ?, flagged = 0, confidence = 1 WHERE id = ?')
    .run(score, score, 'human', attemptId);
  return getAttempt(attemptId);
}

export function listOverrides(attemptId) {
  return getDb().prepare('SELECT * FROM overrides WHERE attempt_id = ? ORDER BY created_at').all(attemptId);
}

/* ---------- transcripts, snapshots, flags ---------- */

export function addTranscript(t) {
  getDb().prepare('INSERT INTO transcripts (student_id,attempt_id,task_id,role,text,element,rung,mode,created_at) VALUES (?,?,?,?,?,?,?,?,?)')
    .run(t.studentId, t.attemptId || null, t.taskId || null, t.role, t.text, t.element || null, t.rung ?? null, t.mode || null, now());
}

export function getTranscript(studentId, taskId) {
  return getDb().prepare('SELECT * FROM transcripts WHERE student_id = ? AND task_id = ? ORDER BY id').all(studentId, taskId);
}

export function listTranscripts(studentId, limit = 200) {
  return getDb().prepare('SELECT * FROM transcripts WHERE student_id = ? ORDER BY id DESC LIMIT ?').all(studentId, limit);
}

export function addSnapshot(studentId, payload, story) {
  const d = getDb();
  d.prepare('INSERT INTO snapshots (student_id,at,payload,story) VALUES (?,?,?,?)').run(studentId, payload.at, j(payload), j(story));
  return listSnapshots(studentId);
}

export function listSnapshots(studentId, limit = 30) {
  return getDb().prepare('SELECT * FROM snapshots WHERE student_id = ? ORDER BY at DESC LIMIT ?')
    .all(studentId, limit).map((r) => ({ id: r.id, at: r.at, ...p(r.payload, {}), story: p(r.story) }));
}

export function addFlag(f) {
  getDb().prepare('INSERT INTO flags (student_id,kind,level,detail,attempt_id,created_at) VALUES (?,?,?,?,?,?)')
    .run(f.studentId, f.kind, f.level || null, j(f.detail), f.attemptId || null, now());
}

export function listFlags({ resolved = 0, limit = 100 } = {}) {
  return getDb().prepare('SELECT * FROM flags WHERE resolved = ? ORDER BY created_at DESC LIMIT ?')
    .all(resolved, limit).map((r) => ({ ...r, detail: p(r.detail) }));
}

export function resolveFlag(id) {
  getDb().prepare('UPDATE flags SET resolved = 1 WHERE id = ?').run(id);
}

/* ---------- the game layer ---------- */

export function getGameState(studentId) {
  const d = getDb();
  let row = d.prepare('SELECT * FROM game_state WHERE student_id = ?').get(studentId);
  if (!row) {
    d.prepare('INSERT INTO game_state (student_id) VALUES (?)').run(studentId);
    row = d.prepare('SELECT * FROM game_state WHERE student_id = ?').get(studentId);
  }
  return {
    studentId: row.student_id, xp: row.xp, sparks: row.sparks, streak: row.streak,
    longest: row.longest, freezes: row.freezes, lastActiveDay: row.last_active_day,
    mark: row.mark, leaderboardOptIn: !!row.leaderboard_opt_in,
  };
}

export function saveGameState(state) {
  getDb().prepare(`UPDATE game_state SET xp=?, sparks=?, streak=?, longest=?, freezes=?,
      last_active_day=?, mark=?, leaderboard_opt_in=? WHERE student_id=?`)
    .run(state.xp, state.sparks, state.streak, state.longest, state.freezes,
      state.lastActiveDay ?? null, state.mark ?? null, state.leaderboardOptIn ? 1 : 0, state.studentId);
  return getGameState(state.studentId);
}

export function addReward({ studentId, attemptId = null, source, xp, sparks, lines = [] }) {
  getDb().prepare('INSERT INTO rewards (student_id,attempt_id,source,xp,sparks,lines,created_at) VALUES (?,?,?,?,?,?,?)')
    .run(studentId, attemptId, source, xp, sparks, j(lines), now());
}

export function listRewards(studentId, sinceIso = null) {
  const d = getDb();
  const rows = sinceIso
    ? d.prepare('SELECT * FROM rewards WHERE student_id = ? AND created_at >= ? ORDER BY created_at').all(studentId, sinceIso)
    : d.prepare('SELECT * FROM rewards WHERE student_id = ? ORDER BY created_at').all(studentId);
  return rows.map((r) => ({ id: r.id, attemptId: r.attempt_id, source: r.source, xp: r.xp, sparks: r.sparks, lines: p(r.lines, []), createdAt: r.created_at }));
}

export function xpSince(studentId, sinceIso) {
  const row = getDb().prepare('SELECT COALESCE(SUM(xp),0) AS xp FROM rewards WHERE student_id = ? AND created_at >= ?').get(studentId, sinceIso);
  return row?.xp || 0;
}

export function addUnlock({ studentId, kind, key, meta = null }) {
  try {
    getDb().prepare('INSERT INTO unlocks (student_id,kind,key,meta,created_at) VALUES (?,?,?,?,?)')
      .run(studentId, kind, key, j(meta), now());
    return true;
  } catch {
    return false;   // already held; unlocks are idempotent by design
  }
}

export function listUnlocks(studentId) {
  return getDb().prepare('SELECT * FROM unlocks WHERE student_id = ? ORDER BY created_at').all(studentId)
    .map((r) => ({ kind: r.kind, key: r.key, meta: p(r.meta), at: r.created_at }));
}

export function getQuests(studentId, period, periodKey) {
  return getDb().prepare('SELECT * FROM quests WHERE student_id = ? AND period = ? AND period_key = ?')
    .all(studentId, period, periodKey)
    .map((r) => ({ id: r.id, key: r.quest_key, period: r.period, periodKey: r.period_key, goal: r.goal, xp: r.xp, rerolls: r.rerolls, claimed: !!r.claimed }));
}

export function saveQuests(studentId, quests, rerolls = 0) {
  const d = getDb();
  for (const q of quests) {
    d.prepare(`INSERT OR IGNORE INTO quests (student_id,period,period_key,quest_key,goal,xp,rerolls,created_at)
      VALUES (?,?,?,?,?,?,?,?)`).run(studentId, q.period, q.periodKey, q.key, q.goal, q.xp, rerolls, now());
  }
  return getQuests(studentId, quests[0]?.period, quests[0]?.periodKey);
}

export function clearQuests(studentId, period, periodKey) {
  getDb().prepare('DELETE FROM quests WHERE student_id = ? AND period = ? AND period_key = ? AND claimed = 0')
    .run(studentId, period, periodKey);
}

export function claimQuest(studentId, period, periodKey, questKey) {
  const d = getDb();
  const row = d.prepare('SELECT * FROM quests WHERE student_id=? AND period=? AND period_key=? AND quest_key=? AND claimed=0')
    .get(studentId, period, periodKey, questKey);
  if (!row) return null;
  d.prepare('UPDATE quests SET claimed = 1 WHERE id = ?').run(row.id);
  return { key: row.quest_key, xp: row.xp };
}

export function insertDuel(duel) {
  getDb().prepare('INSERT INTO duels (id,student_id,task_id,peer_attempt_id,peer_student_id,score,response,criteria,created_at) VALUES (?,?,?,?,?,?,?,?,?)')
    .run(duel.id, duel.studentId, duel.taskId, duel.peerAttemptId, duel.peerStudentId, duel.score, j(duel.response), j(duel.criteria), now());
}

export function listDuels(studentId, sinceIso = null) {
  const d = getDb();
  const rows = sinceIso
    ? d.prepare('SELECT * FROM duels WHERE student_id = ? AND created_at >= ?').all(studentId, sinceIso)
    : d.prepare('SELECT * FROM duels WHERE student_id = ?').all(studentId);
  return rows.map((r) => ({ id: r.id, taskId: r.task_id, peerAttemptId: r.peer_attempt_id, score: r.score, createdAt: r.created_at }));
}

/** A peer answer on the same commission, from someone else, never the same student. */
export function findPeerAttempt(studentId, taskId) {
  return getDb().prepare(`SELECT * FROM attempts WHERE task_id = ? AND student_id != ? AND score IS NOT NULL
      AND id NOT IN (SELECT COALESCE(peer_attempt_id,'') FROM duels WHERE student_id = ?)
      ORDER BY created_at DESC LIMIT 1`)
    .all(taskId, studentId, studentId).map(mapAttempt)[0] || null;
}

export function leaderboard(sinceIso) {
  return getDb().prepare(`SELECT s.id, s.display_name, g.mark, COALESCE(SUM(r.xp),0) AS xp
      FROM students s JOIN game_state g ON g.student_id = s.id
      LEFT JOIN rewards r ON r.student_id = s.id AND r.created_at >= ?
      WHERE g.leaderboard_opt_in = 1
      GROUP BY s.id ORDER BY xp DESC`).all(sinceIso)
    .map((r) => ({ studentId: r.id, displayName: r.display_name, mark: r.mark, xp: r.xp }));
}

export function classXpSince(sinceIso) {
  const row = getDb().prepare('SELECT COALESCE(SUM(xp),0) AS xp FROM rewards WHERE created_at >= ?').get(sinceIso);
  return row?.xp || 0;
}

export function exportStudent(studentId) {
  return {
    student: getStudent(studentId),
    strands: getStrandStates(studentId),
    moves: getMoveStates(studentId),
    attempts: listAttempts(studentId, 10000),
    transcripts: listTranscripts(studentId, 10000),
    snapshots: listSnapshots(studentId, 1000),
    game: getGameState(studentId),
    rewards: listRewards(studentId),
    unlocks: listUnlocks(studentId),
    exportedAt: now(),
  };
}
