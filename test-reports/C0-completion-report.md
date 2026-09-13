# taskC0 完成报告：生产配置模板 + 部署配置项清单

> 日期：2026-09-13｜执行：C 阶段部署配置工程师（独立 agent）
> 计划：`.ai-hub/plans/dev-plan-cmin-deploy.md` taskC0（前提 P2/P5）
> 契约红线：零 API 契约变更（P3），`contracts/*.json` 未触碰

## 1. 交付物

| 交付物 | 路径 | 说明 |
|---|---|---|
| 生产配置模板 | `edu-agent/.env.example` | 覆盖 config.py Settings **全 220 字段**，分域注释（应用/MySQL/Redis/Milvus/Neo4j/jieba/Mongo/MinIO/本地模型/LLM/Agent 循环/上下文压缩/HITL/Redis 防过载/token 预算/观测性/记忆/缓存前缀/Embedding/MCP/工具闭环/HITL 护栏/Rerank sidecar/Harness/RAG Contextual/日志/鉴权/检索/SQL 安全/评估/路径），生产推荐形态（ENV_NAME=prod、DEBUG=false、强密钥占位+`secrets.token_hex` 生成指引、CORS_ORIGINS 生产占位、LLM_API_KEY 来源注释），文件头含 **dev/prod 双形态对照表**（dev 形态改 2 键即 ENV_NAME=local+DEBUG=true） |
| 部署配置项清单 | `.ai-hub/plans/deploy-config-checklist.md` | **380 行 / 220 键**逐键核对，表格列=键/默认值/必填性/影响面/生产值指引；§0 硬门禁键表（`_security_guard` 硬校验 **JWT_SECRET/API_TOKEN**、`_debug_env_gate` 硬校验 **ENV_NAME+DEBUG**、lifespan 存储初始化 DEBUG=false 拒启） |

## 2. 覆盖度程序化比对（现状自证）

用 `edu-agent/.venv` Python 正则比对 `app/config.py` Settings 字段 vs `.env.example` 键（含注释键）：

```text
config.py fields: 220
env.example keys : 220
MISSING: []
EXTRA(not in config): []
```

必填（无默认值）字段 2 个：`MYSQL_PASSWORD`、`LLM_API_KEY`——模板均为 `REPLACE_ME_*` 占位+来源注释。

## 3. scratch 实机验证（核心证据）

**方法**：系统临时目录 `C:\Users\Administrator\AppData\Local\Temp\eduagent-c0-scratch` 建 scratch 环境，复制 `.env.example→.env`；按生产形态填 **新生成强随机密钥**（`secrets.token_hex(32)`→JWT_SECRET 64 字符、`secrets.token_urlsafe(24)`→API_TOKEN，密钥只存在于 scratch，不入工作区，验证后 scratch 整目录删除）；基础设施凭据取自本机 gitignored `.env`（MySQL/MinIO/LLM/Embedding/Rerank）与 task35 登记（VM Neo4j）；以 `uvicorn app.main:app --port 8002 --env-file .env`（scratch 目录 + PYTHONPATH 指向 edu-agent）启动临时实例。

**预检（DEBUG=false 下 lifespan 全存储必须连通，否则拒启）**：

```text
MILVUS: 192.168.85.101:19530 REACHABLE
MONGO : 192.168.85.101:27017 REACHABLE
MINIO : 192.168.85.101:9000  auth OK
NEO4J : bolt://192.168.85.101:7687  auth OK
本机   : MySQL 3306 / Redis 6379 LISTENING
```

### 断言结果（3/3 全过）

**① 启动成功（P1-8 门禁过，无默认 JWT_SECRET 告警）**：

```text
=== EduAgent v0.3.0 正在启动 ===
=== 存储初始化完成: {'mysql': 'ok', 'mysql_ro': 'ok', 'milvus': 'ok',
    'mongodb': 'ok', 'minio': 'ok', 'neo4j': 'ok', 'redis': 'ok'} ===
Application startup complete.
Uvicorn running on http://127.0.0.1:8002
```

- 日志 grep `公开 JWT_SECRET|默认 API_TOKEN|禁止上线` → **0 条**（`_security_guard` 无告警）
- 日志 grep `启动拒绝|ValueError|Traceback` → **0 条**（`_debug_env_gate`/门禁全过）
- 无关告警仅 2 条环境噪音：本机无 `C:/ai-models/bge-m3` 目录 → embedding/reranker 走 API 兜底（warmup 后台任务，不影响启动）

**② /health 200**：

```text
health=200
{"status":"ok","app":"EduAgent","version":"0.3.0"}
```

**③ 无 token GET /api/admin/users → 401**（DEBUG=false 无虚拟管理员后门）：

```text
admin_users_no_token=401
{"code":"40101","message":"缺少 Authorization 请求头","data":null}
```

### 清理

- 临时 uvicorn 进程已停止，端口 8002 复查 `connection refused`（零残留进程）
- scratch 目录（含随机密钥的 .env）已整目录删除

## 4. git 纪律核验（P5 密钥零入库）

- `git check-ignore edu-agent/.env` → 命中 `.gitignore:1:.env`；`.env` **未被 git 跟踪**
- 本次 commit 只含 `.env.example`（占位符，无真实密钥）与清单文档；随机密钥从未写入仓库任何文件
- 真实基础设施凭据（MySQL/MinIO/Neo4j/LLM key）仅存在于 scratch .env（已删除）

## 5. 发现与登记

1. **VM Neo4j 密码与 config.py 默认值不同**（task35 报告已登记 `hzk******`，config 默认 `edu_neo4j_pwd_2026` 对 VM 无效）——`.env.example` 保持 `REPLACE_ME_NEO4J_PASSWORD` 占位，生产部署必查此键，清单中 NEO4J_PASSWORD 行已标注。
2. **DEBUG=false 下 lifespan 对 6 类存储 fail-fast**：任一不可达即拒启（app/main.py:87-140），清单 §0 已列硬门禁表——这是 C1 一键脚本必须先拉起 VM Docker 的原因。
3. 本机无 `C:/ai-models/bge-m3` → scratch 实例 embedding 自动走 API 兜底（仅 warning 不阻断），与 AGENTS 教训 7（查询/入库 embedding 同通道）联动：生产换通道需重建向量库，清单 EMBED_BACKEND 行已标注。

## 6. DoD 核对

- [x] `.env.example` 覆盖 config.py 全字段（220/220）且生产/dev 双形态兼容
- [x] 部署配置项清单 220 键产出（待用户逐条审，审后定稿——GWT②）
- [x] scratch 生产形态启动验证 3/3（含 P1-8 门禁 + 无默认密钥告警）
- [x] 临时进程零残留 + scratch 密钥零残留
- [x] `.env` 未被跟踪；commit 只含模板与清单
