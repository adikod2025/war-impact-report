/**
 * L0 validity gate and L1 deterministic evidence (docs/03 §A.1).
 * Nothing in this file uses AI. Everything here bounds what AI is allowed to say.
 */
import { extractFeatures, wordCount, overlap, items } from './text.mjs';
import { runMachine, scoreProcess, ruleMatches } from './probe.mjs';

const OPEN_MODES = new Set(['open_short', 'open_list', 'structured', 'probe']);

/** Flatten any response into the text the student actually wrote. */
export function responseText(task, response = {}) {
  switch (task.mode) {
    case 'structured':
      return Object.values(response.fields || {}).join('\n');
    case 'open_short':
    case 'open_list':
      return response.text || '';
    case 'probe':
      return response.rule || '';
    default:
      return '';
  }
}

export function isOpenMode(mode) {
  return OPEN_MODES.has(mode);
}

/** L0 — reject responses that cannot carry evidence, with a repair prompt. */
export function validityGate(task, response = {}) {
  const text = responseText(task, response);
  const ok = (extra = {}) => ({ valid: true, ...extra });

  if (!isOpenMode(task.mode)) {
    const empty = (task.mode === 'select' && !response.choice)
      || (task.mode === 'multi_select' && !(response.choices || []).length)
      || (task.mode === 'order' && !(response.order || []).length)
      || (task.mode === 'match' && !Object.keys(response.pairs || {}).length);
    if (empty) return { valid: false, reason: 'empty', repair: 'Nothing was selected yet — have a go, even if you are not sure.' };
    return ok();
  }

  if (task.mode === 'probe' && !(response.tests || []).length) {
    return { valid: false, reason: 'no_tests', repair: 'Run at least a couple of tests on the box before you state the rule — otherwise there is nothing to reason from.' };
  }

  const minWords = task.checks?.minWords?.response ?? (task.mode === 'probe' ? 4 : 8);
  if (wordCount(text) < minWords) {
    return { valid: false, reason: 'too_short', repair: `That is a start, but it is too short to show your thinking. Aim for at least ${minWords} words.` };
  }

  const vocab = task.payload?.conceptVocabulary || [];
  const f = extractFeatures(text, { stimulus: task.stimulus, conceptVocabulary: vocab });
  if (f.degenerate) {
    return { valid: false, reason: 'degenerate', repair: 'That does not look like an answer yet. Try writing one real sentence about the problem.' };
  }
  if (f.stimulusVerbatim >= 0.5 && task.mode !== 'probe') {
    return { valid: false, reason: 'copied', repair: 'Most of that is copied from the question. Say it in your own words — that is where the thinking shows.' };
  }
  if (vocab.length && f.conceptVocabHits === 0 && f.words < 40) {
    return { valid: false, reason: 'off_task', repair: 'This does not seem to be about the problem in front of you. Read the prompt again and answer that.' };
  }
  return ok();
}

function kendallDistance(order, answer) {
  const pos = new Map(answer.map((id, i) => [id, i]));
  let discordant = 0;
  let pairs = 0;
  for (let i = 0; i < order.length; i += 1) {
    for (let j = i + 1; j < order.length; j += 1) {
      const a = pos.get(order[i]);
      const b = pos.get(order[j]);
      if (a === undefined || b === undefined) continue;
      pairs += 1;
      if (a > b) discordant += 1;
    }
  }
  return pairs ? discordant / pairs : 1;
}

/**
 * L1 — the objective, machine-checkable part of the score, plus the feature
 * vector that both the AI scorer and the offline estimator consume.
 */
