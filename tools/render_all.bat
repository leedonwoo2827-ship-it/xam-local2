@echo off
REM ASCII ONLY.
REM ---------------------------------------------------------------------------
REM Render every bundle in a book, one by one, detached from any app session.
REM
REM WHY THIS EXISTS. The app's render job runs inside the uvicorn process. If the
REM window that started uvicorn closes, an overnight run dies with it. This bat
REM is a plain process: start it, close everything else, go home.
REM
REM   tools\render_all.bat                        active book (data\books.json)
REM   tools\render_all.bat D:\00work\ocr-output-260723
REM
REM Log: data\render_all.log   (append; the driver prints one line per scene)
REM Stop: close the window, or Ctrl+C. Bundles already done are skipped next run
REM       only if you pass --skip-done to make_bundle_video (it has --force too).
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0.."

set "BOOK=%~1"
if not defined BOOK (
  for /f "usebackq delims=" %%A in (`venv\Scripts\python.exe -c "from services.book import paths; print(paths.book_dir())"`) do set "BOOK=%%A"
)
if not defined BOOK goto :nobook

set "LOG=%CD%\data\render_all.log"
if not exist "%CD%\data" mkdir "%CD%\data"

echo.
echo   book : %BOOK%
echo   log  : %LOG%
echo.
echo   Slides come from 05\^<bundle^>\images\slide_NN.png (exported from deck.pptx).
echo   The driver adds --reuse-images itself when those images match the pptx.
echo.

set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
cd /d "%CD%\vendor\chodangi"
"..\..\venv\Scripts\python.exe" -X utf8 -u make_bundle_video.py --book "%BOOK%" --reuse-images >> "%LOG%" 2>&1
echo exit=%errorlevel% >> "%LOG%"
echo.
echo   done. tail the log to see what happened:
echo     powershell -c "Get-Content '%LOG%' -Tail 40"
echo.
goto :eof

:nobook
echo [error] could not resolve the book folder. Pass it as the first argument.
exit /b 1
