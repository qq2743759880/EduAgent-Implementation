# task C-17 · 学生端核心读路径性能不达演示底线:GET /api/series/1 当日两次实测 8.1s/16.3s,courses 列表单请求 ~2s,gamification/rankings 4~8s;CDP 渲染下 learning 页会话区标题轮询 24s 仍停留"加载中…"。"点开课程详情"是演示第一动作,冷场 10 秒级直接毁节奏;Redis 基建就在手边(task39 缓存已实证 322.6ms→5.3ms)却没用在系列详情读路径上

> 执行者：待指派子 agent。验收者：独立测试 agent。承接批判 C-17（来源：task19-技术批判.md，2026-09-12）。

## 目标

学生端核心读路径性能不达演示底线:GET /api/series/1 当日两次实测 8.1s/16.3s,courses 列表单请求 ~2s,gamification/rankings 4~8s;CDP 渲染下 learning 页会话区标题轮询 24s 仍停留"加载中…"。"点开课程详情"是演示第一动作,冷场 10 秒级直接毁节奏;Redis 基建就在手边(task39 缓存已实证 322.6ms→5.3ms)却没用在系列详情读路径上（完整批判见原文件）

## 修复措施

定位 series/1 慢查询(explain/N+1)→套用既有 task39 Redis 读缓存模式;列表/详情接口加 P95 埋点进 check-demo;前端详情页补骨架屏把感知等待拆给 loading 态

## 落点

待指派（由编排者分配子 agent 承接；文档模板见 `docs/history/tasks/` 既有 task 文档）

## 验收指标

series/1 加缓存后压测 P95<500ms;无缓存时 explain 报告定位慢因

## 竞品对标

https://httparchive.org/reports/state-of-the-web（2026-09-12）

## 引用

- 原批判文件：`task19-技术批判.md`
- 竞品 URL：https://httparchive.org/reports/state-of-the-web
- 任务文档：`docs/history/tasks/critique-C-17-task.md`
