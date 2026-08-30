@echo off
rem ===================================================================
rem  Double-click this file. It does everything: checks Node, sets up
rem  the data, starts Thinkforge, and opens it in your browser.
rem ===================================================================
setlocal
cd /d "%~dp0"

if not exist "server\index.mjs" for /d %%d in (*) do if exist "%%d\server\index.mjs" cd /d "%%d"
if not exist "server\index.mjs" goto :notfound

where node >nul 2>nul
if errorlevel 1 goto :nonode

node -e "var v=process.versions.node.split('.').map(Number); process.exit(v[0]>22||v[0]===22&&v[1]>=5?0:1)" >nul 2>nul
if errorlevel 1 goto :oldnode

set "FLAGS=--no-warnings"
node --no-warnings -e "require('node:sqlite')" >nul 2>nul
if errorlevel 1 set "FLAGS=--no-warnings --experimental-sqlite"

node %FLAGS% scripts\run.mjs
goto :end

:notfound
echo.
echo   Thinkforge is not in this folder or any folder inside it.
echo   Extract the zip first ^(right-click, "Extract All..."^), then run this
echo   file from the folder that appears.
echo.
goto :end

:nonode
echo.
echo   Node.js is not installed. Get the current LTS from https://nodejs.org,
echo   install it, then double-click this file again.
echo.
goto :end

:oldnode
echo.
echo   Thinkforge needs Node.js v22.5 or newer. This machine has:
node -v
echo.

:end
pause
