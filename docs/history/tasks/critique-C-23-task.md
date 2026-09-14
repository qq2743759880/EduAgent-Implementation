# task C-23 · 部署包"最小"的代价是**组件面最宽**：演示一条链路要 MySQL(宿主)+Redis(Docker)+Milvus/Mongo/MinIO/Neo4j(VM)+uvicorn+next 共 8 个运行件，任一不可达在 DEBUG=false 下**整体拒启**（C0 §5 实证）；附录 docker-compose 资产（MySQL+MinIO+etcd+Milvus+Mongo+Neo4j+前后端）存在但从未端到端验证，且 compose 路线与 deploy.mjs 路线是两套互不相认的事实源

> 执行者：待指派子 agent。验收者：独立测试 agent。承接批判 C-23（来源：C5-技术批判.md，2026-09-13）。

## 目标

部署包"最小"的代价是**组件面最宽**：演示一条链路要 MySQL(宿主)+Redis(Docker)+Milvus/Mongo/MinIO/Neo4j(VM)+uvicorn+next 共 8 个运行件，任一不可达在 DEBUG=false 下**整体拒启**（C0 §5 实证）；附录 docker-compose 资产（MySQL+MinIO+etcd+Milvus+Mongo+Neo4j+前后端）存在但从未端到端验证，且 compose 路线与 deploy.mjs 路线是两套互不相认的事实源（完整批判见原文件）

## 修复措施

① 附录头部加"未端到端验证"显著横幅+与 deploy.mjs 路线的适用场景对照表（当前唯一正路=deploy.mjs）；② C 阶段全量把 compose 路线验证收口（healthcheck+种子导入+单命令），届时 VM 四件套进 compose 即可退役 VMware 拓扑

## 落点

待指派（由编排者分配子 agent 承接；文档模板见 `docs/history/tasks/` 既有 task 文档）

## 验收指标

compose 栈在一台有 Docker 的机器 up 后 /health/detail 全 ok + check-demo 8/8（含⑦关键页）；对照表落 README 附录

## 竞品对标

https://supabase.com/docs/guides/self-hosting（2026-09-13）

## 引用

- 原批判文件：`C5-技术批判.md`
- 竞品 URL：https://supabase.com/docs/guides/self-hosting
- 任务文档：`docs/history/tasks/critique-C-23-task.md`
