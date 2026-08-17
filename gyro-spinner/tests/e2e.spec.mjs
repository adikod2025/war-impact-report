import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Screenshots and the downloaded zip land here for manual inspection.
const OUT = process.env.QA_ARTIFACTS || path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'test-artifacts');
fs.mkdirSync(OUT, { recursive: true });

/** Collect console errors + page errors for every test. */
function watchErrors(page) {
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  return errors;
}

/** Simulate iOS 13+ where sensors need an explicit permission grant. */
async function stubIOSPermission(page, result = 'granted') {
  await page.addInitScript((res) => {
    window.__perm = { orientation: 0, motion: 0 };
    window.DeviceOrientationEvent.requestPermission = () => { window.__perm.orientation++; return Promise.resolve(res); };
    window.DeviceMotionEvent.requestPermission = () => { window.__perm.motion++; return Promise.resolve(res); };
  }, result);
}

/** Feed a smooth, physically plausible spin through the app's sensor entry point. */
async function spin(page, { degrees = 360, stepDeg = 1.5, intervalMs = 25, sign = 1 } = {}) {
  await page.evaluate(async (o) => {
    // Absolute attitude accumulates across calls: consecutive spins stay continuous,
    // exactly as a real phone behaves.
    if (typeof window.__spun !== 'number') window.__spun = 0;
    const steps = Math.round(o.degrees / o.stepDeg);
    for (let i = 0; i < steps; i++) {
      window.__spun += o.sign * o.stepDeg;
      // alpha runs counter-clockwise, so a clockwise spin decreases alpha.
      const alpha = ((-window.__spun % 360) + 360) % 360;
      window.__gyro.feed(alpha, 90, 0);
      await new Promise((r) => setTimeout(r, o.intervalMs));
    }
  }, { degrees, stepDeg, intervalMs, sign });
}

/** Hold the phone still at a fixed attitude so the speed estimate settles. */
async function hold(page, { beta = 90, gamma = 0, samples = 20, intervalMs = 30 } = {}) {
  await page.evaluate(async (o) => {
    const alpha = ((-(window.__spun || 0) % 360) + 360) % 360;
    for (let i = 0; i < o.samples; i++) {
      window.__gyro.feed(alpha, o.beta, o.gamma);  // attitude held constant -> speed decays to ~0
      await new Promise((r) => setTimeout(r, o.intervalMs));
    }
  }, { beta, gamma, samples, intervalMs });
}

async function setMode(page, mode) {
  await page.click(`#modeSeg .opt[data-mode="${mode}"]`);
}
/** Self-spin is the default, so tests that are not about the drive pin hand-spin. */
async function setDrive(page, drive) {
  await page.click(`#driveSeg .opt[data-drive="${drive}"]`);
  expect(await page.evaluate(() => window.__gyro.settings.drive)).toBe(drive);
}
async function setCount(page, count) {
  await page.click(`#countSeg .opt[data-count="${count}"]`);
}
async function disableLeadIn(page) {
  await page.click('#optLead');
  expect(await page.evaluate(() => window.__gyro.settings.lead)).toBe(false);
}

test.describe('setup screen', () => {
  test('renders defaults and wires every control', async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto('/index.html');
    await page.waitForFunction(() => !!window.__gyro);

    await expect(page.locator('#setup h1')).toHaveText('Gyro Spinner');
    await expect(page.locator('#setup')).toHaveClass(/active/);
    await expect(page.locator('#countSeg .opt[data-count="24"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#modeSeg .opt[data-mode="auto"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#driveSeg .opt[data-drive="self"]')).toHaveAttribute('aria-pressed', 'true');

    await setCount(page, 36);
    await setMode(page, 'manual');
    await expect(page.locator('#modeHint')).toContainText('you tap');
    await setDrive(page, 'hand');
    await expect(page.locator('#driveHint')).toContainText('You turn the phone');
    await page.click('#optSound');
    await page.click('#optLock');
    await page.click('#optHaptics');
    expect(await page.evaluate(() => ({ ...window.__gyro.settings })))
      .toEqual({ count: 36, mode: 'manual', drive: 'hand', sound: false, lead: true, lock: false, wake: true, haptics: false });

    await setCount(page, 72);
    await setMode(page, 'guide');
    expect(await page.evaluate(() => window.__gyro.settings.count)).toBe(72);
    expect(await page.evaluate(() => window.__gyro.settings.mode)).toBe('guide');
    // Only one option per segment stays selected.
    expect(await page.locator('#countSeg .opt[aria-pressed="true"]').count()).toBe(1);
    expect(errors).toEqual([]);
  });

  test('shows a recovery hint when iOS denies motion access', async ({ page }) => {
    const errors = watchErrors(page);
    await stubIOSPermission(page, 'denied');
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await page.click('#startBtn');

    await expect(page.locator('#setupError')).toBeVisible();
    await expect(page.locator('#setupError')).toContainText('Motion & Orientation Access');
    await expect(page.locator('#setup')).toHaveClass(/active/);
    await expect(page.locator('#live')).not.toHaveClass(/active/);
    // Button recovers so the user can retry.
    await expect(page.locator('#startBtn')).toBeEnabled();
    await expect(page.locator('#startBtn')).toHaveText('Allow sensors & start');
    expect(errors).toEqual([]);
  });

  test('surfaces a clear error when the camera is unavailable', async ({ page }) => {
    const errors = watchErrors(page);
    await page.addInitScript(() => {
      navigator.mediaDevices.getUserMedia = () => Promise.reject(Object.assign(new Error('nope'), { name: 'NotAllowedError' }));
    });
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await page.click('#startBtn');
    await expect(page.locator('#setupError')).toContainText('Camera access was denied');
    await expect(page.locator('#setup')).toHaveClass(/active/);
    expect(errors).toEqual([]);
  });
});

