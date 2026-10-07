@echo off
REM ============================================================
REM Bili-Study stop (AUTO20, 2026-09-22 rev)
REM   stop-bili-study.cmd          -> app only (backend 9988 + frontend 3322)
REM   stop-bili-study.cmd full     -> app + Redis container
REM   VM infra (Milvus/Mongo/Neo4j) is NEVER stopped by this script -
REM   stop it manually in VMware Workstation if really needed.
REM Watchdog removed 2026-09-22 by owner request.
REM ============================================================

setlocal EnableExtensions
chcp 65001 >nul
set "MODE=%1"
if "%MODE%"=="" set "MODE=app"
set "VIDEO_STOP_TIMEOUT=%2"
if "%VIDEO_STOP_TIMEOUT%"=="" set "VIDEO_STOP_TIMEOUT=15"

echo ============================================
echo  Bili-Study stop  mode=%MODE%
echo ============================================

echo [1/4] Stop verified Bili-Study W3 workers ...
set "BACKEND_DIR=%~dp0bili-study-agent"
pushd "%BACKEND_DIR%"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -m app.domains.video_learning.task_worker --stop
  if errorlevel 1 (
    echo   [STOP FAILED] Could not request video task drain. Backend left running.
    popd
    exit /b 1
  )
  .venv\Scripts\python.exe -m app.domains.video_learning.task_worker --wait-stopped --timeout %VIDEO_STOP_TIMEOUT%
  if errorlevel 1 (
    echo   [WAIT] Video operation still active or stop could not be verified. Backend left running.
    echo   Retry after completion, or run stop-bili-study.cmd %MODE% 600 to wait longer.
    popd
    exit /b 1
  )
  .venv\Scripts\python.exe scripts\manage_workers.py stop
  if errorlevel 1 (
    echo   [WAIT] Document workers still draining. Backend and frontend left running.
    popd
    exit /b 1
  )
) else (
  echo   [STOP FAILED] project venv missing; worker drain cannot be verified. Backend left running.
  popd
  exit /b 1
)
popd

echo [2/4] Kill backend :9988 ...
for /f "tokens=5" %%Q in ('netstat -ano -p tcp ^| findstr /C:":9988 " ^| findstr /C:"LISTENING"') do (
  echo   taskkill pid %%Q
  REM Video worker released its lock after its current task drained above.
  taskkill /F /PID %%Q >nul 2>&1
)

echo [3/4] Kill frontend :3322 ...
for /f "tokens=5" %%Q in ('netstat -ano -p tcp ^| findstr /C:":3322 " ^| findstr /C:"LISTENING"') do (
  echo   taskkill pid %%Q
  taskkill /F /T /PID %%Q >nul 2>&1
)

echo [4/4] Redis container :6377 ...
if /I "%MODE%"=="full" (
  docker stop prisma-ai-redis-container-1 2>nul
  echo   [OK] redis container stopped (WARNING: shared with prisma-ai project)
) else (
  echo   [SKIP] app mode keeps Redis running. Use "stop-bili-study.cmd full" to stop it too.
)

REM ============================================================
echo Done. Remaining listeners, if any:
netstat -ano -p tcp | findstr /C:":9988 " | findstr /C:"LISTENING"
netstat -ano -p tcp | findstr /C:":3322 " | findstr /C:"LISTENING"
echo.
echo  VM infra (Milvus/Mongo/Neo4j @192.168.85.101) left running - stop in VMware manually.
echo.
pause
endlocal
