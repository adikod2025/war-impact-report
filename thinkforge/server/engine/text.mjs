/**
 * Linguistic feature extraction.
 *
 * These features do three jobs:
 *   1. the L0 validity gate (copying, degenerate input, off-task)
 *   2. the deterministic caps that bound any AI judgement
 *   3. the offline rubric estimator used when no AI key is configured
 *
 * Nothing here is clever. It is deliberately transparent so a teacher can be
 * told exactly why a response scored what it scored.
 */

const STOPWORDS = new Set(`a an the and or but if then than that this these those it its is are was were be been being
of to in on at for with from by as so not no nor do does did doing have has had having i you he she they we me my your
their our his her them us who whom which what when where why how all any both each few more most other some such only own
same too very can will just should now would could there here about into over under again further once`.split(/\s+/));

const CONNECTIVES = ['because', 'so that', 'therefore', 'since', 'whenever', 'which means', 'leads to', 'causes',
  'in order to', 'as a result', 'that is why', 'thats why', 'this means', 'due to', 'results in', 'depends on',
  'if', 'then', 'so', 'follows', 'explains'];

const HEDGES = ['usually', 'often', 'most', 'some', 'might', 'may', 'could', 'tends', 'tend to', 'roughly', 'about',
  'probably', 'likely', 'in this case', 'at least', 'seems', 'suggests', 'appears', 'generally', 'sometimes'];

const ABSOLUTES = ['always', 'never', 'everyone', 'nobody', 'all of them', 'definitely', 'obviously', 'proves', 'every single'];

const CONTRAST = ['unless', 'except', 'however', 'but if', 'although', 'whereas', 'on the other hand', 'otherwise',
  'would fail', 'wouldn\'t work', 'would not work', 'counter', 'instead', 'unlike', 'rival', 'other explanation',
  'could also', 'might not', 'apart from'];

const GENERALITY = ['whenever', 'in general', 'generally', 'any time', 'anytime', 'always when', 'people tend',
  'the rule', 'a rule', 'in any', 'every time', 'this applies', 'as a principle', 'usually means'];

const VAGUE = ['stuff', 'things', 'thing', 'better', 'good', 'bad', 'nice', 'cool', 'interesting', 'important', 'lots'];

export function tokens(text) {
  return String(text || '').toLowerCase().match(/[a-z0-9']+/g) || [];
}

export function contentTokens(text) {
  return tokens(text).filter((t) => t.length > 2 && !STOPWORDS.has(t));
}

export function wordCount(text) {
  return tokens(text).length;
}

const RX_CACHE = new Map();
function phraseRegex(phrase) {
  const key = phrase;
  if (!RX_CACHE.has(key)) {
    const body = phrase.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
    RX_CACHE.set(key, new RegExp(`\\b${body}\\b`, 'g'));
  }
  return RX_CACHE.get(key);
}

/** Whole-word phrase counting — substring matching would score "whenever" as "never". */
function countPhrases(lower, list) {
  let n = 0;
  for (const p of list) if (phraseRegex(p).test(lower)) n += 1;
  return n;
}

/** Split a response into the items the student meant as separate ideas. */
export function items(text) {
  return String(text || '')
    .split(/\r?\n|(?:^|\s)[-•*]\s|(?:^|\s)\d+[.)]\s|;/)
    .map((s) => s.trim())
    .filter((s) => wordCount(s) >= 2);
}

/** Jaccard-ish containment of a against b. */
export function overlap(a, b) {
  const A = new Set(contentTokens(a));
  const B = new Set(contentTokens(b));
  if (!A.size) return 0;
  let hit = 0;
  for (const t of A) if (B.has(t)) hit += 1;
  return hit / A.size;
}

/** Greedy clustering of near-duplicate items; returns cluster count and members. */
export function clusters(list, threshold = 0.5) {
  const out = [];
  for (const item of list) {
    const set = new Set(contentTokens(item));
    if (!set.size) continue;
    let placed = false;
    for (const cl of out) {
      let hit = 0;
      for (const t of set) if (cl.tokens.has(t)) hit += 1;
      const sim = hit / Math.max(1, Math.min(set.size, cl.tokens.size));
      if (sim >= threshold) {
        cl.members.push(item);
        placed = true;
        break;
      }
    }
    if (!placed) out.push({ tokens: set, members: [item] });
  }
  return out;
}

/** Fraction of items that add tokens not seen in the items above them. */
export function progression(list) {
  const seen = new Set();
  let advancing = 0;
  list.forEach((item, i) => {
    const toks = contentTokens(item);
    const fresh = toks.filter((t) => !seen.has(t));
    if (i === 0 || fresh.length >= Math.max(1, Math.ceil(toks.length * 0.35))) advancing += 1;
    toks.forEach((t) => seen.add(t));
  });
  return list.length ? advancing / list.length : 0;
}

/**
 * Share of the response covered by verbatim runs of `n` words lifted from the
 * source. Vocabulary overlap is the wrong test for copying — a short honest
 * answer necessarily reuses the question's nouns — so the gate uses this.
 */
export function verbatimShare(text, source, n = 5) {
  const t = tokens(text);
  const src = tokens(source);
  if (t.length < n || src.length < n) return 0;
  const grams = new Set();
  for (let i = 0; i + n <= src.length; i += 1) grams.add(src.slice(i, i + n).join(' '));
  const covered = new Array(t.length).fill(false);
  for (let i = 0; i + n <= t.length; i += 1) {
    if (grams.has(t.slice(i, i + n).join(' '))) for (let j = i; j < i + n; j += 1) covered[j] = true;
  }
  return covered.filter(Boolean).length / t.length;
}

export function extractFeatures(text, { stimulus = '', commonIdeas = [], conceptVocabulary = [] } = {}) {
  const raw = String(text || '');
  const lower = raw.toLowerCase();
  const toks = tokens(raw);
  const content = contentTokens(raw);
  const list = items(raw);
  const cl = clusters(list);
  const uniqueContent = new Set(content);

  const vocabHits = conceptVocabulary.filter((w) => lower.includes(String(w).toLowerCase())).length;
  const commonOverlap = commonIdeas.length
    ? list.filter((it) => commonIdeas.some((ci) => overlap(it, ci) >= 0.5)).length / Math.max(1, list.length)
    : 0;

  const repeated = toks.length > 3 && uniqueContent.size <= 2;

  return {
    words: toks.length,
    contentWords: content.length,
    uniqueContentWords: uniqueContent.size,
    items: list.length,
    clusters: cl.length,
    clusterSizes: cl.map((c) => c.members.length),
    progression: progression(list),
    connectives: countPhrases(lower, CONNECTIVES),
    hedges: countPhrases(lower, HEDGES),
    absolutes: countPhrases(lower, ABSOLUTES),
    contrast: countPhrases(lower, CONTRAST),
    generality: countPhrases(lower, GENERALITY),
    vague: countPhrases(lower, VAGUE),
    numbers: (raw.match(/\b\d+(?:[.,]\d+)?\b/g) || []).length,
    properNouns: (raw.match(/(?!^)\b[A-Z][a-z]{2,}\b/g) || []).length,
    stimulusOverlap: overlap(raw, stimulus),
    stimulusVerbatim: verbatimShare(raw, stimulus),
    conceptVocabHits: vocabHits,
    commonIdeaShare: commonOverlap,
    degenerate: repeated,
  };
}
