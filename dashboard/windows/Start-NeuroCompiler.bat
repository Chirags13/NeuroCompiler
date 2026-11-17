@echo off
rem NeuroCompiler dashboard launcher: boots WSL (Ubuntu), starts the dashboard server inside it, opens the browser.
rem Override the distro or repo path with NC_DISTRO / NC_REPO if yours differ.
if "%NC_DISTRO%"=="" set NC_DISTRO=Ubuntu
if "%NC_REPO%"=="" set NC_REPO=~/neurocompiler
echo Starting WSL (%NC_DISTRO%) and the NeuroCompiler dashboard...
start "NeuroCompiler server" /min wsl.exe -d %NC_DISTRO% -- bash -lc "cd %NC_REPO% && ./dashboard/run.sh"
rem wait until the server answers (up to ~60 s)
set /a tries=0
:wait
set /a tries+=1
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/health -TimeoutSec 2) | Out-Null; exit 0 } catch { exit 1 }"
if %errorlevel%==0 goto open
if %tries% geq 30 goto fail
timeout /t 2 /nobreak >nul
goto wait
:open
start "" http://localhost:8000/
exit /b 0
:fail
echo The server did not start. Open a WSL terminal and run: cd %NC_REPO% ^&^& ./dashboard/run.sh
pause
