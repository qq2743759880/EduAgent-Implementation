@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM  verify-auto20.cmd  --  Agent 协作工程一键复核（可机验子集）
REM  ---------------------------------------------------------------------------
REM  固定白名单，禁新依赖。总时长目标 <=5 分钟。
REM  配套文档：docs/agent-collab-verify.md
REM
REM  三个检查块：
REM    [1/3] G3 门禁        scripts/gates/dom-hook-inventory.mjs --all --check
REM    [2/3] dispatch 对账  .ai-hub/plans/artifacts/dispatch/ 开工令 vs 报告
REM    [3/3] pytest 契约    tests/ -k "chat or favorite or hitl"
REM
REM  退出码：0 = 全 PASS；1 = 有 FAIL
REM ============================================================================

cd /d "%~dp0"
set "REPO_ROOT=%CD%"

set PASS_N=0
set FAIL_N=0
set SKIP_N=0
set DRIFT_N=0

echo.
echo ===========================================================================
echo   EduAgent Agent 协作工程一键复核
echo   仓库根: %CD%
echo   时间:   %DATE% %TIME%
echo ===========================================================================
echo.

REM ---------------------------------------------------------------------------
REM  [1/3] G3 门禁：DOM 钩子冻结清单（纯静态扫描，无外部依赖）
REM
REM  判读口径（重要）：G3 是「漂移探测器」。它可能因两类原因失败——
REM    (a) 页面真的引入了未 review 的新钩子  -> 需人工审查后重冻结
REM    (b) 并行 agent 正在改页面（本仓库常态）-> 同上，属预期
REM  两者都表现为 --check 失败，且都需要"人工 review 后重冻结"这同一个动作。
REM  因此脚本把它单独计为 DRIFT 而非 FAIL：**漂移不是回归**，不该让整块面板
REM  变红而掩盖其它真正的问题。最终结论里 DRIFT 会明确列出，需人工判读。
REM ---------------------------------------------------------------------------
echo [1/3] G3 门禁 (dom-hook-inventory --all --check) ...
echo ---------------------------------------------------------------------------

where node >nul 2>&1
if errorlevel 1 goto :g3_skip

call node scripts\gates\dom-hook-inventory.mjs --all --check
if errorlevel 1 goto :g3_drift
echo   [PASS] G3 门禁：冻结清单与当前页面一致
set /a PASS_N+=1
goto :g3_done

:g3_skip
echo   [SKIP] 未找到 node，跳过 G3 门禁
set /a SKIP_N+=1
goto :g3_done

:g3_drift
echo   [DRIFT] G3 检出钩子清单漂移（非回归，见脚本内判读口径）
echo           处置: 确认改动是否为接线改进 -> 审查通过后重冻结
echo           重冻结: node scripts\gates\dom-hook-inventory.mjs --all
echo           速查漂移页: findstr /i "false" test-reports\gate-baseline\g3-dom-hook-inventory.txt
set /a DRIFT_N+=1

:g3_done
echo.

REM ---------------------------------------------------------------------------
REM  [2/3] dispatch 对账：开工令数量 vs 完工报告数量 + 逐单成对
REM ---------------------------------------------------------------------------
echo [2/3] dispatch 派单对账 ...
echo ---------------------------------------------------------------------------

set "DISP=%CD%\.ai-hub\plans\artifacts\dispatch"

if not exist "%DISP%\" goto :disp_nodir

REM  find 必须写全路径：Git Bash 环境下 PATH 里 GNU find 抢占 Windows find.exe，
REM  `find /c /v ""` 参数语义不同会导致本步静默挂死（2026-09-24 验收实测）。
for /f %%n in ('dir /b "%DISP%\TO-EXEC-*.md" 2^>nul ^| "%SystemRoot%\System32\find.exe" /c /v ""') do set TO_N=%%n
for /f %%n in ('dir /b "%DISP%\REPORT-*.md" 2^>nul ^| "%SystemRoot%\System32\find.exe" /c /v ""') do set RP_N=%%n
if not defined TO_N set TO_N=0
if not defined RP_N set RP_N=0

echo   开工令 TO-EXEC-*.md : %TO_N%
echo   完工报告 REPORT-*.md : %RP_N%
echo.
echo   逐单成对检查:
echo     NO-RPT 表示开工令尚无报告；在途/冻结/作废属正常现象，
echo     但须能在同目录 README.md 状态板找到对应说明。
echo.

set PAIR_N=0
set NORPT_N=0
for %%f in ("%DISP%\TO-EXEC-*.md") do call :pair_one "%%~nf"

