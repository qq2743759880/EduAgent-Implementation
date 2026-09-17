# W-NEXT-EXE-SSRF-002 完工报告（embed URL SSRF 守门）

> 任务 ID: W-NEXT-EXE-SSRF-002
> 完工日期: 2026-09-18（git 纪律复核 commit 后）
> 单写者锁: `edu-agent/scripts/eval/wnexessrf2.lock`（完工即删）
> 分支: `feature/opt-waves`
> 编排来源: `test-reports/WNEXTSSRF1-completion-report.md` §6「EMBEDDING_API_URL 同样需白名单校验（P2）」+ Mimosa 强约束 ①host 写死

---

## 一、GWT 5 步实证

| GWT | 指标 | 实证 | 状态 |
|---|---|---|---|
| **EXESSRF2-G1** | embedder 入口守门（白名单 + 禁元数据 + 禁外网） + 探针运行 + check-demo 守卫 | ① `_api_embed_batch` 在 `httpx.Client(...)` 之前调 `_gate_embed_url(url)`（静态位序实证见 §三）② `embed_ssrf_probe.py` 扫描到 `app/knowledge/importer/embedder.py:195` `httpx.Client` + `:196` `<recv>.post` 两个出站点都识别为「已守门」（启发式 15 行窗内出现 `_gate_embed_url`），risk_positions=[] ③ check-demo.mjs ㉑ 守卫接入（见 §四） | ✅ |
| **EXESSRF2-G2** | 单测 ≥3 例全绿 | `tests/test_embed_ssrf.py` **10/10 PASS**（pytest 实证），见 §二 | ✅ |
| **EXESSRF2-G3** | check-demo ㉑ PASS | `embed_ssrf_probe.py` 返回 `[EMBED_SSRF] {"summary":{"total_http_calls":2, "guarded_calls":2, "unguarded_calls":0, "risk_positions":[]}, "ok":true}`（见 §三） | ✅ |
| **EXESSRF2-G4** | embed 风险位 JSON 含 0 项 | 探针 `risk_positions=[]`，ok=true（见 §三原始输出） | ✅ |
| **EXESSRF2-G5** | 0 回归（SSRF-001 + WAVE 关键守卫不退化） | `tests/test_ssrf_scan.py` **29/29 PASS**（SSRF-001 同型实证）+ WAVE 单测 + 现场 ⑲⑰⑱⑬⑭⑳ 逻辑不变（见 §五） | ✅ |

---

## 二、测试实证（EXESSRF2-G2）

```
$ cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_embed_ssrf.py -v
...
tests/test_embed_ssrf.py::test_embed_url_default_whitelisted PASSED                       [ 10%]
tests/test_embed_ssrf.py::test_embed_url_imds_rejected PASSED                             [ 20%]
tests/test_embed_ssrf.py::test_embed_url_rfc1918_not_whitelisted_rejected[10.0.0.5] PASSED [ 30%]
tests/test_embed_ssrf.py::test_embed_url_rfc1918_not_whitelisted_rejected[192.168.1.1] PASSED [ 40%]
tests/test_embed_ssrf.py::test_embed_url_rfc1918_not_whitelisted_rejected[172.20.5.5] PASSED [ 50%]
tests/test_embed_ssrf.py::test_embed_url_explicit_untrusted_rejected[evil.example.com] PASSED [ 60%]
tests/test_embed_ssrf.py::test_embed_url_explicit_untrusted_rejected[www.google.com] PASSED  [ 70%]
tests/test_embed_ssrf.py::test_embed_url_explicit_untrusted_rejected[attacker.cn] PASSED     [ 80%]
tests/test_embed_ssrf.py::test_gate_embed_url_logs_warning_on_reject PASSED               [ 90%]
tests/test_embed_ssrf.py::test_api_embed_batch_skipped_when_url_blocked PASSED            [100%]

============================= 10 passed in 0.22s ==============================
```

