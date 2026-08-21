/* Minimal view layer: element builder, hash router, API client, shared state. */

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style' && typeof v === 'object') {
      // Custom properties need setProperty — Object.assign silently drops them,
      // which would leave every strand the same colour.
      for (const [prop, val] of Object.entries(v)) {
        if (prop.startsWith('--')) el.style.setProperty(prop, val);
        else el.style[prop] = val;
      }
    }
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'selected') el[k] = !!v;
    else el.setAttribute(k, v);
  }
  for (const child of children.flat(3)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

/**
 * The tiny subset of markdown the content bank uses: **bold**, *italic*,
 * `code`, and paragraph breaks. Everything is escaped first — task text is
 * authored content, but student text also flows through here.
 */
export function md(text) {
  const esc = String(text ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return esc
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|\W)\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');
}

export const api = {
  async get(path) { return unwrap(await fetch(path)); },
  async post(path, body) {
    return unwrap(await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body || {}) }));
  },
  async del(path) { return unwrap(await fetch(path, { method: 'DELETE' })); },
};

async function unwrap(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || res.statusText), { data, status: res.status });
  return data;
}

export const store = {
  get studentId() { return localStorage.getItem('tf.student'); },
  set studentId(v) { v ? localStorage.setItem('tf.student', v) : localStorage.removeItem('tf.student'); },
  status: null,
  profile: null,
};

const routes = new Map();
export function route(name, render) { routes.set(name, render); }

export function go(path) {
  if (location.hash === `#${path}`) render();
  else location.hash = path;
}

const root = () => document.getElementById('root');

export async function render() {
  const [name, ...params] = (location.hash.slice(1) || '/').split('/').filter(Boolean);
  const view = routes.get(name || 'home') || routes.get('home');
  const el = root();
  el.replaceChildren(h('p', { class: 'loading' }, 'Loading…'));
  try {
    const out = await view(params);
    el.replaceChildren(...(Array.isArray(out) ? out : [out]));
    window.scrollTo(0, 0);   // not scrollIntoView: that hides the heading under the sticky bar
  } catch (err) {
    el.replaceChildren(h('div', { class: 'card' },
      h('h2', {}, 'Something went wrong'),
      h('p', { class: 'muted' }, String(err.message || err)),
      h('button', { class: 'primary', onclick: () => render() }, 'Try again')));
  }
  paintNav(name || 'home');
}

function paintNav(current) {
  const items = store.studentId
    ? [['home', 'Home'], ['session', 'Session'], ['growth', 'Growth'], ['moves', 'The moves'], ['teacher', 'Teacher'], ['about', 'How it works']]
    : [['home', 'Start'], ['moves', 'The moves'], ['teacher', 'Teacher'], ['about', 'How it works']];
  document.getElementById('nav').replaceChildren(...items.map(([path, label]) =>
    h('a', { href: `#${path}`, 'aria-current': path === current ? 'page' : null }, label)));
}

window.addEventListener('hashchange', render);

/* ---------- shared bits ---------- */

export function levelPips(level, colour) {
  return h('div', { class: 'levels', style: { '--strand': colour } },
    [0, 1, 2, 3, 4].map((i) => h('i', { class: i < level ? 'on' : '' })));
}

export function dial({ name, colour, theta, se, level, levelName, n }) {
  const toPct = (t) => Math.max(0, Math.min(100, ((t + 2) / 4.5) * 100));
  return h('div', { class: 'dial', style: { '--strand': colour } },
    h('div', { class: 'row between' },
      h('strong', {}, name),
      h('span', { class: 'tag' }, `Level ${level} · ${levelName}`)),
    h('div', { class: 'bar' },
      h('div', { class: 'band', style: { left: `${toPct(theta - se)}%`, width: `${Math.max(2, toPct(theta + se) - toPct(theta - se))}%` } }),
      h('div', { class: 'fill', style: { width: `${toPct(theta)}%`, opacity: .85 } })),
    h('div', { class: 'meta' },
      h('span', {}, n ? `${n} mission${n === 1 ? '' : 's'}` : 'not started'),
      h('span', {}, `±${se.toFixed(2)} certainty`)));
}

export const LEVEL_NAMES = ['Not yet', 'Noticing', 'Listing', 'Connecting', 'Extending', 'Directing'];

export function aiBadge(status) {
  if (!status) return null;
  return status.ai.available
    ? h('span', { class: 'tag good' }, `AI marking on · ${status.ai.model}`)
    : h('span', { class: 'tag warn' }, 'Offline mode — deterministic marking');
}

export function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}
