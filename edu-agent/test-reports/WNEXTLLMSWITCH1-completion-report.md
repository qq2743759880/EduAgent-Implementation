# W-NEXT-LLMSWITCH-001 完成报告：非流式 chat 主模型切换 deepseek-flash（thinking disabled）

- 日期：2026-09-18　|　执行：ZCode subagent（编排者派单）
- 分支：`feature/opt-waves`，起点 tip = `badb2f640e5efaad08c22db2a1b34eab121e4208`（提交前 3 探针复核一致，parent 纯前向）
- 收口对象：`critique-backlog-tracker.md` task29 批判②（非流式 P95 14.8~19.7s，"推理模型物理下限，突破需换非推理模型"）
- **Key 脱敏声明**：本报告与新增代码/脚本均不含完整 key；所有 sk-*/ark-* 引用一律 `前8***后4` 脱敏。probe/盲测脚本运行时从 `.env` 现读，不落盘、不打印。

---

## 1. 结论（TL;DR）

非流式 `/api/chat` 端到端 P95：**11449ms → 6166ms（-46.1%）**；较 2026-09-05 历史基线 14.8~19.7s **下降 58%~69%**。答案生成 LLM 单次耗时：deepseek-v4-flash（推理态）6.7~7.9s → deepseek-flash（thinking disabled）2.5~4.1s（中位 3.3s，含 RAG 上下文全文生成）。流式路径零回归（SSE start→retrieval→token×61→done，TTFT 1599ms）。chat 受影响面 pytest 141 通过、0 新增失败。

## 2. 代码勘察（切换前事实链）

非流式 chat 主模型调用链（`model="strong"`）：

```
POST /api/chat → router.chat_non_stream → service.chat_answer
  → app.ai.graph.run_agent（service.py:22 `from app.ai.graph import run_agent as run_langgraph_agent`）
  → sixnode harness answer_node
      非流式：app/ai/harness/sixnode.py:383 `_llm_call(messages, model="strong", ...)`（失败降级 fast:387）
      流式　：sixnode.py:430-432 `call_chat_stream_with_retry(model="strong")`
  → app/chat/generator.py `_ChatClient.call_chat / call_chat_stream`（唯二请求体构造点）
```

- FAST 档（minimax-m3）只承担意图决策/reflect/记忆抽取等短输出调用（max_tokens 20~30），**不是**非流式答案生成主模型——编排者简报中"非流式主模型=STRONG"经代码勘察**属实**。
- `.env` LLM 请求体构造仅 generator.py 两处；OpenAI 兼容层为裸 `requests.Session.post(json=body)` 直传，**额外字段天然透传**，无需网关分支。

### 勘察中发现的两个隐藏环境缺陷（P0 级，比模型名更致命）

1. **`.env` 双源 base URL 行被乱码注释行吞掉**：`LLM_STRONG_BASE_URL` / `LLM_FAST_BASE_URL` / `LLM_BASE_URL` 都位于 `#` 开头的 mojibake 注释行内（历史上被按 latin-1 误写，注释与赋值挤在同一行），python-dotenv 整行跳过 → 运行时 effective 值为**空字符串**（fresh probe 实测 `LLM_STRONG_BASE_URL=''`、`LLM_FAST_BASE_URL=''`），全部回退 `LLM_BASE_URL` config 默认值 `https://dashscope.aliyuncs.com/compatible-mode/v1`。即：**干净重启后 STRONG（deepseek sk- key）与 FAST（ark- key）都会打到 DashScope 全部鉴权失败**。旧进程今天仍能出真实答案，全靠启动 shell 里遗留的 env 导出（进程外不可见、不可复制）。编排者简报"STRONG = LLM_STRONG_BASE_URL=https://api.deepseek.com 已生效"的前提**不成立**。
2. **deepseek-v4-flash 已从 /models 下架但 completions 仍服务**：官方 `GET /models` 只返回 `['deepseek-flash', 'deepseek-v4-pro']`（实测 200）；`POST /chat/completions` 传 `deepseek-v4-flash` 今日仍 200（带 reasoning_content，max_tokens=10 时 content_len=0 全被推理吃掉）。"随时可能彻底下线 + 默认强制推理"双风险成立，切换必要性确认。

