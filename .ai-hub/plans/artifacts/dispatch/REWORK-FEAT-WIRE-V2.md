# REWORK-FEAT-WIRE-V2 — 返工令：6 个 P0（编排者批判审计 ORCH-AUDIT-feat-wire-v2.md 全文为输入）

> 纪律不变：新前端（127.0.0.1:3322 + public/*.html）实测为唯一准则；每项三段式证据（复现→修法→修后实证）。审计报告：`test-reports/ORCH-AUDIT-feat-wire-v2.md`（必读，含每项实证数据与修法锚点）。

## 返工项（按序）

1. **P0-1+P0-6（一起修，记忆链路）**：名字槽位 update 语义（新名字 create 事件关闭旧名字 valid_to，事件溯源 HEAD 判据=AGENTS 教训11 原文 `valid_to IS NULL AND event_type<>'delete'`）+ 召回注入按「同槽位最新 HEAD 优先」排序 + 演示账号冲突记忆一次性治理（三核闸，备份 user_memory_event 受影响行）。**验收=编排者重复实测：A 会话说新名字→B 会话 5 秒内问→答对**（5 秒不是 45 秒，若提取仍异步需前置到 answer 同步路径）。
2. **P0-2**：chat 页答后反馈条（有记忆事件落库时显示「已记住：…」，无则不显示）；验收=CDP 截图。
3. **P0-3**：83 个 delegated 元素逐一 CDP 点击差分（前后 DOM/网络差），坏 handler 当场修；产出 `test-reports/feat-wire-v2/matrix/delegated-differential.json`；验收=编排者抽 10 个复点。
4. **P0-4**：≥100MB 文件全链实测（ffmpeg 生成测试文件即可）+ 失败注入（中途断一片→可重试 UI）+ 进度/错误态截图；验收=编排者复传。
5. **P0-5**：管理端「会话审计」只读视图：admin-only 后端端点（分页+按 user_id 过滤，服务端角色硬校验）+ admin 页面入口（明确「审计用途」标注）；验收=编排者用 admin/student 双角色实测隔离边界。

## 铁律

同 FEAT-WIRE-V2（行为层授权延续；后端修必配 pytest；SQL 参数绑定；不 push；分项独立 commit；报告 `REPORT-REWORK-FEAT-WIRE-V2.md`）。注意 P0-1 的记忆修复禁破坏 user_memory_event append-only 语义——update 用 valid_to 关旧事件实现，不 UPDATE 旧行内容。
