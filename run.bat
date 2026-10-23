@echo off
REM ---------------------------------------------------------------------------
REM XAM LOCAL - start the local console
REM
REM ASCII ONLY. Flat IF + GOTO. Override the port with:  set PORT=8871 && run.bat
REM
REM This console IS the server. Keep it open while you work - closing it kills
REM the app and any running render. uvicorn runs in the foreground on purpose.
REM
REM Every exit path ends at :hold so the window never vanishes before you can
REM read why. A silently closing window used to mean "port already in use" and
REM there was no way to tell.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
if not defined PORT set "PORT=8871"

if not exist "venv\Scripts\python.exe" goto :noinstall

REM Port already taken? uvicorn would exit instantly and close this window.
netstat -ano -p tcp | findstr /r /c:"LISTENING" | findstr /c:":%PORT% " >nul
if not errorlevel 1 goto :portbusy

echo.
echo   XAM LOCAL  -^>  http://127.0.0.1:%PORT%/
echo.
echo   KEEP THIS WINDOW OPEN. It is the server.
echo   Closing it stops the app and any render in progress.
echo   Press Ctrl+C to stop on purpose.
echo.

REM loopback only - this console can write to the BOOK tree, never expose it
start "" /b cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:%PORT%/"

venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port %PORT%
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" echo   Server stopped.
if not "%RC%"=="0" echo   [ERROR] Server exited with code %RC%. Read the lines above.
goto :hold

:portbusy
echo.
echo   [ERROR] Port %PORT% is already in use.
echo.
echo   XAM LOCAL is probably already running - check your other windows and
echo   your browser at  http://127.0.0.1:%PORT%/
echo.
echo   If it is a leftover process, close it with:
echo       for /f "tokens=5" %%%%p in ('netstat -ano ^^^| findstr :%PORT%') do taskkill /f /pid %%%%p
echo.
echo   Or start on another port:   set PORT=8871 ^&^& run.bat
goto :hold

:noinstall
echo.
echo   [ERROR] venv not found. Run setup.bat first.
goto :hold

:hold
echo.
pause
exit /b 0
