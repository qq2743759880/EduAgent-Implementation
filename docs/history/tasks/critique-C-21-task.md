# task C-21 · 进程治理是"裸 spawn"级：后端 uvicorn/前端 next start 均 detached spawn 后无人看护——进程崩溃不自愈、宿主重启后不自启（README 巡检第 4 条自己承认"Redis 未配开机自启待验证"）；stop 用 `taskkill /F /T` 强杀无优雅关闭窗口（in-flight SSE 请求直接断）；deploy-*.log 为追加式无轮转无上限，与 12-factor"日志=事件流交给执行环境"背道而驰

> 执行者：待指派子 agent。验收者：独立测试 agent。承接批判 C-21（来源：C5-技术批判.md，2026-09-13）。

## 目标

进程治理是"裸 spawn"级：后端 uvicorn/前端 next start 均 detached spawn 后无人看护——进程崩溃不自愈、宿主重启后不自启（README 巡检第 4 条自己承认"Redis 未配开机自启待验证"）；stop 用 `taskkill /F /T` 强杀无优雅关闭窗口（in-flight SSE 请求直接断）；deploy-*.log 为追加式无轮转无上限，与 12-factor"日志=事件流交给执行环境"背道而驰（完整批判见原文件）

## 修复措施

① start 拉起后登记 PID+做一次性健康复查循环（可选 `--watch` 简单守护，崩溃重拉上限 N 次并写事件日志）；② stop 对后端先试 SIGTERM（uvicorn 优雅退出）再 taskkill /F 兜底；③ deploy-*.log 加启动时尺寸检查（>50MB 轮转为 .1 文件）；④ README 巡检第 4 条补实测结论（Redis restart 策略 `docker inspect --format '{{.HostConfig.RestartPolicy.Name}}'`）

## 落点

待指派（由编排者分配子 agent 承接；文档模板见 `docs/history/tasks/` 既有 task 文档）

## 验收指标

kill -9 后端 PID，`--watch` 应重拉并记录事件；stop 后确认 uvicorn 退出码非 9 强杀路径；日志轮转触发一次

## 竞品对标

https://12factor.net/（2026-09-13）

## 引用

- 原批判文件：`C5-技术批判.md`
- 竞品 URL：https://12factor.net/
- 任务文档：`docs/history/tasks/critique-C-21-task.md`
