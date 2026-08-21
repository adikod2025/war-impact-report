#!/usr/bin/env node
/**
 * One step: set up if needed, start the server, wait until it really answers,
 * then open the browser at the right address.
 *
 *   node scripts/run.mjs
 *
 * Written because every failure so far has been a step between "I have the
 * files" and "I am looking at the app" — a wrong folder, a pasted URL, a
 * closed window. This removes all of them.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
process.chdir(root);

const port = Number(process.env.PORT || 4173);
const url = `http://localhost:${port}`;

/** Chrome if we can find it, otherwise whatever the system uses. */
function openBrowser(target) {
  const chromeCandidates = process.platform === 'win32'
    ? [
      `${process.env['PROGRAMFILES']}\\Google\\Chrome\\Application\\chrome.exe`,
      `${process.env['PROGRAMFILES(X86)']}\\Google\\Chrome\\Application\\chrome.exe`,
      `${process.env.LOCALAPPDATA}\\Google\\Chrome\\Application\\chrome.exe`,
    ]
    : process.platform === 'darwin'
      ? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
      : ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'];

  // spawn() reports a missing program with an async 'error' event, not a
  // throw — without a handler that crashes the whole launcher.
  const tryLaunch = (cmd, args) => {
    try {
      const child = spawn(cmd, args, { detached: true, stdio: 'ignore' });
      child.on('error', () => {});
      child.unref();
      return true;
    } catch {
      return false;
    }
  };

  for (const exe of chromeCandidates) {
    if (exe && fs.existsSync(exe) && tryLaunch(exe, [target])) return 'Chrome';
  }
  const fallback = process.platform === 'win32'
    ? ['cmd', ['/c', 'start', '""', target]]
    : process.platform === 'darwin'
      ? ['open', [target]]
      : ['xdg-open', [target]];
  return tryLaunch(fallback[0], fallback[1]) ? 'your default browser' : null;
}

async function reachable() {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/api/status`, { signal: AbortSignal.timeout(2000) });
    return res.ok;
  } catch {
    return false;
  }
}

if (await reachable()) {
  console.log(`\n  Thinkforge is already running. Opening ${url}\n`);
  openBrowser(url);
  process.exit(0);
}

const dbFile = process.env.THINKFORGE_DB || path.join(root, 'data', 'thinkforge.db');
if (!fs.existsSync(dbFile)) {
  console.log('\n  First run — adding a demo class so there is something to look at.');
  console.log('  (Delete data/thinkforge.db later to start empty.)\n');
  await new Promise((resolve) => {
    const seed = spawn(process.execPath, ['--no-warnings', path.join(root, 'scripts', 'seed.mjs')], { stdio: 'inherit' });
    seed.on('exit', resolve);
  });
}

const { start } = await import(path.join(root, 'server', 'index.mjs').replace(/\\/g, '/').replace(/^([A-Za-z]):/, 'file:///$1:'));
await start();

for (let i = 0; i < 40; i += 1) {
  if (await reachable()) break;
  await new Promise((r) => setTimeout(r, 250));
}

const opened = openBrowser(url);
console.log(opened
  ? `  Opening ${url} in ${opened}.\n`
  : `  Could not open a browser automatically — go to ${url} yourself.\n`);
console.log('  Keep this window open while you use Thinkforge. Ctrl+C stops it.\n');
