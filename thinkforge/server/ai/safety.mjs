/**
 * Child-safety and privacy controls (docs/03 Part C).
 *
 * Deliberately deterministic: a regex-and-lexicon layer that runs *before*
 * anything reaches a model, so a distress signal is never left to an LLM to
 * notice, and no personal data is sent off the box in the first place.
 */

const PII_PATTERNS = [
  [/\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b/g, '[email removed]'],
  [/\b(?:\+?\d[\d\s-]{8,}\d)\b/g, '[number removed]'],
  [/\b\d{1,4}\s+[A-Z][a-z]+\s(?:Road|Street|St|Lane|Avenue|Ave|Drive|Close|Way)\b/g, '[address removed]'],
  [/\b(?:instagram|snapchat|tiktok|discord|whatsapp)\b[:\s@]*[\w.@-]{3,}/gi, '[handle removed]'],
];

const DISTRESS = [
  'kill myself', 'want to die', 'end my life', 'self harm', 'self-harm', 'cut myself', 'hurt myself',
  'nobody would miss me', 'better off dead', 'suicidal', 'suicide',
];
const HARM_TO_OTHERS = ['kill him', 'kill her', 'kill them', 'hurt them badly', 'bring a knife', 'bring a weapon'];
const ABUSE_DISCLOSURE = ['hits me', 'hurts me at home', 'touched me', 'scared to go home', 'my dad hits', 'my mum hits'];

const OFF_SCOPE = [
  'what do you look like', 'are you my friend', 'do you love me', 'be my girlfriend', 'be my boyfriend',
  'what is your phone number', 'meet me', 'keep this secret',
];

const ANSWER_EXTRACTION = [
  'just tell me the answer', 'give me the answer', 'what is the answer', 'tell me the answer',
  'just say it', 'stop asking questions', 'do it for me', 'write it for me',
];

export const CRISIS_TEXT = 'It sounds like something serious is going on. I am an AI and I am not the right help for this — please tell a trusted adult right now: a parent, a carer, or a teacher. If you are in danger, contact your local emergency number.';

function matches(text, list) {
  const t = String(text || '').toLowerCase();
  return list.filter((p) => t.includes(p));
}

export function redactPII(text) {
  let out = String(text || '');
  let redacted = 0;
  for (const [re, replacement] of PII_PATTERNS) {
    out = out.replace(re, () => { redacted += 1; return replacement; });
  }
  return { text: out, redacted };
}

/**
 * @returns {{action:'allow'|'redact'|'escalate'|'redirect', level:string, matched:string[], reply:string|null, text:string}}
 */
export function screenStudentText(text) {
  const distress = matches(text, DISTRESS);
  if (distress.length) {
    return { action: 'escalate', level: 'distress', matched: distress, reply: CRISIS_TEXT, text: '' };
  }
  const harm = matches(text, HARM_TO_OTHERS);
  if (harm.length) {
    return { action: 'escalate', level: 'harm_to_others', matched: harm, reply: CRISIS_TEXT, text: '' };
  }
  const abuse = matches(text, ABUSE_DISCLOSURE);
  if (abuse.length) {
    return { action: 'escalate', level: 'safeguarding', matched: abuse, reply: CRISIS_TEXT, text: '' };
  }
  const off = matches(text, OFF_SCOPE);
  if (off.length) {
    return {
      action: 'redirect', level: 'off_scope', matched: off,
      reply: 'I am an AI thinking coach, so I only talk about the task you are working on. Shall we get back to it?',
      text: '',
    };
  }
  const { text: clean, redacted } = redactPII(text);
  return { action: redacted ? 'redact' : 'allow', level: 'ok', matched: [], reply: null, text: clean, redacted };
}

export function isAnswerExtraction(text) {
  return matches(text, ANSWER_EXTRACTION).length > 0;
}

/**
 * Post-filter on tutor output: a turn that reproduces the answer key is
 * rejected and regenerated one rung higher (docs/03 §B.1).
 */
export function leaksAnswer(tutorText, answerKey) {
  if (!answerKey) return false;
  const keyTokens = String(answerKey).toLowerCase().match(/[a-z]{4,}/g) || [];
  if (keyTokens.length < 6) return false;
  const t = String(tutorText || '').toLowerCase();
  const distinctive = [...new Set(keyTokens)];
  const hits = distinctive.filter((w) => t.includes(w)).length;
  return hits / distinctive.length > 0.55;
}

export const AI_DISCLOSURE = 'I am an AI coach, not a person.';
