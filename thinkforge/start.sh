#!/usr/bin/env bash
# Thinkforge launcher for macOS and Linux.  Usage:  ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

# Are we running from inside the archive, or from a folder missing its files?
if [ ! -f server/index.mjs ] || [ ! -f scripts/doctor.mjs ]; then
  echo
  echo "  This does not look like a complete Thinkforge folder."
  echo "  Current folder: $(pwd)"
  echo
  echo "  If you started this from inside the .zip or .tar.gz, extract the archive"
  echo "  first, then run ./start.sh from the extracted thinkforge folder."
  echo
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js is not installed. Get the current LTS from https://nodejs.org and run this again."
  exit 1
fi

MAJOR=$(node -p "process.versions.node.split('.')[0]")
MINOR=$(node -p "process.versions.node.split('.')[1]")
if [ "$MAJOR" -lt 22 ] || { [ "$MAJOR" -eq 22 ] && [ "$MINOR" -lt 5 ]; }; then
  echo "Thinkforge needs Node v22.5 or newer (found $(node -v)). Install the current LTS from https://nodejs.org."
  exit 1
fi

# Older 22.x builds still need the flag for the built-in database.
FLAGS="--no-warnings"
if ! node --no-warnings -e "require('node:sqlite')" >/dev/null 2>&1; then
  FLAGS="$FLAGS --experimental-sqlite"
fi

node $FLAGS scripts/doctor.mjs || { echo "Fix the above and run ./start.sh again."; exit 1; }

if [ ! -f data/thinkforge.db ] && [ "${THINKFORGE_SEED:-ask}" != "no" ]; then
  printf "No data yet. Add a demo class of five learners so the teacher view has something in it? [Y/n] "
  read -r reply || reply="y"
  case "$reply" in [Nn]*) ;; *) node $FLAGS scripts/seed.mjs ;; esac
fi

echo
echo "Starting Thinkforge. Open http://localhost:${PORT:-4173} in your browser."
echo "Press Ctrl+C to stop it."
echo
node $FLAGS server/index.mjs
