import { test, expect } from '@playwright/test';

// Unit tests run the app's exported pure core inside the page.
test.beforeEach(async ({ page }) => {
  await page.goto('/index.html?test=1');
  await page.waitForFunction(() => !!window.__gyro);
});

test('angleDelta wraps across the 0/360 seam in both directions', async ({ page }) => {
  const r = await page.evaluate(() => {
    const { angleDelta } = window.__gyro.core;
    return {
      seamUp: angleDelta(359, 1),
      seamDown: angleDelta(1, 359),
      plain: angleDelta(10, 40),
      half: angleDelta(0, 180),
      negHalf: angleDelta(180, 0),
      zero: angleDelta(90, 90),
    };
  });
  expect(r.seamUp).toBeCloseTo(2, 6);
  expect(r.seamDown).toBeCloseTo(-2, 6);
  expect(r.plain).toBeCloseTo(30, 6);
  expect(r.half).toBeCloseTo(180, 6);
  expect(r.negHalf).toBeCloseTo(180, 6); // 180 is the canonical representative
  expect(r.zero).toBe(0);
});

test('headingFromOrientation tracks yaw for an upright phone', async ({ page }) => {
  const r = await page.evaluate(() => {
    const { headingFromOrientation } = window.__gyro.core;
    const at = (a) => headingFromOrientation(a, 90, 0);
    return {
      a0: at(0).heading, a90: at(90).heading, a180: at(180).heading, a270: at(270).heading,
      src: at(0).source,
      tilted: headingFromOrientation(45, 75, 6).heading,
      flatSource: headingFromOrientation(30, 0, 0).source,
      flatHeading: headingFromOrientation(30, 0, 0).heading,
    };
  });
  // alpha increases counter-clockwise, compass heading decreases.
  expect(r.a0).toBeCloseTo(0, 4);
  expect(r.a90).toBeCloseTo(270, 4);
  expect(r.a180).toBeCloseTo(180, 4);
  expect(r.a270).toBeCloseTo(90, 4);
  expect(r.src).toBe('back');
  // Slightly tilted phone still yields ~ the same yaw (within a couple of degrees).
  expect(Math.abs(((r.tilted - 315 + 540) % 360) - 180)).toBeLessThan(8);
  // Flat phone: camera axis is vertical, so it falls back to the top edge.
  expect(r.flatSource).toBe('top');
  expect(r.flatHeading).toBeCloseTo(330, 4);
});

test('RotationTracker accumulates unwrapped rotation and rejects glitches', async ({ page }) => {
  const r = await page.evaluate(() => {
    const { RotationTracker } = window.__gyro.core;
    const out = {};

    // Clockwise past the seam: 350 -> 10 is +20, not -340.
    let t = new RotationTracker(), now = 0;
    for (const h of [350, 355, 0, 5, 10]) { t.update(h, now, 'back'); now += 100; }
    out.cw = t.total;

    // Counter-clockwise past the seam.
    t = new RotationTracker(); now = 0;
    for (const h of [10, 5, 0, 355, 350]) { t.update(h, now, 'back'); now += 100; }
    out.ccw = t.total;

    // Three full clockwise turns.
    t = new RotationTracker(); now = 0;
    for (let i = 0; i <= 1080; i += 5) { t.update(((i % 360) + 360) % 360, now, 'back'); now += 16; }
    out.threeTurns = t.total;

    // Source switch must re-anchor, not add a fake 180 deg jump.
    t = new RotationTracker(); now = 0;
    t.update(10, now, 'back'); now += 100;
    t.update(20, now, 'back'); now += 100;
    t.update(200, now, 'top'); now += 100;
    t.update(210, now, 'top');
    out.switched = t.total;

    // Impossible spike (>1500 deg/s) is ignored.
    t = new RotationTracker(); now = 0;
    t.update(0, now, 'back'); now += 5;
    t.update(170, now, 'back'); now += 100;
    t.update(175, now, 'back');
    out.glitch = t.total;

    // Speed estimate: 60 deg/s steady.
    t = new RotationTracker(); now = 0;
    for (let i = 0; i < 40; i++) { t.update((i * 1) % 360, now, 'back'); now += 1000 / 60; }
    out.speed = t.speed;
    return out;
  });
  expect(r.cw).toBeCloseTo(20, 6);
  expect(r.ccw).toBeCloseTo(-20, 6);
  expect(r.threeTurns).toBeCloseTo(1080, 4);
  expect(r.switched).toBeCloseTo(20, 6);
  expect(r.glitch).toBeCloseTo(5, 6);
  expect(r.speed).toBeGreaterThan(55);
  expect(r.speed).toBeLessThan(65);
});

