# -*- coding: utf-8 -*-
# W-NEXT-OPS-001 小单B — full-run 回归门禁一键脚本（承接 TEST-BASE §4 门禁定义 + §7 移交 2）
#
# 门禁断言（唯一权威 = test-reports/TEST-BASE-completion-report.md §4「门禁复信」）：
#   cd edu-agent && .venv\Scripts\python.exe -m pytest tests/ -q -p no:cacheprovider
#   exit code == 0 即 PASS（0 failed；skipped=57 例白名单语义，见 TEST-BASE §4 附表；
#   终态基线 1712P/57S/0F，约 7-8 分钟）
#
# exit code：
#   0 = PASS（门禁通过）
#   1 = FAIL（回归，输出失败清单尾部 50 行；完整日志 logs\gate_fullrun.log）
#   2 = 环境前置不可达（非代码回归，先修环境再跑，不误报给代码侧）
#
# 环境预检（TCP 可达性，超时 3s）：
#   MySQL   硬门：读 .env MYSQL_HOST/MYSQL_PORT，兜底 localhost:3306   —— 不可达 exit 2
#   Redis   硬门：读 .env REDIS_URL，兜底 redis://127.0.0.1:6379/0     —— 不可达 exit 2
#           （conftest 双防污染护栏①每用例清 rl:* 计数器依赖真实 Redis；TEST-BASE §3-1）
#   Milvus  默认硬门：读 .env MILVUS_URI，兜底 http://127.0.0.1:19530 —— 不可达 exit 2
#           ⚠ 降级窗口开关 -AllowMilvusDown：明示放行。理由（2026-09-20 实测登记）：
#             当前环境 Milvus 宿主不可达（8000 /health/detail milvus=error），而 TEST-BASE run7
#             终态基线（1712P/57S/0F）本就是在该降级形态下取得——其 skip 白名单含 2 例
#             Milvus 依赖测试（test_contract_task_m2.py:203 / test_contract_task_vec.py:89，
#             均为无条件 @pytest.mark.skip，Milvus 在不在线都不进跑面）。故 Milvus 离线跑出的
#             门禁结果与 run7 基线构成逐位可比；Milvus 在线恢复后应回到默认严格模式。
#   8000 后端  只 WARN 不阻断：live_backend 系测试在 8000 离线时按 conftest 连接拦截机制 skip
#           （TEST-BASE §3 B 类），门禁仍可 exit 0 但覆盖面缩小——如实打印，不伪装。
#
# 预检目标可用环境变量覆盖（CI/演练用，优先级：env > .env > 内置兜底）：
#   GATE_MYSQL_HOST / GATE_MYSQL_PORT / GATE_REDIS_URL / GATE_MILVUS_URI
#
# 用法：
#   scripts\eval\gate_fullrun.cmd                    # cmd 一键入口（推荐，双击/CI 均可）
#   powershell -File scripts\eval\gate_fullrun.ps1 -PrecheckOnly     # 只跑预检
#   powershell -File scripts\eval\gate_fullrun.ps1 -AllowMilvusDown  # Milvus 降级窗放行
param(
    [switch]$PrecheckOnly,
    [switch]$AllowMilvusDown,
    [switch]$SkipPrecheck
)
$ErrorActionPreference = 'Continue'

$EduRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path    # edu-agent/
$Py      = Join-Path $EduRoot '.venv\Scripts\python.exe'
$EnvFile = Join-Path $EduRoot '.env'
$Log     = Join-Path $EduRoot 'logs\gate_fullrun.log'
$PytestArgs = @('-m', 'pytest', 'tests/', '-q', '-p', 'no:cacheprovider')

# ---------------------------------------------------------------- 工具
function Read-DotEnv([string]$path) {
    $map = @{}
    if (Test-Path $path) {
        foreach ($line in Get-Content -LiteralPath $path -ErrorAction SilentlyContinue) {
            $t = "$line".Trim()
            if ($t -match '^[A-Za-z_][A-Za-z0-9_]*=' ) {
                $idx = $t.IndexOf('=')
                $map[$t.Substring(0, $idx)] = $t.Substring($idx + 1).Trim()
            }
        }
    }
    return $map
}

function Test-Port([string]$h, [int]$p, [int]$ms = 3000) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $c.BeginConnect($h, $p, $null, $null)
        return ($iar.AsyncWaitHandle.WaitOne($ms) -and $c.Connected)
    } catch {
        return $false
    } finally {
        try { $c.Close() } catch {}
    }
}

function Split-UrlAuthority([string]$url) {
    # redis://host:port/db | http://host:port  ->  @(host, port)
    try {
        $u = [Uri]$url
        if ($u.Port -gt 0) { return @($u.Host, $u.Port) }
        if ($u.Scheme -eq 'http' -or $u.Scheme -eq 'https') { return @($u.Host, 80) }
        if ($u.Scheme -eq 'redis') { return @($u.Host, 6379) }
    } catch {}
    return @($null, 0)
}

