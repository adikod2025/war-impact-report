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

    await setCount(page, 36);
    await setMode(page, 'manual');
    await expect(page.locator('#modeHint')).toContainText('you tap');
    await page.click('#optSound');
    await page.click('#optLock');
    expect(await page.evaluate(() => ({ ...window.__gyro.settings })))
      .toEqual({ count: 36, mode: 'manual', sound: false, lead: true, lock: false, wake: true });

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
