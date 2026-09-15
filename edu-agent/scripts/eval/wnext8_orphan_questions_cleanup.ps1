<#
W-NEXT-8 任务五：历史孤儿题数据治理（批判 T7-C2）——一次性清理脚本
================================================================
背景：`question.yn=1` 且 `question_bank.yn=0` 的孤儿题（题库已软删、题目仍有效），
      下游按 `question.yn=1` 统计会把它们算进已删题库。
本脚本把「只读复核 → mysqldump 备份 → 人工确认 → 软删 → 前后行数复核」固化为一步，
**默认 dry-run（只读+备份），必须显式 -Execute 才执行 UPDATE**（人工确认闸门）。

用法（在 edu-agent/ 下）：
  powershell -File scripts\eval\wnext8_orphan_questions_cleanup.ps1              # dry-run：复核 + 备份
  powershell -File scripts\eval\wnext8_orphan_questions_cleanup.ps1 -Execute      # 备份 + 软删（yn=0）
  powershell -File scripts\eval\wnext8_orphan_questions_cleanup.ps1 -Ids 10537,10538 -Execute

安全约定：
- 只做 `question.yn=1 → 0` 的软删；不删行、不改 question_bank（已 yn=0）。
- UPDATE 带 `AND yn=1` 条件（幂等：重复执行第二次影响 0 行）。
- 备份落 deploy/backups/（已 .gitignore），执行前校验备份文件非空。
#>
param(
  [int[]]$Ids = @(10537, 10538, 10539),
  [switch]$Execute
)

$ErrorActionPreference = "Stop"

# ---------- 定位路径与客户端 ----------
$Here       = Split-Path -Parent $MyInvocation.MyCommand.Path   # edu-agent/scripts/eval
$BackendDir = Resolve-Path (Join-Path $Here "..\..")            # edu-agent
$RepoRoot   = Resolve-Path (Join-Path $BackendDir "..")         # 工作区根
$BackupDir  = Join-Path $RepoRoot "deploy\backups"
$EnvFile    = Join-Path $BackendDir ".env"

function Resolve-MySqlTool([string]$Name) {
  $cmd = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $fallback = "C:\Program Files\MySQL\MySQL Server 8.0\bin\$Name.exe"
  if (Test-Path $fallback) { return $fallback }
  throw "未找到 $Name.exe（请把 MySQL 8.0 bin 加入 PATH）"
}
$mysql    = Resolve-MySqlTool "mysql"
$mysqldump = Resolve-MySqlTool "mysqldump"

# ---------- 凭据：只从 .env 读，不落盘不打印 ----------
if (-not (Test-Path $EnvFile)) { throw "未找到 $EnvFile" }
$line = Select-String -Path $EnvFile -Pattern '^\s*MYSQL_PASSWORD\s*=\s*(.*)$' | Select-Object -First 1
if (-not $line) { throw ".env 缺 MYSQL_PASSWORD" }
$env:MYSQL_PWD = $line.Matches[0].Groups[1].Value.Trim()

$idList = ($Ids -join ",")
$OrphanSql = "SELECT q.id, q.question_code, q.bank_id, q.yn AS q_yn, b.yn AS b_yn " +
             "FROM question q JOIN question_bank b ON q.bank_id = b.id " +
             "WHERE q.yn = 1 AND b.yn = 0 ORDER BY q.id"
$OrphanCountSql = "SELECT COUNT(*) FROM question q JOIN question_bank b ON q.bank_id = b.id WHERE q.yn = 1 AND b.yn = 0"
$TargetCountSql = "SELECT COUNT(*) FROM question WHERE yn = 1 AND id IN ($idList)"
$BankIdsSql = "SELECT DISTINCT bank_id FROM question WHERE id IN ($idList) ORDER BY bank_id"

function Invoke-Sql([string]$Sql) {
  & $mysql -uroot --default-character-set=utf8mb4 -D edu -N -B -e $Sql
  if ($LASTEXITCODE -ne 0) { throw "mysql 执行失败(exit=$LASTEXITCODE): $Sql" }
}

