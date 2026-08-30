#!/usr/bin/env node
/**
 * Starts Thinkforge, checks it is actually reachable, and says what is wrong if
 * it is not. Run this when the browser says the connection was refused:
 *
 *   node scripts/selftest.mjs
 *
 * It starts its own copy on a spare port and shuts it down again, so it is safe
 * to run at any time.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const serverPath = path.join(root, 'server', 'index.mjs');
const version = (() => {
  try { return JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).version; } catch { return '?'; }
})();
const port = 4173 + 900;
const dbFile = path.join(os.tmpdir(), `thinkforge-selftest-${process.pid}.db`);

console.log(`\nThinkforge self-test — version ${version}`);
console.log(`Folder: ${root}\n`);

if (!fs.existsSync(serverPath)) {
  console.log('  ✗  The application files are not here.');
  console.log('     Extract the archive and run this from inside the thinkforge folder.\n');
  process.exit(1);
}

console.log(`  …  starting a test copy on port ${port}`);
const child = spawn(process.execPath, ['--no-warnings', serverPath], {
  env: { ...process.env, PORT: String(port), HOST: '127.0.0.1', THINKFORGE_DB: dbFile },
  stdio: ['ignore', 'pipe', 'pipe'],
});

let out = '';
let err = '';
child.stdout.on('data', (c) => { out += c.toString(); });
child.stderr.on('data', (c) => { err += c.toString(); });

const started = await new Promise((resolve) => {
  const timer = setTimeout(() => resolve('timeout'), 20000);
  const check = () => { if (out.includes('is running')) { clearTimeout(timer); resolve('ok'); } };
  child.stdout.on('data', check);
  child.on('exit', (code) => { clearTimeout(timer); resolve(`exited:${code}`); });
});

const cleanup = () => {
  child.kill();
  for (const suffix of ['', '-wal', '-shm']) fs.rmSync(dbFile + suffix, { force: true });
};

if (started !== 'ok') {
  console.log('  ✗  The server did not start.\n');
  if (started.startsWith('exited')) {
    console.log('     It exited immediately. That is the bug fixed in version 1.0.4 —');
    console.log('     if this folder says an older version above, use the newer download.\n');
  } else {
    console.log('     It did not report itself within 20 seconds.\n');
  }
  if (out.trim()) console.log(`     Output:\n${out.trim().split('\n').map((l) => `       ${l}`).join('\n')}\n`);
  if (err.trim()) console.log(`     Errors:\n${err.trim().split('\n').map((l) => `       ${l}`).join('\n')}\n`);
  cleanup();
  process.exit(1);
}

let reachable = false;
let reason = '';
for (const target of [`http://127.0.0.1:${port}/api/status`, `http://localhost:${port}/api/status`]) {
  try {
    const res = await fetch(target, { signal: AbortSignal.timeout(5000) });
    if (res.ok) { reachable = true; console.log(`  ✓  answered on ${target.replace('/api/status', '')}`); }
  } catch (e) { reason = e.message; }
}

cleanup();

if (!reachable) {
  console.log('  ✗  It started but nothing could connect to it.');
  console.log(`     ${reason}`);
  console.log('     Something on this machine is blocking local connections —');
  console.log('     usually antivirus or a firewall rule. Allow Node.js, or try another port.\n');
  process.exit(1);
}

console.log('\n  Everything works. Start it for real with:\n');
console.log('    npm start\n');
console.log('  then open  http://localhost:4173  in your browser,');
console.log('  and leave the terminal window open while you use it.\n');