test.describe('auto capture', () => {
  test('a full clockwise spin captures 24 evenly spaced frames and lands on results', async ({ page }) => {
    const errors = watchErrors(page);
    await stubIOSPermission(page, 'granted');
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await disableLeadIn(page);
    await page.click('#startBtn');

    await expect(page.locator('#live')).toHaveClass(/active/);
    expect(await page.evaluate(() => window.__perm.orientation)).toBe(1);
    expect(await page.evaluate(() => window.__perm.motion)).toBe(1);
    // Camera is live; stash the track so we can prove it gets stopped.
    await page.waitForFunction(() => window.__gyro.state.stream && window.__gyro.state.stream.getVideoTracks().length);
    await page.evaluate(() => { window.__track = window.__gyro.state.stream.getVideoTracks()[0]; });
    await page.waitForFunction(() => document.getElementById('video').videoWidth > 0);

    const first = await page.evaluate(() => window.__gyro.snapshot());
    expect(first.armed).toBe(true);
    expect(first.shots).toBe(1);          // the origin frame fires on arming

    await spin(page, { degrees: 360 });

    await expect(page.locator('#results')).toHaveClass(/active/, { timeout: 15000 });
    const snap = await page.evaluate(() => window.__gyro.snapshot());
    expect(snap.shots).toBe(24);
    expect(snap.withImages).toBe(24);
    expect(snap.done).toBe(true);
    expect(snap.direction).toBe(1);

    // Every frame sits within a sample step of its ideal 15 deg marker.
    snap.angles.forEach((a, i) => {
      const signed = ((a - i * 15 + 540) % 360) - 180;   // circular error, -180..180
      expect(Math.abs(signed), `frame ${i} recorded at ${a}°`).toBeLessThanOrEqual(2);
    });

    await expect(page.locator('#grid .thumb')).toHaveCount(24);
    await expect(page.locator('#grid .thumb img')).toHaveCount(24);
    await expect(page.locator('#statShots')).toHaveText('24');
    await expect(page.locator('#resTitle')).toHaveText('360° set complete');
    await expect(page.locator('#resSub')).toHaveText('24 frames at 15° steps · 1920×1080.');
    expect(Number(await page.locator('#statEven').textContent().then((t) => parseFloat(t)))).toBeLessThan(3);

    // Camera released.
    expect(await page.evaluate(() => window.__track.readyState)).toBe('ended');
    expect(await page.evaluate(() => window.__gyro.state.stream)).toBeNull();

    // Frames are real, decodable JPEGs at the sensor's resolution.
    const info = await page.evaluate(async () => {
      const s = window.__gyro.state.shots[3];
      const head = new Uint8Array(await s.blob.slice(0, 3).arrayBuffer());
      const bmp = await createImageBitmap(s.blob);
      return { type: s.blob.type, size: s.blob.size, head: [...head], w: bmp.width, h: bmp.height };
    });
    expect(info.type).toBe('image/jpeg');
    expect(info.head).toEqual([0xff, 0xd8, 0xff]);
    expect(info.size).toBeGreaterThan(2000);
    expect(info.w).toBeGreaterThanOrEqual(640);
    expect(info.h).toBeGreaterThanOrEqual(480);

    await page.screenshot({ path: path.join(OUT, 'results-24.png') });
    expect(errors).toEqual([]);
  });

  test('a counter-clockwise spin works identically', async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await setCount(page, 12);
    await disableLeadIn(page);
    await page.click('#startBtn');
    await expect(page.locator('#live')).toHaveClass(/active/);
    await page.waitForFunction(() => document.getElementById('video').videoWidth > 0);

    await spin(page, { degrees: 360, sign: -1, stepDeg: 2, intervalMs: 22 });

    await expect(page.locator('#results')).toHaveClass(/active/, { timeout: 15000 });
    const snap = await page.evaluate(() => window.__gyro.snapshot());
    expect(snap.shots).toBe(12);
    expect(snap.withImages).toBe(12);
    expect(snap.direction).toBe(-1);
    expect(snap.angles).toEqual([0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330].map((v, i) => snap.angles[i]));
    snap.angles.forEach((a, i) => expect(Math.abs(a - i * 30)).toBeLessThanOrEqual(2));
    expect(errors).toEqual([]);
  });

  test('the .zip download is a valid archive of every frame', async ({ page }, testInfo) => {
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await setCount(page, 12);
    await disableLeadIn(page);
    await page.click('#startBtn');
    await page.waitForFunction(() => document.getElementById('video').videoWidth > 0);
    await spin(page, { degrees: 360, stepDeg: 2, intervalMs: 20 });
    await expect(page.locator('#results')).toHaveClass(/active/, { timeout: 15000 });

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.click('#zipBtn'),
    ]);
    expect(download.suggestedFilename()).toMatch(/^gyro360-\d{8}-\d{4}\.zip$/);
    const dest = path.join(OUT, 'set.zip');
    await download.saveAs(dest);
    const stat = fs.statSync(dest);
    expect(stat.size).toBeGreaterThan(10_000);
    await expect(page.locator('#zipBtn')).toHaveText(/Saved to Files/);
    testInfo.attach('zip', { path: dest });
  });

  test('rotating too fast raises a warning without dropping frames', async ({ page }) => {
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await setCount(page, 12);
    await disableLeadIn(page);
    await page.click('#startBtn');
    await page.waitForFunction(() => document.getElementById('video').videoWidth > 0);

    // ~150 deg/s — well past the blur threshold.
    await spin(page, { degrees: 120, stepDeg: 3, intervalMs: 20 });
    const mid = await page.evaluate(() => window.__gyro.snapshot());
    expect(mid.speed).toBeGreaterThan(80);
    await expect(page.locator('#hudSpeedChip')).toHaveClass(/alert/);
    await expect(page.locator('#banner')).toHaveText('Slow down — frames will blur');

    await spin(page, { degrees: 240, stepDeg: 1, intervalMs: 25 });
    await expect(page.locator('#results')).toHaveClass(/active/, { timeout: 15000 });
    const snap = await page.evaluate(() => window.__gyro.snapshot());
    expect(snap.shots).toBe(12);
  });

  test('tilting the phone off vertical raises the level warning', async ({ page }) => {
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await disableLeadIn(page);
    await page.click('#startBtn');
    await expect(page.locator('#live')).toHaveClass(/active/);
    await hold(page, { beta: 60, gamma: 22 });
    await expect(page.locator('#hudLevelChip')).toHaveClass(/alert/);
    await expect(page.locator('#hudLevel')).toHaveText('Tilt');
    await expect(page.locator('#banner')).toHaveText('Hold the phone upright');
    await hold(page, { beta: 90, gamma: 1 });
    await expect(page.locator('#hudLevel')).toHaveText('OK');
    await expect(page.locator('#banner')).toBeHidden();
  });
});

