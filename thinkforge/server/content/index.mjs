import analysis from './tasks/analysis.mjs';
import synthesis from './tasks/synthesis.mjs';
import lateral from './tasks/lateral.mjs';
import logic from './tasks/logic.mjs';
import argument from './tasks/argument.mjs';
import reverse from './tasks/reverse.mjs';
import systems from './tasks/systems.mjs';
import metacog from './tasks/metacog.mjs';

export const TASKS = [...analysis, ...synthesis, ...lateral, ...logic, ...argument, ...reverse, ...systems, ...metacog];

const BY_ID = new Map(TASKS.map((t) => [t.id, t]));

export function getTask(id) {
  return BY_ID.get(id) || null;
}

/** The version of a task that is safe to send to a browser (no answers). */
export function publicTask(task) {
  if (!task) return null;
  const { payload = {}, rubric, checks, misconceptions, hints, ...rest } = task;
  const safePayload = { ...payload };
  delete safePayload.answer;
  delete safePayload.answerKey;
  delete safePayload.distractor;
  if (safePayload.machine) {
    const { rule, canonicalForms, ...machine } = safePayload.machine;
    safePayload.machine = machine;
  }
  if (Array.isArray(safePayload.options)) {
    safePayload.options = safePayload.options.map(({ correct, why, ...o }) => o);
  }
  return {
    ...rest,
    payload: safePayload,
    hintCount: (hints || []).length,
    criteria: (rubric?.criteria || []).map((c) => ({ id: c.id, name: c.name, weight: c.weight })),
  };
}

export function tasksForStrand(strand) {
  return TASKS.filter((t) => t.strand === strand);
}
