@echo off
chcp 65001 >nul
setlocal EnableExtensions
REM ============================================================
REM EduAgent stop (W-NEXT-PORTS-001, 2026-09-20)
REM Kills backend :9988 and frontend :3322 by listening port.
REM ============================================================

echo [1/2] Kill backend :9988 ...
for /f "tokens=5" %%Q in ('netstat -ano -p tcp ^| findstr /C:":9988 " ^| findstr /C:"LISTENING"') do (
  echo   taskkill pid %%Q
  taskkill /F /T /PID %%Q >nul 2>&1
)

echo [2/2] Kill frontend :3322 ...
for /f "tokens=5" %%Q in ('netstat -ano -p tcp ^| findstr /C:":3322 " ^| findstr /C:"LISTENING"') do (
  echo   taskkill pid %%Q
  taskkill /F /T /PID %%Q >nul 2>&1
)

echo Done. Remaining listeners, if any:
netstat -ano -p tcp | findstr /C:":9988 " | findstr /C:"LISTENING"
netstat -ano -p tcp | findstr /C:":3322 " | findstr /C:"LISTENING"
echo.
pause
endlocal
