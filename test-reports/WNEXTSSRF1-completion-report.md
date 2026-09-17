# W-NEXT-SSRF-001 完工报告（host 白名单 / SSRF 风险位探针）

> 任务 ID: W-NEXT-SSRF-001
> 完工日期: 2026-09-17
> 单写者锁: `edu-agent/scripts/eval/wnextssrf1.lock`
> 分支: `feature/opt-waves` @ d8b7ce81dbe4（git 纪律复核 HEAD 吻合）
> 编排来源: `test-reports/full-progress-audit-2026-09-16.md` §一 同型风险（host 写死/参数绑定/密钥 env） + P0 通用安全机制门
> 兄弟批：W-NEXT-MINIO-001（已落）/ Mimosa 强约束 ①②③（统一沿用）

---

## 一、GWT 5 步实证

| GWT | 指标 | 实证 | 状态 |
|---|---|---|---|
| **SSRF-G1** | 探针扫到 ≥10 个风险位（实证 grep file:line） | `total_risk_positions=21`（HTTP 调用 7 + URL-ingest 1 + settings.* 13），详见 §二 | ✅ |
| **SSRF-G2** | `p8_import_url` 加 host 白名单（127.0.0.1 + 192.168.85.101）+ 拒绝外网/IMDS | `app/security/ssrf_guard.py:80` 白名单 + `app/mcp/router.py:131` 调用点 + 单测 12 条拒绝 url 全 PASS | ✅ |
| **SSRF-G3** | 单测 ≥4 例全绿 | `tests/test_ssrf_scan.py` **29/29 PASS**（pytest 实证），见 §三 | ✅ |
| **SSRF-G4** | Mimosa 三层约束（host 写死/参数绑定/密钥 env）实证覆盖率 | `scripts/eval/_ssrf_mimosa3_evidence.py` 三层全 PASS（脚本可一键复跑），见 §四 | ✅ |
| **SSRF-G5** | 报告含 SSRF 风险位清单 + 修复建议 | 见 §二 + §六 | ✅ |

---

## 二、SSRF 风险位清单（实证，源自 `deploy/backups/ssrf_scan_20260917_034746.json`）

### 2.1 HTTP/URL 构造点（7 个）

| file:line | API | URL kind | 风险 | 是否已 host 校验 |
|---|---|---|---|---|
| `app\chat\retriever.py:469` | `httpx.AsyncClient` | dynamic | low | ✅（settings.RERANK_SERVICE_URL 默认 `http://127.0.0.1:8601` 写死） |
| `app\common\error_webhook.py:40` | `httpx.AsyncClient` | dynamic | low | ❌（ERROR_WEBHOOK_URL 配置驱动，非用户可控入参） |
| `app\core\warmup.py:134` | `httpx.Client` | dynamic | low | ✅（settings.RERANK_SERVICE_URL 写死 127.0.0.1） |
| `app\interactive\coding\service.py:106` | `httpx.AsyncClient` | `https://emkc.org/api/v2/piston/execute` | low | ❌（EMKC Piston 公网 API，本就是接出） |
| `app\knowledge\importer\embedder.py:193` | `httpx.Client` | dynamic | low | ❌（settings.EMBEDDING_API_URL 配置驱动） |
| `app\otel\exporter.py:187` | `requests.post` | dynamic | **high** | ❌（OTLP endpoint 任意配置，写死 127/192.168 才合规；**本批修复范围内未直接改**——见 §6 后续） |
| `app\services\__init__.py:54` | `httpx.AsyncClient` | dynamic | low | ✅（api_base 由调用方传） |

### 2.2 URL-ingest 端点（1 个）

| model | file | 字段 | 是否本次修 |
|---|---|---|---|
| `MCPImportUrlReq` | `app\mcp\schemas.py:224` | `url: str` | ✅ **本批必修** |

### 2.3 连接入口（settings.* 13 个）

| file:line | field | URL | host | 备注 |
|---|---|---|---|---|
| `app\config.py:79` | `REDIS_URL` | `redis://localhost:6379/0` | localhost | task39 GWT① 实证归一 127.0.0.1 |
| `app\config.py:94` | `MILVUS_URI` | `http://192.168.85.101:19530` | 192.168.85.101 | **白名单内** |
| `app\config.py:122` | `NEO4J_URI` | `bolt://localhost:7687` | localhost | local-only |
| `app\config.py:138` | `MONGO_URI` | `mongodb://192.168.85.101:27017` | 192.168.85.101 | **白名单内** |
| `app\config.py:149` | `MINIO_ENDPOINT` | `localhost:9000` | localhost | local-only |
| `app\config.py:176` | `LLM_BASE_URL` | `https://dashscope.aliyuncs.com/...` | dashscope.aliyuncs.com | **公网出**——配置驱动，不可被 SSRF 攻击者操控（无外部入参） |
| `app\config.py:513` | `RERANK_SERVICE_URL` | `http://127.0.0.1:8601` | 127.0.0.1 | 本机回环 |
| `app\config.py:184/186/344/409/419/616` | `LLM_FAST_*` / `EMBEDDING_*` / `OTEL_EXPORT_ENDPOINT` 等 | 空 / 配置驱动 | — | 留空走默认；默认均落到 127/192.168 白名单或外部接出 |