## 3. 变更清单（diff 摘要）

| 文件 | 变更 |
|---|---|
| `.env`（**未 git 跟踪**，不进 commit） | ① 目标行 `LLM_MODEL_STRONG=deepseek-v4-flash` → `LLM_MODEL_STRONG=deepseek-flash`（字节级单处替换）；② 补两行修复（与乱码注释行内既有意图同值）：`LLM_FAST_BASE_URL=https://ark.cn-beijing.volces.com/api/plan/v3`、`LLM_STRONG_BASE_URL=https://api.deepseek.com`。其余字节逐一复核不变（备份比对 `rest identical: True`，行尾 `\r\r\n` 风格保持）。FAST 模型名/minimax-m3 未动。 |
| `app/config.py` | 新增 `LLM_THINKING_DISABLED: bool = True`（注释：仅对生效模型名 `deepseek-*` 的 DeepSeek 混合模型生效；流式不注入）。 |
| `app/chat/generator.py` | ① 新增 `_inject_thinking_disabled(body, model)`：开关开 + 生效模型名 `deepseek-` 前缀门控 → 注入 `"thinking": {"type": "disabled"}`；② `call_chat`（非流式）构造后调用注入；③ HTTP 400 且响应文本提及 thinking → 剥除该字段同模型重试一次 + WARNING 告警（三态③容错，不整链误降级 FAST）；④ `call_chat_stream`（流式）**不注入**（见 §6 决策）。 |
| `tests/test_wnext_llmswitch_thinking.py`（新增） | 8 个用例：状态①注入生效 ×2、状态②开关关闭回推理态 ×2、状态③容错 ×4（非 deepseek 不注入 / 400-thinking 剥除重试且不打扰 FAST / 400 无关原因正常抛出且既有切源链确认 / 流式永不注入）。stub 网关，无真实网络依赖。 |
| `scripts/_wnextllmswitch1_blind.py`（新增） | 真实 API 三态盲测可复跑脚本（app 真实请求体 capture→原样重放观测 reasoning_content；未知模型 400 容错）。 |
| 契约/前端/eval 旧脚本 | **零改动**（模型是配置层，不涉 `contracts/`、`edu-frontend/`、`scripts/eval/` 既有脚本）。 |

## 4. 真实实测（真实 HTTP + 真实 key，全链路同机同日对比）

### 4.1 非流式端到端（`scripts/_perf_chat_nonstream.py`，3 问题 × n，user000001 真登录）

| 指标 | 切前（deepseek-v4-flash 推理态，n=9，15:32） | 切后（deepseek-flash thinking disabled，n=15，15:52） | 变化 |
|---|---|---|---|
| P50 | 8156ms | **5813ms** | -28.7% |
| P90 | 11449ms | **6144ms** | -46.3% |
| **P95** | **11449ms** | **6166ms** | **-46.1%** |
| MAX | 11449ms | 6166ms | -46.1% |
| 成功率 | 9/9 HTTP 200 | 15/15 HTTP 200 | — |

- 历史 backlog 基线（2026-09-05）：P95 14.8~19.7s → 本次 6166ms，**-58%~-69%**，达成"进入秒级"目标。
- 答案生成 LLM 单次（logs/app.log `[LLM] ... non-stream`）：切前 deepseek-v4-flash 6726~7875ms → 切后 deepseek-flash 2541~4126ms（中位 3296ms，**-55%**；含 5 篇 RAG docs 上下文完整作答）。
- 对照官方裸 probe（短 prompt）：deepseek-flash thinking disabled 573~896ms、`reasoning_content=NONE`；默认推理态 765~921ms、`reasoning_content PRESENT`（88 reasoning_tokens）。

