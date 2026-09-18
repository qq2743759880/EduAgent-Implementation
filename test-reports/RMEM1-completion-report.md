# W-NEXT-R-MEM-001 完成报告（R04-b 落库脱敏 + R08 enqueue_turn 完整对话窗）

> 分支 `feature/opt-waves`；主体实现 commit `41f2c6d`（本报告为 docs 回填提交）。
> 任务书：吞并 R04-b（落库脱敏，P3-23/24 承接）+ R08（enqueue_turn 对话窗，P2-12 承接）两条同域任务。
> lock：`edu-agent/scripts/eval/rmem1.lock`（commit 前已删）。

## 一、R04-b：记忆落库脱敏（P3-23/24 语义）

### 1.1 落库链路审计结论（敏感面识别）

| 链路点 | 字段 | 敏感面 |
|---|---|---|
| 队列 turn 载荷（Redis LPUSH） | `messages[].content` | 对话窗**原文**（用户粘贴的密钥/token/手机号/身份证），LLM 失败时 `window_preview` 前 2 条（≤200 字）还会入 degraded 键 |
| 队列 candidate 载荷 | `content` | 规则抽取（`ingest.detect_memories` 截取的**用户原文片段**）+ LLM 抽取（`extract_llm` 产出的事实陈述，含原文引用） |
| `user_memory_event`（事实源，insert/update/rewind/consolidate 四类事件） | `content` | 上述候选直通（`store.write` ← queue 单一链路，已核实 `MemoryStore.write` 仅 queue 调用；`consolidate` 的 summary 来自已脱敏记忆的再摘要，天然干净） |
| `memory_type`/`topic` | 固定词表（`_coerce_entry` 白名单 + 规则常量），低风险，不在本轮范围 | — |

### 1.2 实现（新文件 `app/ai/memory/sanitize.py`，收口于队列写边界）

- **复用既有范式（不重复造轮子）**：手机号/邮箱正则直接 `from app.common.log_sanitizer import _PHONE_PATTERN, _EMAIL_PATTERN`（T19-3 日志脱敏既有口径，138****1234 / u***@d***.com）；掩码标记 `***REDACTED***` 对齐 `app/mcp/executor._REDACTED`（W-NEXT-MCP-001 P0-③ 落库脱敏同款）。唯一新增部分是记忆内容为纯文本所需的**文本级模式**（MCP 的 dict key 命中范式不适用）。
- **模式清单（应用顺序=先特异后泛化）**：① 身份证（18 位含出生日期段结构校验+边界守护，前4********末1）；② 已知密钥前缀 sk- / gh[pousr]_ / AKIA / xox（左边界守护防 `task-2024...` 类单词误伤）；③ JWT（eyJ 三段 base64url）；④ `Bearer <token>`；⑤ key=value（password/token/api_key/access_key/authorization 等，保留 key 与分隔符、剥尾标点、值≥8 才命中）；⑥ 泛化高熵串（≥32 位 base64url/hex run + 边界守护 + 字母数字混合要求）；⑦ 手机号；⑧ 邮箱。
- **接线点（队列写边界，双保险）**：`queue.enqueue_turn_window`（窗内逐条 content 掩码 → Redis 载荷/degraded 预览/LLM 抽取输入同步最小化）+ `queue.enqueue_candidate`（先脱敏再截断 2000，防截断处留半截敏感串；覆盖规则+LLM+未来任何 candidate 来源）。
- **只损内容不损结构（铁律已落实）**：仅对字符串值就地掩码；消息条数/`{role, content}` 键集/事件行 JSON 字段/candidate 载荷六字段全部原样（测试 `test_turn_messages_structure_intact` / `test_enqueue_candidate_payload_sanitize_and_json_shape` 断言键集不变）。
- **检索/HEAD 逻辑零改动（铁律已核实）**：`event_persistence.py`（HEAD 判据 `valid_to IS NULL AND event_type <> 'delete'`、版本盖章、rewind）**零 diff**；AGENTS.md 教训 11 口径在测试与实测中用于断言。
- **命中计数入日志**：`logger.info("[Memory:sanitize] 落库脱敏命中 N 处（累计 M）")`（有命中才记）+ 模块级 `SANITIZE_STATS`（text_calls/hits/window_calls/window_hits，含 `reset_stats_for_test`）。
- **config.py 零追加**（红线达成：脱敏为默认常开行为，无开关需求）。