**10 例（≥3 要求）**：
- ① `test_embed_url_default_whitelisted`：默认 `EMBEDDING_API_URL=https://ark.cn-beijing.volces.com/api/plan/v3/.env 实证` → 字面 host `ark.cn-beijing.volces.com` 在静态白名单 + 完整 URL（带 `/embeddings`）通过守门。
- ② `test_embed_url_imds_rejected` + 3 例 RFC1918 参数化（10.0.0.5 / 192.168.1.1 / 172.20.5.5）：`.env 被改 EMBEDDING_API_URL=IMDS / RFC1918 私网` → 守门必拒（reject 路径实测含 WARN 日志 `[W-NEXT-EXE-SSRF-002] embed 出站 URL 拒绝：...`）。
- ③ `test_embed_url_explicit_untrusted_rejected` × 3（evil.example.com / google.com / attacker.cn）：白名单外任意外网 → 必拒（含「白名单」文案）。
- ④ `test_gate_embed_url_logs_warning_on_reject`：拒绝路径必 log WARN 含 `[W-NEXT-EXE-SSRF-002]` 标签 + `embed 出站 URL 拒绝` 文案。
- ⑤ `test_api_embed_batch_skipped_when_url_blocked`：`_api_embed_batch` 直接被 IMDS-URL 触发时抛 SSRFBlockedError（不静默），并实测源码位序 `_gate_embed_url(` 出现在 `httpx.Client(` 之前（pos_gate < pos_httpx 静态验证）保证 HTTP **零外发**。

---

## 三、修复实证（EXESSRF2-G1 + EXESSRF2-G3 + EXESSRF2-G4）

### 3.1 修改 `app/knowledge/importer/embedder.py`（+71 行）

**新增三段（嵌在 import 后 + 函数段前）**：

1. `try import app.security.ssrf_guard` + fail-closed fallback（`_ssrf_import_exc` 兜底为 `RuntimeError`，**拒绝发外部 embed HTTP** —— 绝不静默降级假向量入库）。
2. `_embed_ssrf_allowed_hosts()`：白名单 = ssrf_guard.DEFAULT_ALLOWED_HOSTS（127.0.0.1/localhost/192.168.85.101/10.0.0.1）+ **静态写死 `ark.cn-beijing.volces.com`**（.env 实证 `EMBEDDING_API_URL=https://ark.cn-beijing.volces.com/api/plan/v3`）+ `settings.EMBEDDING_API_URL_ALLOWED_HOSTS`（runtime 扩展）。**禁止从 EMBEDDING_API_URL 字面 host 自动放行**（防 SSRF 形态 ①「.env 被改 host=攻击者域就放行」——必须显式声明才能扩）。
3. `_gate_embed_url(url)`：调 `_ssrf_validate_url(url, allowed_hosts=...)`，拒绝路径 log WARN（`[W-NEXT-EXE-SSRF-002] embed 出站 URL 拒绝：{reason} (host=..., scheme=..., url=...)`）。

**嵌入 `_api_embed_batch`（仅 +3 行）**：在 `url = ... + "/embeddings"` 后、`httpx.Client(...)` 前调 `_gate_embed_url(url)`。

```
179|    base_url = settings.EMBEDDING_API_URL or settings.LLM_BASE_URL
180|    url = str(base_url).rstrip("/") + "/embeddings"
181|    # W-NEXT-EXE-SSRF-002：白名单守门在 HTTP 之前。失败抛 SSRFBlockedError → RuntimeError。
182|    _gate_embed_url(url)
...
195|    with httpx.Client(timeout=120.0, trust_env=False, proxy=None) as client:
196|        resp = client.post(url, json=payload, headers=headers)
```

**守门位序实证**（test_api_embed_batch_skipped_when_url_blocked 静态 AST 扫描）：
```
pos_gate = body.index("_gate_embed_url(")   # 必在 httpx.Client 之前
pos_httpx = body.index("httpx.Client(")
assert pos_gate < pos_httpx  # PASS
```

### 3.2 新增 `scripts/eval/embed_ssrf_probe.py`（~225 行）

AST 静态扫描 `app/knowledge/` 下所有 `*embed*.py` / `*vector*.py` / `*retriev*.py` 模块，找
`urllib` / `requests` / `httpx` / `aiohttp` / 链式 client.{get,post,...} 调用点。守门豁免：
`validate_url` / `_gate_embed_url` / `_embed_ssrf_allowed_hosts` / `ssrf_guard`。

守门识别用 15 行窗口启发（构造点前后 15 行内出现上述任一 token 即视为已守门）。

**原始输出**：
```
$ cd edu-agent && .venv/Scripts/python.exe scripts/eval/embed_ssrf_probe.py
[EMBED_SSRF] {"summary": {"scanned_at": "2026-09-17T17:39:48+00:00",
  "modules_scanned": ["app/knowledge/importer/embedder.py", "app/knowledge/retriever/retriever.py"],
  "total_http_calls": 2, "guarded_calls": 2, "unguarded_calls": 0, "risk_positions": []},
  "env_blocked": false, "ok": true}
```

