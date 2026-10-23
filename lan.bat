@echo off
REM ---------------------------------------------------------------------------
REM XAM LOCAL - SHARE ON THE OFFICE LAN (read-only for everyone else)
REM
REM Use this when you want colleagues to LOOK at the console - the screens, the
REM progress, the publish checklist. They cannot change anything:
REM
REM     you (127.0.0.1)      full access, exactly like run.bat
REM     everyone else        GET / HEAD only. Saves, builds and renders get 403.
REM
REM The rule lives in core\lan.py and is enforced by a middleware in app.py, so
REM it holds no matter how the server was started. This file only changes the
REM bind address from 127.0.0.1 to 0.0.0.0.
REM
REM ---------------------------------------------------------------------------
REM  WHAT THIS IS NOT
REM
REM  There is no password. Anyone who can reach this PC on the network can read
REM  every screen - questions, answers, explanations, the whole bank. That is
REM  fine on a trusted office LAN and NOT fine anywhere else. Never port-forward
REM  this, never run it on hotel or cafe wifi.
REM
REM  Windows Firewall will ask for permission the first time. Allow it for
REM  PRIVATE networks only - never Public.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
if not defined PORT set "PORT=8871"

if not exist "venv\Scripts\python.exe" goto :noinstall

netstat -ano -p tcp | findstr /r /c:"LISTENING" | findstr /c:":%PORT% " >nul
if not errorlevel 1 goto :portbusy

echo.
echo   XAM LOCAL  -  SHARING ON THE LAN  (read-only for others)
echo.
echo   You, on this PC:
echo     http://127.0.0.1:%PORT%/
echo.
echo   Give colleagues one of these:
venv\Scripts\python -m core.lan
echo.
echo   They will see a "read-only" bar at the top of the screen.
echo.
echo   KEEP THIS WINDOW OPEN. Closing it ends the share and stops the app.
echo   Press Ctrl+C to stop on purpose.
echo.

start "" /b cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:%PORT%/"

REM 0.0.0.0 = every interface. The read-only middleware is what makes this safe.
venv\Scripts\python -m uvicorn app:app --host 0.0.0.0 --port %PORT%
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" echo   Share ended. Server stopped.
if not "%RC%"=="0" echo   [ERROR] Server exited with code %RC%. Read the lines above.
goto :hold

:portbusy
echo.
echo   [ERROR] Port %PORT% is already in use.
echo.
echo   XAM LOCAL is probably already running from run.bat - but that one is
echo   loopback only, so nobody else can reach it. To share, stop that window
echo   first (Ctrl+C) and then run this file.
echo.
echo   If it is a leftover process, close it with:
echo       for /f "tokens=5" %%%%p in ('netstat -ano ^^^| findstr :%PORT%') do taskkill /f /pid %%%%p
goto :hold

:noinstall
echo.
echo   [ERROR] venv not found. Run setup.bat first.
goto :hold

:hold
echo.
pause
exit /b 0
