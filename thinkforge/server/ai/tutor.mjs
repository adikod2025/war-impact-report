/**
 * The Socratic tutor (docs/03 Part B).
 *
 * Three guards sit around the model: safety screening on the way in, the
 * rung-limited prompt, and an answer-leakage filter on the way out. With no
 * API key it serves the task's authored hint ladder instead, and the transcript
 * is marked `scripted` so nobody mistakes it for a dialogue.
 */
import { call } from './client.mjs';
import { tutorSystem, tutorUser, TUTOR_SCHEMA } from './prompts.mjs';
import { screenStudentText, isAnswerExtraction, leaksAnswer, AI_DISCLOSURE } from './safety.mjs';

export const MAX_TURNS = 6;

/** Which rung of the scaffold ladder this student has earned. */
export function chooseRung({ independence = 0.5, attempts = 1, turnsUsed = 0, lastScore = null }) {
  let rung = 0;
  if (turnsUsed >= 1) rung += 1;
  if (attempts >= 2 || (lastScore !== null && lastScore < 0.4)) rung += 1;
  if (independence < 0.35) rung += 1;
  if (turnsUsed >= 4) rung += 1;
  return Math.max(0, Math.min(3, rung));
}

/** Deterministic tutor: the authored hint ladder plus misconception matching. */
export function scriptedTurn({ task, rung, studentMessage, text }) {
  if (isAnswerExtraction(studentMessage)) {
    return {
      reply: `${AI_DISCLOSURE} I am not going to give you the answer — that is the part that does you good. Here is the next nudge instead:\n\n${task.hints[Math.min(rung, task.hints.length - 1)]}`,
      element: 'interpretation', rung, mode: 'scripted',
    };
  }
  const hit = (task.misconceptions || []).find((m) => {
    const signalWords = m.signal.toLowerCase().split(/\s+/).filter((w) => w.length > 4);
    return signalWords.length && signalWords.every((w) => (text || '').toLowerCase().includes(w));
  });
  const hint = task.hints[Math.min(rung, task.hints.length - 1)];
  return {
    reply: hit ? `${hit.tutorMove}\n\n${hint}` : hint,
    element: 'assumptions', rung, mode: 'scripted',
  };
}

/**
 * @returns {{reply:string, element:string, rung:number, mode:'ai'|'scripted'|'safety', escalate?:object}}
 */
export async function tutorTurn({ task, text, scoreSummary, history = [], studentMessage = '', age = 12, independence = 0.5, attempts = 1, hintsSeen = 0, caller = call }) {
  const turnsUsed = history.filter((h) => h.role === 'tutor').length;
  if (turnsUsed >= MAX_TURNS) {
    return {
      reply: 'We have talked this one through enough for now — have a go at your revision, and we will pick the next one up fresh.',
      element: 'purpose', rung: 3, mode: 'closed',
    };
  }

  const screen = screenStudentText(studentMessage);
  if (screen.action === 'escalate') {
    return { reply: screen.reply, element: 'purpose', rung: 0, mode: 'safety', escalate: { level: screen.level, matched: screen.matched } };
  }
  if (screen.action === 'redirect') {
    return { reply: screen.reply, element: 'purpose', rung: 0, mode: 'safety' };
  }

  const rung = chooseRung({ independence, attempts, turnsUsed, lastScore: scoreSummary?.score ?? null });
  const safeMessage = screen.text;

  const fallback = () => scriptedTurn({ task, rung, studentMessage: safeMessage, text });

  let result;
  try {
    result = await caller({
      system: tutorSystem({ age, rung }),
      messages: [{
        role: 'user',
        content: tutorUser({
          task, text, history, hintsSeen, studentMessage: safeMessage,
          scoreSummary: scoreSummary ? JSON.stringify(scoreSummary) : null,
        }),
      }],
      schema: TUTOR_SCHEMA,
      effort: 'low',
      maxTokens: 800,
    });
  } catch {
    return fallback();
  }
  if (!result.ok || !result.json?.reply) return fallback();

  const answerKey = task.payload?.answerKey || task.rubric?.solo?.[3] || '';
  if (leaksAnswer(result.json.reply, answerKey)) {
    // Do not ship a turn that gives the game away; drop back to the authored
    // ladder, which is known safe.
    return { ...fallback(), leakageBlocked: true };
  }

  return {
    reply: result.json.reply,
    element: result.json.element,
    rung: result.json.rung ?? rung,
    mode: 'ai',
    model: result.model,
    promptHash: result.promptHash,
  };
}
