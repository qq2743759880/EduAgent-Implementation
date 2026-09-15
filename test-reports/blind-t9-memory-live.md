# blind-t9-memory-live — 记忆链路三项 live 实证

- **executionSessionId**：`20260915_185443_blindt9`
- **身份**：编排者直验（独立 agent，8010 临时实例，用完已关闭，不扰 8000）
- **日期**：2026-09-15（GMT+8）
- **口径**：一手实测；禁采信任何历史完工报告；每条断言给证据等级标注
  `[实测]` / `[代码佐证]` / `[推演]` / `[未验证]` / `[文档原文]`
- **被测代码**：`edu-agent/app/ai/memory/*`（service.py / queue.py / ingest.py / extract_llm.py / store.py / persistence.py / event_persistence.py / dream.py）、`app/main.py`、`app/chat/service.py`、`app/chat/generator.py`
- **只读约束遵守**：全部 DB 校验为参数绑定 SELECT；写库仅发生在「通过产品自身 API/入口」触发（chat → 异步记忆抽取），未做任何直写注入；测试数据自建自清（uid=100066，已软删/软失效）

---

## 结论速览（编排者复验三重点）

| 复验重点 | 结论 | 证据 |
|---|---|---|
| 真落库（非 degraded 兜底） | ✅ 通过，但**落库表是 `user_memory_event`（事件溯源），不是 `user_memory`** | T1 实测 |
| 启动失败不炸主服务 | ✅ 通过：worker 启动失败 → `/health` 200 + 日志 WARN，主服务功能全活 | T2 实测 |
| degraded 非静默 | ✅ 通过：LLM 通道抽干 → degraded 计数 +1，reason 显式，规则候选仍入库 | T3 实测 |

**附加发现（与验收直接相关）**：
- 🔴 **P1 缺陷（抽取结果截断丢弃）**：LLM 记忆抽取输出被 `max_tokens` 截断时，整批候选被静默判为 `llm_unparseable_output` 而落 degraded，**即使前几条已是合法 JSON**。这不是"静默丢弃"（degraded 已落），但**把本可抽取的事实丢进了 degraded**，削弱了真实召回。详见 §4。
- 🟡 助手侧事实抽取**归因失败**（环境门槛）：T1-round2 追问助手时，规则 0 候选（预期内）+ LLM 抽取因输出截断判 degraded → 本轮"助手事实"未入库。非代码逻辑缺失，是 §4 缺陷的下游表现，已在默认参数下复现根因。

---

## 1. 测试环境（实例编排）

| 实例 | 端口 | 配置差异 | 用途 | 状态 |
|---|---|---|---|---|
| A | 8010 | 默认 `.env`（`MEMORY_EVENT_ENABLED=true`，fast=火山 minimax-m3，strong=DeepSeek） | T1 真实落库 + round2 | 已停 |
| B | 8010 | `LLM_FAST_BASE_URL=http://127.0.0.1:9/v1`（抽干 fast 通道） | T3 degraded | 已停 |
| C | 8010 | 进程内 monkeypatch `start_memory_worker` → raise | T2 启动失败注入 | 已停 |
| D | 8010 | 默认配置 | 收尾自清 | 已停 |
| E/E3 | 8010 | `MEMORY_EVENT_ENABLED=false` | T1c 表归属判定 | 已停 |

- 启动命令（A）：`MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010`
- 测试账号：**自建** `blindt9mry185443`（uid=100066，student，`POST /api/auth/register`），token 走 `POST /api/auth/login`。
- 环境注意：`HTTP_PROXY` 指向本机代理，curl 一律 `--noproxy '*'`，python 用 `httpx.Client(trust_env=False)`。[实测]

---

## 2. T1 — 真实 chat 60s 落库（非 degraded 兜底）

### 2.1 验收口径澄清（关键）

任务书原文写"user_memory 表出现抽取行"。但**读代码 + 实测双证**：当前生产默认 `MEMORY_EVENT_ENABLED=True`，记忆写路径的事实源是 **`user_memory_event`（事件溯源表）**，`user_memory`（旧快照表）**保持 0 行**。

- `[代码佐证]` `app/ai/memory/persistence.py:202-217` `build_persistence()`：`MEMORY_EVENT_ENABLED=True`（默认）→ 返回 `SqlEventMemoryPersistence`，其 `insert` 写 `INSERT INTO user_memory_event`（`event_persistence.py:201-207`）；仅 `False` 时才返回写 `user_memory` 的 `SqlMemoryPersistence`。
- `[实测]` T1 落库后：`user_memory_event` +1（`create` 事件），`user_memory` 仍 0 行。
- `[实测]` T1c（`MEMORY_EVENT_ENABLED=false` 单进程实跑）：真实 chat 后 `user_memory 0→2`，`user_memory_event 12→13` → **事实源切回 `user_memory`**。两表在不同开关下各自主笔，印证 `persistence.py` 工厂逻辑。
- **结论**：验收口径应为「默认配置下查 `user_memory_event`；若验收强制要求 `user_memory`，需关闭 `MEMORY_EVENT_ENABLED`」。[实测 + 代码佐证]