# ---------------------------------------------------------------- 预检
function Invoke-Precheck {
    $dotenv = Read-DotEnv $EnvFile

    $mysqlHost = if ($env:GATE_MYSQL_HOST) { $env:GATE_MYSQL_HOST }
                 elseif ($dotenv['MYSQL_HOST']) { $dotenv['MYSQL_HOST'] } else { 'localhost' }
    $mysqlPort = if ($env:GATE_MYSQL_PORT) { [int]$env:GATE_MYSQL_PORT }
                 elseif ($dotenv['MYSQL_PORT']) { [int]$dotenv['MYSQL_PORT'] } else { 3306 }
    $redisUrl  = if ($env:GATE_REDIS_URL)  { $env:GATE_REDIS_URL }
                 elseif ($dotenv['REDIS_URL']) { $dotenv['REDIS_URL'] } else { 'redis://127.0.0.1:6379/0' }
    $milvusUri = if ($env:GATE_MILVUS_URI) { $env:GATE_MILVUS_URI }
                 elseif ($dotenv['MILVUS_URI']) { $dotenv['MILVUS_URI'] } else { 'http://127.0.0.1:19530' }

    $rh, $rp = Split-UrlAuthority $redisUrl
    $mh, $mp = Split-UrlAuthority $milvusUri

    Write-Host ("[GATE-PRECHECK] mysql   {0}:{1} ..." -f $mysqlHost, $mysqlPort)
    $mysqlOk = Test-Port $mysqlHost $mysqlPort
    Write-Host ("[GATE-PRECHECK] mysql   {0}:{1} -> {2}" -f $mysqlHost, $mysqlPort, $(if ($mysqlOk) { 'REACHABLE' } else { 'UNREACHABLE' }))

    Write-Host ("[GATE-PRECHECK] redis   {0}:{1} ..." -f $rh, $rp)
    $redisOk = Test-Port $rh $rp
    Write-Host ("[GATE-PRECHECK] redis   {0}:{1} -> {2}" -f $rh, $rp, $(if ($redisOk) { 'REACHABLE' } else { 'UNREACHABLE' }))

    Write-Host ("[GATE-PRECHECK] milvus  {0}:{1} ..." -f $mh, $mp)
    $milvusOk = Test-Port $mh $mp
    Write-Host ("[GATE-PRECHECK] milvus  {0}:{1} -> {2}" -f $mh, $mp, $(if ($milvusOk) { 'REACHABLE' } else { 'UNREACHABLE' }))

    # 8000 只 WARN（live_backend 系 skip 机制，覆盖面差异如实打印）
    $backend = 'DOWN'
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $backend = '200' }
    } catch {}
    if ($backend -eq '200') {
        Write-Host '[GATE-PRECHECK] backend 127.0.0.1:8000 /health -> 200（live_backend 系将真实运行）'
    } else {
        Write-Host '[GATE-PRECHECK] WARN backend 127.0.0.1:8000 /health 不可达 -> live_backend 系将按 conftest 机制 skip，门禁仍可过但覆盖面缩小'
    }

    # ---- 硬门判定
    if (-not $mysqlOk -or -not $redisOk) {
        Write-Host '[GATE] decision=ENV-UNREACHABLE exit=2（MySQL/Redis 不可达——非代码回归，先修环境：MySQL=Windows 服务 3306；Redis=宿主 Docker 容器，见 deploy/README §1.1）'
        return 2
    }
    if (-not $milvusOk) {
        if ($AllowMilvusDown) {
            Write-Host '[GATE-PRECHECK] -AllowMilvusDown 明示放行：与 TEST-BASE run7 终态基线的降级形态一致（task_m2:203/task_vec:89 两例为无条件 skip 白名单，Milvus 在不在线均不进跑面，1712P/57S 构成可比）'
        } else {
            Write-Host '[GATE] decision=ENV-UNREACHABLE exit=2（Milvus 不可达——非代码回归。处置：拉起 Milvus 宿主后重跑；降级窗口确需跑门禁用 -AllowMilvusDown，见脚本头注）'
            return 2
        }
    }
    Write-Host '[GATE-PRECHECK] PASS（硬门全通过）'
    return 0
}

# ---------------------------------------------------------------- 主流程
if (-not $SkipPrecheck) {
    $pc = Invoke-Precheck
    if ($pc -ne 0) { exit $pc }
}
if ($PrecheckOnly) {
    Write-Host '[GATE] -PrecheckOnly 到此结束'
    exit 0
}

if (-not (Test-Path $Py)) {
    Write-Host "[GATE] decision=ENV-UNREACHABLE exit=2（venv python 不存在: $Py —— 先按 deploy/README §2.1 建 venv，非代码回归）"
    exit 2
}

$LogDir = Split-Path $Log -Parent
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

Write-Host ("[GATE] RUN cd {0} && {1} {2}  （TEST-BASE §4 门禁命令；约 7-8 分钟，日志 {3}）" -f $EduRoot, $Py, ($PytestArgs -join ' '), $Log)
$sw = [System.Diagnostics.Stopwatch]::StartNew()

Push-Location $EduRoot
try {
    & $Py @PytestArgs 2>&1 | Tee-Object -FilePath $Log
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
$sw.Stop()
Write-Host ("[GATE] pytest exit={0} elapsed={1:N0}s" -f $code, $sw.Elapsed.TotalSeconds)

if ($code -eq 0) {
    Write-Host "[GATE] decision=PASS exit=0（full-run 回归门禁通过；skipped 构成对照 TEST-BASE §4 白名单 57 例）"
    exit 0
}

Write-Host "[GATE] decision=FAIL exit=$code（回归门禁拦截）——失败清单尾部 50 行如下（完整输出: $Log）："
Write-Host '-------------------- gate_fullrun.log tail 50 --------------------'
Get-Content -LiteralPath $Log -Tail 50
Write-Host '------------------------------------------------------------------'
exit 1