### 1.3 命中实测（节选，全量见 pytest 37 例）

| 输入样例 | 结果 |
|---|---|
| `sk-abc123XYZdef456ghi789` / `ghp_…` / `AKIA…` / `xoxb-…` / JWT / Bearer | → `***REDACTED***` |
| `password=SuperSecret123!` | → `password=***REDACTED***`（key 保留） |
| `13812345678` / `110101199003078515` / `user@example.com` | → `138****5678` / `1101********5` / `u***@…` |
| 不误伤组（hits=0 原样返回）：中文偏好句、订单号 20240918123456、日期、`https://docs.python.org/3.11/...`、`task-2024091812345678`、普通英文/学号 | 全部零命中 |

## 二、R08：enqueue_turn 完整对话窗（P2-12 条款「开工前现状自证」先行）

### 2.1 现状自证（grep 全量排查结论）

- `enqueue_turn` 既有调用点全量 = 2 处，均在 `app/chat/service.py`（非流式 :505、流式 finalize :630），**历史上已带 `assistant_reply=` 成对入窗，无「仅单侧 text」调用点**（`ingest_turn`/`enqueue_candidates` 仅测试引用）。即任务书假设的「旧单侧调用点」在 R01-b 后已不存在——差距在**多轮历史**：两处均只传本轮 (query, answer) 最小窗，会话前几轮上下文（`history_turns` 在两处均已在作用域内）被丢弃，多轮对话下记忆抽取缺前文。
- 对齐动作（逐调用点）：
  1. **非流式 `chat_answer`**：改传 `messages=build_turn_window(history_turns, query=req.query, answer=answer)`（历史轮+本轮成对）；
  2. **流式 `make_stream_finalize`**：新增可选参 `memory_history_window`（默认 None），`chat_stream` 构造处传入 `history_turns`；`flows/graph_stream.py` 旧调用**零改动**（不传 → 退化本轮成对，行为兼容），finalize 内统一走完整窗拼装；
  3. **旧单侧契约兼容**：`text(+assistant_reply)` 入参保留，可入队（返回 1）。

### 2.2 新能力

- **`build_turn_window`（service 层纯函数）**：history（`[(role,content)]` 或 `[{role,content}]`）+ 本轮 (query, answer) → 完整窗；空 answer 只拼 user 侧（T9-C3 语义）；后续经 `normalize_window` 取最近 `MEMORY_INGEST_WINDOW=10` 条。
- **半窗守卫**：整窗有 user 而零 assistant → `logger.warning("记忆窗缺 assistant 半边…")`（兼容不硬拒，暴露未对齐调用点）。
- **载荷版本**：`enqueue_turn_window` 载荷带 `v=2`；消费端 `_detect_payload_shape` **形状探测**路由：`kind=turn + 非空 messages` → turn 路径（v1 无 v 字段 / v2 均兼容，v 仅观测）；有 `content`（含残缺 turn 兜底）→ candidate 写库路径；两者皆无 → poison 计数丢弃不炸 worker。

## 三、验证实证（独立实证，非复述实现）

### 3.1 pytest（全离线契约 + 离线 worker）

