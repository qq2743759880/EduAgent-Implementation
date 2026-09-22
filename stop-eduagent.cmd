@echo off
REM ============================================================
REM EduAgent stop (AUTO20, 2026-09-22 rev)
REM   stop-eduagent.cmd          -> app only (backend 9988 + frontend 3322)
REM   stop-eduagent.cmd full     -> app + Redis container
REM   VM infra (Milvus/Mongo/Neo4j) is NEVER stopped by this script -
REM   stop it manually in VMware Workstation if really needed.
REM Watchdog removed 2026-09-22 by owner request.
REM ============================================================

setlocal EnableExtensions
chcp 65001 >nul
set "MODE=%1"
if "%MODE%"=="" set "MODE=app"

echo ============================================
echo  EduAgent stop  mode=%MODE%
echo ============================================

echo [1/3] Kill backend :9988 ...
for /f "tokens=5" %%Q in ('netstat -ano -p tcp ^| findstr /C:":9988 " ^| findstr /C:"LISTENING"') do (
  echo   taskkill pid %%Q
  taskkill /F /T /PID %%Q >nul 2>&1
)

echo [2/3] Kill frontend :3322 ...
for /f "tokens=5" %%Q in ('netstat -ano -p tcp ^| findstr /C:":3322 " ^| findstr /C:"LISTENING"') do (
  echo   taskkill pid %%Q
  taskkill /F /T /PID %%Q >nul 2>&1
)

echo [3/3] Redis container :6377 ...
if /I "%MODE%"=="full" (
  docker stop prisma-ai-redis-container-1 2>nul
  echo   [OK] redis container stopped (WARNING: shared with prisma-ai project)
) else (
  echo   [SKIP] app mode keeps Redis running. Use "stop-eduagent.cmd full" to stop it too.
)

echo Done. Remaining listeners, if any:
netstat -ano -p tcp | findstr /C:":9988 " | findstr /C:"LISTENING"
netstat -ano -p tcp | findstr /C:":3322 " | findstr /C:"LISTENING"
echo.
echo  VM infra (Milvus/Mongo/Neo4j @192.168.85.101) left running - stop in VMware manually.
echo.
pause
endlocal
