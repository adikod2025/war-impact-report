@echo off
rem Thinkforge launcher for Windows.  Usage: double-click, or run start.cmd
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is not installed. Get the current LTS from https://nodejs.org and run this again.
  pause
  exit /b 1
)

for /f "delims=" %%v in ('node -p "const [a,b]=process.versions.node.split('.').map(Number); (a>22||(a===22&&b>=5))?'ok':'old'"') do set NODEOK=%%v
if not "%NODEOK%"=="ok" (
  echo Thinkforge needs Node v22.5 or newer.
  node -v
  pause
  exit /b 1
)

set FLAGS=--no-warnings
node --no-warnings -e "require('node:sqlite')" >nul 2>nul
if errorlevel 1 set FLAGS=--no-warnings --experimental-sqlite

node %FLAGS% scripts\doctor.mjs
if errorlevel 1 (
  echo.
  echo Fix the above and run start.cmd again.
  pause
  exit /b 1
)

if not exist data\thinkforge.db (
  set /p SEED="No data yet. Add a demo class of five learners? [Y/n] "
  if /i not "%SEED%"=="n" node %FLAGS% scripts\seed.mjs
)

echo.
node %FLAGS% server\index.mjs
pause
