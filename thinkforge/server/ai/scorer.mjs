/**
 * AI rubric marking (L2, docs/03 §A.1). Returns criteria in exactly the shape
 * the offline estimator returns, so L3 reconciliation never needs to know
 * which path produced them.
 */
import { call, recordFailure } from './client.mjs';
import { redactPII, anyCorrupted, repairDeep } from './safety.mjs';
import { scorerSystem, scorerUser, SCORER_SCHEMA, EQUIVALENCE_SCHEMA } from './prompts.mjs';

/**
 * @param {object} [deps] injectable caller, so the marking contract can be
 *   tested without a network round trip (tests/ai.test.mjs).
 */
export function makeAiRubric({ caller = call } = {}) {
  return async function aiRubric(task, response, features) {
    const rawText = task.mode === 'structured'
      ? Object.entries(response.fields || {}).map(([k, v]) => `[${k}] ${v}`).join('\n')
      : (response.text || response.rule || '');
    const { text } = redactPII(rawText);

    let result;
    try {
      result = await caller({
        system: scorerSystem(),
        messages: [{ role: 'user', content: scorerUser({ task, response, features, text }) }],
        schema: SCORER_SCHEMA,
        effort: 'medium',
        maxTokens: 2000,
      });
    } catch (err) {
      recordFailure('rubric marking', err);
      throw err;
    }
    if (!result.ok || !result.json) {
      recordFailure('rubric marking', new Error(`marker returned ${result.reason || 'no parseable JSON'}`));
      return null;
    }

    const byId = new Map((task.rubric?.criteria || []).map((c) => [c.id, c]));
    const criteria = (result.json.criteria || [])
      .filter((c) => byId.has(c.id))
      .map((c) => {
        const def = byId.get(c.id);
        // Evidence is mandatory above zero: a score the model cannot quote is
        // a score it invented.
        const score = c.evidence && String(c.evidence).trim() ? Math.max(0, Math.min(3, c.score)) : 0;
        return {
          id: c.id,
          name: def.name,
          weight: def.weight,
          score,
          anchor: def.anchors[String(score)],
          anchors: def.anchors,
          rationale: repairDeep(c.rationale),
          evidence: c.evidence ? repairDeep(c.evidence) : null,
        };
      });

    // Any criterion the model failed to return counts as unevidenced, not absent.
    for (const [id, def] of byId) {
      if (!criteria.find((c) => c.id === id)) {
        criteria.push({ id, name: def.name, weight: def.weight, score: 0, anchor: def.anchors['0'], rationale: 'Not marked by the assessor.', evidence: null });
      }
    }

    const rubricScore = criteria.reduce((sum, c) => sum + c.weight * (c.score / 3), 0);
    // Scores survive a corrupted feedback string; the prose does not ship.
    const repairedFeedback = repairDeep(result.json.feedback);
    const feedback = anyCorrupted(repairedFeedback) ? null : repairedFeedback;
    if (!feedback && result.json.feedback) recordFailure('rubric feedback', new Error('generated feedback looked corrupted; used the deterministic text instead'));
    return {
      criteria,
      rubricScore: Math.max(0, Math.min(1, rubricScore)),
      soloLevel: result.json.soloLevel,
      offTask: !!result.json.offTask,
      feedback,
      model: result.model,
      promptHash: result.promptHash,
    };
  };
}

/** Cheap, reliable AI job: is this stated rule the same rule as the machine's? */
export async function checkRuleEquivalence(stated, machine) {
  let result;
  try {
    result = await call({
      system: 'You compare two descriptions of a rule and decide whether they describe exactly the same behaviour. You are strict about missing conditions and lenient about wording.',
      messages: [{
        role: 'user',
        content: `THE MACHINE'S ACTUAL RULE (canonical forms):\n${(machine.canonicalForms || []).map((f) => `- ${f}`).join('\n')}\n\nTHE STUDENT'S STATED RULE:\n"""${stated}"""\n\nAre they the same rule?`,
      }],
      schema: EQUIVALENCE_SCHEMA,
      effort: 'low',
      maxTokens: 500,
    });
  } catch (err) {
    recordFailure('rule equivalence', err);
    return null;
  }
  if (!result.ok || !result.json) return null;
  return result.json;
}