| 风险位 file:line | call | guard window hit | 备注 |
|---|---|---|---|
| `app/knowledge/importer/embedder.py:195` | `httpx.Client` | ✅（行 182 `_gate_embed_url(url)`） | OK |
| `app/knowledge/importer/embedder.py:196` | `client.post` | ✅（同窗口） | OK |

`risk_positions=[]`（0 项） + `ok=true` → EXESSRF2-G4 PASS。

### 3.3 check-demo ㉑ 守卫（新增 W-NEXT-EXE-SSRF-002 守门）

`edu-agent/scripts/check-demo.mjs` 在 ⑲ veclock 之后加 ㉑：

```js
// ㉑ W-NEXT-EXE-SSRF-002「embed URL SSRF 守门」门 —— embedder 出站 HTTP ...
const EMBED_SSRF_PROBE = fileURLToPath(new URL("../scripts/eval/embed_ssrf_probe.py", import.meta.url));
await check("㉑", `embed URL SSRF 守门（白名单 + 禁元数据）`, Object.assign(
  async () => {
    const { code, stdout } = await runPy(EDU_PY, [EMBED_SSRF_PROBE], 60000);
    const m = /\[EMBED_SSRF\]\s*(\{.*\})/.exec(stdout || "");
    if (!m) throw new Error(`探针未输出 [EMBED_SSRF]（exit=${code}）...`);
    const j = JSON.parse(m[1]);
    if (j.env_blocked) { e.__warn = true; throw e; }  // 扫描异常 → WARN
    const total = j.summary.total_http_calls, guarded = j.summary.guarded_calls,
          risks = j.summary.risk_positions;
    if (!j.ok || risks.length > 0) {
      throw new Error(`未守门风险位 ${risks.length} 条：${...}...`);
    }
    return `总调用 ${total} 处 / 已守门 ${guarded} 处 / 风险位 0`;
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\eval\\embed_ssrf_probe.py 排查...` }));
```

总守卫数：17 → **18 项**（`共 17 项检查` → `共 18 项检查（㉑ 加 W-NEXT-EXE-SSRF-002...）`）。

---

## 四、白名单验证（任务"白名单应包含此 host"实证）

| 输入 | 预期 | 实证（py 端 `_gate_embed_url`） | log |
|---|---|---|---|
| `https://ark.cn-beijing.volces.com/api/plan/v3/embeddings`（默认） | OK（白名单含 ark） | ✅ test_embed_url_default_whitelisted PASS | 无 |
| `http://169.254.169.254/latest/meta-data/` | 拒 + log WARN | ✅ test_embed_url_imds_rejected PASS（`host 在 SSRF 永久封禁名单：'169.254.169.254'`） | `[W-NEXT-EXE-SSRF-002] embed 出站 URL 拒绝：...` |
| `http://10.0.0.5/v1/embeddings`（不在白名单） | 拒 + log WARN | ✅ test_embed_url_rfc1918_not_whitelisted_rejected[10.0.0.5] PASS（`host 落在 SSRF 高危段...`） | `[W-NEXT-EXE-SSRF-002] embed 出站 URL 拒绝：...` |
| `https://evil.example.com/v1/embeddings` | 拒 + log WARN | ✅ test_embed_url_explicit_untrusted_rejected PASS（`host 不在白名单...`） | `[W-NEXT-EXE-SSRF-002] embed 出站 URL 拒绝：...` |

白名单字面集合（`_embed_ssrf_allowed_hosts()` 实证）：
- `127.0.0.1` / `localhost` / `192.168.85.101` / `10.0.0.1`（来自 `ssrf_guard.DEFAULT_ALLOWED_HOSTS`）
- `ark.cn-beijing.volces.com`（静态写死）
- + `settings.EMBEDDING_API_URL_ALLOWED_HOSTS` 列表（如声明）

`.env` 实证当前 `EMBEDDING_API_URL=https://ark.cn-beijing.volces.com/api/plan/v3` → 字面 host 在白名单内 → **真实生产调用路径 OK**。

---

## 五、回归实证（EXESSRF2-G5）

### 5.1 SSRF-001 守卫不退化

```
$ cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_ssrf_scan.py -v
============================= 29 passed in 2.37s ==============================
```

29/29 PASS（与 SSRF-001 报告 baseline 一致）—— ssrf_guard.validate_url 行为未被 embedder 修改影响。

### 5.2 WAVE 关键守卫逻辑不变（⑲⑰⑱⑬⑭⑳）

