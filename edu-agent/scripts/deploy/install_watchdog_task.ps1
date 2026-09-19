# -*- coding: utf-8 -*-
# W-NEXT-OPS-001 小单A — 看门狗服务化安装（Windows 任务计划注册）
#
# STABILITY P0-A 承接：「看门狗非免死金牌——它自己不在岗就没人拉起」。
# 手工常驻版（前台/后台裸进程）随 agent 会话/终端回收而亡（STABILITY 取证：外部 TerminateProcess 史），
# 本脚本把它注册为 Windows 计划任务「EduAgent-Watchdog」：
#   触发器① BootTrigger  开机延迟 60s 启动
#   触发器② TimeTrigger  每 5 分钟重复触发（无限期；WakeToRun=false，不主动唤醒睡眠机器）
#   动作     edu-agent\.venv\Scripts\python.exe  scripts\watchdog_8000.py   （loop 常驻模式）
#
# ⚠ 设计差异声明（真实契约优先于任务书字面，AGENTS.md 教训 8 同款纪律）：
#   任务书曾写「每 5 分钟唤醒执行 watchdog_8000.py --once（--once 已存在：单次探活+按需拉起）」。
#   实读 watchdog_8000.py：--once = 单次探活、健康 exit 0 / 不健康 exit 1、**不拉起**（--once 用法注释
#   第 21 行 + run_once() 实现均无 spawn 路径）。每 5 分钟一次的 --once 永远无法复活 8000，
#   也无法复活已死的看门狗本身 → 与 P0-A 意图相悖。
#   故任务动作取 watchdog_8000.py 无参（loop 模式）：30s 探活 / 3 连败 / 冷却 90s / 僵尸清理 /
#   三级降级拉起，全部复用本体既有逻辑（本脚本零改动 watchdog_8000.py，守红线）。
#   每 5 分钟的重复触发 = 「看门狗的看门狗」：loop 实例在岗时，pid 文件防重入 +
#   MultipleInstancesPolicy=IgnoreNew 使触发为 no-op；loop 实例死亡（≤5 分钟内）由下次触发重拉。
#
# 用法（管理员 PowerShell；InteractiveToken 形态，注册到当前用户）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy\install_watchdog_task.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy\install_watchdog_task.ps1 -StopExisting
#       ^ 检测到手工常驻版看门狗在岗时自动 --stop，防双实例（注册前必做）
#   加 -Force 覆盖重注册（已存在 EduAgent-Watchdog 时先删后建）
#
# 边界（如实）：InteractiveToken 形态 = 用户登录后任务才可运行；「开机延迟 60s」在未登录时会等
# StartWhenAvailable 到登录后补跑。真无人值守（不登录也拉起）需改 S4U/服务账号形态，
# 属服务化 v2 待办（见 test-reports/OPS1-completion-report.md P0 自批判）。
#
# exit code：0=注册成功或已存在跳过；1=失败（原因见输出）。
param(
    [switch]$StopExisting,
    [switch]$Force
)
# 注：必须 Continue——schtasks 查无此任务时会写 stderr（"系统找不到指定的文件"），
# Stop + stderr 重定向会把它升级成 terminating 异常，误伤"任务不存在=可注册"的正常分支
# （PS 5.1 实测踩坑，2026-09-20）。脚本判定一律以 $LASTEXITCODE 为准。
$ErrorActionPreference = 'Continue'

$TaskName = 'EduAgent-Watchdog'
$EduRoot  = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path   # edu-agent/
$PyExe    = Join-Path $EduRoot '.venv\Scripts\python.exe'
$WdScript = Join-Path $EduRoot 'scripts\watchdog_8000.py'
$PidFile  = Join-Path $EduRoot 'logs\watchdog_8000.pid'

