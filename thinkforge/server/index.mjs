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

const handler = async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const ip = req.socket.remoteAddress || 'local';

  if (url.pathname.startsWith('/api/')) {
    if (!allow(ip)) return send(res, 429, { error: 'slow_down' });
    return handleApi(req, res, url);
  }
  if (req.method !== 'GET') return send(res, 405, 'method not allowed');
  return serveStatic(CLIENT_ROOT, url.pathname, res);
};

const server = http.createServer(handler);

/**
 * Windows resolves `localhost` to ::1 before 127.0.0.1, so a server bound only
 * to IPv4 loopback can be unreachable in a browser that does not fall back —
 * "the page won't open" with the server apparently running. A second listener
 * on IPv6 loopback fixes that without putting anything on the network, which
 * is why this is two loopback binds rather than one wildcard bind.
 */
const secondary = HOST === '127.0.0.1' ? http.createServer(handler) : null;

function listen(srv, host) {
  return new Promise((resolve) => {
    srv.once('error', () => resolve(false));   // machine has no IPv6: fine
    srv.listen(PORT, host, () => resolve(true));
  });
}

export async function start() {
  getDb();
  const ai = await aiStatus();
  const bound = await listen(server, HOST);
  if (!bound) throw new Error(`Port ${PORT} is already in use. Start with PORT=4174 (or any free port).`);
  if (secondary) await listen(secondary, '::1');

  const mode = ai.available
    ? `AI marking + tutoring on (${ai.model})`
    : `offline mode (${ai.reason}) - deterministic marking and the authored hint ladder`;
  console.log('');
  console.log(`  Thinkforge is running - ${mode}`);
  console.log('');
  console.log(`  Open this in your browser:   http://localhost:${PORT}`);
  console.log(`  If that does not open, try:  http://127.0.0.1:${PORT}`);
  console.log('');
  console.log('  Leave this window open. Press Ctrl+C here to stop it.');
  console.log('');
  if (HOST !== '127.0.0.1' && HOST !== 'localhost') {
    console.log(`  Reachable from the network on ${HOST}:${PORT} - it holds student work, so keep it to a trusted network.`);
    console.log('');
  }
  return server;
}

/** Close every listener this process opened. */
export function close() {
  server.close();
  if (secondary) secondary.close();
}

export { server };

if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  start().catch((err) => {
    // A failure to start is an operational problem for whoever is standing at
    // the machine, not a bug report: say the one useful sentence and stop.
    console.error('');
    console.error(`  Thinkforge could not start: ${err.message}`);
    console.error('');
    process.exit(1);
  });
}