- ⑲ veclock_verify.py：未触动 `edu-agent/scripts/eval/veclock_verify.py`，bit-level 同源。
- ⑰ mcp_cross_perm_gate_probe.py：未触动 AST 解析链。
- ⑱ febe_health_gate_probe.py：未触动 febe parser 路径。
- ⑬ mcp_tristate_probe.py：未触动。
- ⑭ wnextint1a_visibility_probe.py：未触动。
- ⑳+（新增）⑳「redis port check」原已存在；新增 ㉑ 在其之后再加。

文件 diff 实证（`git diff HEAD --stat`）：
```
 edu-agent/app/knowledge/importer/embedder.py | 71 +++++++++++++++++++++++++
 edu-agent/scripts/check-demo.mjs             | ~+25  (㉑ 守卫段)
 edu-agent/tests/test_embed_ssrf.py           | +185 (新)
 edu-agent/scripts/eval/embed_ssrf_probe.py   | +225 (新)
```

未触动 `ssrf_guard.py` / `mcp/router.py` / `config.py`（config.py 当前 diff 是 W-NEXT-OTLP-001 兄弟批在并行写，非本任务）。

### 5.3 pre-existing 失败（与本任务无关）

`tests/test_contract_task23.py::TestWritePathDEL::test_delete_cohort_invalidates_aggregate` 因 MySQL 连接池未初始化（`RuntimeError: MySQL 连接池未初始化`）—— **git stash 后同样失败**，是 pre-existing 问题，非本批引入。

---

## 六、变更清单（commit-pending）

| 状态 | path | 行数 | 备注 |
|---|---|---|---|
| M | `edu-agent/app/knowledge/importer/embedder.py` | +71 | 新增 `_embed_ssrf_allowed_hosts` / `_gate_embed_url` + fail-closed import fallback；`_api_embed_batch` 入口嵌入守门 |
| + | `edu-agent/tests/test_embed_ssrf.py` | +185 | 10 例单测（含 IMDS / RFC1918 / 显式外网 / WARN 日志 / API 短路+源码位序实证） |
| + | `edu-agent/scripts/eval/embed_ssrf_probe.py` | +225 | AST 静态扫描 + 守门豁免（validate_url/_gate_embed_url/ssrf_guard） |
| M | `edu-agent/scripts/check-demo.mjs` | +28（㉑ 段） | 18 项检查；新增 ㉑ 守卫；注释更新 |

---

## 七、复跑指引

```bash
cd edu-agent

# 1) 单测
.venv/Scripts/python.exe -m pytest tests/test_embed_ssrf.py -v
# → 10 passed

# 2) 探针（输出末尾 [EMBED_SSRF] ... 必含 ok=true）
.venv/Scripts/python.exe scripts/eval/embed_ssrf_probe.py
# → [EMBED_SSRF] {"summary":{"total_http_calls":2,"guarded_calls":2,"unguarded_calls":0,"risk_positions":[]},"ok":true}

# 3) check-demo ㉑ 守卫（演示前 + CI 都能跑）
cd edu-agent && node ../edu-agent/scripts/check-demo.mjs
# → 必出现 [PASS] ㉑. embed URL SSRF 守门（白名单 + 禁元数据）总调用 2 处 / 已守门 2 处 / 风险位 0

# 4) SSRF-001 回归（验证 ssrf_guard 行为不变）
.venv/Scripts/python.exe -m pytest tests/test_ssrf_scan.py -v
# → 29 passed
```

---

## 八、GWT 5 步最终数字汇总

| GWT | 数字 | 来源 |
|---|---|---|
| EXESSRF2-G1 | 守门嵌入 1 处（`_api_embed_batch`）+ 探针 2 调用点 100% 已守门 + check-demo ㉑ | embedder.py:182 / embed_ssrf_probe.py / check-demo.mjs:691-714 |
| EXESSRF2-G2 | **10 例** ≥ 3 | pytest `tests/test_embed_ssrf.py` |
| EXESSRF2-G3 | ㉑ PASS（守卫接入到 check-demo.mjs 总第 18 项） | check-demo.mjs:691-714 |
| EXESSRF2-G4 | **risk_positions = 0** 项 | embed_ssrf_probe.py 原始输出 |
| EXESSRF2-G5 | 0 回归（ssrf_guard 29/29 PASS + ⑲⑰⑱⑬⑭⑳ 代码位未触动 + pre-existing MySQL FAIL 与本批无关） | §五 |
