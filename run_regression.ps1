$env:NO_PROXY="127.0.0.1,localhost"
$env:no_proxy="127.0.0.1,localhost"

Write-Host "WAITING_FOR_SERVICE..."
$i=0
do {
    Start-Sleep 10
    try {
        $r = curl.exe -s --noproxy "*" -o NUL -w "%{http_code}" http://127.0.0.1:8000/health -m 3
        if ($r -eq "200") { break }
    } catch {}
    $i++
    Write-Host "  waiting ${i}..."
} while ($i -lt 18)
Write-Host "HEALTH=$r"

Set-Location edu-agent

# 1. course_domain pytest
Write-Host "`n=== COURSE_DOMAIN === "
.\\.venv\Scripts\python.exe -X utf8 -m pytest tests/test_course_domain.py -q 2>&1 | Select-String -NotMatch "INFO|WARNING|DEBUG|^[0-9]{2}:"

# 2. smoke test
Write-Host "`n=== SMOKE_TASK11 === "
.\\.venv\Scripts\python.exe -X utf8 scripts/_smoke_task11.py 2>&1 | Select-Object -Last 6

# 3. judge verification
Write-Host "`n=== JUDGE_VERIFY === "
.\\.venv\Scripts\python.exe -X utf8 -c "
import json, urllib.request, urllib.error
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def h(m,p,**kw):
    req=urllib.request.Request('http://127.0.0.1:8000'+p,headers=kw.get('h',{}))
    try:
        with op.open(req) as r: return r.status,json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code,json.loads(e.read())

# R1
s,j=h('GET','/api/knowledge/partitions');print(f'R1a_anon_parts:{s}_{j.get(\"code\")}')
s,j=h('GET','/api/mcp/servers',h={'X-Force-Role':'admin'});print(f'R1b_force_mcp:{s}_{j.get(\"code\")}')

# R2
s,j=h('GET','/api/series/2628/cohorts')
if s==200 and j.get('code')==0:
    d=j.get('data',{})
    pm=d.get('page_meta',{})
    n=len(d.get('items',[]))
    print(f'R2a_cohort_shell:{s}_items={n}_pm.has_more={pm.get(\"has_more\")}_pm.total={pm.get(\"total\")}')
else:
    print(f'R2a_cohort_FAIL:{s}_{j}')

# R3
s,j=h('GET','/api/nonexistent');print(f'R3a_404_shell:{s}_{j.get(\"code\")}_data={j.get(\"data\")}')

# R4
s,j=h('GET','/api/series',h={'Authorization':'Bearer bad'});print(f'R4a_bad_token:{s}_{j.get(\"code\")}')

# S5
s,j=h('GET','/api/series?price_min=9999&price_max=100');print(f'S5a_price_invert:{s}_{j.get(\"code\")}')

# S6
s,j=h('GET','/api/cohorts/99999999');print(f'S6a_offline_cohort:{s}_{j.get(\"code\")}')

print('ALL_DONE')
"
Write-Host "`n=== REGRESSION_COMPLETE ==="

# ===== W4 门禁（防复生）：C2 page_meta 双轨清零 + C4 respbar 演示残留清零 =====
Write-Host "`n=== W4_GATE === "
$gateScript = Join-Path $PSScriptRoot 'scripts\gate-w4-critique.mjs'
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if ($null -eq $nodeCmd) {
    Write-Host "W4_GATE_SKIPPED: 未检测到 node，跳过 W4 门禁（不中断回归）。"
} else {
    & node $gateScript 2>&1 | Select-Object -Last 40
    Write-Host "W4_GATE_EXIT=$LASTEXITCODE"
}
Write-Host "`n=== ALL_DONE_W4 ==="