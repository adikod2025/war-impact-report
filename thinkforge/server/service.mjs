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
import * as game from './game/index.mjs';
import { critiqueTask, anonymise } from './game/duel.mjs';

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

  const metBefore = new Set(history.flatMap((h) => h.moves || []));

  const warmup = due.length ? pick((r) => r.task.moves.some((m) => due.includes(m)), used) : null;
  if (warmup) { used.add(warmup.task.id); chosen.push({ beat: 'warm-up', why: 'A move that is due for retrieval — you are just about to forget it.', ...warmup }); }

  const core = pick(() => true, used);
  if (core) { used.add(core.task.id); chosen.push({ beat: 'move of the day', why: reasonFor(core, metBefore), ...core }); }

  const mission = pick((r) => !chosen.some((c) => c.task.strand === r.task.strand), used)
    || pick(() => true, used);
  if (mission) { used.add(mission.task.id); chosen.push({ beat: 'mission', why: reasonFor(mission, metBefore), ...mission }); }

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

function reasonFor(r, metBefore = new Set()) {
  const parts = [];
  const isNew = r.task.moves.every((m) => !metBefore.has(m));
  if (r.parts.review > 0.4) parts.push('due for review');
  if (isNew) parts.push('a move you have not met yet');
  else if (r.parts.novelty === 1) parts.push('this move in a domain you have not used it in');
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

  const allStrong = criteria.length && weakest.score >= 2;
  const processLevel = allStrong
    ? `Every criterion is doing work here. The next step up is not more of this — it is going beyond the case: ${(task.rubric?.solo?.[4] || 'generalise the move and say where else it would hold').replace(/\.\s*$/, '')}.`
    : strongest && strongest.score >= 2 && weakest && weakest.score < strongest.score
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

  // Move retention state. The snapshot before the update is what the game
  // layer diffs against, so a card can only advance when the mastery did.
  const moveStates = db.getMoveStates(studentId);
  const beforeMoveStates = moveStates.map((m) => ({ ...m, domains: [...(m.domains || [])] }));
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

  const original = revisionOf ? db.getAttempt(revisionOf) : null;
  const rewards = grantRewards({
    studentId, task, scored, attempt,
    beforeMoveStates,
    revisionGain: original ? scored.score - original.score : null,
  });

  return {
    valid: true,
    attempt,
    rewards,
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

/* ------------------------------------------------------------ the game layer */

const WEEK_START = () => `${game.weekKey()}T00:00:00.000Z`;
const CLASS_GOAL_PER_STUDENT = 250;

/**
 * Turn one completed attempt into XP, sparks, tempered cards, badges, quest
 * progress and a streak update. Nothing here can be earned without the
 * corresponding learning event having actually happened (docs/04 §2).
 */
function grantRewards({ studentId, task, scored, attempt, beforeMoveStates, revisionGain }) {
  const afterMoveStates = db.getMoveStates(studentId);
  const earned = game.rewardsForAttempt({ task, scored, attempt, beforeMoveStates, afterMoveStates, revisionGain });

  const state = db.getGameState(studentId);
  const streak = game.updateStreak(state, game.dayKey());
  const next = {
    ...state,
    xp: state.xp + earned.xp,
    sparks: state.sparks + earned.sparks,
    streak: streak.streak, longest: streak.longest, freezes: streak.freezes,
    lastActiveDay: streak.lastActiveDay,
  };
  db.addReward({ studentId, attemptId: attempt.id, source: 'attempt', xp: earned.xp, sparks: earned.sparks, lines: earned.lines });

  const attempts = db.listAttempts(studentId);
  const deck = game.deckFor(afterMoveStates);
  const bosses = game.bossCommissions(afterMoveStates);
  const held = new Set(db.listUnlocks(studentId).filter((u) => u.kind === 'badge').map((u) => u.key));
  const newBadges = game.checkBadges({
    attempts, indices: indices(attempts, heldMoves(studentId)), moveStates: afterMoveStates, deck, bosses, held,
  });
  for (const b of newBadges) db.addUnlock({ studentId, kind: 'badge', key: b.key, meta: { evidence: b.evidence, name: b.name } });

  // Quests are evaluated after the attempt lands, so an award always reflects
  // work that is already recorded.
  const questResult = settleQuests({ studentId, attempts, deck, bosses, afterMoveStates, earned, attemptId: attempt.id });
  next.xp += questResult.xp;
  next.sparks += questResult.sparks;

  const saved = db.saveGameState(next);
  const rankBefore = game.rankFor(state.xp);
  const rankAfter = game.rankFor(saved.xp);

  return {
    lines: earned.lines,
    xp: earned.xp + questResult.xp,
    sparks: earned.sparks + questResult.sparks,
    total: { xp: saved.xp, sparks: saved.sparks },
    rank: rankAfter,
    rankUp: rankAfter.key !== rankBefore.key ? rankAfter : null,
    tempered: earned.tempered,
    badges: newBadges,
    quests: questResult.claimed,
    streak: { ...streak, message: game.streakMessage(streak) },
    isBoss: earned.isBoss,
  };
}

function questsFor(studentId, period, ctx, { regenerate = false } = {}) {
  const periodKey = period === 'day' ? game.dayKey() : game.weekKey();
  let stored = db.getQuests(studentId, period, periodKey);
  if (!stored.length || regenerate) {
    const rerolls = regenerate ? (stored[0]?.rerolls || 0) + 1 : 0;
    if (regenerate) db.clearQuests(studentId, period, periodKey);
    const generated = game.generateQuests({ studentId, period, ctx, rerolls });
    db.saveQuests(studentId, generated, rerolls);
    stored = db.getQuests(studentId, period, periodKey);
  }
  return stored.map((q) => ({ ...q, ...game.getQuest(q.key), goal: q.goal, xp: q.xp, period, periodKey }));
}

function settleQuests({ studentId, attempts, deck, bosses, afterMoveStates, earned, attemptId }) {
  const ctx = game.questContext({
    attempts, deck, bosses,
    duelsThisWeek: db.listDuels(studentId, WEEK_START()).length,
    newDomainEvents: earned.newDomains.map((m) => ({ attemptId, move: m })),
    temperEvents: earned.tempered.map((t) => ({ attemptId, move: t.move })),
  });
  const today = game.dayKey();
  const week = game.weekKey();
  const todayAttempts = attempts.filter((a) => a.createdAt.slice(0, 10) === today);
  const weekAttempts = attempts.filter((a) => a.createdAt.slice(0, 10) >= week);

  const claimed = [];
  let xp = 0;
  let sparks = 0;
  for (const period of ['day', 'week']) {
    for (const quest of questsFor(studentId, period, ctx)) {
      if (quest.claimed) continue;
      const progressed = game.progressFor(quest, period === 'day' ? todayAttempts : weekAttempts, ctx);
      if (!progressed.done) continue;
      const paid = db.claimQuest(studentId, period, quest.periodKey, quest.key);
      if (!paid) continue;
      const sparkAward = game.AWARDS.quest.sparks;
      xp += paid.xp;
      sparks += sparkAward;
      db.addReward({ studentId, attemptId, source: `quest:${quest.key}`, xp: paid.xp, sparks: sparkAward, lines: [{ key: 'quest', xp: paid.xp, sparks: sparkAward, label: game.AWARDS.quest.label, certifies: quest.blurb, detail: quest.label }] });
      claimed.push({ key: quest.key, label: quest.label, xp: paid.xp, sparks: sparkAward });
    }
  }
  return { claimed, xp, sparks };
}

/** Everything the game surfaces render from. */
export function gameFor(studentId) {
  const student = db.getStudent(studentId);
  if (!student) return null;
  const moveStates = db.getMoveStates(studentId);
  const attempts = db.listAttempts(studentId);
  const deck = game.deckFor(moveStates);
  const bosses = game.bossCommissions(moveStates);
  const ctx = game.questContext({ attempts, deck, bosses, duelsThisWeek: db.listDuels(studentId, WEEK_START()).length });
  const quests = [...questsFor(studentId, 'day', ctx), ...questsFor(studentId, 'week', ctx)];

  return {
    ...game.gameProfile({
      state: db.getGameState(studentId),
      moveStates, attempts,
      indices: indices(attempts, heldMoves(studentId)),
      quests,
      unlocks: db.listUnlocks(studentId),
      weekXp: db.xpSince(studentId, WEEK_START()),
      duelsThisWeek: ctx.duelsThisPeriod,
    }),
    classGoal: classGoal(),
    student: { id: student.id, displayName: student.displayName },
  };
}

export function rerollQuests(studentId, period = 'day') {
  const moveStates = db.getMoveStates(studentId);
  const attempts = db.listAttempts(studentId);
  const deck = game.deckFor(moveStates);
  const bosses = game.bossCommissions(moveStates);
  const ctx = game.questContext({ attempts, deck, bosses, duelsThisWeek: db.listDuels(studentId, WEEK_START()).length });
  questsFor(studentId, period, ctx, { regenerate: true });
  return gameFor(studentId);
}

/** Sparks buy autonomy and decoration. They cannot buy hints, scores or levels. */
export function spendSparks(studentId, item) {
  const state = db.getGameState(studentId);
  const mark = game.MARKS.find((m) => m.key === item);
  const spend = game.SPEND[item];
  const cost = spend ? spend.cost : mark ? mark.cost : null;
  if (cost === null) return { error: 'unknown_item' };
  if (state.sparks < cost) return { error: 'not_enough_sparks', need: cost, have: state.sparks };

  const next = { ...state, sparks: state.sparks - cost };
  if (item === 'freeze') {
    if (state.freezes >= game.DEFAULT_FREEZES + 3) return { error: 'freezes_full' };
    next.freezes = state.freezes + 1;
  }
  if (mark) {
    db.addUnlock({ studentId, kind: 'mark', key: mark.key, meta: { name: mark.name } });
    next.mark = mark.key;
  }
  db.saveGameState(next);
  return { ok: true, item, spent: cost, game: gameFor(studentId) };
}

export function setMark(studentId, key) {
  const state = db.getGameState(studentId);
  const owned = db.listUnlocks(studentId).some((u) => u.kind === 'mark' && u.key === key);
  if (key && !owned) return { error: 'not_owned' };
  db.saveGameState({ ...state, mark: key || null });
  return { ok: true, game: gameFor(studentId) };
}

export function setLeaderboardOptIn(studentId, optIn) {
  const state = db.getGameState(studentId);
  db.saveGameState({ ...state, leaderboardOptIn: !!optIn });
  return { ok: true, optIn: !!optIn };
}

/**
 * The class's shared weekly goal — the collaboration half of the
 * competition-plus-collaboration pairing the evidence favours.
 */
export function classGoal() {
  const students = db.listStudents();
  const target = Math.max(600, students.length * CLASS_GOAL_PER_STUDENT);
  const progress = db.classXpSince(WEEK_START());
  return {
    week: game.weekKey(),
    target,
    progress,
    share: Math.min(1, target ? progress / target : 0),
    reached: progress >= target,
    contributors: students.length,
  };
}

/** Opt-in, effort-ranked, and empty unless somebody chose to appear. */
export function leaderboard() {
  return {
    week: game.weekKey(),
    basis: 'XP earned this week — effort, not ability. Opt in from your Forge page.',
    rows: db.leaderboard(WEEK_START()),
  };
}

/* ----------------------------------------------------------------- Forge-off */

export function startDuel({ studentId, taskId }) {
  const task = getTask(taskId);
  if (!task) return { error: 'not_found' };
  const peer = db.findPeerAttempt(studentId, taskId);
  if (!peer) return { error: 'no_opponent', message: 'Nobody else has taken this commission yet. Try another one — or come back when they have.' };
  const critique = critiqueTask(task);
  return {
    taskId,
    peerAttemptId: peer.id,
    peerAnswer: anonymise(peer, task),
    task: publicTask(critique),
    original: { title: task.title, prompt: task.prompt, stimulus: task.stimulus },
  };
}

export async function submitDuel({ studentId, taskId, peerAttemptId, response = {} }) {
  const task = getTask(taskId);
  const peer = db.getAttempt(peerAttemptId);
  if (!task || !peer || peer.studentId === studentId) return { error: 'not_found' };

  const critique = critiqueTask(task);
  const ai = await aiStatus();
  const scored = await scoreResponse(critique, response, ai.available ? { aiRubric: makeAiRubric() } : {});
  if (!scored.valid) return { valid: false, reason: scored.reason, repair: scored.repair };

  const id = db.uid('d');
  db.insertDuel({ id, studentId, taskId, peerAttemptId, peerStudentId: peer.studentId, score: scored.score, response, criteria: scored.criteria });

  // Both sides earn: the critic for the thinking, the author for having their
  // work studied. Nobody loses anything, and no ranking is produced.
  const award = (target, key) => {
    const a = game.AWARDS[key];
    const st = db.getGameState(target);
    db.saveGameState({ ...st, xp: st.xp + a.xp, sparks: st.sparks + a.sparks });
    db.addReward({ studentId: target, attemptId: null, source: key, xp: a.xp, sparks: a.sparks, lines: [{ key, xp: a.xp, sparks: a.sparks, label: a.label, certifies: a.certifies }] });
  };
  award(studentId, 'duel');
  award(peer.studentId, 'reviewed');

  return {
    valid: true,
    score: scored.score,
    criteria: scored.criteria,
    feedback: offlineFeedback(critique, scored),
    earned: { xp: game.AWARDS.duel.xp, sparks: game.AWARDS.duel.sparks },
    game: gameFor(studentId),
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

/**
 * A human score replaces the machine's, and the ability estimate is rebuilt
 * rather than patched: the strand is replayed from the starting prior through
 * every attempt in order. Slower than reversing one update, but it is
 * auditable, and a class-sized history is tiny.
 */
export function recomputeStrand(studentId, strand) {
  const attempts = db.listAttempts(studentId).filter((a) => a.strand === strand);
  let theta = START_THETA;
  let n = 0;
  for (const a of attempts) {
    const u = eloUpdate({
      theta,
      difficulty: a.difficulty ?? 0,
      score: a.adjustedScore ?? a.score ?? 0,
      studentN: n,
      itemN: 9999,                       // item difficulty is not rewritten by a replay
      confidence: a.confidence ?? 1,
    });
    theta = u.theta;
    n += 1;
  }
  db.upsertStrandState(studentId, strand, theta, n);
  return { theta, n, level: levelForTheta(theta) };
}

export function applyOverride({ attemptId, guardianId, score, note }) {
  const before = db.getAttempt(attemptId);
  if (!before) return null;
  const attempt = db.overrideScore({ attemptId, guardianId, score, note });
  const ability = recomputeStrand(before.studentId, before.strand);
  return { attempt, ability, previousScore: before.score };
}

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
          .map((p) => ({ strand: p.strand, level: p.level, pointLevel: p.pointLevel, settled: p.settled, theta: p.theta, se: p.se, n: p.n })),
        lastActive: attempts.length ? attempts[attempts.length - 1].createdAt : null,
        flagged: attempts.filter((a) => a.flagged).length,
      };
    }),
    reviewQueue: db.listFlaggedAttempts(25).map((a) => ({
      ...a, taskTitle: getTask(a.taskId)?.title, taskPrompt: getTask(a.taskId)?.prompt,
    })),
    safety: db.listFlags({ resolved: 0 }).filter((f) => f.kind === 'safety'),
    missingElement: missingElementReadout(students),
    classGoal: classGoal(),
    xpComposition: xpComposition(students),
  };
}

/**
 * What the game is actually paying for, class-wide (docs/04 §6). If XP drifts
 * towards turning up rather than towards transfer and calibration, that is
 * visible here rather than hidden inside the mechanic.
 */
function xpComposition(students) {
  const totals = new Map();
  let all = 0;
  for (const s of students) {
    for (const r of db.listRewards(s.id)) {
      for (const line of r.lines || []) {
        totals.set(line.key, (totals.get(line.key) || 0) + (line.xp || 0));
        all += line.xp || 0;
      }
    }
  }
  return [...totals.entries()]
    .map(([key, xp]) => ({ key, label: game.AWARDS[key]?.label || key, xp, share: all ? xp / all : 0 }))
    .sort((a, b) => b.xp - a.xp);
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
