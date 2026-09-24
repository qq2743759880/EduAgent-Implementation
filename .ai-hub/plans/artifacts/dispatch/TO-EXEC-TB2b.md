# TO-EXEC-TB2b — OTel 真瀑布：扩域修复（编排者裁定：批准选项②，TB2 阻塞上报转正式扩域单）

> 分支 `feature/opt-waves`。TB2 执行者三层定因（① exporter 裸 POST 缺 `/v1/traces`；② `otel/exporter.py` 发私有 JSON 非 OTLP resourceSpans 信封；③ 业务链路 child_span/start_span 生产调用点=0）编排者已采纳，**裁定走选项②补分层 span**——owner 对 OTel 的原始裁定是"部署 Jaeger 看真瀑布"，删句回退仅当本单再失败才启用。开工令自包含。

## 背景定性（TB2 已证，本单承接）

- Jaeger 站可用：容器 `eduagent-jaeger`（OTLP HTTP 宿主 127.0.0.1:14318 ← 4318 被他人容器占用；UI 16686），手工 span 父子瀑布已验证。**容器保留，勿删**。
- 探活绿≠链路通：`_tcp_probe` 纯 socket 握手不发 HTTP——本单须把探活升级为发真实 OTLP HTTP 探测（或至少在文档标注局限）。
- 「脚手架齐备、链路未接」第二次出现（上次 can_use_tool 权限门）——本单闭环定义=Jaeger UI 看到一条真实 chat 请求的分层瀑布，不是"export enabled 日志"。

## 工作项

1. **导出路径**：`.env` 设 `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:14318/v1/traces`；同时**停用私有 `OTEL_EXPORT_ENDPOINT`** 路（注释掉或置空，防双路 400 噪音）。字节级 .env 编辑纪律（禁 echo 追加）。
2. **导出体**：将 `app/observability/otel/exporter.py` 的私有 dict 导出替换为真 OTLP：优先走 OTel SDK 的 OTLPSpanExporter（`opentelemetry-exporter-otlp-proto-http`，查 .venv 是否已装，缺则报备再加依赖）；私有 JSON 路径退役（保留兼容开关或直接删，报告里说明取舍）。
3. **分层 span**（瀑布主体）：chat 链路内嵌 child span——至少 `chat.request`（root）→ `retrieval`（含三通道/重排子段如有现成 hook 点）→ `llm_call`（含上游模型名 attr）→ `tool_calls`（如有）→ 响应。用现有 `child_span`/`start_span` 基建，**kind/parentSpanId/时间戳/状态齐**；失败路径 span 也要记录（status=error）。埋点点位选入口层（router/sse/服务层分界），**禁改 `app/chat/service.py` 的并发槽逻辑（TA5 所有，只许在其外围包裹 span）**。
4. **顺序依赖（硬性）**：TA5（并发槽泄漏修复）先落地——开工前 `git log --oneline -5` 确认 TA5 commit 在基线里；TA5 未落地先做 1-2 步与埋点设计，第 3 步动 service 邻接文件前再核对。同文件冲突时以 TA5 为准，等它提交。
5. **端到端实证**：重启后端（窗口记录）→ student 发一次真实提问 → Jaeger UI 查询该 trace，截图瀑布（分层可见）。失败路径也造一次（如临时不可达上游）看 error span。探活升级为 HTTP 真探测并复验"绿=真通"。
6. **手册**：TB2 未写的手册站由本单补——`docs/面试演示-逐步点击手册.md`「OTel 演示站」（起容器命令含 14318 端口/发问/16686 截图位置/停容器命令）。

## 铁律

- 域：`.env`（仅 OTel 两行）、`app/observability/**`、chat 链路 span 埋点（router/sse/服务层包裹，不碰并发槽与业务语义）、手册。禁碰 executor 两 handler（TA6）、recommender（TB1）、前端。
- 若新装 pip 依赖，commit 里带 requirements 变更并单独说明。
- 不 push；单 commit：`feat(obs)/tb2b: OTel 真瀑布(OTLP 信封+chat 分层 span+HTTP 探活)+Jaeger 演示站`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TB2b.md`：三层断点逐项修复证据、Jaeger 瀑布截图、error span 证据、探活升级说明、依赖变更。
- **再次失败=启动删句回退**（TB2 开工令第 22 行条款），容器清理+简历删句由编排者执行。

## owner 验收口径（GWT）

Given Jaeger UI 打开，When owner 发起一次提问，Then UI 能看到该请求的完整分层 span 瀑布（retrieval/LLM 各段可指认）；断上游时 span 显示错误状态。