test('ShotPlan fires exactly N evenly spaced shots, clockwise or counter-clockwise', async ({ page }) => {
  const r = await page.evaluate(() => {
    const { ShotPlan } = window.__gyro.core;
    const run = (count, sign, stepDeg) => {
      const plan = new ShotPlan(count, 0);
      const fired = [];
      for (let a = 0; a <= 360; a += stepDeg) {
        for (const i of plan.update(sign * a)) fired.push({ i, a: sign * a });
      }
      return { fired, done: plan.done, dir: plan.direction, next: plan.next };
    };
    return {
      cw24: run(24, 1, 0.5),
      ccw24: run(24, -1, 0.5),
      cw12: run(12, 1, 1),
      cw72: run(72, 1, 0.25),
    };
  });
  for (const [key, count] of [['cw24', 24], ['ccw24', 24], ['cw12', 12], ['cw72', 72]]) {
    const run = r[key];
    expect(run.fired.length, key).toBe(count);
    expect(run.done, key).toBe(true);
    expect(run.fired.map((f) => f.i), key).toEqual([...Array(count).keys()]);
    // Every trigger lands within one sampling step of its ideal angle.
    const step = 360 / count;
    for (const f of run.fired) {
      expect(Math.abs(Math.abs(f.a) - f.i * step), key + ' idx ' + f.i).toBeLessThanOrEqual(1.01);
    }
  }
  expect(r.ccw24.dir).toBe(-1);
  expect(r.cw24.dir).toBe(1);
});

test('ShotPlan ignores wobble and never double-fires a taken shot', async ({ page }) => {
  const r = await page.evaluate(() => {
    const { ShotPlan } = window.__gyro.core;
    const plan = new ShotPlan(24, 0);
    const fired = [];
    // Rotate to 20 deg, wobble back and forth over the 15 deg marker many times.
    const path = [0, 5, 10, 16, 12, 16, 11, 17, 9, 20, 14, 20, 30, 25, 31, 45.2, 40];
    for (const a of path) for (const i of plan.update(a)) fired.push(i);
    return { fired, next: plan.next, maxProgress: plan.maxProgress };
  });
  expect(r.fired).toEqual([0, 1, 2, 3]); // 0, 15, 30, 45 — each exactly once
  expect(r.maxProgress).toBeCloseTo(45.2, 5);
});

test('ShotPlan.remaining counts down to the next marker', async ({ page }) => {
  const r = await page.evaluate(() => {
    const { ShotPlan } = window.__gyro.core;
    const plan = new ShotPlan(24, 0);
    plan.update(0);
    const a = plan.remaining(0);
    plan.update(7);
    const b = plan.remaining(7);
    plan.update(15);
    const c = plan.remaining(15);
    return { a, b, c, next: plan.next };
  });
  expect(r.a).toBeCloseTo(15, 5);
  expect(r.b).toBeCloseTo(8, 5);
  expect(r.c).toBeCloseTo(15, 5); // now counting toward the 30 deg marker
  expect(r.next).toBe(2);
});

test('nearestIndex and maxGapError report set quality', async ({ page }) => {
  const r = await page.evaluate(() => {
    const { nearestIndex, maxGapError } = window.__gyro.core;
    const perfect = [...Array(24).keys()].map((i) => i * 15);
    const sloppy = perfect.slice();
    sloppy[5] = 79; // 4 deg late
    return {
      n0: nearestIndex(0, 24, 1),
      n1: nearestIndex(14.6, 24, 1),
      n2: nearestIndex(-30, 24, -1),
      wrap: nearestIndex(361, 24, 1),
      perfect: maxGapError(perfect, 24),
      sloppy: maxGapError(sloppy, 24),
      single: maxGapError([0], 24),
    };
  });
  expect(r.n0).toBe(0);
  expect(r.n1).toBe(1);
  expect(r.n2).toBe(2);
  expect(r.wrap).toBe(0);
  expect(r.perfect).toBeCloseTo(0, 6);
  expect(r.sloppy).toBeCloseTo(4, 6);
  expect(r.single).toBe(0);
});

test('crc32 matches the reference vector and makeZip writes a valid archive header', async ({ page }) => {
  const r = await page.evaluate(() => {
    const { crc32, makeZip } = window.__gyro.core;
    const enc = new TextEncoder();
    const zip = makeZip([{ name: 'a.txt', data: enc.encode('hello') }], new Date(2024, 0, 2, 3, 4, 5));
    return zip.arrayBuffer().then((buf) => {
      const u = new Uint8Array(buf);
      return {
        crc: crc32(enc.encode('123456789')) >>> 0,
        empty: crc32(new Uint8Array(0)) >>> 0,
        size: u.length,
        localSig: [u[0], u[1], u[2], u[3]],
        type: zip.type,
      };
    });
  });
  expect(r.crc).toBe(0xcbf43926);
  expect(r.empty).toBe(0);
  expect(r.localSig).toEqual([0x50, 0x4b, 0x03, 0x04]);
  expect(r.type).toBe('application/zip');
  expect(r.size).toBe(30 + 5 + 5 + 46 + 5 + 22);
});