function Main {
    Write-Host "[WATCHDOG-INSTALL] task=$TaskName edu_root=$EduRoot"

    # ---- 0) 前置文件检查
    if (-not (Test-Path $PyExe))    { Write-Host "[WATCHDOG-INSTALL] FAIL venv python 不存在: $PyExe（先按 deploy/README §2.1 建 venv）"; return 1 }
    if (-not (Test-Path $WdScript)) { Write-Host "[WATCHDOG-INSTALL] FAIL 看门狗脚本不存在: $WdScript"; return 1 }

    # ---- 1) 查重（已存在则跳过；-Force 先删后建）
    schtasks.exe /Query /TN $TaskName *> $null
    if ($LASTEXITCODE -eq 0) {
        if (-not $Force) {
            Write-Host "[WATCHDOG-INSTALL] SKIP 任务已存在（查重命中，幂等跳过；重注册请加 -Force）"
            schtasks.exe /Query /TN $TaskName /FO LIST | Out-Host
            return 0
        }
        Write-Host "[WATCHDOG-INSTALL] -Force：删除既有任务后重注册"
        schtasks.exe /Delete /TN $TaskName /F | Out-Null
    }

    # ---- 2) 手工常驻版检测（防双实例：两实例会争 pid 文件，后者拒启 exit 2，功能无损但留噪音）
    if (Test-Path $PidFile) {
        $oldPid = 0
        try { $oldPid = [int](Get-Content $PidFile -ErrorAction Stop | Select-Object -First 1) } catch {}
        $cmdline = ''
        if ($oldPid -gt 0) {
            try { $cmdline = (Get-CimInstance Win32_Process -Filter "ProcessId=$oldPid" -ErrorAction Stop).CommandLine } catch {}
        }
        if ($cmdline -and $cmdline -like '*watchdog_8000.py*') {
            if ($StopExisting) {
                Write-Host "[WATCHDOG-INSTALL] 手工常驻看门狗在岗 pid=$oldPid → -StopExisting 自动 --stop"
                & $PyExe $WdScript --stop
            } else {
                Write-Host "[WATCHDOG-INSTALL] FAIL 手工常驻看门狗在岗 pid=$oldPid（防双实例）。"
                Write-Host "  处置：powershell -File scripts\deploy\install_watchdog_task.ps1 -StopExisting"
                Write-Host "  或手动：$PyExe scripts\watchdog_8000.py --stop"
                return 1
            }
        } elseif ($oldPid -gt 0) {
            Write-Host "[WATCHDOG-INSTALL] pid 文件为陈旧残留 pid=$oldPid（进程不在或非看门狗）→ 忽略，loop 实例启动时会自愈替换"
        }
    }

    # ---- 3) 生成任务 XML（BootTrigger delay 60s + TimeTrigger 每 5 分钟无限重复）
    $sid  = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $startBoundary = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>EduAgent 8000 uvicorn watchdog (W-NEXT-OPS-001). Boot trigger (lag 60s) + 5-min repetition. Action = watchdog_8000.py loop mode (30s probe / 3-strike / cooldown / zombie cleanup / respawn). 5-min retrigger = watchdog-of-the-watchdog; pid-file dedup + IgnoreNew make triggers no-ops while alive.</Description>
    <Author>$user</Author>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT60S</Delay>
    </BootTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>PT5M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>$startBoundary</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$sid</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <Duration>PT10M</Duration>
      <WaitTimeout>PT1H</WaitTimeout>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$PyExe</Command>
      <Arguments>"$WdScript"</Arguments>
      <WorkingDirectory>$EduRoot</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
    # ExecutionTimeLimit=PT0S 是关键：loop 常驻模式无自然终点，默认 72h 时限会把看门狗定时杀掉
    $xmlPath = Join-Path $env:TEMP 'eduagent-watchdog-task.xml'
    $xml | Out-File -FilePath $xmlPath -Encoding Unicode -Force
    Write-Host "[WATCHDOG-INSTALL] 任务 XML 已生成: $xmlPath"

    # ---- 4) 注册
    schtasks.exe /Create /F /TN $TaskName /XML $xmlPath | Out-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WATCHDOG-INSTALL] FAIL schtasks /Create exit=$LASTEXITCODE"
        return 1
    }

    # ---- 5) 注册后状态回显
    Write-Host "[WATCHDOG-INSTALL] 注册完成，任务状态："
    schtasks.exe /Query /TN $TaskName /V /FO LIST | Out-Host
    Write-Host "[WATCHDOG-INSTALL] OK 立即拉起：schtasks /Run /TN $TaskName"
    Write-Host "[WATCHDOG-INSTALL] OK 卸载：powershell -File scripts\deploy\uninstall_watchdog_task.ps1"
    Write-Host "[WATCHDOG-INSTALL] OK 事件/证据：edu-agent\logs\watchdog_8000_events.log"
    return 0
}

exit Main
