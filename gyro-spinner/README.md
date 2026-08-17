# Gyro Spinner — 360° capture for iPhone

A single self-contained HTML page. The phone **spins itself** by driving its own speaker
and haptics, with the gyroscope closing the loop: drive, coast, stop, shoot, repeat, until
it has walked a full 360° and captured an evenly spaced set.

No build step, no dependencies, no install. One file: `index.html`.

## Read this first — what the self-spin can and cannot do

A phone has no motor and no wheels. The only way it can move itself is to throw its own mass
around: the reaction force of the speaker cone, plus the haptic engine where the OS exposes
it. That force is small — enough to slide a phone across glass, nowhere near enough to shift
one on carpet.

So the honest limits:

- **It needs a low-friction surface.** Glass, a polished table, a laminate worktop — or,
  best of all, a lazy-susan or a bearing turntable, where you are only fighting the bearing.
  On carpet, rubber, a soft mat or a grippy case it will not move at all, and the app will
  tell you so rather than buzzing away pointlessly.
- **Volume at maximum, silent switch off, case off.** iOS mutes Web Audio when the ringer
  switch is on, and the drive is the audio.
- **It is loud.** The drive is an audible buzz at full volume for the length of the shoot.
- **iOS Safari has no vibration API.** `navigator.vibrate` does nothing on iPhone. The
  speaker does the real work; the app also fires the one haptic iOS 17.4+ exposes to the web
  (the switch-control Taptic tick), which adds a little.
- **Rotation is not fast.** Expect tens of degrees per second at best, so a 24-frame set
  takes a minute or two. That is fine — it stops for every frame anyway.

If the surface is wrong, switch **Spin drive** to **Hand spin** and turn it yourself; the
shutter still fires at every angle.

## Open it on your iPhone

The page needs **HTTPS** — iOS only exposes the motion sensors and the camera on a secure
origin. Pick whichever is easiest:

1. **Fastest — open the hosted file directly.** In Safari on the iPhone, go to:

   `https://raw.githack.com/adikod2025/war-impact-report/claude/iphone-gyro-spinner-360-1svyds/gyro-spinner/index.html`

   Then **Share → Add to Home Screen** so it launches full-screen like an app.

2. **GitHub Pages** (nicer URL). Repo → Settings → Pages → Source: this branch, folder `/`.
   The page is then at `https://adikod2025.github.io/war-impact-report/gyro-spinner/`.

3. **Own machine.** Serve the folder over HTTPS on your LAN (e.g. `npx serve` behind
   `ngrok`/`cloudflared`) and open that URL. Plain `http://` on a LAN IP will *not* work —
   iOS blocks sensors and camera there.

> Use **Safari**. Chrome and Firefox on iOS cannot open the camera from a web page.

## First run

Tap **Allow sensors & start**. iOS shows two prompts:

- *"…would like to access motion and orientation"* → **Allow**
- *"…would like to access the camera"* → **Allow**

If you dismissed either one, the page tells you exactly where to re-enable it. Motion access
lives in **Settings → Apps → Safari → Motion & Orientation Access**.

On the first run in Self-spin the app spends about fifteen seconds **tuning**: it sweeps a
range of carrier tones and both stroke polarities, watching the gyro to see which one
actually moves this phone on this surface. Leave it alone while the bar chart fills. You can
skip it, but tuned is dramatically better than untuned — the resonance shifts with every
surface.

## Spin drive

| Drive | What happens |
|---|---|
| **Self-spin** | The speaker walks the phone round; the gyro controls it. Needs a slippery surface. |
| **Hand spin** | You turn the phone or the turntable. No sound, no vibration. |

## Modes

| Mode | What happens |
|---|---|
| **Auto** | The shutter fires by itself each time the phone has rotated one step. |
| **Manual** | The dial counts down to the next angle; you tap the shutter. |
| **Guide** | No camera. The dial and beeps pace the spin while a separate camera shoots. |

Shots per 360°: **12** (30° steps), **24** (15°), **36** (10°), **72** (5°).
24 is the usual choice for photogrammetry and turntable sets; 36–72 for stitched panoramas.

## The live screen

- **Ring** — the dots are world-fixed angles. The next one sweeps toward the pointer at the
  top; the green arc trails behind, covering the shots already taken. It mirrors
  automatically if you spin anti-clockwise.
- **Centre number** — degrees still to travel before the next frame.
- **Speed** — turns amber past ~80°/s, where frames start to smear. Slow down.
- **Level** — the bubble at the bottom of the ring. Keep the phone upright; tilt between
  frames is the main cause of stitching failures.
- **Beep + white flash** on every capture, so you can look at the subject rather than the phone.

## Results

