/**
 * The application layer: everything that happens between an HTTP request and
 * the engine. Scoring, state updates, session assembly and the tutor loop live
 * here so the router stays a thin translation of HTTP into these calls.
 */
import * as db from './db.mjs';
import { TASKS, getTask, publicTask } from './content/index.mjs';
import { STRANDS, getMove, getStrand, levelForTheta, defaultTierForAge, LEVELS } from './content/frameworks.mjs';
import { scoreResponse } from './engine/scoring.mjs';
import { update as eloUpdate, expected } from './engine/elo.mjs';
import { rankTasks } from './engine/selector.mjs';
import { rankReviews, isHeld, nextReviewAt } from './engine/mastery.mjs';
import { indices, strandProfile, buildSnapshot } from './engine/growth.mjs';
import { makeAiRubric, checkRuleEquivalence } from './ai/scorer.mjs';
import { tutorTurn } from './ai/tutor.mjs';
import { growthStory } from './ai/narrative.mjs';
import { aiStatus } from './ai/client.mjs';
import { screenStudentText } from './ai/safety.mjs';

const START_THETA = -1.0;

/* ------------------------------------------------------------------ state */

function thetaMap(studentId) {
  const rows = db.getStrandStates(studentId);
  const map = {};
  for (const s of STRANDS) map[s.id] = START_THETA;
  for (const r of rows) map[r.strand] = r.theta;
  return map;
}

function strandRow(studentId, strand) {
  const rows = db.getStrandStates(studentId);
  return rows.find((r) => r.strand === strand) || { strand, theta: START_THETA, n: 0 };
}

export function heldMoves(studentId) {
  return db.getMoveStates(studentId).filter(isHeld).map((m) => m.move);
}

export function profile(studentId) {
  const student = db.getStudent(studentId);
  if (!student) return null;
  const attempts = db.listAttempts(studentId);
  const byStrand = {};
  for (const a of attempts) (byStrand[a.strand] ||= []).push(a);
  const states = db.getStrandStates(studentId);
  const moves = db.getMoveStates(studentId);
  const held = moves.filter(isHeld).map((m) => m.move);
  return {
    student,
    strands: strandProfile(states.length ? states : STRANDS.map((s) => ({ strand: s.id, theta: START_THETA, n: 0 })), byStrand),
    indices: indices(attempts, held),
    moves: moves.map((m) => ({
      ...m,
      name: getMove(m.move)?.name || m.move,
      strand: getMove(m.move)?.strand,
      held: isHeld(m),
      dueAt: m.lastSeen ? nextReviewAt(m) : null,
    })),
    heldMoves: held,
    attempts: attempts.length,
    minutes: Math.round(attempts.reduce((sum, a) => sum + (a.durationMs || 0), 0) / 60000),
    snapshots: db.listSnapshots(studentId, 12),
  };
}

/* ------------------------------------------------------------ session plan */

/**
 * The five-beat session (docs/02 §5). Beat 1 is retrieval of a due move,
 * beat 2 introduces or fades a move, beat 3 is the authentic mission.
 */
export function planSession(studentId) {
  const student = db.getStudent(studentId);
  if (!student) return null;
  const history = db.listAttempts(studentId).map((a) => ({
    taskId: a.taskId, strand: a.strand, moves: a.moves, domain: a.domain, score: a.score,
  }));
  const moveStates = db.getMoveStates(studentId);
  const theta = thetaMap(studentId);
  const due = rankReviews(moveStates).filter((r) => r.urgency > 0.2).map((r) => r.move);

  const ranked = rankTasks({ tasks: TASKS, strandTheta: theta, history, moveStates, age: student.age });
  const pick = (filter, used) => ranked.find((r) => !used.has(r.task.id) && filter(r));

  const used = new Set();
  const chosen = [];

  const warmup = due.length ? pick((r) => r.task.moves.some((m) => due.includes(m)), used) : null;
  if (warmup) { used.add(warmup.task.id); chosen.push({ beat: 'warm-up', why: 'A move that is due for retrieval.', ...warmup }); }

  const core = pick(() => true, used);
  if (core) { used.add(core.task.id); chosen.push({ beat: 'move of the day', why: reasonFor(core), ...core }); }

  const mission = pick((r) => !chosen.some((c) => c.task.strand === r.task.strand), used)
    || pick(() => true, used);
  if (mission) { used.add(mission.task.id); chosen.push({ beat: 'mission', why: reasonFor(mission), ...mission }); }

  return {
    student,
    beats: chosen.map((c) => ({
      beat: c.beat, why: c.why, successChance: c.p, utility: c.utility,
      task: publicTask(c.task),
      rung: ladderRung(c.task, moveStates),
    })),
    due,
  };
}

