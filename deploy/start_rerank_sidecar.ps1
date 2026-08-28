# task-R1-② Rerank sidecar 部署启动脚本（P0 批判落实批次）
# 独立进程承载 BGE-reranker GPU 推理，主应用经 HTTP 调 sidecar（不阻塞主事件循环）。
# 启动后访问 http://127.0.0.1:8601/health 应返回 200（model_loaded=true）。
#
# 用法（在项目根 edu-agent/ 下执行）：
#   pwsh deploy/start_rerank_sidecar.ps1          # 前台运行（调试）
#   pwsh deploy/start_rerank_sidecar.ps1 -Background  # 后台守护（生产/测试窗口）
param(
    [int]$Port = 8601,
    [string]$Host = "127.0.0.1",
    [switch]$Background
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot ".." "edu-agent")
Set-Location $root

$venv = Join-Path $root ".venv" "Scripts" "python.exe"
if (-not (Test-Path $venv)) { throw "venv 未找到: $venv" }

$cmd = "& '$venv' -m uvicorn app.rerank_service.main:app --host $Host --port $Port"
Write-Host "[rerank-sidecar] 启动: $cmd"

if ($Background) {
    $log = Join-Path $root "logs" "rerank_sidecar.log"
    New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
    Start-Process -FilePath $venv -ArgumentList @("-m","uvicorn","app.rerank_service.main:app","--host",$Host,"--port",$Port) `
        -RedirectStandardOutput $log -RedirectStandardError $log -WindowStyle Hidden
    Write-Host "[rerank-sidecar] 后台已启动，日志: $log"
    # 等待 /health 就绪
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $h = Invoke-RestMethod -Uri "http://${Host}:${Port}/health" -TimeoutSec 2
            Write-Host ("[rerank-sidecar] /health OK: model_loaded={0} device={1}" -f $h.model_loaded, $h.device)
            exit 0
        } catch { Start-Sleep -Seconds 1 }
    }
    Write-Warning "[rerank-sidecar] /health 未在 30s 内就绪，请检查日志"
} else {
    Invoke-Expression $cmd
}
