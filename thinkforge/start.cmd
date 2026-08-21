@echo off
rem Thinkforge launcher for Windows.  Extract the zip first, then run this.
setlocal
cd /d "%~dp0"

rem --- Are we running from inside the zip? Explorer extracts only the file you
rem --- double-click into a temp folder, so its siblings are missing.
if not exist "server\index.mjs" goto :notextracted
if not exist "scripts\doctor.mjs" goto :notextracted

where node >nul 2>nul
if errorlevel 1 goto :nonode

node -e "var v=process.versions.node.split('.').map(Number); process.exit(v[0]>22||v[0]===22&&v[1]>=5?0:1)" >nul 2>nul
if errorlevel 1 goto :oldnode

rem Older 22.x builds still need a flag for the built-in database.
set "FLAGS=--no-warnings"
node --no-warnings -e "require('node:sqlite')" >nul 2>nul
if errorlevel 1 set "FLAGS=--no-warnings --experimental-sqlite"

node %FLAGS% scripts\doctor.mjs
if errorlevel 1 goto :doctorfailed

if exist "data\thinkforge.db" goto :run
set "SEED=y"
set /p "SEED=No data yet. Add a demo class of five learners? [Y/n] "
if /i "%SEED%"=="n" goto :run
node %FLAGS% scripts\seed.mjs

:run
echo.
echo Starting Thinkforge. Open http://localhost:4173 in your browser.
echo Press Ctrl+C in this window to stop it.
echo.
node %FLAGS% server\index.mjs
goto :end

:notextracted
echo.
echo   It looks like this was started from inside the zip file.
echo.
echo   Windows only unpacked start.cmd, so the rest of Thinkforge is missing.
echo   Current folder:
echo     %CD%
echo.
echo   Do this instead:
echo     1. Find thinkforge-1.0.0.zip in your Downloads folder.
echo     2. Right-click it and choose "Extract All...".
echo     3. Open the extracted thinkforge-1.0.0 folder.
echo     4. Double-click start.cmd in there.
echo.
goto :end

:nonode
echo.
echo   Node.js is not installed.
echo   Get the current LTS from https://nodejs.org, install it, then run start.cmd again.
echo.
goto :end

:oldnode
echo.
echo   Thinkforge needs Node.js v22.5 or newer. This machine has:
node -v
echo   Install the current LTS from https://nodejs.org and run start.cmd again.
echo.
goto :end

:doctorfailed
echo.
echo   Fix the problems listed above, then run start.cmd again.
echo.

:end
pause
