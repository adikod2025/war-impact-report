/**
 * The growth story (docs/03 §D.2): generated from the deltas plus the
 * student's own quoted work, or a deterministic template when offline.
 */
import { call } from './client.mjs';
import { narrativeSystem, NARRATIVE_SCHEMA } from './prompts.mjs';
import { templateNarrative } from '../engine/growth.mjs';
import { redactPII } from './safety.mjs';
import { STRANDS } from '../content/frameworks.mjs';

export async function growthStory({ current, previous, portfolio = [], age = 12 }) {
  const template = templateNarrative(current, previous);
  if (!previous) return template;

  const deltas = current.strands.map((s) => {
    const before = previous.strands.find((p) => p.strand === s.strand);
    return {
      strand: STRANDS.find((x) => x.id === s.strand)?.name || s.strand,
      level: s.level,
      change: Math.round((s.theta - (before?.theta ?? s.theta)) * 100) / 100,
    };
  });

  const quotes = portfolio.slice(0, 3).map((p) => ({
    move: p.move, task: p.taskTitle, quote: redactPII(p.text || '').text.slice(0, 220),
  }));

  let result;
  try {
    result = await call({
      system: narrativeSystem(),
      messages: [{
        role: 'user',
        content: `Student age: ${age}\n\nCHANGES SINCE LAST WEEK (logits; positive = improved)\n${JSON.stringify(deltas)}\n\nGROWTH INDICES NOW\n${JSON.stringify(current.indices)}\n\nTHE STUDENT'S OWN RECENT WORK (quote one of these verbatim)\n${JSON.stringify(quotes)}`,
      }],
      schema: NARRATIVE_SCHEMA,
      effort: 'low',
      maxTokens: 600,
    });
  } catch {
    return template;
  }
  if (!result.ok || !result.json) return template;
  return { ...result.json, source: 'ai', model: result.model };
}