### 2.2 主结果

真实 chat 请求（`POST /api/chat`，body 含规则触发词"请记住…我在准备雅思考试…目标 6.5…更喜欢 Python 而不是 Java"）：

- `[实测]` 请求发出后 **27.8s** 内 `user_memory_event` 新增 `create` 行（阈值 60s ✅）。
- 新增 4 行，**覆盖两类来源**：
  - 规则抽取（`ingest.detect_memories_window`，只扫用户发言）：
    - `目标：雅思考试`（goal / learning-goals / imp5）
    - `我在准备雅思考试…更喜欢 Python 而不是 Java…`（profile / preferences / imp5）
  - LLM 抽取（`extract_llm`，第三人称改写）：
    - `用户正在准备雅思考试，目标分数为6.5分`（goal / imp5）
    - `用户更偏好Python而非Java`（preference / imp4）
- `[实测]` worker 日志佐证：`[Memory:queue] turn 消费完成 user=100066 候选回灌=4 窗口条数=1`，随后 4 条 `[Memory] 写入记忆 user=100066 id=110~113`。
- 用户偏好（Python 偏好）与助手事实（雅思目标）两类均有覆盖 ✅。

> 注：T1 首轮 chat 的 `answer` 字段为空（HTTP 200，`degraded_reason=null`，`latency_ms=24483`，`retrieved_count=5`），但记忆抽取**照常落库**——这是 agent 链路 `sixnode.answer` 节点 strong→fast 均返回空串且未兜底的独立问题（`app/ai/harness/sixnode.py:379-391` 对"空字符串"无兜底，只有异常才兜底）。[实测 + 代码佐证]。不影响记忆落库结论，但建议另立任务排查。

### 2.3 助手侧事实抽取（round2，环境门槛标注）

- 第二轮追问"请先复述你了解到的我的备考目标和语言偏好"，助手正常回复（`answer_len=1457`，strong 档，`degraded=null`）。
- `[实测]` 本轮规则基线 = 0 候选（用户文本无触发词，预期内）；窗口 = 用户问 + 助手答（成对）。
- `[实测]` 60s 内**无新增落库行**；worker 日志：`LLM 输出不可解析，判 degraded … user=100066 reason=llm_unparseable_output`。
- 根因见 §4（LLM 抽取输出被截断 → 整批丢弃），非"助手事实本不该抽"。[实测 + 代码佐证]

---

## 3. T2 — worker 启动失败注入 → /health 200 + WARN（不阻断）

> R01 报告称此项无专项测试，本任务 live 实跑补。

**注入方式**：不改被测源码，进程内 monkeypatch（`t2_harness.py`）：`app.ai.memory.service.start_memory_worker = 抛 RuntimeError 的协程`，再以完全相同方式拉起 FastAPI app。

- `[实测]` 日志出现：`WARNING app.main:lifespan:181 记忆 worker 启动失败（记忆写队列本轮无人消费，降级运行，不影响主服务）: RuntimeError: injected worker start failure (blind-t9 T2)`
- `[实测]` `GET /health` → `HTTP 200`，body `{"status":"ok","app":"EduAgent","version":"0.3.0"}`
- `[实测]` `Application startup complete.` 正常（lifespan yield 未中断）
- `[实测]` 主服务功能全活（worker 未启动不影响）：`GET /api/auth/me` → 200 真实用户数据；`GET /api/chat/sessions` → 200 真实会话列表；`GET /health/detail` → 200（mysql/milvus/mongodb/minio/neo4j/redis 全 ok）
- `[实测]` 日志中**无** `记忆写队列消费者已启动`（grep 计数 = 0，worker 确实未拉起）→ 注入生效且未崩主服务。

**结论**：worker 启动失败仅 WARN、不阻断主服务 ✅。对应 `app/main.py:174-184` 的 try/except（`except Exception as e: logger.warning(...)`）语义成立。[实测 + 代码佐证]

---

## 4. T3 — LLM 失败 degraded（非静默丢弃）

**注入方式**：实例 B 以 `LLM_FAST_BASE_URL=http://127.0.0.1:9/v1`（不存在的端口）抽干 fast LLM 通道（`MEMORY_EXTRACT_MODEL=fast` 默认）。

- `[实测]` 真实 chat（规则触发词"请记住：我打算考软考中级…"）→ HTTP 200，strong 档正常出答案（`answer_len=267`），`degraded_reason=null`（主链路用 strong，未被 fast 抽取失败波及）。
- `[实测]` **degraded 记录 +1**（Redis list `edu:mem_queue:degraded`），reason 显式：
  `llm_call_failed: ConnectionError: HTTPConnectionPool(host='127.0.0.1', port=9): Max retries exceeded …`
