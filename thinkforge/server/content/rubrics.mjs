/**
 * Reusable evidence models.
 *
 * In Evidence-Centered Design the evidence model is what turns an observation
 * into a claim, and it is reusable across tasks that elicit the same thing.
 * Each criterion carries:
 *   - anchors 0-3, written so a human marker and an AI marker agree
 *   - `heuristic`, the deterministic estimator used when no AI key is present
 *     (documented in docs/03 §A.1, "offline path")
 *
 * Heuristic types (implemented in server/engine/offline-scorer.mjs):
 *   slots       required fields filled with enough substance
 *   count       number of distinct items, against a target
 *   distinct    items differ from each other (token-overlap clustering)
 *   depth       each line adds new content over the previous one
 *   connective  causal / conditional linking language ("because", "whenever", "so that")
 *   hedge       calibrated language ("usually", "in most cases", "unless")
 *   contrast    counter-case language ("unless", "except", "however", "but if")
 *   novelty     distance from the task's authored commonIdeas
 *   specific    concrete nouns/numbers rather than vague filler
 *   generality  general-rule phrasing rather than restating the instance
 */

const LIB = {
  completeness: {
    name: 'All parts present',
    anchors: {
      0: 'Most required parts are missing or empty.',
      1: 'Some parts present, others empty or filled with filler.',
      2: 'All parts present, but at least one is thin or repeats another.',
      3: 'Every part present and carrying real content of its own.',
    },
    heuristic: { type: 'slots' },
  },
  distinctness: {
    name: 'Genuinely different items',
    anchors: {
      0: 'One idea, or the same idea reworded.',
      1: 'Two ideas that are close variants of each other.',
      2: 'Several ideas, with one or two overlapping.',
      3: 'Each item is a different kind of thing, not a restyled twin.',
    },
    heuristic: { type: 'distinct', target: 4 },
  },
  fluency: {
    name: 'Enough ideas produced',
    anchors: {
      0: 'Fewer ideas than asked for.',
      1: 'Just reaches the minimum.',
      2: 'Comfortably past the minimum.',
      3: 'Well past the minimum with the quality holding up.',
    },
    heuristic: { type: 'count', target: 6 },
  },
  specificity: {
    name: 'Concrete, not vague',
    anchors: {
      0: 'Only general words: "stuff", "things", "better".',
      1: 'Mostly vague, one concrete detail.',
      2: 'Concrete, but the detail could apply to almost any case.',
      3: 'Specific to this case: names the actual thing, amount, person or moment.',
    },
    heuristic: { type: 'specific' },
  },
  depth_chain: {
    name: 'Each step goes deeper',
    anchors: {
      0: 'No chain — one statement, or steps unrelated to each other.',
      1: 'A second step, but it restates the first in other words.',
      2: 'The chain moves, then stalls or jumps without a link.',
      3: 'Every step explains the step above it, and the chain reaches something you could act on.',
    },
    heuristic: { type: 'depth' },
  },
  root_vs_symptom: {
    name: 'Root cause vs symptom',
    anchors: {
      0: 'Treats the first visible problem as the cause.',
      1: 'Goes one layer down but stops at another symptom.',
      2: 'Reaches a plausible underlying cause but does not say why it is the root.',
      3: 'Names the root cause and says how it differs from the symptoms above it.',
    },
    heuristic: { type: 'depth', min: 3 },
  },
  rival_explanations: {
    name: 'Rival explanations considered',
    anchors: {
      0: 'One explanation, treated as the only one.',
      1: 'Mentions that other explanations exist without naming one.',
      2: 'Names a rival explanation (reverse direction, third factor, or chance).',
      3: 'Names rivals and says what evidence would tell them apart.',
    },
    heuristic: { type: 'contrast' },
  },
  criteria_named: {
    name: 'Says what "good" means first',
    anchors: {
      0: 'Judges without saying what is being judged against.',
      1: 'One criterion, unexplained.',
      2: 'Several criteria, but unweighted or overlapping.',
      3: 'Clear criteria, weighted or ranked, decided before the options were compared.',
    },
    heuristic: { type: 'slots' },
  },
  structure_mapping: {
    name: 'Maps relationships, not looks',
    anchors: {
      0: 'Matches things because they look or sound alike.',
      1: 'One relationship carried across, the rest surface.',
      2: 'Several relationships mapped, with a mismatch left unnoticed.',
      3: 'Maps the relationships and says where the analogy stops working.',
    },
    heuristic: { type: 'connective' },
  },
  warrant: {
    name: 'States the warrant',
    anchors: {
      0: 'No principle linking evidence to claim.',
      1: 'Restates the evidence or the claim instead of linking them.',
      2: 'States a linking principle, but vaguely or covering only part of the jump.',
      3: 'States a general rule that actually licenses the step from this evidence to this claim.',
    },
    heuristic: { type: 'generality' },
  },
  evidence_fit: {
    name: 'Evidence actually supports the claim',
    anchors: {
      0: 'Evidence is missing, or is really just the claim again.',
      1: 'Evidence is real but points somewhere else.',
      2: 'Evidence supports part of the claim.',
      3: 'Evidence is relevant, checkable, and supports the size of claim being made.',
    },
    heuristic: { type: 'specific' },
  },
  qualifier_fit: {
    name: 'Strength matches the support',
    anchors: {
      0: 'Absolute language on thin evidence ("always", "everyone knows").',
      1: 'Unqualified claim where a hedge was needed.',
      2: 'Hedged, but the hedge is vague ("kind of", "maybe").',
      3: 'Strength of wording fits the strength of the evidence, and says so.',
    },
    heuristic: { type: 'hedge' },
  },
  rebuttal_real: {
    name: 'Real exception, not a token one',
    anchors: {
      0: 'No exception given.',
      1: 'A token exception that could not actually happen.',
      2: 'A real exception, but it barely dents the claim.',
      3: 'A case that would genuinely defeat the claim, stated plainly.',
    },
    heuristic: { type: 'contrast' },
  },
  steelman_fair: {
    name: 'Opposing view stated fairly',
    anchors: {
      0: 'Caricature: the other side is made to look stupid.',
      1: 'The weakest version of the other side.',
      2: 'A fair version, but missing its best reason.',
      3: 'The strongest version — its holder would sign it.',
    },
    heuristic: { type: 'connective' },
  },
  stakeholder_fairness: {
    name: 'Views stated in their own terms',
    anchors: {
      0: 'Only one point of view appears.',
      1: 'Others are listed but given the writer\'s own opinion.',
      2: 'Several views, one of them flattened or dismissed.',
      3: 'Each stakeholder\'s actual interest is stated as they would state it.',
    },
    heuristic: { type: 'distinct', target: 3 },
  },
  movement: {
    name: 'Got a usable idea out of the provocation',
    anchors: {
      0: 'No provocation, or the provocation is just a sensible idea.',
      1: 'A real provocation, then it is simply dismissed.',
      2: 'A movement is attempted but lands back on the obvious answer.',
      3: 'The impossible idea is used as a stepping stone to a workable one, and the step is visible.',
    },
    heuristic: { type: 'connective' },
  },
  originality: {
    name: 'Non-obvious but still relevant',
    anchors: {
      0: 'Only the ideas everybody gives.',
      1: 'Common ideas plus one small twist.',
      2: 'At least one idea outside the obvious set, and it fits the problem.',
      3: 'Several ideas outside the obvious set, all of them still answering the actual question.',
    },
    heuristic: { type: 'novelty' },
  },
  flexibility_categories: {
    name: 'Ideas from different directions',
    anchors: {
      0: 'All ideas are the same kind of solution.',
      1: 'Two kinds, heavily weighted to one.',
      2: 'Three kinds of solution.',
      3: 'Four or more genuinely different kinds — the search moved, not just the wording.',
    },
    heuristic: { type: 'distinct', target: 4 },
  },
  contradiction_stated: {
    name: 'Contradiction named, not compromised',
    anchors: {
      0: 'States a problem, not a contradiction.',
      1: 'Names two wants but not their conflict.',
      2: 'States the contradiction, then splits the difference.',
      3: 'States "we want X and also not-X" and finds a way to keep both.',
    },
    heuristic: { type: 'contrast' },
  },
  ifr_stated: {
    name: 'Ideal final result',
    anchors: {
      0: 'Describes an ordinary improvement.',
      1: 'Ambitious but still a machine doing the job.',
      2: 'States an ideal where cost or harm nearly vanishes.',
      3: 'States the ideal where the job happens by itself, then names the nearest reachable version.',
    },
    heuristic: { type: 'generality' },
  },
  loop_signs: {
    name: 'Links and signs',
    anchors: {
      0: 'A list of things with no arrows between them.',
      1: 'Arrows drawn but unsigned or wrongly signed.',
      2: 'Most links correctly signed, the loop does not quite close.',
      3: 'A closed loop with every link correctly signed.',
    },
    heuristic: { type: 'slots' },
  },
  loop_type: {
    name: 'Reinforcing or balancing',
    anchors: {
      0: 'Loop type not identified.',
      1: 'Type guessed without reasoning.',
      2: 'Correct type, reasoning partly right.',
      3: 'Correct type, justified by the signs, plus what it does over time.',
    },
    heuristic: { type: 'connective' },
  },
  second_order_chain: {
    name: '"And then what?" three times',
    anchors: {
      0: 'Only the immediate effect.',
      1: 'Two steps, the second obvious.',
      2: 'Three steps, all in the same direction.',
      3: 'Three steps including one that works against the original goal.',
    },
    heuristic: { type: 'depth' },
  },
  delay_identified: {
    name: 'Delay found and used',
    anchors: {
      0: 'No delay noticed.',
      1: 'Says things "take time" without locating it.',
      2: 'Locates the delay in the right place.',
      3: 'Locates the delay and says what wrong move people make because of it.',
    },
    heuristic: { type: 'connective' },
  },
  leverage_placement: {
    name: 'Leverage judged, not guessed',
    anchors: {
      0: 'Suggests changing a number and stops.',
      1: 'Suggests a rule change without comparing it to alternatives.',
      2: 'Compares two intervention levels.',
      3: 'Places the intervention on the ladder (numbers → buffers → loops → rules → goals) and justifies the placement.',
    },
    heuristic: { type: 'connective' },
  },
  rule_generality: {
    name: 'Rule predicts unseen cases',
    anchors: {
      0: 'Describes what happened in the tests, not a rule.',
      1: 'A rule that fits the tests but fails an obvious other case.',
      2: 'A correct rule stated too narrowly or with an extra condition that is not needed.',
      3: 'The rule stated generally and exactly — it predicts cases never tested.',
    },
    heuristic: { type: 'generality' },
  },
  test_design: {
    name: 'Tests that could have proved you wrong',
    anchors: {
      0: 'Tests only confirm the first guess.',
      1: 'Tests vary several things at once.',
      2: 'Mostly one-thing-at-a-time, but no test that could disconfirm.',
      3: 'Controlled tests, including one designed to break the current guess.',
    },
    heuristic: { type: 'connective' },
  },
  intent_reconstruction: {
    name: 'Recovers problem and constraint',
    anchors: {
      0: 'Describes what the thing is, not why it is that way.',
      1: 'Guesses a purpose without evidence from the object.',
      2: 'Names the problem it solves, but not the constraint on the designer.',
      3: 'Names the problem *and* the constraint, using details of the object as evidence.',
    },
    heuristic: { type: 'connective' },
  },
  plan_quality: {
    name: 'Plan before doing',
    anchors: {
      0: 'No plan, or "I will try my best".',
      1: 'A plan that just restates the task.',
      2: 'A plan with steps but no named tool.',
      3: 'Names the move, the order, and what would tell them it is going wrong.',
    },
    heuristic: { type: 'slots' },
  },
  strategy_fit: {
    name: 'Tool fits the problem',
    anchors: {
      0: 'No tool named.',
      1: 'A tool named, reason missing or generic.',
      2: 'A reasonable tool with a reason that would fit any problem.',
      3: 'The tool is named and the reason points at what makes *this* problem that shape.',
    },
    heuristic: { type: 'connective' },
  },
  error_classification: {
    name: 'Names the error type honestly',
    anchors: {
      0: 'Blames luck, the question, or "being bad at this".',
      1: 'Says what was wrong but not what kind of mistake it was.',
      2: 'Classifies the mistake correctly.',
      3: 'Classifies it and names the specific check that would have caught it.',
    },
    heuristic: { type: 'connective' },
  },
  bridge_targets: {
    name: 'Transfer targets are real',
    anchors: {
      0: 'No target, or "in school".',
      1: 'One target, same kind of situation as the task.',
      2: 'Two targets, but from the same area of life.',
      3: 'Two targets from different areas, each with why the move fits there.',
    },
    heuristic: { type: 'distinct', target: 2 },
  },
  integration: {
    name: 'Parts joined into one whole',
    anchors: {
      0: 'Nothing joined.',
      1: 'Parts listed side by side.',
      2: 'Two parts connected, the rest loose.',
      3: 'The parts are made to work together into a single account.',
    },
    heuristic: { type: 'connective' },
  },
  beyond_case: {
    name: 'Goes beyond the case given',
    anchors: {
      0: 'Stays entirely inside the example.',
      1: 'Hints at a general point without stating it.',
      2: 'States a general point that is close to a restatement.',
      3: 'States a principle that would hold in cases not mentioned, and names one.',
    },
    heuristic: { type: 'generality' },
  },
};

/**
 * Compose a rubric criterion.
 * @param {string} id      key in the library
 * @param {number} weight  contribution to the task score (weights must sum to 1)
 * @param {object} [over]  per-task overrides: { name, anchors:{0..3}, heuristic }
 */
export function c(id, weight, over = {}) {
  const base = LIB[id];
  if (!base) throw new Error(`Unknown rubric criterion: ${id}`);
  return {
    id,
    weight,
    name: over.name || base.name,
    anchors: { ...base.anchors, ...(over.anchors || {}) },
    heuristic: { ...base.heuristic, ...(over.heuristic || {}) },
  };
}

export const CRITERIA = LIB;
export const RUBRIC_VERSION = '1.0.0';
