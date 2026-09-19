# -*- coding: utf-8 -*-
# W-NEXT-OPS-001 小单A — 看门狗服务化卸载（Windows 任务计划注销）
#
# 行为：
#   1) schtasks /End  结束 EduAgent-Watchdog 正在运行的任务实例（若在跑）
#   2) schtasks /Delete /F  删除任务
#   3) /Query 复核（期望：任务不存在）
#
# 边界（如实）：
#   - /End 只杀任务拉起的看门狗 loop 实例；看门狗此前 DETACHED+BREAKAWAY 拉起的 8000 uvicorn
#     是独立进程，不会被连带杀——卸载看门狗 ≠ 停 8000。要停 8000：
#     node scripts\deploy\deploy.mjs stop
#   - 卸载后 8000 重新失去自愈兜底（无声死亡史见 watchdog_8000.py 头注），请尽快重装：
#     powershell -File scripts\deploy\install_watchdog_task.ps1
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy\uninstall_watchdog_task.ps1
# exit code：0=已删除（或本就不存在）；1=删除失败。
$ErrorActionPreference = 'Continue'
$TaskName = 'EduAgent-Watchdog'

Write-Host "[WATCHDOG-UNINSTALL] task=$TaskName"

# 1) 结束在跑任务实例（不在跑时报错属预期，忽略）
schtasks.exe /End /TN $TaskName *> $null

# 2) 删除任务
schtasks.exe /Delete /TN $TaskName /F | Out-Host
if ($LASTEXITCODE -ne 0) {
    schtasks.exe /Query /TN $TaskName *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WATCHDOG-UNINSTALL] OK 任务本就不存在（幂等）"
        exit 0
    }
    Write-Host "[WATCHDOG-UNINSTALL] FAIL schtasks /Delete exit=$LASTEXITCODE"
    exit 1
}

# 3) 复核
schtasks.exe /Query /TN $TaskName *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "[WATCHDOG-UNINSTALL] FAIL 删除后任务仍可查询到"
    exit 1
}
Write-Host "[WATCHDOG-UNINSTALL] OK 任务已删除（复核：查询不到）"
Write-Host "[WATCHDOG-UNINSTALL] 提醒：8000 uvicorn 不受影响（独立进程）；停止它用 node scripts\deploy\deploy.mjs stop"
exit 0
