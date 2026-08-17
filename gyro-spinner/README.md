# Gyro Spinner — 360° capture for iPhone

A single self-contained HTML page. Spin your iPhone (or the subject) and the gyroscope
fires the shutter at perfectly even angles, so you end up with an evenly spaced 360° set
instead of eyeballing it.

No build step, no dependencies, no install. One file: `index.html`.

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

## Modes

| Mode | What happens |
|---|---|
| **Auto** | The shutter fires by itself each time the phone has rotated one step. Just spin. |
| **Manual** | The dial counts down to the next angle; you tap the shutter. |
| **Guide** | No camera. The dial and beeps pace your spin while a separate camera shoots. |

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
| "No motion data" banner | Settings → Apps → Safari → Motion & Orientation Access → on, then reload. |
| Motion prompt never appears | The prompt only comes from a real tap. Reload and tap the start button directly. |
| Camera error | Another app holds the camera — close it. Or re-allow via **aA** → Website Settings → Camera. |
| Angles drift over a long spin | Yaw comes from the gyro; drift is normal after several minutes. Tap **Cancel** and start a fresh set. |
| Nothing fires in Auto | You need to actually rotate — the first frame fires at the origin, the rest at each step. |

## How it works

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

Automated suite: 28 Playwright tests (unit + end-to-end) covering the rotation maths, shot
planning, both spin directions, all three modes, permission-denied paths, camera lifecycle,
zip integrity, and layout at three iPhone sizes. See `TESTING.md` for what was verified and
the known limits of the harness.