- Thumbnails of every frame with its index and measured angle.
- **Max gap** — the worst deviation from perfectly even spacing across the set. Under ~2° is a
  clean spin.
- **Download all as .zip** — lands in Files → Downloads. Or press-and-hold any thumbnail to
  save that frame straight to Photos.
- Frames are saved at the **full camera frame**, which is a little wider than the on-screen
  preview (the preview fills the screen; the file keeps every pixel the sensor gave).

## Getting good sets

- **Rotate around the lens, not around yourself.** Keep the phone at the same spot in space
  and pivot it; walking a circle changes the parallax between frames.
- For turntable-style capture, leave the phone on a tripod and spin the *subject* instead —
  then use **Guide** or **Manual** mode, since the phone isn't the thing rotating.
- One steady pass beats a fast one. ~20–40°/s is comfortable and stays well under the blur
  warning.
- Lock exposure on (default) keeps brightness consistent across the set where iOS allows it;
  Safari currently ignores manual exposure constraints on most models, so if the light varies
  a lot, shoot away from a bright sky.
- Keep the screen awake option on — the page holds a wake lock on iOS 16.4+.

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Not moving" / "Nothing moved while tuning" | The surface is too grippy. Bare phone on glass, or a lazy-susan. Volume max, silent switch off. |
| Drive is silent | iOS mutes Web Audio with the ringer switch on. Flip it off and restart the set. |
| It spins but never stops squarely | Normal — it shoots wherever it settles and reports the spacing error. Fewer shots per turn helps. |
| "No motion data" banner | Settings → Apps → Safari → Motion & Orientation Access → on, then reload. |
| Motion prompt never appears | The prompt only comes from a real tap. Reload and tap the start button directly. |
| Camera error | Another app holds the camera — close it. Or re-allow via **aA** → Website Settings → Camera. |
| Angles drift over a long spin | Yaw comes from the gyro; drift is normal after several minutes. Tap **Cancel** and start a fresh set. |
| Nothing fires in Auto | You need to actually rotate — the first frame fires at the origin, the rest at each step. |

## How the self-spin works

**The waveform.** A symmetric buzz gets you nothing: the phone rattles in place and stays
put. Net motion needs an asymmetric force profile working against stick-slip friction — a
short violent shove that breaks static friction and slides the phone, then a long gentle
return that stays under the friction threshold and does not drag it back. The drive is an
audible carrier tone amplitude-modulated by exactly that lopsided envelope, at roughly 12
strokes a second. The two halves are built to carry **equal momentum but very unequal peak
force**, which is the whole trick — and it is what the test suite measures.

**The tuning.** A phone body, plus whatever it is standing on, has sharp mechanical
resonances. A few tens of Hz either side of one is the difference between crawling and
sitting still, and it moves with every surface, so the app measures rather than assumes:
it sweeps six carrier tones × two stroke polarities, scoring each by the rotation the gyro
actually reports, and keeps the winner. Each candidate is brought to a stop first, so a good
tone cannot leave the phone coasting and hand its score to the next one.

**The loop.** A controller ticks 20× a second: shove at full power to break static friction,
settle into proportional-integral control at a ~22°/s cruise, then cut power early enough
that friction coasts the phone into the next capture angle. The shutter is **gated on the
drive being quiet** — a frame is never taken while the speaker is pushing, because that is
exactly the moment it would smear. If it stops short of the marker, it nudges again. If full
power produces no rotation for four seconds, it stops and tells you the surface is wrong.

## How the angle tracking works

- Orientation samples (`alpha`/`beta`/`gamma`) are turned into a full rotation matrix, and yaw
  is read as the compass azimuth of the axis the rear camera points along. That stays stable
  with the phone upright, where raw `alpha` is degenerate (gimbal lock at `beta` = 90°). With
  the phone flat, it falls back to the top-edge axis and re-anchors without a jump.
- Rotation is unwrapped across the 0/360° seam and accumulated, so a full turn reads as 360°,
  not a wrap back to 0. Impossible jumps (>1500°/s) are discarded as sensor glitches.
- Shot targets fire on forward progress only, so wobbling back and forth over a marker never
  double-fires, and direction locks in from your first few degrees of movement.
- The .zip is written in-page (store-only, CRC-32) — no library, nothing leaves the phone.

Everything runs locally. No network calls, no analytics, no uploads.

## Tests

Automated suite: 39 Playwright tests (unit + end-to-end) covering the drive waveform, the
resonance tuner, the closed-loop controller against a simulated phone-on-a-surface, the
rotation maths, shot planning, both spin directions, all three modes, permission-denied
paths, camera lifecycle, zip integrity, and layout at three iPhone sizes. See `TESTING.md`
for what was verified and the known limits of the harness.
