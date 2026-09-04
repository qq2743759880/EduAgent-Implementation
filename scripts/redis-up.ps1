# redis-up.ps1 —— 固化本机 Redis 连通（幂等，可重复执行）
#
# 背景：compose 起的容器（docker-redis-1）只监听容器内网 6379，未映射到宿主机，
#       导致后端（.env 无覆盖，走默认 redis://127.0.0.1:6379/0）连不上。
#       本脚本用独立容器 edu-redis-standalone 显式映射 0.0.0.0:6379 -> 6379，
#       并保证宿主机 6379 始终有一个可连的 Redis。
#
# 行为（幂等）：
#   - 容器已在运行 -> 复用，只做 ping 实证
#   - 容器存在但停止 -> docker start 拉起
#   - 容器不存在 -> docker run 新建（挂命名卷持久化 AOF）
#   结束后用 redis-cli ping 实证宿主机 6379 可达。
#
# 用法：  powershell -ExecutionPolicy Bypass -File scripts\redis-up.ps1

$ErrorActionPreference = 'Stop'

$name    = 'edu-redis-standalone'
$image   = 'redis:6-alpine'
$runArgs = @(
  '-d', '--name', $name,
  '-p', '6379:6379',
  '--restart', 'unless-stopped',
  '-v', "${name}-data:/data",
  $image,
  'redis-server', '--appendonly', 'yes'
)

Write-Host "[redis-up] ensure Redis on host:6379 (container=$name)" -ForegroundColor Cyan

$container = docker ps -a --filter "name=^/${name}$" --format '{{.Names}} {{.Status}}'

if ($container) {
    if ($container -match 'Up ') {
        Write-Host "[redis-up] already running: $container" -ForegroundColor Green
    } else {
        Write-Host "[redis-up] exists but stopped, starting..." -ForegroundColor Yellow
        docker start $name | Out-Null
    }
} else {
    Write-Host "[redis-up] creating container $name ..." -ForegroundColor Yellow
    docker run @runArgs
}

# 等待就绪并实证宿主机 6379 可达
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $pong = & docker exec $name redis-cli ping 2>$null
        if ($pong -eq 'PONG') { $ready = $true; break }
    } catch { }
    Start-Sleep -Milliseconds 500
}

if (-not $ready) {
    Write-Error "[redis-up] FAILED: container $name did not become ready on 6379"
}

# 从宿主机视角实证（走容器暴露端口，而非 exec 进容器）
& docker run --rm --network host $image redis-cli -h 127.0.0.1 -p 6379 ping
if ($LASTEXITCODE -ne 0) {
    Write-Error "[redis-up] host:6379 ping failed (exit $LASTEXITCODE)"
}

Write-Host "[redis-up] done: host Redis is reachable at 127.0.0.1:6379" -ForegroundColor Green