function reasonFor(r) {
  const parts = [];
  if (r.parts.review > 0.4) parts.push('due for review');
  if (r.parts.novelty === 1) parts.push('this move in a domain you have not tried it in');
  if (r.parts.deficit > 0.5) parts.push('your weakest strand right now');
  if (r.parts.starvation > 0.7) parts.push('this strand has been left alone too long');
  if (!parts.length) parts.push(`pitched at about a ${Math.round(r.p * 100)}% chance of success`);
  return parts.join(', ');
}

/**
 * Where on the fading ladder this student stands for this task's moves:
 * study → complete → attempt-with-hints → attempt-clean.
 */
export function ladderRung(task, moveStates) {
  const states = task.moves.map((m) => moveStates.find((s) => s.move === m)).filter(Boolean);
  if (!states.length) return { rung: 'study', label: 'New move — read the worked example first.' };
  const unaided = Math.max(...states.map((s) => s.unaidedSuccesses || 0));
  const seen = Math.max(...states.map((s) => (s.successes || 0) + (s.failures || 0)));
  if (seen === 0) return { rung: 'study', label: 'New move — read the worked example first.' };
  if (unaided === 0) return { rung: 'complete', label: 'Finish the partly-worked version, then do yours.' };
  if (unaided < 2) return { rung: 'guided', label: 'Have a go — hints are there if you need them.' };
  return { rung: 'clean', label: 'You have this one. No hints unless you ask.' };
}

/* ---------------------------------------------------------------- scoring */

/**
 * Deterministic feedback, at Hattie & Timperley's task / process /
 * self-regulation levels and never at the self level. Used whenever the AI
 * marker is unavailable.
 */
function offlineFeedback(task, scored) {
  const criteria = [...(scored.criteria || [])].sort((a, b) => a.score - b.score);
  const weakest = criteria[0];
  const strongest = criteria[criteria.length - 1];
  const missing = scored.capsApplied?.map((c) => c.field) || [];
  const solo = task.rubric?.solo?.[3];
  const anchorFor = (c) => c.anchors?.[String(Math.floor(c.score))] || c.anchor;

  const taskLevel = missing.length
    ? `The "${missing.join('", "')}" part is missing or too thin — that is what the rest of the answer rests on, so it caps the score.`
    : weakest && weakest.score < 2.5
      ? `Thinnest part — ${weakest.name.toLowerCase()}: ${anchorFor(weakest)}`
      : 'All the parts the rubric looks for are present and doing work.';

  const processLevel = strongest && strongest.score >= 2 && weakest && weakest.score < strongest.score
    ? `Your ${strongest.name.toLowerCase()} carried this. The move that would change it most is the one behind ${weakest.name.toLowerCase()}.`
    : 'Run the move one step at a time rather than writing the whole answer in one pass — the steps are where it goes wrong.';

  return {
    task: taskLevel,
    process: processLevel,
    selfRegulation: solo
      ? `Check your own work against this before you submit next time: ${solo}`
      : 'Before submitting, reread it once and ask what a reader could still object to.',
    source: 'offline',
  };
}

