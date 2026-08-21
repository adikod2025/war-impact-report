# Installing Thinkforge on your own machine

Thinkforge is a small web app you run locally. It needs **Node.js v22.5 or
newer** and nothing else — no database to install, no build step, no account.
Everything stays on your machine.

---

## 1. Install Node.js (once)

Download the current LTS from **https://nodejs.org** and run the installer.
To check it worked, open a terminal and run:

```
node -v
```

You should see `v22.5.0` or higher.

## 2. Unpack Thinkforge

**Extract the archive before running anything.** On Windows, double-clicking a
file *inside* a zip makes Explorer copy only that one file to a temp folder, so
the app cannot find the rest of itself and Node reports
`Cannot find module ...\\scripts\\doctor.mjs`.

- **Windows** — right-click the `.zip` → **Extract All…** → open the extracted
  `thinkforge-1.0.0` folder.
- **macOS / Linux** — `tar -xzf thinkforge-1.0.0.tar.gz` (or double-click), then
  open the `thinkforge-1.0.0` folder.

Anywhere is fine — Documents, Desktop, a USB stick.

## 3. Start it

**macOS / Linux** — open a terminal in that folder and run:

```
./start.sh
```

**Windows** — double-click **`start.cmd`** (or run it from a terminal).

The first run offers to add a demo class of five learners so the teacher view
has something in it. Say yes the first time; say no if you are setting this up
for real students.

Then open **http://localhost:4173** in a browser.

To stop it, press `Ctrl+C` in the terminal (or close the window on Windows).

---

## 4. Optional: turn on the AI coach and marker

Thinkforge is fully functional without this. With no key it marks deterministically
from the structure and language of an answer, and the coach serves the authored
hint ladder — and it says so on screen rather than pretending.

To turn on AI marking, the Socratic coach and growth narratives:

1. Get a key from https://console.anthropic.com/settings/keys
2. Copy `.env.example` to `.env` in the same folder.
3. Put your key in it:

```
ANTHROPIC_API_KEY=sk-ant-...
```

4. Start it again. The header will show **AI marking on**.

Costs are small — a marked answer is a few thousand tokens — but they are real,
and they are billed to your key. The `doctor` check below tells you which mode
you are in.

---

## 5. If something goes wrong

If the browser says **it cannot connect**, run the self-test — on Windows
double-click **`check.cmd`**, otherwise:

```
node scripts/selftest.mjs
```

It starts a test copy, checks it is reachable, and tells you the cause.

For everything else, run the preflight check:

```
node scripts/doctor.mjs
```

It checks the six things that actually break on a fresh machine — Node version,
the built-in database, a writable data folder, the port, the curriculum files,
and whether AI is configured — and tells you what to do about each one.

| Symptom | Fix |
|---|---|
| `Cannot find module ...\scripts\doctor.mjs`, path contains `AppData\Local\Temp` | You ran `start.cmd` from inside the zip. Extract the archive first (step 2), then run it from the extracted folder. |
| `node: command not found` | Node.js is not installed — step 1. |
| "needs Node v22.5 or newer" | Your Node is too old; install the current LTS. |
| "Port 4173 already in use" | Start on another port: `PORT=4174 ./start.sh` |
| Permission denied running `./start.sh` | `chmod +x start.sh`, then try again. |
| Windows blocks the script | Right-click `start.cmd` → Properties → Unblock. |
| Everything says "marked by rules only" | No API key — that is normal. See step 4. |
| Header says **degraded** | A key is set but calls are failing. `node scripts/doctor.mjs` and check the terminal for the reason. |

---

## 6. Where your data lives

Everything is in one file: **`data/thinkforge.db`**.

- **Back it up** by copying that file.
- **Move it to another machine** by copying the whole folder.
- **Delete everything** by deleting the file (or use the Delete button in the app,
  which removes one learner and all their work).

The app stores a first name and an age per learner, their answers, and their
coach conversations. No email, no photo, no account. If you set an API key,
answers are sent to Anthropic for marking with personal details stripped out
first; nothing is used to train a model.

## 7. Running it for a class

By default Thinkforge only listens on the machine it runs on. To let other
devices on the same network reach it — a classroom set of tablets, say — set
the host in your `.env`:

```
HOST=0.0.0.0
```

Then other devices use `http://<your-machine-ip>:4173`. Only do this on a
network you trust: it holds children's work and there are no user accounts.

## 8. Updating

Download the newer release, unzip it next to the old one, and copy your
`data/thinkforge.db` and `.env` across. The database schema migrates itself on
start.
