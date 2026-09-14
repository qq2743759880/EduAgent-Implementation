# task C-16 · 演示可交付度仍被"VMware+Docker 双优先级依赖"绑架:check-demo 当日实测绿 5/8(Milvus/Mongo/Redis 全红),管理线 E2E 唯一 ENV_BLOCKED 即知识库分区;A 批只交付了检查单(C16 的 A 部分),存储五件套收敛为 2 件的 C 阶段里程碑零动作,知识库/RAG/检索整条演示线在 VM 关机时全灭,断链兜底只有"报红指引"没有"降级可用"

> 执行者：待指派子 agent。验收者：独立测试 agent。承接批判 C-16（来源：task19-技术批判.md，2026-09-12）。

## 目标

演示可交付度仍被"VMware+Docker 双优先级依赖"绑架:check-demo 当日实测绿 5/8(Milvus/Mongo/Redis 全红),管理线 E2E 唯一 ENV_BLOCKED 即知识库分区;A 批只交付了检查单(C16 的 A 部分),存储五件套收敛为 2 件的 C 阶段里程碑零动作,知识库/RAG/检索整条演示线在 VM 关机时全灭,断链兜底只有"报红指引"没有"降级可用"（完整批判见原文件）

## 修复措施

C 阶段 pgvector 收敛占位立即给出最小验证脚本(2629×2048 双引擎 P95/召回对比,预期同量级即退役 Milvus);短期给检索线加 BM25/空态降级开关,Milvus 断链时 chat/RAG 页给诚实降级而非报错

## 落点

待指派（由编排者分配子 agent 承接；文档模板见 `docs/history/tasks/` 既有 task 文档）

## 验收指标

跑通 pgvector 2629×2048 对比脚本;关 VM 后 chat 页应出降级文案而非异常

## 竞品对标

https://supabase.com/blog/openai-embeddings-postgres-vector（2026-09-12）

## 引用

- 原批判文件：`task19-技术批判.md`
- 竞品 URL：https://supabase.com/blog/openai-embeddings-postgres-vector
- 任务文档：`docs/history/tasks/critique-C-16-task.md`