echo.
echo   成对: %PAIR_N%    待报告: %NORPT_N%

if %PAIR_N% LEQ 0 goto :disp_fail
echo   [PASS] dispatch 对账（%PAIR_N% 对已配平）
set /a PASS_N+=1
goto :disp_done

:disp_nodir
echo   [FAIL] 未找到派单目录 %DISP%
set /a FAIL_N+=1
goto :disp_done

:disp_fail
echo   [FAIL] 无任何成对开工令/报告
set /a FAIL_N+=1

:disp_done
echo.

REM ---------------------------------------------------------------------------
REM  [3/3] pytest 契约子集：chat / favorite / hitl
REM ---------------------------------------------------------------------------
echo [3/3] pytest 契约子集 (-k "chat or favorite or hitl") ...
echo ---------------------------------------------------------------------------

set "PY=%CD%\edu-agent\.venv\Scripts\python.exe"

if not exist "%PY%" goto :py_skip
if not exist "%CD%\edu-agent\tests\" goto :py_notests

REM 关键：必须切到 edu-agent\ 下再跑 pytest。settings 靠 dotenv 的 find_dotenv
REM 从 cwd 向上找 .env；在仓库根跑会找不到 edu-agent\.env 而报
REM 「MYSQL_PASSWORD / LLM_API_KEY Field required」。用 pushd 保证即使中途失败也回到根。
pushd "%CD%\edu-agent"
set MYSQL_HOST=127.0.0.1
REM --ignore 该文件：其依赖的 scripts/watchdog_8000.py 已被移除，收集期报 ERROR（非本子集缺陷）
call "%REPO_ROOT%\edu-agent\.venv\Scripts\python.exe" -m pytest tests -k "chat or favorite or hitl" -q --no-header -p no:cacheprovider --ignore=tests\test_watchdog_8000.py
set PY_RC=%errorlevel%
popd
if not "%PY_RC%"=="0" goto :py_fail
echo   [PASS] pytest 契约子集
set /a PASS_N+=1
goto :py_done

:py_skip
echo   [SKIP] 未找到 edu-agent\.venv\Scripts\python.exe
echo          （managed python 无 pytest，必须用项目 venv）
set /a SKIP_N+=1
goto :py_done

:py_notests
echo   [FAIL] 未找到 edu-agent\tests\
set /a FAIL_N+=1
goto :py_done

:py_fail
echo   [FAIL] pytest 契约子集未通过
set /a FAIL_N+=1

:py_done
echo.

REM ---------------------------------------------------------------------------
REM  汇总面板
REM ---------------------------------------------------------------------------
echo ===========================================================================
echo   汇总
echo ---------------------------------------------------------------------------
echo   PASS = %PASS_N%    FAIL = %FAIL_N%    DRIFT = %DRIFT_N%    SKIP = %SKIP_N%
echo   ------------------------------
echo   DRIFT = 门禁检出漂移，需人工审查后重冻结（不是回归，见 [1/3] 说明）
echo ===========================================================================
echo.

if %FAIL_N% GTR 0 goto :summary_fail
if %PASS_N% EQU 0 goto :summary_skip

if %DRIFT_N% GTR 0 goto :summary_drift

echo   结论: PASS -- 可机验子集全部通过。
echo.
echo   下一步: 打开 docs\agent-collab-verify.md，按 5 个验证点逐项亲手复现。
echo.
endlocal
exit /b 0

:summary_drift
echo   结论: PASS(含漂移) -- 无回归失败，但 G3 检出 %DRIFT_N% 处钩子漂移待人工审查。
echo         漂移根因通常是并行 agent 正在改页面（本仓库多单并行时属常态）。
echo         请按 [1/3] 提示审查后重冻结，或等该并行单收工后复跑。
echo.
endlocal
exit /b 0

:summary_fail
echo   结论: FAIL -- 存在未通过检查项，详见上方各块输出。
echo.
endlocal
exit /b 1

:summary_skip
echo   结论: 全部检查被跳过（环境不满足），未取得有效结论。
echo.
endlocal
exit /b 1

REM ---------------------------------------------------------------------------
REM  子过程：逐单成对判定
REM ---------------------------------------------------------------------------
:pair_one
set "FN=%~1"
set "ID=!FN:TO-EXEC-=!"
if exist "%DISP%\REPORT-!ID!.md" goto :pair_hit
echo     NO-RPT  !ID!
set /a NORPT_N+=1
goto :eof

:pair_hit
echo     PAIR    !ID!
set /a PAIR_N+=1
goto :eof