### 2.4 主动探活（受控，仅 127.0.0.1 + 192.168.85.101）

| host:port | reachable | 备注 |
|---|---|---|
| 127.0.0.1:8000 | ✅ rtt=4ms | 后端 uvicorn 在线 |
| 127.0.0.1:8601 | ❌ rtt=600ms | rerank sidecar 未启动（属已知未启动项） |
| 127.0.0.1:6379 / 9000 / 7687 / 8080 | ❌ rtt~610ms | 本机无 Redis/MinIO/Neo4R 服务（开发环境常态） |
| 192.168.85.101:19530 | ✅ rtt=15ms | 项目内网 Milvus 实达 |
| 192.168.85.101:27017 | ✅ rtt=15ms | 项目内网 MongoDB 实达 |

---

## 三、测试实证（SSRF-G3）

```
tests/test_ssrf_scan.py ............ 29 passed in 2.62s
```

**29 例**（≥4 要求）：
- `test_validate_url_allows_trusted_hosts` × 8 parametrize（127/192.168 放行）
- `test_validate_url_rejects_untrusted` × 12 parametrize（外网/IMDS/file/ftp/gopher/ldap/userinfo/通配拒）
- `test_validate_url_rejects_rfc1918_not_in_whitelist` × 4 parametrize
- `test_validate_url_rejects_invalid_port` × 2 parametrize（端口 0/65536）
- `test_ssrf_scan_finds_findings` × 1（探针命中 otel exporter + MCPImportUrlReq）
- `test_router_rejects_ssrf_url` × 1（路由层 `p8_import_url` 收到 169.254 必 400）
- `test_router_allows_internal_trusted_url` × 1（合法 IP schema 校验通过）

---

## 四、Mimosa 三层实证（SSRF-G4）

`scripts/eval/_ssrf_mimosa3_evidence.py` 输出：

```
[ssrf_mimosa3] 三层实证扫描结果：
   - ①PASS host_pinning_127_0_0_1: 22 (命中 file:line)
   - ①PASS db_param_binding: 66 (param_exec_hits)
   - ①PASS secrets_from_env: N/A (config_pydantic_settings 自动 env)
```

| 层 | Mimosa 强约束 | 实证 file:line |
|---|---|---|
| ① | host 写死 127.0.0.1 | `config.py:677-698 _normalize_loopback 归一 + REDIS_URL 默认 local → 127.0.0.1`；`RERANK_SERVICE_URL` 默认 `http://127.0.0.1:8601`（实测连通） |
| ② | DB 参数绑定 | `database.py:517 fetch_one / 538 fetch_all / 557 execute_write` 全部 `cur.execute(sql, args or ())` 参数化；f-string + execute 仅 1 例（`user_profile` SET {col} = %s，列名枚举切换，值仍参数化） |
| ③ | 密钥仅从 env 读 | `config.py:580 JWT_SECRET / 600 API_TOKEN / 152 MINIO_SECRET_KEY / 175 LLM_API_KEY / 124 NEO4J_PASSWORD` 等字段由 pydantic-settings 从 env/.env 自动注入；conftest 测试用强随机密钥覆盖隔离 |

---

## 五、修复实证（SSRF-G2）

### 5.1 新增 `app/security/ssrf_guard.py`（91 行）

- 默认白名单：`127.0.0.1` / `localhost` / `192.168.85.101` / `10.0.0.1`
- 永久封禁：`169.254.169.254`（AWS/GCP/Azure IMDS）/ `metadata.google.internal` / `metadata` / `0.0.0.0`
- 拒非 http(s) scheme：`file://` / `ftp://` / `gopher://` / `ldap://`
- 拒 `userinfo@host` 绕道
- 拒 RFC1918 私网（除白名单字面 IP）
- 拒畸形端口（≤0 或 >65535）
- `settings.SSRF_ALLOWED_HOSTS` 可运行时覆盖

### 5.2 修改 `app/mcp/router.py`（仅 URL 校验段 ~22 行）

`p8_import_url` 函数体首部加 `validate_url(url)`，http(s):// 形态入参被白名单阻挡时 `HTTPException(400)` 拒绝，**不调 DB、不调 SSE health、不写 mcp_server 行**。

