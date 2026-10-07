@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "PYTHONUTF8=1"
set "DEBUG=false"
set "PROJECT_PYTHON=%~dp0bili-study-agent\.venv\Scripts\python.exe"
if not exist "%PROJECT_PYTHON%" (
  echo [FAIL] Project Python missing: "%PROJECT_PYTHON%"
  if /I not "%~1"=="--no-pause" pause
  exit /b 2
)
REM Double-click: wait for the result. Automation: --no-pause as first argument.
REM Examples: start-bili-study.cmd --no-pause status
REM           start-bili-study.cmd --no-pause start --backend-timeout 240
if /I "%~1"=="--no-pause" (
  "%PROJECT_PYTHON%" -X utf8 -B "%~dp0deploy\local_launcher.py" %2 %3 %4 %5 %6 %7 %8 %9
) else (
  "%PROJECT_PYTHON%" -X utf8 -B "%~dp0deploy\local_launcher.py" %*
)
set "LAUNCH_RESULT=%ERRORLEVEL%"
if /I not "%~1"=="--no-pause" pause
exit /b %LAUNCH_RESULT%
