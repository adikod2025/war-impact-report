/**
 * The AI contract, exercised without a network call: what we send, and how much
 * of what comes back we are willing to believe.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRequest, usesRefusalFallback, MODEL } from '../server/ai/client.mjs';
import { TUTOR_SCHEMA, NARRATIVE_SCHEMA, EQUIVALENCE_SCHEMA, tutorSystem, narrativeSystem } from '../server/ai/prompts.mjs';
import { looksCorrupted, anyCorrupted, repairProse, repairDeep } from '../server/ai/safety.mjs';
import { growthStory } from '../server/ai/narrative.mjs';
import { makeAiRubric } from '../server/ai/scorer.mjs';
import { tutorTurn } from '../server/ai/tutor.mjs';
import { scoreResponse } from '../server/engine/scoring.mjs';
import { SCORER_SCHEMA } from '../server/ai/prompts.mjs';
import { getTask } from '../server/content/index.mjs';

const task = getTask('arg-t1-toulmin-lite');
const goodResponse = {
  fields: {
    claim: 'The school should install a bike rack by the science block',
    evidence: 'Seven bicycles are propped against the railings every morning',
    warrant: 'Whenever people repeatedly leave something in the same spot, that spot is where somewhere to put it is needed',
  },
};

test('the request carries no sampling parameters and constrains the output schema', () => {
  const body = buildRequest({ system: 's', messages: [{ role: 'user', content: 'u' }], schema: SCORER_SCHEMA, effort: 'medium' });
  assert.equal(body.model, MODEL);
  assert.equal(body.temperature, undefined, 'the Opus/Sonnet 5 family rejects temperature');
  assert.equal(body.top_p, undefined);
  assert.deepEqual(body.thinking, { type: 'adaptive' });
  assert.equal(body.output_config.effort, 'medium');
  assert.equal(body.output_config.format.type, 'json_schema');
  assert.equal(body.output_config.format.schema, SCORER_SCHEMA);
  assert.ok(body.max_tokens >= 500);
});

test('no output schema uses a keyword the API rejects', () => {
  // Learned the hard way against the live API: `minimum`/`maximum` on an
  // integer is a 400, and the failure was invisible because every AI path
  // falls back to a deterministic one. Bounded integers use `enum` instead.
  const banned = ['minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum', 'multipleOf', 'pattern', 'format'];
  const walk = (node, path) => {
    if (!node || typeof node !== 'object') return;
    for (const key of Object.keys(node)) {
      assert.ok(!banned.includes(key), `${path}.${key} is not supported in a structured-output schema`);
      walk(node[key], `${path}.${key}`);
    }
  };
  for (const [name, schema] of Object.entries({ SCORER_SCHEMA, TUTOR_SCHEMA, NARRATIVE_SCHEMA, EQUIVALENCE_SCHEMA })) walk(schema, name);
});

test('bounded integers are expressed as enums the API accepts', () => {
  assert.deepEqual(SCORER_SCHEMA.properties.criteria.items.properties.score.enum, [0, 1, 2, 3]);
  assert.deepEqual(TUTOR_SCHEMA.properties.rung.enum, [0, 1, 2, 3]);
});

test('refusal fallbacks are opted into on the models that need them', () => {
  assert.equal(usesRefusalFallback('claude-opus-5'), true);
  assert.equal(usesRefusalFallback('claude-fable-5'), true);
  assert.equal(usesRefusalFallback('claude-haiku-4-5'), false);
});

test('a criterion the marker cannot quote is forced to zero', async () => {
  const rubric = makeAiRubric({
    caller: async () => ({
      ok: true, model: 'test', promptHash: 'abc',
      json: {
        soloLevel: 4,
        criteria: [
          { id: 'warrant', score: 3, evidence: null, rationale: 'It felt strong.' },
          { id: 'evidence_fit', score: 3, evidence: 'Seven bicycles are propped against the railings', rationale: 'Countable and relevant.' },
          { id: 'completeness', score: 2, evidence: 'The school should install a bike rack', rationale: 'All three slots used.' },
        ],
        feedback: { task: 't', process: 'p', selfRegulation: 's' },
      },
    }),
  });
  const out = await rubric(task, goodResponse, {});
  const warrant = out.criteria.find((c) => c.id === 'warrant');
  assert.equal(warrant.score, 0, 'an unquoted score is an invented score');
  assert.equal(out.criteria.find((c) => c.id === 'evidence_fit').score, 3);
});

test('criteria the marker skipped or invented are handled, not trusted', async () => {
  const rubric = makeAiRubric({
    caller: async () => ({
      ok: true, model: 'test',
      json: {
        soloLevel: 3,
        criteria: [
          { id: 'warrant', score: 2, evidence: 'Whenever people repeatedly leave something', rationale: 'General rule stated.' },
          { id: 'made_up_criterion', score: 3, evidence: 'x', rationale: 'not in the rubric' },
        ],
        feedback: { task: 't', process: 'p', selfRegulation: 's' },
      },
    }),
  });
  const out = await rubric(task, goodResponse, {});
  assert.equal(out.criteria.length, task.rubric.criteria.length);
  assert.ok(!out.criteria.some((c) => c.id === 'made_up_criterion'), 'a criterion outside the rubric must be dropped');
  assert.equal(out.criteria.find((c) => c.id === 'completeness').score, 0, 'an unmarked criterion is unevidenced, not absent');
});

test('the structural cap still bounds an enthusiastic AI marker', async () => {
  const rubric = makeAiRubric({
    caller: async () => ({
      ok: true, model: 'test',
      json: {
        soloLevel: 5,
        criteria: task.rubric.criteria.map((c) => ({ id: c.id, score: 3, evidence: 'The school should install a bike rack', rationale: 'Excellent.' })),
        feedback: { task: 't', process: 'p', selfRegulation: 's' },
      },
    }),
  });
  const noWarrant = {
    fields: {
      claim: 'The school should install a covered bicycle rack outside the science block',
      evidence: 'Seven bicycles are propped against the railings there every single morning',
      warrant: '',
    },
  };
  const scored = await scoreResponse(task, noWarrant, { aiRubric: rubric });
  assert.equal(scored.scorer, 'ai');
  assert.ok(scored.score <= 0.5, `a full-marks judgement must still be capped, got ${scored.score}`);
});

test('a failing marker falls back to the offline estimator rather than losing the work', async () => {
  const rubric = makeAiRubric({ caller: async () => { throw new Error('upstream down'); } });
  const scored = await scoreResponse(task, goodResponse, { aiRubric: rubric });
  assert.equal(scored.valid, true);
  assert.equal(scored.scorer, 'offline');
  assert.ok(scored.score > 0);
});

test('corrupted generations are caught before a child sees them', () => {
  // Both of these came back from the live API during validation.
  assert.equal(looksCorrupted('a warrant \ning the evidence to the claim'), true);
  assert.equal(looksCorrupted('Calibration sits at 81 \\are are how you actually are'), true);
  assert.equal(looksCorrupted('You gave a real rule, not a restatement — that is the hard part done.'), false);
  assert.equal(looksCorrupted(''), true);
  assert.equal(anyCorrupted({ a: 'fine', b: { c: 'also \uFFFD fine' } }), true);
  assert.equal(anyCorrupted({ a: 'fine', b: ['still fine'] }), false);
});

test('recoverable generation artefacts are repaired rather than thrown away', () => {
  // Both forms came back from the live API in roughly half of tutor turns.
  assert.equal(repairProse('affected by this \\u2014 and what would they say?'), 'affected by this — and what would they say?');
  assert.equal(repairProse('the right kind of work \\good/bad here'), 'the right kind of work good/bad here');
  assert.equal(looksCorrupted(repairProse('a \\u2014 b')), false);
  // Lost text is not recoverable and must still be blocked.
  assert.equal(looksCorrupted(repairProse('a warrant \ning the evidence')), true);
  assert.deepEqual(repairDeep({ a: 'x \\u2014 y', b: ['z \\u2014'] }), { a: 'x — y', b: ['z —'] });
});

test('a corrupted growth story falls back to the deterministic template', async () => {
  const current = { strands: [{ strand: 'argument', theta: 0.2, level: 2 }], indices: {} };
  const previous = { strands: [{ strand: 'argument', theta: -0.3, level: 1 }] };
  const story = await growthStory({
    current, previous, age: 12,
    caller: async () => ({ ok: true, model: 'test', json: { headline: 'ok', body: 'a warrant \ning the evidence', next: 'go' } }),
  });
  assert.equal(story.source, 'template', 'mangled prose must never reach the student');
});

test('a corrupted tutor reply falls back to the authored ladder', async () => {
  const turn = await tutorTurn({
    task, text: 'something', studentMessage: 'help',
    caller: async () => ({ ok: true, model: 'test', json: { reply: 'try \\the the the the thing', element: 'assumptions', rung: 0 } }),
  });
  assert.equal(turn.corruptionBlocked, true);
  assert.equal(turn.mode, 'scripted');
});

test('a corrupted feedback string is dropped without losing the scores', async () => {
  const rubric = makeAiRubric({
    caller: async () => ({
      ok: true, model: 'test',
      json: {
        soloLevel: 3,
        criteria: task.rubric.criteria.map((c) => ({ id: c.id, score: 2, evidence: 'Seven bicycles are propped against the railings', rationale: 'fine' })),
        feedback: { task: 'a warrant \ning the evidence', process: 'fine', selfRegulation: 'fine' },
      },
    }),
  });
  const out = await rubric(task, goodResponse, {});
  assert.equal(out.feedback, null, 'the prose is dropped');
  assert.ok(out.rubricScore > 0, 'the marking survives');
});

test('a tutor turn that leaks the answer is replaced by the authored ladder', async () => {
  const leaky = getTask('arg-t2-warrant-audit');
  const turn = await tutorTurn({
    task: leaky, text: 'chess wins so it deserves the room', studentMessage: 'am I close?',
    caller: async () => ({ ok: true, model: 'test', json: { reply: leaky.payload.answerKey, element: 'assumptions', rung: 0 } }),
  });
  assert.equal(turn.leakageBlocked, true);
  assert.equal(turn.mode, 'scripted');
  assert.ok(turn.reply.includes(leaky.hints[0]));
});

test('a well-behaved tutor turn is passed through with its diagnosis', async () => {
  const turn = await tutorTurn({
    task, text: 'because bikes lean there', studentMessage: 'is my warrant ok?',
    caller: async () => ({ ok: true, model: 'test', promptHash: 'h', json: { reply: 'What general rule would make that evidence matter to anyone, anywhere?', element: 'assumptions', rung: 0 } }),
  });
  assert.equal(turn.mode, 'ai');
  assert.equal(turn.element, 'assumptions');
  assert.match(turn.reply, /general rule/);
});

test('an unreachable model never blocks the coach', async () => {
  const turn = await tutorTurn({
    task, text: 'x', studentMessage: 'help',
    caller: async () => { throw new Error('network'); },
  });
  assert.equal(turn.mode, 'scripted');
  assert.ok(turn.reply.length > 20);
});
