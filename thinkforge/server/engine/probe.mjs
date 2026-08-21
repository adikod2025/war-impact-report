/**
 * Black-box machines for `probe` tasks, and the process scoring that goes
 * with them (docs/03 §A.2). The rule is a small declarative tree, never
 * evaluated code, so task content stays data.
 */

function leafValue(term, inputs) {
  if (term.fn === 'parity') {
    const n = Number(inputs[term.var]);
    return Number.isFinite(n) ? (n % 2 === 0 ? 'even' : 'odd') : null;
  }
  if (term.fn === 'sum') return term.vars.reduce((a, v) => a + Number(inputs[v] || 0), 0);
  if (term.fn === 'diff') return Number(inputs[term.vars[0]] || 0) - Number(inputs[term.vars[1]] || 0);
  return inputs[term.var];
}

function compare(value, cmp, target) {
  switch (cmp) {
    case '==': return value === target || String(value) === String(target);
    case '!=': return String(value) !== String(target);
    case '>': return Number(value) > Number(target);
    case '>=': return Number(value) >= Number(target);
    case '<': return Number(value) < Number(target);
    case '<=': return Number(value) <= Number(target);
    case 'in': return Array.isArray(target) && target.map(String).includes(String(value));
    default: throw new Error(`Unknown comparison: ${cmp}`);
  }
}

export function evaluateRule(node, inputs) {
  if (!node) return false;
  if (node.op === 'and') return node.terms.every((t) => evaluateRule(t, inputs));
  if (node.op === 'or') return node.terms.some((t) => evaluateRule(t, inputs));
  if (node.op === 'not') return !evaluateRule(node.terms[0], inputs);
  return compare(leafValue(node, inputs), node.cmp, node.val);
}

export function runMachine(machine, inputs) {
  const on = evaluateRule(machine.rule, inputs);
  return { on, text: on ? machine.outputText?.true || 'ON' : machine.outputText?.false || 'off' };
}

/** Two tests are "controlled" when exactly one input differs. */
export function isControlledPair(a, b) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  let diff = 0;
  for (const k of keys) if (String(a[k]) !== String(b[k])) diff += 1;
  return diff === 1;
}

/**
 * @param {Array<{inputs:object,on:boolean}>} tests in the order the student ran them
 * @param {object} machine
 * @returns {{efficiency:number,control:number,discrimination:number,process:number,tests:number}}
 */
export function scoreProcess(tests, machine) {
  const n = tests.length;
  if (!n) return { efficiency: 0, control: 0, discrimination: 0, process: 0, tests: 0 };

  const minTests = machine.minTests || 3;
  const maxUseful = machine.maxUseful || minTests * 3;

  let controlled = 0;
  for (let i = 1; i < n; i += 1) {
    if (isControlledPair(tests[i - 1].inputs, tests[i].inputs)) controlled += 1;
    else if (tests.slice(0, i).some((t) => isControlledPair(t.inputs, tests[i].inputs))) controlled += 1;
  }
  const control = n > 1 ? controlled / (n - 1) : 0;

  // A test discriminates when it produced an outcome different from the test it
  // was paired with — i.e. it could have come out either way and settled something.
  const outcomes = new Set(tests.map((t) => String(t.on)));
  const discrimination = outcomes.size > 1 ? 1 : 0;

  const efficiency = n <= minTests
    ? 1
    : Math.max(0, Math.min(1, 1 - (n - minTests) / Math.max(1, maxUseful - minTests)));

  const process = 0.4 * control + 0.35 * discrimination + 0.25 * efficiency;
  return {
    efficiency: r(efficiency), control: r(control), discrimination, process: r(process), tests: n,
  };
}

/** Cheap offline check of a stated rule against the machine's canonical forms. */
export function ruleMatches(stated, machine) {
  const s = String(stated || '').toLowerCase().replace(/(\d)\s+([a-z])/g, '$1$2');
  if (!s.trim()) return 0;
  const forms = machine.canonicalForms || [];
  let best = 0;
  for (const form of forms) {
    const words = form.toLowerCase().match(/[a-z0-9]+/g) || [];
    const key = words.filter((w) => w.length > 2 && !['the', 'and', 'when', 'that', 'with', 'not', 'for', 'its'].includes(w));
    if (!key.length) continue;
    const hit = key.filter((w) => s.includes(w)).length / key.length;
    best = Math.max(best, hit);
  }
  return r(best);
}

const r = (x) => Math.round(x * 1000) / 1000;