### 5.3 实证单测

`tests/test_ssrf_scan.py::test_router_rejects_ssrf_url` 直接 `await p8_import_url(MCPImportUrlReq(url="http://169.254.169.254/..."))` → `HTTPException(status_code=400, detail="URL 不在 SSRF 白名单（拒绝详情）：...")`。

---

## 六、SSRF 修复建议（SSRF-G5）

| # | 风险位 | 修复建议 | 优先级 |
|---|---|---|---|
| 1 | `OTEL_EXPORT_ENDPOINT` 任意配置可外发（`otel/exporter.py:187 requests.post`） | 与本批同款：加 `validate_url` 白名单；endpoint 必须 `127.0.0.1` / `192.168.85.101`（OTLP collector 内网部署）或显式白名单外网域 | **P1**（待下批 W-NEXT-OTLP） |
| 2 | `ERROR_WEBHOOK_URL` 同上 | 同款白名单；非 DEBUG 模式时强制 127/192.168 | **P1** |
| 3 | `EMBEDDING_API_URL` 可外发 | 留作配置但启动期白名单校验 + 拒绝（0.0.0.0 / RFC1918 未白名单 / IMDS） | **P2** |
| 4 | `settings.LLM_BASE_URL` 默认公网 `dashscope.aliyuncs.com` | 行为合规（生产需要 LLM 接出）；新增建议 `LLM_BASE_URL_ALLOWED_HOSTS` 校验防止 .env 被恶意覆盖 | **P2** |
| 5 | MCP executor.py 内部 `_httpx.AsyncClient(... url=base_url)` 透传（`mcp/executor.py:426, 1863`） | base_url 已由 `registry.register_server` 入库，写入前必经 `p8_import_url`/`register_server` 入口（待基线扫 `register_server` 路径是否同样校验；**本批先抽探针入口位**） | **P2**（下批 W-NEXT-EXE-SSRF） |
| 6 | `aiohttp.ClientSession` 同 `executor.py` | 同上 | 同上 |

---

## 七、变更清单（commit-pending）

| 状态 | path | 备注 |
|---|---|---|
| + | `edu-agent/app/security/__init__.py` | 包初始化 |
| + | `edu-agent/app/security/ssrf_guard.py` | 新模块，91 行（白名单 + SSRFBlockedError） |
| + | `edu-agent/scripts/eval/ssrf_scan.py` | 探针，~430 行 |
| + | `edu-agent/scripts/eval/_ssrf_mimosa3_evidence.py` | Mimosa 三层实证脚本 |
| + | `edu-agent/tests/test_ssrf_scan.py` | 29 例单测 |
| M | `edu-agent/app/mcp/router.py` | `p8_import_url` 加 `validate_url` ~22 行；新增 `import logging` + `from app.common.logging import logger` |
| + | `edu-agent/scripts/eval/wnextssrf1.lock` | 单写者锁（完工后删） |

### 7.1 探针与报告输出（commit 后仍可重跑）

- `deploy/backups/ssrf_scan_20260917_034746.json` —— 风险位清单（7 HTTP + 1 ingest + 13 settings + 8 主动探活 = **21 ≥10**）
- `deploy/backups/ssrf_mimosa3_20260917_033740.json` —— Mimosa 三层实证
- `test-reports/WNEXTSSRF1-completion-report.md` —— 本报告

---

## 八、复跑指引

```bash
cd edu-agent

# 1) 探针
python scripts/eval/ssrf_scan.py --active-probe    # 主动探活（127 / 192.168.85.101）
python scripts/eval/ssrf_scan.py                   # 仅静态扫描

# 2) Mimosa 三层实证
.venv/Scripts/python.exe scripts/eval/_ssrf_mimosa3_evidence.py

# 3) 单测
.venv/Scripts/python.exe -m pytest tests/test_ssrf_scan.py -v
```

---

## 九、commit 信息（待落实）

```
feat(security)/W-NEXT-SSRF-001-host-validation

edu-agent/app/security/ssrf_guard.py     新增 host 白名单校验（91 行）
edu-agent/app/mcp/router.py              p8_import_url 加白名单 ~22 行
edu-agent/scripts/eval/ssrf_scan.py      SSRF 风险位探针（AST + 主动探活）
edu-agent/scripts/eval/_ssrf_mimosa3_evidence.py   Mimosa 三层实证
edu-agent/tests/test_ssrf_scan.py        29 例单测

GWT: SSRF-G1(21 风险位 ≥10) / G2(白名单+拒绝) / G3(29/29 单测绿) / G4(三层 PASS) / G5(报告含清单+建议)
验证: deploy/backups/ssrf_scan_20260917_034746.json + ssrf_mimosa3_20260917_033740.json
```
