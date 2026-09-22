@echo off
REM ============================================================
REM EduAgent one-click start (AUTO20, 2026-09-22 rev)
REM   backend  : http://127.0.0.1:9988  (uvicorn, edu-agent/.venv)
REM   frontend : http://127.0.0.1:3322  (next dev - ALWAYS fresh pages)
REM   VM infra : Milvus :19530 / MongoDB :27017 / Neo4j :7687 (VMware 192.168.85.101)
REM   Redis    : docker container :6377
REM   stop     : stop-eduagent.cmd        (app only)
REM   stop all : stop-eduagent.cmd full  (+ Redis container; VM stays)
REM   health   : cd edu-agent  then  node scripts\check-demo.mjs
REM Watchdog removed 2026-09-22 by owner request.
REM ============================================================

setlocal EnableExtensions
chcp 65001 >nul
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND_DIR=%ROOT%\edu-agent"
set "FRONTEND_DIR=%ROOT%\edu-frontend"
set "BACKEND_PORT=9988"
set "FRONTEND_PORT=3322"
set "VM_HOST=192.168.85.101"
set "REDIS_CONTAINER=prisma-ai-redis-container-1"

echo ============================================
echo  EduAgent start  backend :%BACKEND_PORT%  frontend :%FRONTEND_PORT% (dev mode)
echo ============================================

echo [1/6] Probe VM infra %VM_HOST% (Milvus 19530 / Mongo 27017 / Neo4j 7687) ...
powershell -NoProfile -Command "$ok=$true; foreach($p in 19530,27017,7687){$c=New-Object Net.Sockets.TcpClient; $ar=$c.BeginConnect('%VM_HOST%',$p,$null,$null); if($ar.AsyncWaitHandle.WaitOne(3000) -and $c.Connected){Write-Host ('  [OK] VM port '+$p)}else{Write-Host ('  [WARN] VM port '+$p+' down (RAG/Neo4j demo degraded)') -ForegroundColor Yellow; $ok=$false}; $c.Close()}" 
if errorlevel 1 echo   [WARN] VM probe failed - continue anyway.

echo [2/6] Start Redis container %REDIS_CONTAINER% ...
docker start %REDIS_CONTAINER% >nul 2>&1
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; $ar=$c.BeginConnect('127.0.0.1',6377,$null,$null); if($ar.AsyncWaitHandle.WaitOne(3000) -and $c.Connected){Write-Host '  [OK] Redis :6377'}else{Write-Host '  [WARN] Redis :6377 down' -ForegroundColor Yellow}; $c.Close()"

if not exist "%BACKEND_DIR%\logs" mkdir "%BACKEND_DIR%\logs"

echo [3/6] Backend :%BACKEND_PORT% ...
netstat -ano -p tcp | findstr /C:":%BACKEND_PORT% " | findstr /C:"LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo   [SKIP] port %BACKEND_PORT% already listening.
) else (
  if not exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
    echo   [FAIL] venv python missing: %BACKEND_DIR%\.venv\Scripts\python.exe
    pause
    exit /b 1
  )
  start "EduAgent-Backend" /MIN /D "%BACKEND_DIR%" cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --port %BACKEND_PORT% >> logs\uvicorn_9988.log 2>&1"
  echo   [OK] uvicorn spawn issued on :%BACKEND_PORT%.
)

echo [4/6] Frontend :%FRONTEND_PORT% (next dev - pages always fresh) ...
netstat -ano -p tcp | findstr /C:":%FRONTEND_PORT% " | findstr /C:"LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo   [SKIP] port %FRONTEND_PORT% already listening.
) else (
  if not exist "%FRONTEND_DIR%\node_modules\next\dist\bin\next" (
    echo   [FAIL] next binary missing under %FRONTEND_DIR%\node_modules
    pause
    exit /b 1
  )
  start "EduAgent-Frontend" /MIN /D "%FRONTEND_DIR%" cmd /c "node node_modules\next\dist\bin\next dev -p %FRONTEND_PORT% >> next-3322.log 2>&1"
  echo   [OK] next dev spawn issued on :%FRONTEND_PORT%.
)

echo [5/6] Probe checklist: first wait 20s, then poll ...
%SystemRoot%\System32\ping.exe -n 21 127.0.0.1 >nul
set /a TRIES=0
:B_WAIT
set "B_HTTP=000"
for /f %%i in ('curl -s -o nul -w "%%{http_code}" http://127.0.0.1:%BACKEND_PORT%/health 2^>nul') do set "B_HTTP=%%i"
if "%B_HTTP%"=="200" goto B_DONE
set /a TRIES+=1
if %TRIES% GEQ 30 goto B_DONE
%SystemRoot%\System32\ping.exe -n 6 127.0.0.1 >nul
goto B_WAIT
:B_DONE
set "F_HTTP=000"
for /f %%i in ('curl -s -o nul -w "%%{http_code}" http://127.0.0.1:%FRONTEND_PORT%/login-register.html 2^>nul') do set "F_HTTP=%%i"
if "%B_HTTP%"=="200" (echo   [OK]   backend  http://127.0.0.1:%BACKEND_PORT%/health  HTTP %B_HTTP%) else (echo   [FAIL] backend  http://127.0.0.1:%BACKEND_PORT%/health  HTTP %B_HTTP%)
if "%F_HTTP%"=="200" (echo   [OK]   frontend http://127.0.0.1:%FRONTEND_PORT%/login-register.html  HTTP %F_HTTP%) else (echo   [FAIL] frontend http://127.0.0.1:%FRONTEND_PORT%/login-register.html  HTTP %F_HTTP%)

echo [6/6] Warm up first page hit (dev cold compile) ...
curl -s -o nul http://127.0.0.1:%FRONTEND_PORT%/login-register.html
curl -s -o nul http://127.0.0.1:%FRONTEND_PORT%/courses.html

echo.
echo  Demo entry : http://127.0.0.1:3322/login-register.html
echo  Accounts   : user000001 / Test@123456   (student)
echo               adm02test  / Test@123456   (admin)
echo  Full check : cd edu-agent  then  node scripts\check-demo.mjs
echo.
pause
endlocal
