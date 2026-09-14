# task C-18 · 错误契约泄漏:Milvus 断链时 GET /api/knowledge/partitions 返回 HTTP 500 + code 50000,message 直带内部异常串"MilvusException: Fail connecting to server on 192.168.85.101:19530"——内网拓扑(组件名+IP+端口)漏给任何登录用户;且 50000 兜底把"依赖不可用"与"代码缺陷"混进同一壳,前端无法按语义给降级文案,error_codes 表无依赖不可用类目

> 执行者：待指派子 agent。验收者：独立测试 agent。承接批判 C-18（来源：task19-技术批判.md，2026-09-12）。

## 目标

错误契约泄漏:Milvus 断链时 GET /api/knowledge/partitions 返回 HTTP 500 + code 50000,message 直带内部异常串"MilvusException: Fail connecting to server on 192.168.85.101:19530"——内网拓扑(组件名+IP+端口)漏给任何登录用户;且 50000 兜底把"依赖不可用"与"代码缺陷"混进同一壳,前端无法按语义给降级文案,error_codes 表无依赖不可用类目（完整批判见原文件）

## 修复措施

error_codes 增"依赖不可用"类目(如 50301 DEPENDENCY_UNAVAILABLE→HTTP 503),message 脱敏为"知识库服务暂不可用,请稍后重试",内部 detail 只进日志;管理端知识库页按 503 给降级横幅

## 落点

待指派（由编排者分配子 agent 承接；文档模板见 `docs/history/tasks/` 既有 task 文档）

## 验收指标

停 Milvus 调 /api/knowledge/partitions 应 503+脱敏 message;补一条 pytest 契约用例锁行为

## 竞品对标

https://docs.stripe.com/api/errors（2026-09-12）

## 引用

- 原批判文件：`task19-技术批判.md`
- 竞品 URL：https://docs.stripe.com/api/errors
- 任务文档：`docs/history/tasks/critique-C-18-task.md`