test.describe('dial rendering', () => {
  /** Centroid of accent-green pixels in the dial's upper half (excludes the level bubble). */
  const arcSide = (page) => page.evaluate(() => {
    const cv = document.getElementById('dial');
    const d = cv.getContext('2d').getImageData(0, 0, cv.width, cv.height).data;
    let sx = 0, n = 0;
    for (let y = 0; y < cv.height / 2; y += 2) {
      for (let x = 0; x < cv.width; x += 2) {
        const i = (y * cv.width + x) * 4;
        if (d[i] < 90 && d[i + 1] > 170 && d[i + 2] > 110 && d[i + 2] < 210 && d[i + 3] > 120) { sx += x; n++; }
      }
    }
    return { n, cx: n ? sx / n : null, mid: cv.width / 2 };
  });

  for (const [label, sign] of [['clockwise', 1], ['counter-clockwise', -1]]) {
    test(`the progress arc trails the pointer on a ${label} spin`, async ({ page }) => {
      await page.goto('/index.html');
    await setDrive(page, 'hand');
      await setMode(page, 'guide');
      await disableLeadIn(page);
      await page.click('#startBtn');
      await expect(page.locator('#live')).toHaveClass(/active/);
      await spin(page, { degrees: 90, stepDeg: 1.5, intervalMs: 20, sign });
      await page.waitForTimeout(120);

      const side = await arcSide(page);
      expect(side.n, 'accent pixels found on the dial').toBeGreaterThan(200);
      // Shots already taken trail behind the pointer: left for CW, right for CCW.
      if (sign === 1) expect(side.cx).toBeLessThan(side.mid);
      else expect(side.cx).toBeGreaterThan(side.mid);
      await page.screenshot({ path: path.join(OUT, `dial-${label}.png`) });
    });
  }
});

