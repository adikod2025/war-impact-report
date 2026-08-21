/** Tiny request helpers — no framework, no dependencies. */
import fs from 'node:fs';
import path from 'node:path';

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon', '.woff2': 'font/woff2',
};

export function send(res, status, body, headers = {}) {
  const payload = typeof body === 'string' || Buffer.isBuffer(body) ? body : JSON.stringify(body);
  res.writeHead(status, {
    'content-type': typeof body === 'object' && !Buffer.isBuffer(body) ? 'application/json; charset=utf-8' : 'text/plain; charset=utf-8',
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer',
    ...headers,
  });
  res.end(payload);
}

export async function readJson(req, limit = 256 * 1024) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    let overflowed = false;
    req.on('data', (c) => {
      size += c.length;
      if (size > limit) {
        // Drain rather than destroy: killing the socket loses the 413 response.
        if (!overflowed) { overflowed = true; chunks.length = 0; reject(new Error('payload_too_large')); }
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => {
      if (overflowed) return;
      if (!chunks.length) return resolve({});
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); } catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

export function serveStatic(root, urlPath, res) {
  const rel = urlPath === '/' ? '/index.html' : urlPath;
  const file = path.join(root, path.normalize(rel).replace(/^(\.\.[/\\])+/, ''));
  if (!file.startsWith(root)) return send(res, 403, 'forbidden');
  fs.readFile(file, (err, data) => {
    if (err) {
      // Single-page app: unknown paths fall back to the shell.
      return fs.readFile(path.join(root, 'index.html'), (e2, shell) => (e2 ? send(res, 404, 'not found') : send(res, 200, shell, { 'content-type': MIME['.html'] })));
    }
    send(res, 200, data, { 'content-type': MIME[path.extname(file)] || 'application/octet-stream' });
  });
}

/** Fixed-window limiter, per IP. Enough for a classroom; not a WAF. */
export function rateLimiter({ windowMs = 60000, max = 240 } = {}) {
  const hits = new Map();
  return (ip) => {
    const now = Date.now();
    const entry = hits.get(ip);
    if (!entry || now - entry.start > windowMs) { hits.set(ip, { start: now, n: 1 }); return true; }
    entry.n += 1;
    if (hits.size > 5000) hits.clear();
    return entry.n <= max;
  };
}
