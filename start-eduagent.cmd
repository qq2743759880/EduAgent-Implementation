@echo off
REM ============================================================
REM EduAgent one-click start (W-NEXT-PORTS-001, 2026-09-20)
REM   backend  : http://127.0.0.1:9988  (uvicorn, edu-agent/.venv)
REM   frontend : http://127.0.0.1:3322  (next start, dist .next-prod)
REM   stop     : stop-eduagent.cmd
REM   health   : cd edu-agent  then  node scripts\check-demo.mjs
REM File is pure ASCII with CRLF endings (batch-parser safe).
REM The two Chinese user-facing messages are emitted via PowerShell
REM [char] escapes so the file itself stays ASCII.
REM ============================================================

setlocal EnableExtensions
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "BACKEND_DIR=%ROOT%\edu-agent"
set "FRONTEND_DIR=%ROOT%\edu-frontend"
set "BACKEND_PORT=9988"
set "FRONTEND_PORT=3322"
set "VM_HOST=192.168.85.101"
set "VM_PORT=19530"
set "REDIS_CONTAINER=prisma-ai-redis-container-1"

echo ============================================
echo  EduAgent start  backend :%BACKEND_PORT%  frontend :%FRONTEND_PORT%
echo ============================================

echo [1/5] Probe Milvus VM %VM_HOST%:%VM_PORT% ...
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; $ar=$c.BeginConnect('%VM_HOST%',%VM_PORT%,$null,$null); if($ar.AsyncWaitHandle.WaitOne(4000) -and $c.Connected){exit 0}else{exit 1}" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   [FAIL] Milvus VM %VM_HOST%:%VM_PORT% NOT reachable.
  powershell -NoProfile -Command "Write-Host ('  ' + [char]0x8BF7 + [char]0x5148 + [char]0x542F + [char]0x52A8 + ' VMware ' + [char]0x865A + [char]0x62DF + [char]0x673A + ' CentOS 7 64 ' + [char]0x4F4D + [char]0xFF0C + [char]0x518D + [char]0x91CD + [char]0x65B0 + [char]0x8FD0 + [char]0x884C + [char]0x672C + [char]0x811A + [char]0x672C + [char]0x3002)"
  echo.
  pause
  exit /b 1
)
echo   [OK] Milvus VM reachable.

echo [2/5] Start Redis container %REDIS_CONTAINER% ...
docker start %REDIS_CONTAINER% 2>nul
echo   [OK] docker start issued; error is ignored if already running.

if not exist "%BACKEND_DIR%\logs" mkdir "%BACKEND_DIR%\logs"

echo [3/5] Backend :%BACKEND_PORT% ...
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

echo [4/5] Frontend :%FRONTEND_PORT% ...
netstat -ano -p tcp | findstr /C:":%FRONTEND_PORT% " | findstr /C:"LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo   [SKIP] port %FRONTEND_PORT% already listening.
) else (
  if not exist "%FRONTEND_DIR%\.next-prod\BUILD_ID" (
    echo   [FAIL] .next-prod build missing. Run first:
    echo     cd edu-frontend
    echo     set NEXT_PROD_DIST_DIR=.next-prod
    echo     node node_modules\next\dist\bin\next build
    pause
    exit /b 1
  )
  start "EduAgent-Frontend" /MIN /D "%FRONTEND_DIR%" cmd /c "set NEXT_PROD_DIST_DIR=.next-prod&& node node_modules\next\dist\bin\next start -p %FRONTEND_PORT% >> next-3322.log 2>&1"
  echo   [OK] next start spawn issued on :%FRONTEND_PORT%.
)

echo [5/5] Probe checklist: first wait 20s, then poll ...
REM ping-based sleep: timeout.exe /nobreak fails when stdin is redirected; ping is stdin-safe.
%SystemRoot%\System32\ping.exe -n 21 127.0.0.1 >nul
REM Backend cold start (BGE-M3/CUDA warm-up) can exceed 60s: poll up to 150s.
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

echo.
powershell -NoProfile -Command "Write-Host ([char]0x4F53 + [char]0x68C0 + [char]0xFF1A + 'cd edu-agent  then  node scripts\check-demo.mjs')"
echo.
pause
endlocal
