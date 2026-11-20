@echo off
REM ---------------------------------------------------------------------------
REM XAM LOCAL - overnight chain: author -> build -> ebook -> part2
REM
REM ASCII ONLY. run.bat (the server) must be running first.
REM Stops at the deadline (default 07:30) so the PC is free in the morning.
REM   overnight.bat            rounds 1-10, deadline 07:30
REM   overnight.bat 07:00      another deadline
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
set "DL=%~1"
if "%DL%"=="" set "DL=07:30"
if not exist "venv\Scripts\python.exe" goto :noinstall
venv\Scripts\python tools\overnight_chain.py --rounds 1-10 --deadline %DL%
goto :hold

:noinstall
echo.
echo   [ERROR] venv not found. Run setup.bat first.

:hold
echo.
pause
exit /b 0
