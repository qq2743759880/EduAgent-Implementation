@echo off
rem W-NEXT-OPS-001 item B - full-run regression gate one-click entry (engine = gate_fullrun.ps1, same dir)
rem NOTE: keep this .cmd pure ASCII - cmd.exe parses batch files in OEM codepage (GBK on zh-CN
rem        hosts), UTF-8 Chinese comments here break parsing (verified 2026-09-20).
rem
rem Usage:
rem   scripts\eval\gate_fullrun.cmd                    full gate (pytest tests/, about 7-8 min)
rem   scripts\eval\gate_fullrun.cmd -PrecheckOnly      env precheck only
rem   scripts\eval\gate_fullrun.cmd -AllowMilvusDown   allow degraded window (see ps1 header)
rem
rem exit code: 0=PASS | 1=regression (prints tail 50 lines of failure log) | 2=env unreachable (not a code regression)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gate_fullrun.ps1" %*
exit /b %ERRORLEVEL%
