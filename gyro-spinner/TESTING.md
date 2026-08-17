# QA report — Gyro Spinner

Automated suite: **45 tests, all passing**, plus repeat runs to check for flakiness. Engine:
Chromium 1194 via Playwright, iPhone-sized viewports, fake camera device, synthetic
orientation samples fed through the app's real sensor entry point, and — for the self-spin
drive — a simulated phone-on-a-surface driven by the app's own audio output.

Run it:

```bash
cd gyro-spinner
npm i -D @playwright/test && npx playwright install chromium
npx playwright test          # starts the static server itself
```

`server.mjs` serves this folder on :8787; `playwright.config.mjs` launches Chromium with a
fake camera device. Set `CHROMIUM_PATH` to use a pre-installed browser binary.

## What is covered

**Vibration drive (unit, 7 tests)**

- `channelWaves`: the two drivers are exactly anti-correlated in torque mode (correlation
  −1.000), identical in mono (+1.000), and largely decorrelated in alternate — with equal
  energy per driver and negligible DC in all three.
- Squaring the carrier off raises RMS by more than 20% while peak excursion stays at 1.0,
  which is the whole point: a speaker is peak-limited, not power-limited.
- `strokeWave`: peak-normalised, finite, no DC offset a speaker could not reproduce. The
  physical claim is asserted directly — the two halves of the stroke carry **equal momentum**
  (areas within 10% of each other) but peak forces in a 1 : 0.25 ratio, which is what breaks
  static friction in one direction only. Flipping duty past 0.5 mirrors the stroke.
- Loop buffer: exactly one stroke period long, carrier snapped to whole cycles per period so
  the loop point cannot click, endpoints near zero.
- `SpinController`: full-power breakaway kick from rest, proportional-integral cruise, zero
  power when over target, cut to coast inside the stopping distance, coast → settle → drive
  with a fresh kick, amplitude always within bounds.
- Stall detection fires after sustained full power with no rotation, and never fires while
  the phone is turning.

**Vibration drive and drive lab (end-to-end, 10 tests)**

These feed the app's real drive output into a plant model — resonant response curve, kinetic
friction, a static-friction threshold, and a much weaker response to the wrong stroke
polarity — and feed the resulting rotation back through the sensor entry point. The whole
loop is under test: waveform → amplitude → movement → gyro → shutter.

- The speaker genuinely emits the waveform: audio context running, measured output RMS > 0.05
  at the analyser while driving, carrier an exact multiple of the stroke rate, and true
  silence (RMS < 0.01) after cancel.
- Tuning is a 17-measurement coordinate descent, and it lands on the plant's true preference
  on **every axis**: carrier within 45 Hz of its 220 Hz resonance, stroke rate within 4 Hz of
  its 8 Hz rocking peak, antiphase pairing, and the working stroke polarity. The losing
  polarity and the losing pairing each score at least 1.5× worse — the sweep measures rather
  than guesses.
- Drive lab: sliders and pairing buttons write through to the running drive live; the gyro
  readout tracks and holds a peak; stopping the drive returns amplitude to zero. A sweep on a
  movable plant produces the "It moves" verdict with a ranked table and dials the winner into
  the controls; a sweep on an immovable one produces the "Nothing shifted it" verdict, which
  is asserted to name the mechanical fixes rather than telling the user to try again.
- **Full self-spin run**: the simulated phone is walked past 300° by the drive alone, all 12
  frames captured, and — the claim that matters — **not one frame taken while the drive was
  pushing**; every capture is asserted to have happened at amplitude ≤ 0.08.
- A surface it cannot slide on (static friction far above anything the speaker can produce):
  every tuning candidate scores ~0, the phone does not move a degree, and the app reports the
  surface instead of buzzing indefinitely.
- Hand spin never starts the drive: no audio, no controller, amplitude stays 0.
- Tuner overlay and the second HUD row fit at 375 and 393 px without overflow or overlapping
  the dial.

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
6. **The resonance tuner scored the wrong tone.** Candidates ran back to back, so a tone that
   got the phone moving left it coasting into the next candidate's measurement window — the
   sweep systematically credited whichever tone followed a good one. It picked 276 Hz on a
   plant whose true resonance was 220 Hz. Each candidate now waits for the phone to come to
   rest and scores only the speed it *added* over the baseline. Caught by the closed-loop
   test, not by inspection.
7. **The controller lost a tick re-arming.** Coming out of settle it set the state to drive
   but left the amplitude at zero until the next tick, delaying the breakaway shove by 50 ms
   in a loop whose entire job is precise timing.

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

**And the big one — the physics is simulated, not measured.** The plant model is a reasonable
stick-slip approximation, and it proves the control logic, the tuner and the shutter gating
are correct *given* a phone that responds to the drive at all. It cannot tell you how much
force your iPhone's speaker actually produces on your table. That number decides whether the
thing crawls round in ninety seconds or sits there buzzing, and only your phone on your
surface can answer it. Expect to try a couple of surfaces; a bearing turntable is the
reliable answer if a bare tabletop will not go.

Specifically untestable here: the iOS 17.4+ switch-control Taptic tick (no WebKit engine
available), and whether iOS throttles a sustained full-amplitude Web Audio loop in the
background — the app holds a wake lock and only drives while the live screen is up.