export async function submitAttempt({ studentId, taskId, response = {}, revisionOf = null }) {
  const student = db.getStudent(studentId);
  const task = getTask(taskId);
  if (!student || !task) return { error: 'not_found' };

  // Safety screening happens before anything is stored or sent anywhere.
  const written = task.mode === 'structured'
    ? Object.values(response.fields || {}).join('\n')
    : (response.text || response.rule || '');
  const screen = screenStudentText(written);
  if (screen.action === 'escalate') {
    db.addFlag({ studentId, kind: 'safety', level: screen.level, detail: { taskId, matched: screen.matched } });
    return { safety: { level: screen.level, message: screen.reply } };
  }

  const ai = await aiStatus();
  const scored = await scoreResponse(task, response, ai.available ? { aiRubric: makeAiRubric() } : {});

  if (!scored.valid) {
    return { valid: false, reason: scored.reason, repair: scored.repair };
  }

  // A `probe` rule stated in the student's own words is checked for
  // equivalence by the model when one is available — an easier and more
  // reliable AI job than open-ended marking.
  if (task.mode === 'probe' && ai.available) {
    try {
      const eq = await checkRuleEquivalence(response.rule, task.payload.machine);
      if (eq) {
        const ruleFit = eq.equivalent ? 1 : eq.partial ? 0.55 : 0.1;
        scored.detail.ruleFit = ruleFit;
        scored.detail.ruleCheck = eq;
        const process = scored.detail.process?.process ?? 0;
        scored.score = Math.min(scored.cap, 0.5 * process + 0.5 * ruleFit);
        scored.adjustedScore = Math.max(0, scored.score - scored.hintPenalty);
        scored.confidence = Math.max(scored.confidence, 0.85);
      }
    } catch { /* keep the offline estimate */ }
  }

  const item = db.getItemState(taskId, task.difficulty);
  const primary = strandRow(studentId, task.strand);
  const upd = eloUpdate({
    theta: primary.theta, difficulty: item.difficulty, score: scored.adjustedScore,
    studentN: primary.n, itemN: item.n, confidence: scored.confidence, weight: 1,
  });
  db.upsertStrandState(studentId, task.strand, upd.theta, primary.n + 1);
  db.updateItemState(taskId, upd.difficulty, item.n + 1);

  // Secondary strands: a task that exercises a move from another strand gives
  // weaker evidence about that strand, not none.
  const secondary = new Set(task.moves.map((m) => getMove(m)?.strand).filter((s) => s && s !== task.strand));
  for (const strand of secondary) {
    const row = strandRow(studentId, strand);
    const su = eloUpdate({
      theta: row.theta, difficulty: item.difficulty, score: scored.adjustedScore,
      studentN: row.n, itemN: 9999, confidence: scored.confidence, weight: 0.35,
    });
    db.upsertStrandState(studentId, strand, su.theta, row.n + 1);
  }

  // Move retention state
  const moveStates = db.getMoveStates(studentId);
  for (const move of task.moves) {
    const s = moveStates.find((x) => x.move === move)
      || { move, successes: 0, failures: 0, unaidedSuccesses: 0, domains: [], level: 0 };
    const good = scored.score >= 0.6;
    const domains = new Set(s.domains);
    if (good) domains.add(task.domain);
    db.upsertMoveState(studentId, {
      move,
      successes: s.successes + (good ? 1 : 0),
      failures: s.failures + (scored.score < 0.4 ? 1 : 0),
      unaidedSuccesses: s.unaidedSuccesses + (good && !scored.hintLevel ? 1 : 0),
      domains: [...domains],
      level: Math.max(s.level, levelForTheta(upd.theta)),
      lastSeen: new Date().toISOString(),
    });
  }

  const feedback = scored.criteria?.length && scored.scorer === 'ai' && scored.aiFeedback
    ? scored.aiFeedback
    : offlineFeedback(task, scored);

  const attempt = db.insertAttempt({
    id: db.uid('a'), studentId, taskId, strand: task.strand, moves: task.moves, domain: task.domain,
    difficulty: item.difficulty, score: scored.score, adjustedScore: scored.adjustedScore,
    objective: scored.objective, rubricScore: scored.rubricScore, criteria: scored.criteria,
    feedback, response, features: scored.features, detail: scored.detail,
    confidence: scored.confidence, confidencePred: response.meta?.confidence ?? null,
    hintLevel: scored.hintLevel, scorer: scored.scorer, model: scored.model,
    promptHash: scored.promptHash, rubricVersion: scored.rubricVersion,
    flagged: scored.flagged, revisionOf, durationMs: response.meta?.durationMs || null,
  });

  if (scored.flagged || scored.confidence < 0.5) {
    db.addFlag({ studentId, kind: 'review', level: 'low_confidence', attemptId: attempt.id, detail: { taskId, confidence: scored.confidence } });
  }

  const levelNow = levelForTheta(upd.theta);
  const levelBefore = levelForTheta(primary.theta);

  return {
    valid: true,
    attempt,
    scored: {
      score: scored.score, adjustedScore: scored.adjustedScore, confidence: scored.confidence,
      scorer: scored.scorer, criteria: scored.criteria, capsApplied: scored.capsApplied,
      objective: scored.objective, detail: scored.detail, hintPenalty: scored.hintPenalty,
    },
    feedback,
    ability: {
      strand: task.strand, theta: upd.theta, delta: upd.studentDelta,
      expected: Math.round(upd.expected * 100) / 100,
      level: levelNow, levelUp: levelNow > levelBefore, levelName: LEVELS[levelNow]?.name,
    },
    calibration: response.meta?.confidence != null
      ? { predicted: response.meta.confidence, actual: Math.round(scored.score * 100), gap: Math.round(response.meta.confidence - scored.score * 100) }
      : null,
    exemplar: task.rubric?.solo?.[3] || null,
    bridge: task.bridge,
  };
}

/* ----------------------------------------------------------------- tutor */