- 新增 `tests/test_contract_rmem1_sanitize_window.py`：**37/37 绿**。覆盖任务书四验收点：脱敏命中（11 模式参数化）、不误伤（8 组正常内容参数化+task- 单词）、结构不损（键集/JSON 字段断言）、成对入库（完整窗→落库）、旧载荷兼容（v1 turn 无 v / 旧 candidate 无 kind / 残缺载荷 poison）、半窗告警兼容、`v=2` 断言、命中计数入日志（caplog 捕获 `[Memory:sanitize] 落库脱敏命中`）。
- 记忆域全量回归：`task25 + task_m1 + task_m1_capacity_tier + task_m1_event_persistence + task_r01 + memory_queue_lifecycle + rmem1 + r11_hitl + hitl_fix_integration` = **102 passed**。
- chat 域回归（`app/chat/service.py` 改动波及面）：`test_chat_delete + chat_flow_args_fix + chat_stream_error + chat_tool_calling + contract_all_routers` = **44 passed**。
- **顺手修复预存测试污染（P2）**：`tests/test_contract_task_m1.py` 的 `_make_client` 裸赋值 `svc._ensure_instances = fake_ensure`（返回 `(store, None)`）且从不恢复——同进程后续文件（r01/rmem1 的 service 用例）拿 None queue 以 `'NoneType' object has no attribute 'enqueue_turn_window'` 失败。加 autouse fixture 快照/恢复 `_ensure_instances/_store/_queue/_worker_started` 四项模块态。该问题在本批改动前即存在（组合运行必现），非本批引入。

### 3.2 离线 worker 实测（`scripts/eval/rmem1_offline_worker_probe.py`，真实起 worker）

真 Redis（init_redis，真 LPUSH/BRPOP broker）+ 真 MySQL（`build_persistence()` 生产同款 `SqlEventMemoryPersistence`）+ `start_consumer()` 真消费循环（非 pump 模拟）；`MEMORY_LLM_EXTRACT_ENABLED=False`（真实 LLM 窗口不可用→任务书口径：契约测试+离线 worker 实测）。合成对话 `记住 我喜欢Python，我的 API key 是 sk-RMEM1probeKEY12345678` / `好的，已记录，手机号 13800138000`：

```
[probe] worker stats: {'candidate': 1, 'turn': 1, 'retry': 0, 'dropped': 0, 'degraded': 0, 'poison': 0, 'loop_error': 0}
[probe] user_memory_event rows = 2
[probe] PASS：HEAD 2 行全部脱敏且语义保留   （content 含 ***REDACTED***、密钥/手机号明文零命中、Python 语义保留）
[probe] 清理完成：user_memory_event 无 990001 残留（物理删除+复核 COUNT=0）
```

### 3.3 真机 E2E（新代码第二实例 ：8001，不扰动共享 ：8000）

- `POST /api/auth/login` 200 → `POST /api/chat`（非流式）**200 code=0**，answer 140 字；
- `POST /api/chat/stream` **200**，`event: start|retrieval|token|done` 全链路，`data:{"delta":…}` 累计成答，done 帧 `code:0`；
- 该轮带 `记住 我喜欢Python，我的 API key 是 sk-RMEM1E2ETEST12345678` → 真 worker 真库落 `user_memory_event` 4 create 行（两次 stream 尝试×explicit+preference），**逐行 `masked=True`、明文零命中（NO_SECRET_LEAK）**，如 `id=167 content=偏好：Python，我的 API key 是 ***REDACTED***`；
- 清理：按 id 精确 DELETE 4 行 + 复核 remaining=0，user1 HEAD 计数回落实测前基线（1）。

## 四、P0 自批判（≥3）

1. **P0｜双实例并存窗口的旧 worker 旁路**：掩码发生在**新代码进程**的队列边界（enqueue_candidate 在 worker 消费侧）。若新代码部署后仍有旧代码 worker 共享同一 Redis 队列（如本次实测环境 :8000），旧 worker 消费 unmasked 在途载荷会写明文。本次实测 NO_SECRET_LEAK 属 BRPOP 竞争运气+双轮恰被新 worker 消费，**不能依赖**。缓解：部署序=先停全部旧 worker 再上新代码（滚动重启单实例时天然满足）；报告如实登记为部署序约束而非代码缺口。
2. **P0｜历史存量数据未脱敏**：本批只守新增写入口；`user_memory_event` 既有行（实测前 user_id=1 已有存量）与既有向量索引中的历史明文不回溯清洗（append-only 表不适合就地改写，且存量规模/敏感度未盘点）。残留风险：历史明文仍可被召回。建议后续登记「存量扫描+按需 rewind/invalidate 清理」任务。
3. **P0｜模式级脱敏的对抗性盲区**：正则范式对**结构未知**的敏感面（如自定义格式私钥块、拆写在多句中的密钥、图片/PDF 内容）无覆盖；key=value 词表有限（可被 `pass word`/变体绕过）。定位为**纵深防御一层**（与 T19-3/MCP P0-③ 同级），非完整 DLP；误伤率靠「特异先于泛化+边界守护+字母数字混合」压制（37 例含 8 组不误伤参数化），但对未知格式零承诺。
4. **P2｜蓝图条款漂移**：dev-plan-reshape-r.md 登记 R08=「skill 路径可移植（P2-12 承接）」、R04-b=「MCP env_json/http_headers_json 掩码」，与任务书的记忆域口径不同。按任务书「吞并两条同域任务+若蓝图无细节按任务书执行」执行了记忆域改造；MCP 落库脱敏此前已由 W-NEXT-MCP-001 P0-③ 落地（executor.py `_redact_sensitive`），skill 路径可移植项在蓝图中仍为未承接状态，需编排者在 tracker 里对账。
5. **P2｜E2E 双写副产物**：实测期间 :8000/:8001 双实例共享 Redis 队列与 MySQL，造成一次×2 的重复记忆行（已精确清理）；若其他 agent 恰在实测窗口做记忆验收，可能读到本批探针行（已全部清理，无残留）。

