/**
 * Anthropic client.
 *
 * Loaded lazily so the platform runs with no SDK and no API key at all — every
 * AI capability in Thinkforge has a deterministic fallback, and the absence of
 * a key degrades quality, never availability (docs/03 §A.0).
 */
import crypto from 'node:crypto';

export const MODEL = process.env.THINKFORGE_MODEL || 'claude-opus-5';
const FALLBACK_BETA = 'server-side-fallback-2026-07-01';

let sdkPromise = null;
let client = null;
let unavailableReason = null;

export function hasApiKey() {
  return !!(process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_AUTH_TOKEN);
}

async function loadClient() {
  if (client) return client;
  if (!hasApiKey()) {
    unavailableReason = 'no_api_key';
    return null;
  }
  if (!sdkPromise) sdkPromise = import('@anthropic-ai/sdk').catch(() => null);
  const mod = await sdkPromise;
  if (!mod) {
    unavailableReason = 'sdk_not_installed';
    return null;
  }
  const Anthropic = mod.default;
  client = new Anthropic();
  return client;
}

export async function aiStatus() {
  const c = await loadClient();
  return {
    available: !!c,
    reason: c ? null : unavailableReason || 'unknown',
    model: c ? MODEL : null,
  };
}

export function promptHash(parts) {
  return crypto.createHash('sha256').update(JSON.stringify(parts)).digest('hex').slice(0, 16);
}

function textOf(message) {
  return (message?.content || [])
    .filter((b) => b.type === 'text')
    .map((b) => b.text)
    .join('\n')
    .trim();
}

/**
 * One Messages API call. Opus-family models reject `temperature`, so
 * determinism comes from a constrained output schema and low effort rather
 * than from sampling parameters.
 */
export function buildRequest({ system, messages, schema = null, effort = 'medium', maxTokens = 4000, thinking = 'adaptive', model = MODEL }) {
  const body = {
    model,
    max_tokens: maxTokens,
    system,
    messages,
    output_config: { effort },
  };
  // No `temperature`: the Opus/Sonnet 5 family rejects sampling parameters.
  // Determinism comes from a constrained output schema and low effort instead.
  if (thinking) body.thinking = { type: 'adaptive' };
  if (schema) body.output_config.format = { type: 'json_schema', schema };
  return body;
}

export function usesRefusalFallback(model = MODEL) {
  return /^claude-(opus-5|fable-5)/.test(model);
}

export async function call({ system, messages, schema = null, effort = 'medium', maxTokens = 4000, thinking = 'adaptive' }) {
  const c = await loadClient();
  if (!c) return { ok: false, reason: unavailableReason };

  const body = buildRequest({ system, messages, schema, effort, maxTokens, thinking });
  const useBeta = usesRefusalFallback();
  let message;
  try {
    message = useBeta
      ? await c.beta.messages.create({ ...body, betas: [FALLBACK_BETA], fallbacks: 'default' })
      : await c.messages.create(body);
  } catch (err) {
    if (useBeta) {
      // The refusal-fallback beta is Claude API only; retry plainly elsewhere.
      message = await c.messages.create(body);
    } else {
      throw err;
    }
  }

  if (message.stop_reason === 'refusal') {
    return { ok: false, reason: 'refusal', category: message.stop_details?.category || null };
  }

  const text = textOf(message);
  const out = {
    ok: true,
    text,
    model: message.model || MODEL,
    stopReason: message.stop_reason,
    usage: message.usage || null,
    promptHash: promptHash({ system, messages, schema }),
  };
  if (schema) {
    try {
      out.json = message.parsed_output ?? JSON.parse(text);
    } catch {
      const match = text.match(/\{[\s\S]*\}/);
      out.json = match ? JSON.parse(match[0]) : null;
      if (!out.json) return { ok: false, reason: 'unparseable', text };
    }
  }
  return out;
}