test.describe('manual and guide modes', () => {
  test('manual mode captures one frame per shutter tap', async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await setCount(page, 12);
    await setMode(page, 'manual');
    await disableLeadIn(page);
    await page.click('#startBtn');
    await expect(page.locator('#live')).toHaveClass(/active/);
    await expect(page.locator('#shutter')).toBeVisible();
    await page.waitForFunction(() => document.getElementById('video').videoWidth > 0);

    expect((await page.evaluate(() => window.__gyro.snapshot())).shots).toBe(1); // origin frame
    for (let i = 1; i < 12; i++) {
      await spin(page, { degrees: 30, stepDeg: 5, intervalMs: 12 });
      await page.click('#shutter');
    }
    await expect(page.locator('#results')).toHaveClass(/active/, { timeout: 15000 });
    const snap = await page.evaluate(() => window.__gyro.snapshot());
    expect(snap.shots).toBe(12);
    expect(snap.withImages).toBe(12);
    await expect(page.locator('#grid .thumb')).toHaveCount(12);
    expect(errors).toEqual([]);
  });

  test('guide mode never opens the camera and stores no images', async ({ page }) => {
    const errors = watchErrors(page);
    await page.addInitScript(() => {
      window.__gumCalls = 0;
      const real = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
      navigator.mediaDevices.getUserMedia = (c) => { window.__gumCalls++; return real(c); };
    });
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await setCount(page, 12);
    await setMode(page, 'guide');
    await disableLeadIn(page);
    await page.click('#startBtn');

    await expect(page.locator('#live')).toHaveClass(/active/);
    await expect(page.locator('#video')).toBeHidden();
    await expect(page.locator('#guidebg')).toBeVisible();
    await expect(page.locator('#shutter')).toBeHidden();
    expect(await page.evaluate(() => window.__gumCalls)).toBe(0);

    await spin(page, { degrees: 360, stepDeg: 2, intervalMs: 18 });
    await expect(page.locator('#results')).toHaveClass(/active/, { timeout: 15000 });
    const snap = await page.evaluate(() => window.__gyro.snapshot());
    expect(snap.shots).toBe(12);
    expect(snap.withImages).toBe(0);
    await expect(page.locator('#resSub')).toContainText('no images stored');
    await expect(page.locator('#zipBtn')).toBeHidden();
    expect(await page.evaluate(() => window.__gumCalls)).toBe(0);
    expect(errors).toEqual([]);
  });
});

test.describe('session control', () => {
  test('the lead-in countdown runs before arming', async ({ page }) => {
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await setMode(page, 'guide');
    await page.click('#startBtn');
    await expect(page.locator('#countdown')).toBeVisible();
    await expect(page.locator('#countdown')).toHaveText('3');
    expect(await page.evaluate(() => window.__gyro.state.armed)).toBe(false);
    await expect(page.locator('#countdown')).toHaveText('1', { timeout: 4000 });
    await expect(page.locator('#countdown')).toBeHidden({ timeout: 3000 });
    expect(await page.evaluate(() => window.__gyro.state.armed)).toBe(true);
  });

  test('cancel stops the camera and returns to setup', async ({ page }) => {
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await disableLeadIn(page);
    await page.click('#startBtn');
    await page.waitForFunction(() => window.__gyro.state.stream);
    await page.evaluate(() => { window.__track = window.__gyro.state.stream.getVideoTracks()[0]; });
    await spin(page, { degrees: 40, stepDeg: 5, intervalMs: 10 });
    await page.click('#abortBtn');
    await expect(page.locator('#setup')).toHaveClass(/active/);
    expect(await page.evaluate(() => window.__track.readyState)).toBe('ended');
    expect(await page.evaluate(() => window.__gyro.state.shots.length)).toBe(0);
    expect(await page.evaluate(() => window.__gyro.state.running)).toBe(false);
  });

  test('finish early keeps the frames already taken', async ({ page }) => {
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await disableLeadIn(page);
    await page.click('#startBtn');
    await page.waitForFunction(() => document.getElementById('video').videoWidth > 0);
    await spin(page, { degrees: 62, stepDeg: 2, intervalMs: 15 });
    await page.click('#finishBtn');
    await expect(page.locator('#results')).toHaveClass(/active/);
    await expect(page.locator('#resTitle')).toHaveText('Set stopped early');
    const snap = await page.evaluate(() => window.__gyro.snapshot());
    expect(snap.shots).toBe(5);            // 0, 15, 30, 45, 60
    expect(snap.withImages).toBe(5);
    await expect(page.locator('#grid .thumb')).toHaveCount(5);
  });

  test('shooting a second set starts clean', async ({ page }) => {
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await setCount(page, 12);
    await disableLeadIn(page);
    await page.click('#startBtn');
    await page.waitForFunction(() => document.getElementById('video').videoWidth > 0);
    await spin(page, { degrees: 360, stepDeg: 2, intervalMs: 16 });
    await expect(page.locator('#results')).toHaveClass(/active/, { timeout: 15000 });

    await page.click('#againBtn');
    await expect(page.locator('#live')).toHaveClass(/active/);
    const snap = await page.evaluate(() => window.__gyro.snapshot());
    expect(snap.shots).toBe(1);
    expect(snap.total).toBeCloseTo(0, 1);
    await spin(page, { degrees: 360, stepDeg: 2, intervalMs: 16 });
    await expect(page.locator('#results')).toHaveClass(/active/, { timeout: 15000 });
    expect((await page.evaluate(() => window.__gyro.snapshot())).shots).toBe(12);
    await expect(page.locator('#grid .thumb')).toHaveCount(12);
  });

  test('warns when the device sends no motion data at all', async ({ page }) => {
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await setMode(page, 'guide');
    await disableLeadIn(page);
    await page.click('#startBtn');
    await expect(page.locator('#banner')).toContainText('No motion data', { timeout: 6000 });
  });
});