## 五、批判承接核对（任务书第 5 项）

无承接项（任务书未列上游遗留批判）。上述自批判 P0-1/P0-2 建议登记 tracker；P2-4 蓝图对账需编排者裁定。

## 六、资产消费证据

- 消费 `.ai-hub/plans/dev-plan-reshape-r.md`（R04-b/R08 条款）+ `formal-prd-edu-agent-refactoring.md` §终审缺陷⑥（P2-12/P3-23,24 派生）+ `audit-edu-rag-mcp.md:211`（P3-24 原始条款）——发现蓝图口径与本任务书漂移（见 P2-4）。
- 消费 `AGENTS.md` 教训 11（落库口径=先查事件表、HEAD 判据）——贯穿测试断言与实测 SQL；教训 8（真实契约优先）——E2E 前先实测 login 字段（`account` 非 `username`）与 SSE `event:`+`data:` 双行格式；教训 2（禁 Playwright、独立实证）——全部用 httpx/curl/直连 DB。
- 复用既有资产：`app/common/log_sanitizer.py`（手机/邮箱正则）、`app/mcp/executor.py`（`***REDACTED***` 口径）、`tests/test_contract_task_r01.py`（离线夹具范式：offline_broker / MemEventMemoryPersistence / DeterministicEmbedder / service 单例换件）。

## 七、改动清单（本批归属）

| 文件 | 变更 |
|---|---|
| `app/ai/memory/sanitize.py` | 新增：模式级脱敏（R04-b 核心，~190 行） |
| `app/ai/memory/queue.py` | enqueue_candidate/enqueue_turn_window 接线脱敏 + `v=2` + `_detect_payload_shape` + docstring |
| `app/ai/memory/service.py` | `build_turn_window` + 半窗守卫 + docstring（`enqueue_turn` 签名/旧契约不变） |
| `app/chat/service.py` | R08 两调用点对齐 + `make_stream_finalize` 可选 `memory_history_window`（graph_stream 零改动） |
| `tests/test_contract_rmem1_sanitize_window.py` | 新增 37 例 |
| `tests/test_contract_task_m1.py` | 预存污染修复（autouse 快照/恢复，+16 行） |
| `scripts/eval/rmem1_offline_worker_probe.py` | 新增离线 worker 实测脚本 |
| `test-reports/RMEM1-completion-report.md` | 本报告 |

红线遵守：未触碰 `retriever.py`/`langgraph_agent.py`/子代理模块/`app/core/**`；`config.py` 零改动；`event_persistence.py` 零 diff（检索/HEAD 零改动）。

## 八、Commit

- 主体实现：`41f2c6d` `fix(memory)/W-NEXT-R-MEM-001: R04-b 落库脱敏 + R08 enqueue_turn 完整对话窗`（7 files, +829/−17；sanitize.py 新增 172 行、契约测试 412 行）。
- 报告回填：本提交（`docs(report)/W-NEXT-R-MEM-001`）。
