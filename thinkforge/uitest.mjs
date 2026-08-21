import { chromium } from 'playwright-core';
const BASE = 'http://localhost:4200';
const errors = [];
const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium', args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push('PAGEERROR ' + e.message));

await page.goto(BASE, { waitUntil: 'networkidle' });
await page.screenshot({ path: '/tmp/shots/1-start.png', fullPage: true });

await page.fill('#nm', 'Ada');
await page.fill('#age', '11');
await page.fill('#guardian', 'Ms Rowe');
await page.check('#consent');
await page.click('button.primary');
await page.waitForSelector('h1');
await page.waitForTimeout(600);
console.log('after create:', await page.textContent('h1'));
await page.screenshot({ path: '/tmp/shots/2-home.png', fullPage: true });

await page.click('text=Start today’s session →');
await page.waitForTimeout(700);
await page.screenshot({ path: '/tmp/shots/3-session.png', fullPage: true });

// open the first mission
await page.click('.card button >> nth=0');
await page.waitForTimeout(700);
await page.screenshot({ path: '/tmp/shots/4-mission.png', fullPage: true });
console.log('mission:', await page.textContent('h1'));

// fill whatever inputs exist
const areas = await page.$$('textarea');
const filler = [
  'More time for football club after school\nI would sleep more on Sunday nights\nFamily evenings would be calmer',
  'I would forget the topic before the test\nTeachers would not see who is stuck\nSome subjects only stick with practice',
  'I wonder whether lessons would get longer to make up for it\nI wonder if the after-school clubs would suddenly fill up',
];
for (let i = 0; i < areas.length; i += 1) await areas[i].fill(filler[i % filler.length]);
const radios = await page.$$('.choice');
if (!areas.length && radios.length) await radios[0].click();
await page.screenshot({ path: '/tmp/shots/5-filled.png', fullPage: true });

await page.click('button:has-text("Submit")');
await page.waitForTimeout(1800);
await page.screenshot({ path: '/tmp/shots/6-feedback.png', fullPage: true });
console.log('feedback visible:', await page.isVisible('text=Against the rubric'));

await page.goto(BASE + '#growth', { waitUntil: 'networkidle' });
await page.waitForTimeout(700);
await page.click('button:has-text("Save this week")');
await page.waitForTimeout(1200);
await page.screenshot({ path: '/tmp/shots/7-growth.png', fullPage: true });

await page.goto(BASE + '#teacher', { waitUntil: 'networkidle' });
await page.waitForTimeout(700);
await page.screenshot({ path: '/tmp/shots/8-teacher.png', fullPage: true });

await page.goto(BASE + '#moves', { waitUntil: 'networkidle' });
await page.waitForTimeout(500);
await page.screenshot({ path: '/tmp/shots/9-moves.png', fullPage: true });

console.log('CONSOLE ERRORS:', errors.length ? errors : 'none');
await browser.close();
