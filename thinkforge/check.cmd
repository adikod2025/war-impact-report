@echo off
rem Run this if the browser says it cannot connect.
setlocal
cd /d "%~dp0"
if not exist "server\index.mjs" for /d %%d in (*) do if exist "%%d\server\index.mjs" cd /d "%%d"
node --no-warnings scripts\selftest.mjs
pause