# ---------- ① 只读复核 ----------
Write-Host "=== ① 只读复核（孤儿题全量 + 本批目标） ===" -ForegroundColor Cyan
$orphans = @(Invoke-Sql $OrphanSql)
Write-Host "question.yn=1 且 question_bank.yn=0 的孤儿题："
$orphans | ForEach-Object { Write-Host "  $_" }
$orphanCount = [int](Invoke-Sql $OrphanCountSql)
$targetCount = [int](Invoke-Sql $TargetCountSql)
$bankIds = @(Invoke-Sql $BankIdsSql)
Write-Host "孤儿题总数 = $orphanCount；本批目标 id=[$idList] 中当前 yn=1 的 = $targetCount；涉及题库 bank_id=[$($bankIds -join ',')]"

# ---------- ② 备份（幂等：每次执行都重新备份） ----------
Write-Host "`n=== ② mysqldump 备份相关行 ===" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp  = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $BackupDir "wnext8_orphan_questions_$stamp.sql"

& $mysqldump -uroot --default-character-set=utf8mb4 --no-create-info --skip-add-locks `
    "--where=id IN ($idList)" --result-file="$backup" edu question
if ($LASTEXITCODE -ne 0) { throw "mysqldump question 失败(exit=$LASTEXITCODE)" }
if ($bankIds.Count -gt 0) {
  # 第二张表追加：用临时文件拼接字节，避免 Powershell 管道引入 BOM/换行改写（导入端可直接 source）
  $tmp = "$backup.bank.tmp"
  & $mysqldump -uroot --default-character-set=utf8mb4 --no-create-info --skip-add-locks `
      "--where=id IN ($($bankIds -join ','))" --result-file="$tmp" edu question_bank
  if ($LASTEXITCODE -ne 0) { throw "mysqldump question_bank 失败(exit=$LASTEXITCODE)" }
  $bytes = [System.IO.File]::ReadAllBytes($backup) + [System.IO.File]::ReadAllBytes($tmp)
  [System.IO.File]::WriteAllBytes($backup, $bytes)
  Remove-Item $tmp -Force
}
$size = (Get-Item $backup).Length
if ($size -le 0) { throw "备份文件为空：$backup（中止，不执行任何写操作）" }
Write-Host "备份落盘：$backup（$size bytes）"
Write-Host "备份内 INSERT 行数：$((Select-String -Path $backup -Pattern '^INSERT INTO' -AllMatches).Count) 条 INSERT 语句"

# ---------- ③ 人工确认闸门 ----------
if (-not $Execute) {
  Write-Host "`n=== ③ DRY-RUN（未执行 UPDATE） ===" -ForegroundColor Yellow
  Write-Host "确认备份有效后，重新运行并加 -Execute 才会软删："
  Write-Host "  powershell -File scripts\eval\wnext8_orphan_questions_cleanup.ps1 -Execute"
  Write-Host "预演 SQL：UPDATE question SET yn=0 WHERE id IN ($idList) AND yn=1  -- 预计影响 $targetCount 行"
  exit 0
}

# ---------- ④ 软删（幂等条件更新） ----------
Write-Host "`n=== ④ 执行软删（-Execute 已确认） ===" -ForegroundColor Cyan
$before = [int](Invoke-Sql $OrphanCountSql)
Invoke-Sql "UPDATE question SET yn = 0 WHERE yn = 1 AND id IN ($idList)" | Out-Null
$after = [int](Invoke-Sql $OrphanCountSql)
Write-Host "清理前孤儿题行数 = $before → 清理后 = $after（期望 0）"

# ---------- ⑤ 复核 ----------
Write-Host "`n=== ⑤ 复核（GWT：本批范围 = 0 行） ===" -ForegroundColor Cyan
$left = @(Invoke-Sql $OrphanSql)
if ($left.Count -eq 0) { Write-Host "PASS：question.yn=1 AND question_bank.yn=0 = 0 行" -ForegroundColor Green }
else { Write-Host "FAIL：仍剩 $($left.Count) 行：`n$($left -join "`n")" -ForegroundColor Red; exit 1 }
Write-Host "备份路径：$backup"
exit 0