test.describe('layout', () => {
  const sizes = [
    { name: 'iphone-se', width: 375, height: 667 },
    { name: 'iphone-15-pro', width: 393, height: 852 },
    { name: 'iphone-15-pro-max', width: 430, height: 932 },
  ];
  for (const s of sizes) {
    test(`no horizontal overflow and readable HUD at ${s.name}`, async ({ page }) => {
      await page.setViewportSize({ width: s.width, height: s.height });
      await page.goto('/index.html');
    await setDrive(page, 'hand');
      const setupOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(setupOverflow).toBeLessThanOrEqual(0);
      await page.screenshot({ path: path.join(OUT, `setup-${s.name}.png`), fullPage: true });

      await disableLeadIn(page);
      await page.click('#startBtn');
      await expect(page.locator('#live')).toHaveClass(/active/);
      await page.waitForFunction(() => document.getElementById('video').videoWidth > 0);
      await spin(page, { degrees: 100, stepDeg: 4, intervalMs: 12 });

      const liveOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(liveOverflow).toBeLessThanOrEqual(0);

      // HUD chips must sit inside the viewport, not clipped.
      const boxes = await page.evaluate(() =>
        [...document.querySelectorAll('.hud.top .chip, .hud.bottom .mini, #shutter')].map((el) => {
          const r = el.getBoundingClientRect();
          return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
        }));
      for (const b of boxes) {
        expect(b.left).toBeGreaterThanOrEqual(-0.5);
        expect(b.right).toBeLessThanOrEqual(s.width + 0.5);
        expect(b.bottom).toBeLessThanOrEqual(s.height + 0.5);
      }
      // The dial fits on screen.
      const dial = await page.locator('#dial').boundingBox();
      expect(dial.width).toBeLessThanOrEqual(s.width);
      expect(dial.height).toBeLessThanOrEqual(s.height);
      await page.screenshot({ path: path.join(OUT, `live-${s.name}.png`) });
    });
  }
});

/* ---------------------------------------------------------------------------
 * Self-spin. The app's drive output is fed into a simulated phone-on-a-surface,
 * whose rotation is fed back through the real sensor entry point — so the whole
 * loop (waveform -> amplitude -> movement -> gyro -> shutter) is under test.
 * ------------------------------------------------------------------------ */

const PLANT = {
  k: 90,             // deg/s^2 of drive at full amplitude, at the best setting
  peak: 220,         // the surface's resonant carrier, in Hz
  width: 80,         // how sharp that resonance is
  strokePeak: 8,     // the body's rocking resonance, in Hz
  strokeWidth: 6,
  friction: 35,      // deg/s^2 of kinetic drag once it is moving
  stick: 20,         // drive needed to break static friction
  reverseGain: 0.3,  // the wrong stroke polarity barely moves it
  // Antiphase drivers make a couple; pushing together mostly just slides it.
  modeGain: { torque: 1, mono: 0.35, alternate: 0.6 },
};

async function installPlant(page, cfg = PLANT) {
  await page.addInitScript((c) => {
    window.__plantCfg = c;
    window.__plant = { theta: 0, w: 0, running: false, captures: [], loudCaptures: 0, maxAmp: 0 };
    window.__startPlant = () => {
      const p = window.__plant;
      if (p.running) return;
      p.running = true;
      let prevShots = 0;
      (async () => {
        const dt = 0.02;
        while (p.running) {
          const d = window.__gyro.driveState();
          if (d.amp > p.maxAmp) p.maxAmp = d.amp;
          const resonance = Math.exp(-Math.pow((d.carrier - c.peak) / c.width, 2));
          const rocking = Math.exp(-Math.pow((d.stroke - c.strokePeak) / c.strokeWidth, 2));
          const polarity = d.duty < 0.5 ? 1 : c.reverseGain;
          const pairing = c.modeGain[d.mode] == null ? 1 : c.modeGain[d.mode];
          const push = c.k * d.amp * resonance * rocking * polarity * pairing;
          let acc = push;
          if (p.w > 0.5) acc -= c.friction;              // sliding
          else if (push < c.stick) { acc = 0; p.w = 0; } // stuck
          p.w = Math.max(0, p.w + acc * dt);
          p.theta += p.w * dt;
          window.__gyro.feed(((-p.theta % 360) + 360) % 360, 90, 0);
          const shots = window.__gyro.state.shots.length;
          if (shots > prevShots) {
            p.captures.push({ amp: d.amp, w: p.w, theta: p.theta });
            if (d.amp > 0.08) p.loudCaptures++;
            prevShots = shots;
          }
          await new Promise((r) => setTimeout(r, 20));
        }
      })();
    };
    window.__stopPlant = () => { window.__plant.running = false; };
  }, cfg);
}

