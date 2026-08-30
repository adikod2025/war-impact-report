#!/usr/bin/env node
/**
 * Browser smoke test: walks a learner through onboarding, a session, a mission,
 * feedback, the coach, the growth page and the teacher view, and fails on any
 * console error. Needs a running server and playwright-core:
 *
 *   npm start &
 *   npm i -D playwright-core && node scripts/ui-smoke.mjs
 */
import { chromium } from 'playwright-core';

const BASE = process.env.BASE || 'http://localhost:4173';
const SHOTS = process.env.SHOTS || null;   // set a directory to save screenshots
const EXE = process.env.CHROMIUM || '/opt/pw-browsers/chromium';
const errors = [];
const shot = async (page, name) => (SHOTS ? page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true }) : null);

const browser = await chromium.launch({ executablePath: EXE, args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push(`PAGEERROR ${e.message}`));

await page.goto(BASE, { waitUntil: 'networkidle' });
await shot(page, '1-start');

await page.fill('#nm', 'Smoke');
await page.fill('#age', '11');
await page.check('#consent');
await page.click('button.primary');
await page.waitForSelector('h1');
await page.waitForTimeout(500);
if (!(await page.textContent('h1')).includes('Smoke')) throw new Error('onboarding did not land on the learner home');
await shot(page, '2-home');

await page.click('text=Start today’s session →');
await page.waitForTimeout(600);
await shot(page, '3-session');

await page.click('.card button >> nth=0');
await page.waitForTimeout(600);
await shot(page, '4-mission');

const areas = await page.$$('textarea');
const filler = [
  'More time for football club after school\nI would sleep more on Sunday nights\nFamily evenings would be calmer',
  'I would forget the topic before the test\nTeachers would not see who is stuck\nSome subjects only stick with practice',
  'I wonder whether lessons would get longer to make up for it\nI wonder if the clubs would suddenly fill up',
];
for (let i = 0; i < areas.length; i += 1) await areas[i].fill(filler[i % filler.length]);
if (!areas.length) { const choices = await page.$$('.choice'); if (choices.length) await choices[0].click(); }

await page.click('button:has-text("Submit")');
await page.waitForSelector('text=Where else this works', { timeout: 20000 })
  .catch(() => { throw new Error('no feedback panel after submitting'); });
await shot(page, '5-feedback');

// the game layer: the HUD must be live, and the Forge must render every panel
await page.waitForSelector('#hud .chip', { timeout: 5000 }).catch(() => { throw new Error('the HUD did not appear'); });
for (const [hash, marker] of [
  ['#forge', 'Boss commissions'],
  ['#forge', 'Your tools'],
  ['#forge', 'Trophies'],
  ['#growth', 'The six growth indices'],
  ['#teacher', 'Where the class is'],
  ['#moves', 'The moves'],
  ['#about', 'How Thinkforge works'],
]) {
  await page.goto(BASE + '/' + hash, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  await page.waitForSelector(`text=${marker}`, { timeout: 15000 })
    .catch(() => { throw new Error(`${hash} did not render`); });
  await shot(page, hash.slice(1));
}

// a forge-off against a seeded classmate
await page.goto(`${BASE}/#duel/lat-t1-pmi-nohomework`, { waitUntil: 'networkidle' });
await page.waitForTimeout(700);
if (await page.isVisible('text=No opponent yet')) {
  console.log('forge-off: no seeded opponent for that commission (expected on an empty database)');
} else {
  const duelFields = await page.$$('textarea');
  await duelFields[0].fill('They gave three genuinely different pluses rather than the same idea three times, and the minus about tests is a real cost.');
  await duelFields[1].fill('There is no interesting entry that is neither good nor bad — everything is already judged, so the move was not really run.');
  await page.click('button:has-text("Submit critique")');
  await page.waitForSelector('text=Both of you earned', { timeout: 20000 })
    .catch(() => { throw new Error('the forge-off did not resolve'); });
  await shot(page, 'duel');
}

await browser.close();
if (errors.length) { console.error('console errors:\n' + errors.join('\n')); process.exit(1); }
console.log('UI smoke test passed with no console errors.');