- `[实测]` worker 日志：`[Memory:queue] LLM 抽取失败，turn 落 degraded（规则候选仍照常入库，不静默丢弃）：user=100066 reason=llm_call_failed … 累计 degraded=1`
- `[实测]` **规则候选仍照常入库 2 行**：`目标：软考中级`（goal/imp5）、`我打算考软考中级…`（profile/imp5）→ "degraded 不吞规则候选"成立。
- `[代码佐证]` `queue.py:199-211`：LLM 抽取异常走 `record_degraded`（`stats['degraded'] += 1` + LPUSH degraded 键），规则候选在 LLM 之前已由 `detect_memories_window` 生成，二者独立；`extract_llm.py:125-126` 把异常显式转为 `("llm_call_failed: ...", error)`，不伪装空列表。

**结论**：LLM 失败显式落 degraded、非静默、且不丢规则候选 ✅。

---

## 5. 附加发现：LLM 抽取输出截断 → 整批判 degraded（P1，建议修复）

`[实测]` 用 wrapper 抓取抽取 LLM（fast=minimax-m3）对 round2 窗口的**原始输出**：

- `MEMORY_EXTRACT_MAX_TOKENS=600`（`config.py:365`），但抽取 prompt 的输入窗口可达 ~1535 字符，输出被硬截断。
- 实测 raw 输出 `len=316`，**尾字符是 `"用户在编程…`（未闭合引号、无 `]`）** → `json.loads` 失败 → `_extract_json_array` 返回 `[]` → `extract_llm.py:134-151` 判 `llm_unparseable_output` → 整批落 degraded。
- **前几条候选本是合法完整 JSON**（`用户正在备考雅思…目标6.5`、`用户自述零基础…` 均完整），仅因**最后一条被截断**导致**整批丢弃**。

根因：`extract_llm.py` 的容错只做"`[]` 完整时 json.loads 成功"，未做"截断数组尾部容错"（如补齐缺失的 `]` / 丢弃最后一条不完整元素）。[代码佐证：`extract_llm.py:134-151`、`dream.py:43-59`]

影响：真实场景中当抽取事实较多时，LLM 输出易触 600 token 上限被截断 → 本可入库存的事实整体进 degraded，削弱长期记忆召回。**这是"degraded 非静默"成立之下的召回质量缺陷**，建议：提高 `MEMORY_EXTRACT_MAX_TOKENS` 或对截断 JSON 做尾部截断修复（丢弃最后不完整元素再 parse）。

---

## 6. 证据等级与自清

| 断言 | 等级 |
|---|---|
| 默认配置落库表=user_memory_event（非 user_memory） | [实测]+[代码佐证] |
| 60s 内真实落库（27.8s，规则+LLM 两类 4 行） | [实测] |
| MEMORY_EVENT_ENABLED=false → 落 user_memory（0→2） | [实测] |
| worker 启动失败 → /health 200 + WARN，主服务全活 | [实测] |
| LLM 失败 → degraded +1，reason 显式，规则候选仍入库 | [实测] |
| 抽取输出截断 → 整批判 degraded（P1） | [实测] |
| 首轮 chat answer 空串但记忆仍落库（独立问题） | [实测]+[代码佐证] |

**测试数据自清**：
- 自建用户 uid=100066（student），其 6 条记忆事件已 `forget_all_for_test` 软失效（`event_type='delete'` 追加，非物理删除）。
- 会话 `s_36e9f5d32388`（round1）/ `s_dfe372db0c93`（round2）/ `s_38d3a523d09b`（t3）已 `DELETE /api/chat/sessions`（yn=0）。
- T1c 的 `user_memory` 2 行（id 20/21）已软删 `deleted=1`。
- 8010 全部实例已停，端口已释放；未触碰 8000 生产实例。[实测]

---

## 7. 下一位同事最该知道的 3 件事

1. **验收必须按"事件溯源"口径查表**：默认 `MEMORY_EVENT_ENABLED=True` 时记忆写的是 `user_memory_event`（append-only，`event_type='create'`、`valid_to IS NULL` 为有效），**`user_memory` 永远是 0 行**；只有关掉该开关才写 `user_memory`。别对着 `user_memory` 表等行而误判"没落库"。

2. **记忆抽取的 LLM 输出截断是当前最大召回隐患（P1）**：`MEMORY_EXTRACT_MAX_TOKENS=600` 配合 ~1535 字符输入窗口，实测输出 316 字符即被截断、无 `]`，导致整批合法候选被误判 `llm_unparseable_output` 落 degraded。修法是提高该上限 + 在 `extract_llm.py` 加"截断数组尾部容错"（丢弃最后不完整元素再 parse），否则"助手侧事实抽取"在多数真实场景会静默进 degraded。

3. **"启动失败不炸服务"是靠 `main.py:174-184` 的裸 try/except 兜底，且 worker 与主链路彻底解耦**：实测注入 `start_memory_worker` 抛异常后，`/health`、`/api/auth/me`、`/api/chat/sessions`、`/health/detail` 全部 200，唯一代价是"本轮记忆无人消费"（静默降级、仅 WARN）。这也是 T3 里"LLM 抽干不波坏 chat 主链路"的同一套隔离设计的体现。

---

*报告完。所有断言均为一手实测或读码佐证，未采信任何历史完工报告。*