test.describe('self-spin drive', () => {
  test('the speaker actually emits the drive waveform, and stops on cancel', async ({ page }) => {
    const errors = watchErrors(page);
    await page.goto('/index.html');
    await setMode(page, 'guide');
    await disableLeadIn(page);
    await page.click('#startBtn');

    // Tuning starts immediately and runs the drive at full power.
    await expect(page.locator('#tuner')).toBeVisible();
    await expect(page.locator('#driveHud')).toBeVisible();
    await page.waitForTimeout(400);
    const live = await page.evaluate(() => window.__gyro.driveState());
    expect(live.running).toBe(true);
    expect(live.ctx).toBe('running');
    expect(live.amp).toBeGreaterThan(0.5);
    expect(live.rms, 'audio actually reaching the output').toBeGreaterThan(0.05);
    expect(live.carrier % live.stroke).toBe(0);      // whole cycles: no loop click

    await page.click('#tuneSkip');
    await expect(page.locator('#tuner')).toBeHidden({ timeout: 20000 });

    await page.click('#abortBtn');
    await expect(page.locator('#setup')).toHaveClass(/active/);
    await page.waitForTimeout(300);
    const dead = await page.evaluate(() => window.__gyro.driveState());
    expect(dead.running).toBe(false);
    expect(dead.amp).toBe(0);
    expect(dead.rms).toBeLessThan(0.01);            // silence, not a stuck tone
    expect(errors).toEqual([]);
  });

  test('tuning finds the surface resonance and the working stroke polarity', async ({ page }) => {
    test.setTimeout(120000);
    await installPlant(page);
    await page.goto('/index.html');
    await setMode(page, 'guide');
    await disableLeadIn(page);
    await page.click('#startBtn');
    await expect(page.locator('#tuner')).toBeVisible();
    await page.evaluate(() => window.__startPlant());

    await expect(page.locator('#tuner')).toBeHidden({ timeout: 60000 });
    const st = await page.evaluate(() => window.__gyro.driveState());
    // Coordinate descent: 7 carriers + 5 stroke rates + 3 pairings + 2 polarities.
    expect(st.results.length).toBe(17);
    expect(st.results.filter((r) => r.stage === 'carrier').length).toBe(7);
    expect(st.results.filter((r) => r.stage === 'stroke').length).toBe(5);
    expect(st.results.filter((r) => r.stage === 'mode').length).toBe(3);

    // Every axis must land on the plant's actual preference, not just any
    // setting that made noise.
    expect(Math.abs(st.carrier - PLANT.peak), `tuned to ${st.carrier}Hz`).toBeLessThan(45);
    expect(Math.abs(st.stroke - PLANT.strokePeak), `stroke ${st.stroke}Hz`).toBeLessThanOrEqual(4);
    expect(st.mode, 'antiphase gives the most rotation in this plant').toBe('torque');
    expect(st.duty).toBeLessThan(0.5);
    expect(st.tuneBest).toBeGreaterThan(1);

    // The losing options scored clearly worse — the sweep measures, it does not guess.
    const bestOf = (stage, pick) => st.results.filter((r) => r.stage === stage && pick(r.value))
      .reduce((a, b) => (b.score > a.score ? b : a));
    expect(bestOf('duty', (v) => v < 0.5).score).toBeGreaterThan(bestOf('duty', (v) => v > 0.5).score * 1.5);
    expect(bestOf('mode', (v) => v === 'torque').score).toBeGreaterThan(bestOf('mode', (v) => v === 'mono').score * 1.5);
    await page.evaluate(() => window.__stopPlant());
  });

  test('the phone spins itself through a full turn, shooting only while quiet', async ({ page }) => {
    test.setTimeout(240000);
    const errors = watchErrors(page);
    await installPlant(page);
    await page.goto('/index.html');
    await setCount(page, 12);
    await disableLeadIn(page);
    await page.click('#startBtn');
    await expect(page.locator('#tuner')).toBeVisible();
    await page.evaluate(() => window.__startPlant());
    await expect(page.locator('#tuner')).toBeHidden({ timeout: 60000 });

    await expect(page.locator('#results')).toHaveClass(/active/, { timeout: 160000 });
    await page.evaluate(() => window.__stopPlant());

    const snap = await page.evaluate(() => window.__gyro.snapshot());
    const plant = await page.evaluate(() => ({ ...window.__plant, captures: window.__plant.captures }));

    expect(snap.shots).toBe(12);
    expect(snap.withImages).toBe(12);
    expect(snap.done).toBe(true);
    // The phone was moved by the drive alone — nothing else touched it.
    expect(plant.theta).toBeGreaterThan(300);
    expect(plant.maxAmp).toBeGreaterThan(0.5);
    // Not one frame was taken while the speaker was pushing.
    expect(plant.loudCaptures, 'frames captured mid-buzz').toBe(0);
    for (const c of plant.captures) expect(c.amp).toBeLessThanOrEqual(0.08);
    await expect(page.locator('#grid .thumb')).toHaveCount(12);
    expect(errors).toEqual([]);
  });

  test('a surface it cannot slide on is reported instead of spinning forever', async ({ page }) => {
    test.setTimeout(120000);
    // Static friction far above anything the speaker can produce: a rubber mat.
    await installPlant(page, { ...PLANT, stick: 500, k: 10 });
    await page.goto('/index.html');
    await setCount(page, 12);
    await setMode(page, 'guide');
    await disableLeadIn(page);
    await page.click('#startBtn');
    await expect(page.locator('#tuner')).toBeVisible();
    await page.evaluate(() => window.__startPlant());
    await expect(page.locator('#tuner')).toBeHidden({ timeout: 60000 });

    // Tuning measured nothing, and the controller gives up rather than buzzing on.
    await expect(page.locator('#banner')).toContainText('surface', { timeout: 30000 });
    const st = await page.evaluate(() => window.__gyro.driveState());
    expect(st.results.every((r) => r.score < 0.5)).toBe(true);
    const plant = await page.evaluate(() => window.__plant);
    expect(plant.theta).toBeLessThan(1);
    await page.evaluate(() => window.__stopPlant());
  });

  test('hand spin never starts the drive', async ({ page }) => {
    await page.goto('/index.html');
    await setDrive(page, 'hand');
    await setMode(page, 'guide');
    await disableLeadIn(page);
    await page.click('#startBtn');
    await expect(page.locator('#live')).toHaveClass(/active/);
    await expect(page.locator('#tuner')).toBeHidden();
    await expect(page.locator('#driveHud')).toBeHidden();
    const st = await page.evaluate(() => window.__gyro.driveState());
    expect(st.running).toBe(false);
    expect(st.amp).toBe(0);
    expect(st.controller).toBeNull();
    await spin(page, { degrees: 90, stepDeg: 3, intervalMs: 15 });
    expect((await page.evaluate(() => window.__gyro.driveState())).amp).toBe(0);
  });
});

