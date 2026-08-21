/**
 * Starting the thing.
 *
 * These tests exist because of a real failure: on Windows the entry-point check
 * compared `file://${process.argv[1]}` with `import.meta.url`, which never match
 * there, so `node server/index.mjs` exited instantly and printed nothing. Every
 * other test passed, because they all import the module rather than run it.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const serverPath = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'server', 'index.mjs');

test('the entry-point check works for both platform path shapes', async () => {
  const { isEntryPoint } = await import('../server/index.mjs');
  assert.equal(isEntryPoint(serverPath, pathToFileURL(serverPath).href), true, 'run directly');
  assert.equal(isEntryPoint('/somewhere/else.mjs', pathToFileURL(serverPath).href), false, 'imported');
  assert.equal(isEntryPoint(undefined, pathToFileURL(serverPath).href), false, 'no argv[1]');

  // The comparison this replaced, against a Windows-shaped path: always false,
  // which is exactly how it shipped broken.
  const winPath = 'C:\\Users\\Someone\\server\\index.mjs';
  const winUrl = 'file:///C:/Users/Someone/server/index.mjs';
  assert.equal(winUrl === `file://${winPath}`, false, 'the old check could never match on Windows');
});

test('running the server as a command actually starts it and says where to go', async () => {
  const dbFile = path.join(os.tmpdir(), `thinkforge-launch-${process.pid}.db`);
  const port = 4400 + (process.pid % 300);
  const child = spawn(process.execPath, ['--no-warnings', serverPath], {
    env: { ...process.env, PORT: String(port), THINKFORGE_DB: dbFile, ANTHROPIC_API_KEY: '' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let out = '';
  const started = await new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), 20000);
    child.stdout.on('data', (chunk) => {
      out += chunk.toString();
      if (/Thinkforge \S+ is running/.test(out)) { clearTimeout(timer); resolve(true); }
    });
    child.on('exit', () => { clearTimeout(timer); resolve(false); });
  });

  try {
    assert.ok(started, `the server exited or stayed silent instead of starting. Output:\n${out}`);
    assert.match(out, /Thinkforge \d+\.\d+\.\d+ is running/, 'the banner must name the version, so it is clear which build a window is running');
    assert.match(out, /http:\/\/localhost:\d+/, 'it must print the URL to open');
    assert.match(out, /Ctrl\+C/, 'it must say how to stop it');

    const res = await fetch(`http://127.0.0.1:${port}/api/status`);
    assert.equal(res.status, 200, 'it must actually answer on the port it printed');
  } finally {
    child.kill();
    for (const suffix of ['', '-wal', '-shm']) fs.rmSync(dbFile + suffix, { force: true });
  }
});
