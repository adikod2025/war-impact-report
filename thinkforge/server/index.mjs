#!/usr/bin/env node
/** Thinkforge server. Zero runtime dependencies; the Anthropic SDK is optional. */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { serveStatic, send, rateLimiter } from './http.mjs';
import { handleApi } from './router.mjs';
import { getDb } from './db.mjs';
import { aiStatus } from './ai/client.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const CLIENT_ROOT = path.join(here, '..', 'client');

/**
 * Load a .env sitting next to the install, if there is one. Deliberately tiny
 * and dependency-free: the only thing anyone puts in it is an API key and a
 * port, and an existing environment variable always wins.
 */
function loadEnvFile(file = path.join(here, '..', '.env')) {
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*)\s*$/i);
    if (!match) continue;
    const [, key, rawValue] = match;
    if (process.env[key] !== undefined) continue;
    process.env[key] = rawValue.replace(/^(['"])(.*)\1$/, '$2');
  }
}
loadEnvFile();

const PORT = Number(process.env.PORT || 4173);
// Loopback by default: this holds children's work, so it is not on the network
// unless somebody deliberately puts it there (HOST=0.0.0.0 for a classroom).
const HOST = process.env.HOST || '127.0.0.1';

const allow = rateLimiter({ windowMs: 60000, max: 300 });

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const ip = req.socket.remoteAddress || 'local';

  if (url.pathname.startsWith('/api/')) {
    if (!allow(ip)) return send(res, 429, { error: 'slow_down' });
    return handleApi(req, res, url);
  }
  if (req.method !== 'GET') return send(res, 405, 'method not allowed');
  return serveStatic(CLIENT_ROOT, url.pathname, res);
});

export async function start() {
  getDb();
  const ai = await aiStatus();
  await new Promise((resolve) => server.listen(PORT, HOST, resolve));
  const mode = ai.available ? `AI marking + tutoring on (${ai.model})` : `offline mode (${ai.reason}) — deterministic marking and the authored hint ladder`;
  console.log(`Thinkforge listening on http://localhost:${PORT}  ·  ${mode}`);
  if (HOST !== '127.0.0.1' && HOST !== 'localhost') {
    console.log(`Reachable from the network on ${HOST}:${PORT} — it holds student work, so keep it to a trusted network.`);
  }
  return server;
}

export { server };

if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) start();
