# TO-EXEC-TB2 — OTel → Jaeger 真实链路（yy 十点修复 · P1）

> 分支 `feature/opt-waves`。owner 裁定：OTel 走 Jaeger 部署，演示"一次请求完整 span 瀑布"。开工令自包含。

## 背景

OTel SDK 埋点已在（`app/observability/`，OTLP HTTP 导出），但从未接过真实后端——启动日志一直 `OTEL_EXPORTER_OTLP_ENDPOINT 未配置，OTLP 导出 disabled`。前提 P6 裁定：Jaeger all-in-one 单容器；**失败回退=从简历删句（本单不阻断其它单）**。

## 工作项

1. **起 Jaeger**：docker 起 `jaegertracing/all-in-one`（OTLP HTTP 4318 + UI 16686，宿主端口不冲突即可；注意 docker 命令必须带 `docker exec`/docker CLI 正常用法，Redis 容器 prisma-ai 共享教训——勿动别人的容器）。容器命名 `eduagent-jaeger`，重启策略 `--rm` 手动管理（演示机不常驻）。
2. **接后端**：`.env` 设 `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318`（+按 `app/observability/otlp.py` 实际读的变量名补全）。**.env 编辑纪律：字节级保留，禁 echo 追加**（历史事故：HITL_ENABLED 被 echo 粘进注释行致开关失效）。
3. **重启后端**（9988，窗口记录起止），启动日志断言 OTLP 导出 enabled。
4. **全链实证**：发起一次真实 chat 请求（student `user000001`），到 Jaeger UI（http://127.0.0.1:16686）找到该 trace，截图 span 瀑布（应含 retrieval→LLM→响应各段）。**若 Jaeger 里没有业务 span**：先查 SDK tracer 是否真的包了 chat 链路（`app/observability/` 各 instrument 点），断在哪补哪——owner 已定性"OpenTelemetry 是假的"，本单必须产出真瀑布才算闭环。
5. **手册**：`docs/面试演示-逐步点击手册.md` 增补「OTel 演示站」：起 Jaeger 命令、发问、UI 截图位置、关停命令。

## 铁律

- 域：docker（新容器）、`.env`（OTel 变量）、手册。禁碰其它 .env 行、后端代码（除非第 4 步证断点在 SDK 接线，改动最小化并单独说明）。
- 不 push；单 commit：`feat(ops)/tb2: Jaeger all-in-one 接入 OTLP+全链 trace 演示站`（容器非文件，commit 只含手册+.env 相关说明文档；.env 本身不入库）。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TB2.md`：容器启动命令与状态、启动日志 OTLP enabled 行、Jaeger trace 截图路径、手册 diff。
- **失败回退**：Jaeger 起不来或 span 链不上且 2h 内无解——停手上报，回退=从简历删句，勿硬凑。

## owner 验收口径

Given Jaeger UI 打开，When owner 发起一次提问，Then UI 里能看到这条请求的完整 span 瀑布并能指认各阶段。