### 4.2 流式回归（SSE 契约）

- `POST /api/chat/stream` 真实一轮：帧序压缩 `start → retrieval → token → done`，61 个 token 帧，总 4438ms，HTTP 200 —— 与 `tests/test_sse_envelope_contract.py` 钉死契约一致。
- 流内模型确认（logs `[LLM-stream]`）：`model=deepseek-flash`，首 token 1599ms / 完成 1820ms。流式路径未注入 thinking（推理 delta 为 `delta.reasoning_content`，现解析器仅取 `delta.content`，自动跳过，内容正确）。
- 测试：受影响面 12 个测试文件 141 passed / 2 skipped / **0 本次新增失败**。唯一失败 `test_wnext2_write_tools.py::test_t8c2_resume_without_pending...`（HITL confirm-expired）经 `git stash` 在 clean HEAD `badb2f6` 上复现同败，属预存问题，与本次无关。

## 5. 三态盲测（真实 API，`scripts/_wnextllmswitch1_blind.py`）

| 态 | 条件 | 实测 | 判定 |
|---|---|---|---|
| ① disabled 生效 | 默认 `.env`（开关 True） | app-path 594ms；wire body `thinking={'type':'disabled'} model='deepseek-flash'`；同体重放 `reasoning_content=NONE` | PASS |
| ② 开关注释/关闭 → 回推理态 | env `LLM_THINKING_DISABLED=false` 覆盖 | wire body `thinking=None`；重放 `reasoning_content PRESENT len=96, reasoning_tokens=53`（推理态回归） | PASS |
| ③ 未知模型容错 | `LLM_MODEL_STRONG=deepseek-nonexistent-xyz` | 400 `The supported API model names are deepseek-flash, deepseek-v4-pro`（顺带实证下架口径）；`requests_made=1`（未误触发剥除重试）；异常上抛交既有 `invalid_request_error→MODEL_ERROR→FAST↔STRONG 立即切源` 链 | PASS |

说明：真实网关目前不存在"支持 thinking 之外又拒绝 thinking 参数"的 DeepSeek 模型，400-thinking 剥除重试分支由单测 stub 钉死（`test_deepseek_400_thinking_strips_and_retries_same_model`）；未知模型 400 不误触剥除已真实 API 验证。

## 6. 关键设计决策

- **流式不加 thinking disabled**：流式 P95 6.4s 已被用户裁定达标（task29 批判②收口口径"以流式为准"），推理流式语义保持，TTFT 基线不动；若产品后续想要流式提速，注入同参数并补 `delta.reasoning_content` 帧审计即可（单测 `test_stream_path_never_injects_thinking` 已把现状钉死）。
- **FAST（minimax-m3）不动**：ark plan/v3 侧无同等 thinking 开关注册（volces thinking 参数面向 doubao 系列，minimax-m3 未声明支持；实测注入风险>收益），且 FAST 只做短输出决策，无 reasoning 等待问题。登记：**FAST 不支持 thinking 控制**。
- **注入门控按"生效模型名"前缀 `deepseek-`**：DashScope/ark 等网关对未知字段可能 4xx，防止未来切源时注入串台。

## 7. P0 自批判（≥3 条）

