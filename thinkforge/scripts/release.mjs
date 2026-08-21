#!/usr/bin/env node
/**
 * Build a self-contained release that runs on a machine with only Node
 * installed: no build step, no npm install, no network.
 *
 *   node scripts/release.mjs
 *
 * Produces dist/thinkforge-<version>.{tar.gz,zip} plus SHA256SUMS.txt.
 * The Anthropic SDK is bundled so AI mode works offline too; it is the only
 * dependency and it is optional at runtime.
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));
const name = `thinkforge-${pkg.version}`;
const dist = path.join(root, 'dist');
const stage = path.join(dist, name);

/** Everything a running install needs, and nothing else. */
const INCLUDE_DIRS = ['server', 'client', 'docs', 'scripts'];
const INCLUDE_FILES = ['README-FIRST.txt', 'README.md', 'INSTALL.md', 'CHANGELOG.md', 'LICENSE', '.env.example', 'start.sh', 'start.cmd'];
const RUNTIME_DEPS = ['@anthropic-ai', 'json-schema-to-ts', 'ts-algebra', '@babel'];
const EXCLUDE_FROM_SCRIPTS = ['release.mjs', 'ui-smoke.mjs'];

fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(stage, { recursive: true });

const copyDir = (from, to, filter = () => true) => {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const src = path.join(from, entry.name);
    const dest = path.join(to, entry.name);
    if (!filter(src, entry)) continue;
    if (entry.isDirectory()) copyDir(src, dest, filter);
    else fs.copyFileSync(src, dest);
  }
};

for (const dir of INCLUDE_DIRS) {
  const from = path.join(root, dir);
  if (!fs.existsSync(from)) continue;
  copyDir(from, path.join(stage, dir), (src, entry) => !(dir === 'scripts' && EXCLUDE_FROM_SCRIPTS.includes(entry.name)));
}
for (const file of INCLUDE_FILES) {
  const from = path.join(root, file);
  if (fs.existsSync(from)) fs.copyFileSync(from, path.join(stage, file));
}

/* Bundle the optional SDK so a machine with no network still gets AI mode. */
let bundledSdk = false;
for (const dep of RUNTIME_DEPS) {
  const from = path.join(root, 'node_modules', dep);
  if (!fs.existsSync(from)) continue;
  copyDir(from, path.join(stage, 'node_modules', dep), (src) => !/[\\/](\.git|test|tests|__tests__|\.github)$/.test(src));
  if (dep === '@anthropic-ai') bundledSdk = true;
}

/* A release package.json: no dev tooling, no private flag, real start script. */
const releasePkg = {
  name: pkg.name,
  version: pkg.version,
  description: pkg.description,
  type: 'module',
  license: pkg.license || 'MIT',
  engines: pkg.engines,
  scripts: {
    start: 'node --no-warnings server/index.mjs',
    doctor: 'node --no-warnings scripts/doctor.mjs',
    seed: 'node --no-warnings scripts/seed.mjs',
  },
  optionalDependencies: pkg.optionalDependencies,
};
fs.writeFileSync(path.join(stage, 'package.json'), `${JSON.stringify(releasePkg, null, 2)}\n`);

fs.writeFileSync(path.join(stage, 'VERSION'), `${pkg.version}\n`);
// Stamp the version into the first thing a Windows user opens.
const firstRead = path.join(stage, 'README-FIRST.txt');
if (fs.existsSync(firstRead)) {
  fs.writeFileSync(firstRead, fs.readFileSync(firstRead, 'utf8').replace(/^THINKFORGE\n=+/, `THINKFORGE ${pkg.version}\n${'='.repeat(11 + pkg.version.length)}`));
}
fs.mkdirSync(path.join(stage, 'data'), { recursive: true });
fs.writeFileSync(path.join(stage, 'data', '.gitkeep'), '');
fs.chmodSync(path.join(stage, 'start.sh'), 0o755);

/* Archives. tar for macOS/Linux, zip for Windows. */
const archives = [];
execFileSync('tar', ['-czf', path.join(dist, `${name}.tar.gz`), '-C', dist, name], { stdio: 'inherit' });
archives.push(`${name}.tar.gz`);
try {
  execFileSync('zip', ['-qr', path.join(dist, `${name}.zip`), name], { cwd: dist, stdio: 'inherit' });
  archives.push(`${name}.zip`);
} catch {
  console.warn('zip not available — skipping the .zip archive');
}

const sums = archives.map((file) => {
  const hash = createHash('sha256').update(fs.readFileSync(path.join(dist, file))).digest('hex');
  return `${hash}  ${file}`;
}).join('\n');
fs.writeFileSync(path.join(dist, 'SHA256SUMS.txt'), `${sums}\n`);

const size = (file) => `${(fs.statSync(path.join(dist, file)).size / 1048576).toFixed(1)} MB`;
console.log(`\nThinkforge ${pkg.version}`);
console.log(`  staged:   dist/${name}/`);
for (const file of archives) console.log(`  archive:  dist/${file}  (${size(file)})`);
console.log(`  checksums: dist/SHA256SUMS.txt`);
console.log(`  AI SDK bundled: ${bundledSdk ? 'yes — works with no npm install' : 'no (run npm install for AI mode)'}\n`);
