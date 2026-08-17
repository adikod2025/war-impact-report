# QA report — Gyro Spinner

Automated suite: **28 tests, all passing**, plus a 3× repeat run (78 executions) to check for
flakiness. Engine: Chromium 1194 via Playwright, iPhone-sized viewports, fake camera device,
synthetic orientation samples fed through the app's real sensor entry point.

Run it:

```bash
cd gyro-spinner
npm i -D @playwright/test && npx playwright install chromium
npx playwright test          # starts the static server itself
```

`server.mjs` serves this folder on :8787; `playwright.config.mjs` launches Chromium with a
fake camera device. Set `CHROMIUM_PATH` to use a pre-installed browser binary.

## What is covered

**Rotation maths (unit, 8 tests)**

- Shortest-angle delta across the 0/360° seam, both directions.
- Yaw extraction from `alpha`/`beta`/`gamma` for an upright phone, a tilted phone, and a flat
  phone (which falls back to the top-edge axis).
- Unwrapped accumulation: three full turns read as 1080°, not 0°; source switches re-anchor
  instead of injecting a fake 180° jump; >1500°/s spikes are discarded; the speed estimate
  tracks a steady 60°/s.
- Shot planning: exactly N triggers for 12/24/36/72, clockwise and anti-clockwise, each within
  one sampling step of its ideal angle; wobbling repeatedly over a marker fires it once;
  countdown-to-next-marker.
- CRC-32 against the standard `123456789` → `0xCBF43926` vector; zip byte layout and signature.

**End-to-end (20 tests)**

- Setup screen defaults, every control wired, one selection per segment.
- iOS motion permission **denied** → actionable recovery message, stays on setup, retryable.
- Camera unavailable → named error, no dead end.
- Full clockwise 360° in Auto → 24 frames, each within 2° of its 15° marker, results screen,
  24 thumbnails, max-gap-error < 3°, camera track ends, frames verified as decodable
  1920×1080 JPEGs (magic bytes + `createImageBitmap`).
- Anti-clockwise 360° → same result, direction detected as −1.
- Zip download → filename pattern, saved to disk, **validated externally with `unzip -t`**:
  12 files, no errors, all 1920×1080 baseline JPEGs.
- Spinning too fast → speed chip alerts, blur banner shows, and no frames are dropped.
- Tilting off vertical → level warning, clears when upright again.
- Dial rendering verified at pixel level: the progress arc trails the pointer on the correct
  side for both spin directions.
- Manual mode: one frame per shutter tap. Guide mode: `getUserMedia` never called, no images
  stored, zip button hidden.
- Lead-in countdown blocks arming until it finishes.
- Cancel stops the camera track and discards frames; Finish early keeps the frames taken;
  a second set starts from a clean state.
- "No motion data" warning when the device sends nothing.
- Layout at 375×667, 393×852 and 430×932: no horizontal overflow, HUD chips and buttons fully
  inside the viewport, dial fits on screen.
- Zero console errors and zero uncaught exceptions across every flow.

## Bugs found and fixed during QA

1. **Guide mode never fired cue points.** The capture evaluator returned early for any
   non-auto mode, so guide sessions could never complete. Now auto and guide both pace
   themselves; only manual waits for taps.
2. **Manual mode could mis-count.** Its bookkeeping could advance the plan by several indices
   while taking a single frame, ending the set early with fewer frames than requested.
3. **Progress arc swept the wrong way.** The markers are drawn world-fixed, so the arc has to
   trail *behind* the pointer, and mirror for an anti-clockwise spin. Both fixed and now
   covered by a pixel-level test.
4. **Dial unreadable over bright scenes.** Added a dark radial scrim and drop shadows behind
   the ring and readout.
5. Cosmetic: a stat label wrapped to two lines; the results screen now also reports the saved
   frame size so the wider-than-preview crop is not a surprise.

## Limits of this harness — what a phone still has to confirm

The proxy in this environment blocks the WebKit browser download, so tests ran on Chromium.
Chromium executes every code path in the app, but it is not iOS Safari. These specific things
are written to spec and reviewed by hand, and are worth a 30-second sanity check on your
phone:

- The two iOS permission prompts. The **denied** path is tested with a stubbed
  `DeviceOrientationEvent.requestPermission`; the granted path is tested the same way. The
  real prompt text and the "must come from a user gesture" rule are Safari behaviour.
- Real gyroscope data. Tests inject synthetic samples through the same entry point the sensor
  uses, so the maths is exercised, but actual iPhone drift and sample rate are not.
- Rear-camera selection and the portrait-oriented video track (the fake device gives 1920×1080
  landscape; a real iPhone in portrait typically gives a portrait track, so the preview will
  match the saved frame more closely than in the screenshots).
- WebAudio beeps and the wake lock — both are guarded in try/catch and degrade silently.
- `a[download]` for the zip: supported on iOS 13+, lands in Files → Downloads.