test.describe('self-spin layout', () => {
  for (const s of [{ name: 'iphone-se', width: 375, height: 667 }, { name: 'iphone-15-pro', width: 393, height: 852 }]) {
    test(`tuner and drive HUD fit at ${s.name}`, async ({ page }) => {
      await page.setViewportSize({ width: s.width, height: s.height });
      await installPlant(page);
      await page.goto('/index.html');
      await disableLeadIn(page);
      await page.click('#startBtn');
      await expect(page.locator('#tuner')).toBeVisible();
      await page.evaluate(() => window.__startPlant());
      await page.waitForTimeout(2500);
      await page.screenshot({ path: path.join(OUT, `tuner-${s.name}.png`) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);

      await page.click('#tuneSkip');
      await expect(page.locator('#tuner')).toBeHidden({ timeout: 20000 });
      await expect(page.locator('#driveHud')).toBeVisible();
      await page.waitForTimeout(1200);
      await page.screenshot({ path: path.join(OUT, `drive-live-${s.name}.png`) });

      // Both HUD rows stay inside the viewport and do not collide with the dial.
      const boxes = await page.evaluate(() =>
        [...document.querySelectorAll('.hud.top .chip, .hud.top2 .chip')].map((el) => {
          const r = el.getBoundingClientRect();
          return { left: r.left, right: r.right, bottom: r.bottom };
        }));
      expect(boxes.length).toBe(7);
      for (const b of boxes) {
        expect(b.left).toBeGreaterThanOrEqual(-0.5);
        expect(b.right).toBeLessThanOrEqual(s.width + 0.5);
      }
      const dial = await page.locator('#dial').boundingBox();
      const lowestChip = Math.max(...boxes.map((b) => b.bottom));
      expect(lowestChip, 'HUD must not overlap the dial').toBeLessThan(dial.y + 8);
      await page.evaluate(() => window.__stopPlant());
    });
  }
});

test.describe('drive lab', () => {
  test('manual controls drive the speaker and read the gyro back', async ({ page }) => {
    const errors = watchErrors(page);
    await installPlant(page);
    await page.goto('/index.html');
    await page.click('#labBtn');
    await expect(page.locator('#lab')).toHaveClass(/active/);
    await page.evaluate(() => window.__startPlant());

    // Sliders write straight through to the running drive.
    await page.locator('#labCarrier').fill('380');
    await page.locator('#labStroke').fill('18');
    await expect(page.locator('#labCarrierV')).toHaveText('380 Hz');
    await expect(page.locator('#labStrokeV')).toHaveText('18 Hz');

    await page.click('#labRun');
    await expect(page.locator('#labRun')).toHaveText('Stop drive');
    await page.waitForTimeout(600);
    let st = await page.evaluate(() => window.__gyro.driveState());
    expect(st.running).toBe(true);
    expect(st.amp).toBeGreaterThan(0.9);
    expect(st.rms).toBeGreaterThan(0.05);
    expect(st.stroke).toBe(18);
    expect(Math.abs(st.carrier - 380)).toBeLessThanOrEqual(18);

    // Speaker pairing is switchable live.
    await page.click('#labModeSeg .opt[data-mode="mono"]');
    expect((await page.evaluate(() => window.__gyro.driveState())).mode).toBe('mono');

    // Power slider is honoured.
    await page.locator('#labAmp').fill('40');
    await page.waitForTimeout(200);
    expect((await page.evaluate(() => window.__gyro.driveState())).amp).toBeCloseTo(0.4, 1);

    // 380 Hz / 18 Hz stroke / mono is far off this plant's resonance, so it has
    // not moved yet — which is itself the honest reading.
    await expect(page.locator('#labPeak')).toHaveText('0.0');

    // Dial in what this plant actually responds to and it starts turning.
    await page.click('#labModeSeg .opt[data-mode="torque"]');
    await page.locator('#labCarrier').fill('220');
    await page.locator('#labStroke').fill('8');
    await page.locator('#labAmp').fill('100');
    await expect(page.locator('#labPeak')).not.toHaveText('0.0', { timeout: 10000 });
    await expect(page.locator('#labNow')).not.toHaveText('0.0');

    await page.click('#labRun');
    await expect(page.locator('#labRun')).toHaveText('Start drive');
    await page.waitForTimeout(200);
    expect((await page.evaluate(() => window.__gyro.driveState())).amp).toBe(0);

    await page.evaluate(() => window.__stopPlant());
    await page.click('#labBack');
    await expect(page.locator('#setup')).toHaveClass(/active/);
    expect(errors).toEqual([]);
  });

  test('sweep reports the winning setting when the phone can move', async ({ page }) => {
    test.setTimeout(180000);
    await installPlant(page);
    await page.goto('/index.html');
    await page.click('#labBtn');
    await page.evaluate(() => window.__startPlant());
    await page.click('#labSweep');
    await expect(page.locator('#labVerdict')).toBeVisible({ timeout: 120000 });
    await expect(page.locator('#labVerdict')).toHaveClass(/good/);
    await expect(page.locator('#labVerdict')).toContainText('It moves.');
    await expect(page.locator('#labVerdict')).toContainText('°/s');
    await page.screenshot({ path: path.join(OUT, 'lab-verdict-good.png'), fullPage: true });
    // Ranked table, best first, and the controls now show the winner.
    const rows = await page.locator('#labResults .lrow').count();
    expect(rows).toBe(6);
    await expect(page.locator('#labResults .lrow').first()).toHaveClass(/top/);
    expect(Number(await page.locator('#labCarrierV').textContent().then((t) => parseInt(t, 10))))
      .toBeGreaterThan(150);
    const st = await page.evaluate(() => window.__gyro.driveState());
    expect(st.amp).toBe(0);                      // sweep leaves the drive quiet
    await page.evaluate(() => window.__stopPlant());
  });

  test('sweep gives a straight answer when nothing can move the phone', async ({ page }) => {
    test.setTimeout(180000);
    await installPlant(page, { ...PLANT, stick: 500, k: 10 });
    await page.goto('/index.html');
    await page.click('#labBtn');
    await page.evaluate(() => window.__startPlant());
    await page.click('#labSweep');
    await expect(page.locator('#labVerdict')).toBeVisible({ timeout: 120000 });
    await expect(page.locator('#labVerdict')).toHaveClass(/bad/);
    await expect(page.locator('#labVerdict')).toContainText('Nothing shifted it');
    // It says what would actually help, rather than telling them to try again.
    await expect(page.locator('#labVerdict')).toContainText('turntable');
    await expect(page.locator('#labVerdict')).toContainText('Hand spin');
    await page.screenshot({ path: path.join(OUT, 'lab-verdict-bad.png'), fullPage: true });
    const plant = await page.evaluate(() => window.__plant);
    expect(plant.theta).toBeLessThan(1);
    await page.evaluate(() => window.__stopPlant());
  });
});