1. **P0-1 编排者前提错误被当场纠出——`.env` 双源 base URL 从未生效**：简报声称 STRONG/FAST base URL 已在 `.env` 配好且生效，实际被乱码注释行吞掉，effective 为空。若按字面"仅改目标行"执行，重启后 STRONG/FAST 全部打到 DashScope 鉴权失败、LLM 全链路降级，"P95 改善"将无从测起。已以最小增量（2 行补配 + 1 行目标替换）修复并逐字节复核。**教训：凡涉 .env，先读 effective 值（fresh 解释器 probe），不信文件外观。**
2. **P0-2 测量中途环境漂移几乎造成假结论**：重启后端后首轮实测 37.5~45.9s（比切前差 3 倍）——根因是 **Redis 进程已死**（6379 无监听，auth fail-open + 各处连接重试）与 **rerank sidecar（8601）未随新后端拉起**（检索回退进程内直连 +1~2s），与本次代码无关。仅靠"P95 变差"表象定论会写出完全相反的报告。已恢复 Redis + sidecar 后重测（sidecar 恢复后检索延迟回落，e2e P95 从无 sidecar 时的 7678ms 进一步降到 6166ms）。**教训：性能对比前必须钉住环境基线（依赖服务存活清单），异常数字先查日志分解（LLM/检索/中间件分段计时），不吻合即停。**
3. **P0-3 "下架"表述过强、遗留兼容窗口未闭环**：deepseek-v4-flash 仅从 `/models` 列表消失，completions 今日仍 200——若编排者据此认为"现在已是故障态"则不成立（历史 402 主因是推理耗时+余额，模型名本身今日尚通）。切换后系统对该模型仍有隐式依赖的残留面（如历史注释、eval 脚本提及）未全量清点，彻底下线日仍可能出现散点故障。已登记，建议下个批盘点全仓 `deepseek-v4-flash` 引用。
4. **P0-4 thinking-400 剥除重试缺真实负样本**：现有 DeepSeek 在售两模型（deepseek-flash / deepseek-v4-pro）都接受 thinking 参数，"网关拒绝 thinking"的真实 400 无法构造，剥除重试分支只有 stub 单测背书。风险：若 DeepSeek 未来改错误消息措辞（不含 "thinking" 字样），该分支失活——届时退化为既有 MODEL_ERROR 切源链，功能不损但告警缺失。
5. **P0-5 FAST 档在本次全部测量中处于 ark 周配额 429 态**（`AccountQuotaExceeded`，2026-09-21 00:00 重置）：决策层 LLM 全部快速失败走规则路由，切前/切后同条件故对比仍公平；但配额恢复后决策层从 429 失败变为真实 minimax 调用，端到端分布会再漂移，本报告数字不代表配额恢复后的稳态。另注：ark 429 若发生在带 `call_chat_with_retry` 的路径会触发指数退避（最长 2+4+8+16+30s），当前答案链路为无重试 `call_chat` 不受累，但 `call_chat_with_retry` 调用面（flows/agent、tool_decision、memory extract）在配额耗尽窗口会显著变慢，属预存风险。
6. **P0-6 样本量不对等**：切前 n=9（60s 量级单样本成本下的取舍）vs 切后 n=15，P95 分位数对样本量敏感；已辅以 LLM 单次耗时分布（切前 5 个样本 6.7~7.9s vs 切后 26 个样本 2.5~4.1s）交叉验证改善结论，方向与幅度一致。

## 8. 运行态移交

- 后端 8000 / rerank sidecar 8601 / Redis 6379 均已恢复并保持运行（backend+sidecar 为本次新拉起的后台任务；Redis 为 `tools/redis/redis-server.exe`）。
- `.env` 当前生效值：`LLM_MODEL_STRONG=deepseek-flash`、`LLM_STRONG_BASE_URL=https://api.deepseek.com`、`LLM_MODEL_FAST=minimax-m3`、`LLM_FAST_BASE_URL=https://ark.cn-beijing.volces.com/api/plan/v3`（key 脱敏：sk-48687***ab36 / ark-ba52***e4cd）。
- 可复跑：`.venv/Scripts/python.exe scripts/_perf_chat_nonstream.py --n 5`、`.venv/Scripts/python.exe scripts/_wnextllmswitch1_blind.py`（及 `LLM_THINKING_DISABLED=false` 前缀跑状态②）。
- lock：`scripts/eval/wnextllmswitch1.lock` 未创建/不存在，无需清理。
