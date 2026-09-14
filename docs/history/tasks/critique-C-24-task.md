# task C-24 · "一键"只覆盖**服务进程编排**，不覆盖**依赖自举**：start 前置检查对 MySQL/VM Milvus/Mongo/Redis 只探测给指引不拉起（VM 电源/Docker Desktop/Redis 容器均脚本能力外），venv、node_modules、edu 库快照恢复（106 表）全靠新人手工按 README §3 走；换一台干净 Windows 机照 runbook 从零到 8/8 的真实耗时从未实测——README 标注两处"待验证"（venv 安装命令历史未统一留存、快照二是否含建库语句）

> 执行者：待指派子 agent。验收者：独立测试 agent。承接批判 C-24（来源：C5-技术批判.md，2026-09-13）。

## 目标

"一键"只覆盖**服务进程编排**，不覆盖**依赖自举**：start 前置检查对 MySQL/VM Milvus/Mongo/Redis 只探测给指引不拉起（VM 电源/Docker Desktop/Redis 容器均脚本能力外），venv、node_modules、edu 库快照恢复（106 表）全靠新人手工按 README §3 走；换一台干净 Windows 机照 runbook 从零到 8/8 的真实耗时从未实测——README 标注两处"待验证"（venv 安装命令历史未统一留存、快照二是否含建库语句）（完整批判见原文件）

## 修复措施

① 给 deploy.mjs 加 `doctor` 子命令：把 README §2/§3 全部前置（venv 存在性/node_modules/BUILD_ID/edu 库表计数/快照文件存在性）逐项机检并输出通过/缺省清单；② 新机器按 README 全流程走一遍并计时，把两处"待验证"补成实测结论落回 README

## 落点

待指派（由编排者分配子 agent 承接；文档模板见 `docs/history/tasks/` 既有 task 文档）

## 验收指标

在干净目录 `node deploy.mjs doctor` 应逐项报"缺 venv/缺 node_modules/edu 库 0 表"并给处置；README 全流程计时报告一份

## 竞品对标

https://cdn.coollabs.io/coolify/install.sh`（下载脚本后管道给（2026-09-13）

## 引用

- 原批判文件：`C5-技术批判.md`
- 竞品 URL：https://cdn.coollabs.io/coolify/install.sh`（下载脚本后管道给
- 任务文档：`docs/history/tasks/critique-C-24-task.md`