export function objectiveScore(task, response = {}) {
  const p = task.payload || {};
  const detail = {};
  let score = null;

  switch (task.mode) {
    case 'select': {
      const opt = (p.options || []).find((o) => o.id === response.choice);
      score = opt?.correct ? 1 : 0;
      detail.chosen = response.choice;
      detail.why = opt?.why || null;
      detail.correctId = (p.options || []).find((o) => o.correct)?.id;
      break;
    }
    case 'multi_select': {
      const chosen = new Set(response.choices || []);
      const targets = (p.options || []).filter((o) => o.correct).map((o) => o.id);
      const hits = targets.filter((id) => chosen.has(id)).length;
      const falsePositives = [...chosen].filter((id) => !targets.includes(id)).length;
      score = Math.max(0, (hits - falsePositives) / Math.max(1, targets.length));
      detail.hits = hits;
      detail.falsePositives = falsePositives;
      detail.missed = targets.filter((id) => !chosen.has(id));
      detail.perOption = (p.options || []).map((o) => ({ id: o.id, chosen: chosen.has(o.id), correct: !!o.correct, why: o.why }));
      break;
    }
    case 'order': {
      const d = kendallDistance(response.order || [], p.answer || []);
      score = Math.max(0, 1 - d);
      detail.exact = JSON.stringify(response.order) === JSON.stringify(p.answer);
      detail.tauDistance = Math.round(d * 100) / 100;
      break;
    }
    case 'match': {
      const answer = p.answer || {};
      const pairs = response.pairs || {};
      const total = Object.keys(answer).length;
      const correct = Object.entries(answer).filter(([l, r]) => pairs[l] === r).length;
      score = total ? correct / total : 0;
      detail.correct = correct;
      detail.total = total;
      detail.wrong = Object.keys(answer).filter((l) => pairs[l] && pairs[l] !== answer[l]);
      break;
    }
    case 'structured': {
      const required = task.checks?.requiredFields || (p.fields || []).filter((f) => f.required).map((f) => f.id);
      const fields = response.fields || {};
      const filled = required.filter((id) => {
        const min = (p.fields || []).find((f) => f.id === id)?.minWords ?? 3;
        return wordCount(fields[id]) >= min;
      });
      score = required.length ? filled.length / required.length : 1;
      detail.filled = filled;
      detail.missing = required.filter((id) => !filled.includes(id));
      break;
    }
    case 'probe': {
      const machine = p.machine || {};
      const tests = (response.tests || []).map((t) => ({ inputs: t.inputs, on: runMachine(machine, t.inputs).on }));
      const process = scoreProcess(tests, machine);
      const raw = ruleMatches(response.rule, machine);
      // The offline match is rough by nature (docs/03 §A.2 prefers an AI
      // equivalence check); stretch it so a paraphrase is not punished as a miss.
      const ruleFit = Math.max(0, Math.min(1, (raw - 0.25) / 0.5));
      score = 0.5 * process.process + 0.5 * ruleFit;
      detail.ruleFitRaw = raw;
      detail.process = process;
      detail.ruleFit = ruleFit;
      break;
    }
    case 'open_short':
    case 'open_list': {
      score = null; // no objective component; caps only
      break;
    }
    default:
      throw new Error(`Unknown mode: ${task.mode}`);
  }

  const text = responseText(task, response);
  const features = extractFeatures(text, {
    stimulus: task.stimulus,
    commonIdeas: p.commonIdeas || [],
    conceptVocabulary: p.conceptVocabulary || [],
  });
  if (task.mode === 'open_list') {
    features.listItems = items(text).length;
    features.minIdeas = p.minIdeas || 3;
  }
  if (task.mode === 'structured') {
    features.perField = Object.fromEntries(
      Object.entries(response.fields || {}).map(([k, v]) => [k, { words: wordCount(v), copied: overlap(v, task.stimulus) }]),
    );
  }
  return { score, detail, features };
}

/**
 * Deterministic ceiling. A response missing a required structural element
 * cannot score above the cap however well it is written — this is the main
 * guard against an AI scorer rewarding fluent-but-empty writing.
 */
export function scoreCap(task, response = {}) {
  const caps = task.checks?.capIfMissing || {};
  const fields = response.fields || {};
  const minWords = task.checks?.minWords || {};
  let cap = 1;
  const applied = [];
  for (const [field, value] of Object.entries(caps)) {
    const required = minWords[field] ?? (task.payload?.fields || []).find((f) => f.id === field)?.minWords ?? 3;
    const present = task.mode === 'probe'
      ? wordCount(response.rule) >= required
      : wordCount(fields[field]) >= required;
    if (!present) {
      cap = Math.min(cap, value);
      applied.push({ field, cap: value });
    }
  }
  return { cap, applied };
}

/** Blend weight β between rubric judgement and the objective component. */
export function blendWeight(mode) {
  switch (mode) {
    case 'open_short':
    case 'open_list': return 1;
    case 'structured': return 0.6;
    case 'probe': return 0.5;
    default: return 0;
  }
}
