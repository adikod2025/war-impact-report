#!/usr/bin/env node
/**
 * Preflight for a local install. Run before the first start, and any time
 * something looks wrong: it checks the things that actually break on a fresh
 * machine and says what to do about each one.
 *
 *   node scripts/doctor.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const checks = [];
const add = (ok, name, detail, fix = null) => checks.push({ ok, name, detail, fix });

/* Node version — node:sqlite is the one hard requirement. */
const [major, minor] = process.versions.node.split('.').map(Number);
const nodeOk = major > 22 || (major === 22 && minor >= 5);
add(nodeOk, 'Node.js version', `found v${process.versions.node}, need v22.5 or newer`,
  nodeOk ? null : 'Install the current LTS from https://nodejs.org — nothing else needs installing.');

/* node:sqlite, and whether this version still needs the flag. */
let sqliteNote = 'built in and ready';
let sqliteOk = false;
let needsFlag = false;
try {
  const { DatabaseSync } = await import('node:sqlite');
  new DatabaseSync(':memory:').exec('create table t(a)');
  sqliteOk = true;
} catch (err) {
  needsFlag = /experimental|flag/i.test(String(err.message));
  sqliteNote = needsFlag
    ? 'available but needs --experimental-sqlite on this Node version (the start script adds it for you)'
    : `unavailable: ${err.message}`;
  sqliteOk = needsFlag;
}
add(sqliteOk, 'Built-in database (node:sqlite)', sqliteNote,
  sqliteOk ? null : 'Upgrade to Node v22.5 or newer.');

/* Somewhere to keep the data. */
const dataDir = process.env.THINKFORGE_DB ? path.dirname(path.resolve(process.env.THINKFORGE_DB)) : path.join(root, 'data');
let writable = false;
try {
  fs.mkdirSync(dataDir, { recursive: true });
  const probe = path.join(dataDir, '.write-probe');
  fs.writeFileSync(probe, 'ok');
  fs.unlinkSync(probe);
  writable = true;
} catch (err) {
  add(false, 'Data folder', `cannot write to ${dataDir}: ${err.message}`, 'Pick another location with THINKFORGE_DB=/path/to/thinkforge.db');
}
if (writable) add(true, 'Data folder', `${dataDir} is writable`);

/* The port. */
const port = Number(process.env.PORT || 4173);
const portFree = await new Promise((resolve) => {
  const srv = net.createServer();
  srv.once('error', () => resolve(false));
  srv.once('listening', () => srv.close(() => resolve(true)));
  srv.listen(port, '127.0.0.1');
});
if (portFree) {
  add(true, `Port ${port}`, 'free');
} else {
  // Occupied by Thinkforge itself is the common case — somebody started it
  // twice — and it deserves a different sentence from a genuine clash.
  let mine = false;
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/status`, { signal: AbortSignal.timeout(1500) });
    mine = res.ok && !!(await res.json()).strands;
  } catch { mine = false; }
  add(mine, `Port ${port}`, mine
    ? `Thinkforge is already running here — just open http://localhost:${port}`
    : 'in use by something else',
  mine ? null : `Start on another port instead:  PORT=4174 npm start`);
}

/* The curriculum loads and is intact. */
try {
  const { TASKS } = await import('../server/content/index.mjs');
  const { allMoves, STRANDS } = await import('../server/content/frameworks.mjs');
  add(TASKS.length > 0, 'Curriculum', `${STRANDS.length} strands, ${allMoves().length} moves, ${TASKS.length} missions loaded`);
} catch (err) {
  add(false, 'Curriculum', `failed to load: ${err.message}`, 'The install looks incomplete — re-extract the release archive.');
}

/* AI is optional, and the platform says so rather than pretending. */
const hasKey = !!(process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_AUTH_TOKEN);
let sdkPresent = false;
try { await import('@anthropic-ai/sdk'); sdkPresent = true; } catch { sdkPresent = false; }
const aiState = hasKey && sdkPresent ? 'on' : hasKey ? 'key found, but the SDK is missing' : 'off';
add(true, 'AI marking and coaching', aiState === 'on'
  ? `on (model ${process.env.THINKFORGE_MODEL || 'claude-opus-5'})`
  : `${aiState} — the platform runs fully without it, using deterministic marking and the authored hint ladder`,
  hasKey ? (sdkPresent ? null : 'Run: npm install') : 'Optional: put ANTHROPIC_API_KEY=sk-ant-... in a .env file next to this folder.');

/* ---- report ---- */
const pad = Math.max(...checks.map((c) => c.name.length));
console.log('\nThinkforge preflight\n');
for (const c of checks) {
  console.log(`  ${c.ok ? '✓' : '✗'}  ${c.name.padEnd(pad)}  ${c.detail}`);
  if (!c.ok && c.fix) console.log(`     ${' '.repeat(pad)}  → ${c.fix}`);
  if (c.ok && c.fix) console.log(`     ${' '.repeat(pad)}  · ${c.fix}`);
}
const failed = checks.filter((c) => !c.ok);
console.log(failed.length
  ? `\n${failed.length} problem${failed.length === 1 ? '' : 's'} to fix before starting.\n`
  : `\nAll good. Start it with:  npm start   →  http://localhost:${port}\n`);

if (needsFlag) console.log('Note: this Node version needs --experimental-sqlite; ./start.sh and start.cmd add it automatically.\n');
process.exit(failed.length ? 1 : 0);