export async function tutor({ studentId, taskId, message = '', attemptId = null }) {
  const student = db.getStudent(studentId);
  const task = getTask(taskId);
  if (!student || !task) return { error: 'not_found' };

  const attempts = db.listAttempts(studentId);
  const last = attemptId ? db.getAttempt(attemptId) : [...attempts].reverse().find((a) => a.taskId === taskId);
  const history = db.getTranscript(studentId, taskId).map((t) => ({ role: t.role, text: t.text }));
  const ind = indices(attempts, heldMoves(studentId)).independence;

  const text = last ? textOfResponse(task, last.response) : '';
  if (message) db.addTranscript({ studentId, attemptId: last?.id, taskId, role: 'student', text: message });

  const turn = await tutorTurn({
    task, text, history, studentMessage: message, age: student.age,
    independence: ind.available ? ind.value / 100 : 0.5,
    attempts: attempts.filter((a) => a.taskId === taskId).length || 1,
    hintsSeen: last?.hintLevel || 0,
    scoreSummary: last ? { score: last.score, criteria: last.criteria?.map((c) => ({ id: c.id, score: c.score })) } : null,
  });

  db.addTranscript({ studentId, attemptId: last?.id, taskId, role: 'tutor', text: turn.reply, element: turn.element, rung: turn.rung, mode: turn.mode });
  if (turn.escalate) {
    db.addFlag({ studentId, kind: 'safety', level: turn.escalate.level, detail: { taskId, matched: turn.escalate.matched } });
  }
  return turn;
}

function textOfResponse(task, response = {}) {
  if (task.mode === 'structured') return Object.entries(response.fields || {}).map(([k, v]) => `[${k}] ${v}`).join('\n');
  return response.text || response.rule || '';
}

/* -------------------------------------------------------------- snapshots */

export async function takeSnapshot(studentId) {
  const p = profile(studentId);
  if (!p) return null;
  const attempts = db.listAttempts(studentId);
  const byStrand = {};
  for (const a of attempts) (byStrand[a.strand] ||= []).push(a);
  const snapshot = buildSnapshot({
    strandStates: db.getStrandStates(studentId),
    attempts, heldMoves: p.heldMoves, minutes: p.minutes, attemptsByStrand: byStrand,
  });
  const previous = db.listSnapshots(studentId, 2)[0] || null;
  const portfolio = [...attempts]
    .filter((a) => a.score >= 0.7 && a.criteria?.length)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map((a) => ({ move: a.moves[0], taskTitle: getTask(a.taskId)?.title, text: textOfResponse(getTask(a.taskId), a.response) }));
  const story = await growthStory({ current: snapshot, previous, portfolio, age: p.student.age });
  db.addSnapshot(studentId, snapshot, story);
  return { snapshot, story, portfolio };
}

/* ---------------------------------------------------------------- teacher */

export function cohort() {
  const students = db.listStudents();
  return {
    students: students.map((s) => {
      const attempts = db.listAttempts(s.id);
      const states = db.getStrandStates(s.id);
      return {
        ...s,
        attempts: attempts.length,
        strands: strandProfile(states.length ? states : STRANDS.map((x) => ({ strand: x.id, theta: START_THETA, n: 0 })), {})
          .map((p) => ({ strand: p.strand, level: p.level, theta: p.theta, n: p.n })),
        lastActive: attempts.length ? attempts[attempts.length - 1].createdAt : null,
        flagged: attempts.filter((a) => a.flagged).length,
      };
    }),
    reviewQueue: db.listFlaggedAttempts(25).map((a) => ({
      ...a, taskTitle: getTask(a.taskId)?.title, taskPrompt: getTask(a.taskId)?.prompt,
    })),
    safety: db.listFlags({ resolved: 0 }).filter((f) => f.kind === 'safety'),
    missingElement: missingElementReadout(students),
  };
}

/** "19 of 24 students omit the warrant" — the readout that drives the next lesson. */
function missingElementReadout(students) {
  const counts = new Map();
  for (const s of students) {
    const seen = new Set();
    for (const a of db.listAttempts(s.id)) {
      for (const c of a.criteria || []) {
        if (c.score <= 1) {
          const key = `${c.id}|${c.name}`;
          if (!seen.has(key)) { counts.set(key, (counts.get(key) || 0) + 1); seen.add(key); }
        }
      }
    }
  }
  return [...counts.entries()]
    .map(([key, n]) => ({ criterion: key.split('|')[0], name: key.split('|')[1], students: n, of: students.length }))
    .sort((a, b) => b.students - a.students)
    .slice(0, 6);
}

export async function status() {
  const ai = await aiStatus();
  return {
    ai,
    strands: STRANDS.map((s) => ({ id: s.id, name: s.name, claim: s.claim, colour: s.colour, moves: s.moves })),
    levels: LEVELS,
    tasks: TASKS.length,
    students: db.listStudents().length,
  };
}

export { defaultTierForAge, getStrand, expected };
