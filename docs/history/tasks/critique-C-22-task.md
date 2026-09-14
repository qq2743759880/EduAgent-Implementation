# task C-22 · 安全清单有"点"无"面"：_security_guard（密钥默认值拒启）、P1-8 门禁、无 token 401、X-Force 生产无效均为 C3 实测的**单点断言**，但没有一个可重复执行的生产安全自检命令——Django 有 `manage.py check --deploy` 一条命令扫全部部署安全项，我们 check-demo ⑧ 只测一个端点一个路径；且 JWT_SECRET 无轮换概念（轮换=全员 token 立即失效，无 fallback 窗口）、错误上报缺位（500 只进本地日志，无 ADMINS/Sentry 等价物，线上炸了没人知道）；/api/metrics 裸端点无鉴权护栏仍未收口（README 附录 task123 自检登记）

> 执行者：待指派子 agent。验收者：独立测试 agent。承接批判 C-22（来源：C5-技术批判.md，2026-09-13）。

## 目标

安全清单有"点"无"面"：_security_guard（密钥默认值拒启）、P1-8 门禁、无 token 401、X-Force 生产无效均为 C3 实测的**单点断言**，但没有一个可重复执行的生产安全自检命令——Django 有 `manage.py check --deploy` 一条命令扫全部部署安全项，我们 check-demo ⑧ 只测一个端点一个路径；且 JWT_SECRET 无轮换概念（轮换=全员 token 立即失效，无 fallback 窗口）、错误上报缺位（500 只进本地日志，无 ADMINS/Sentry 等价物，线上炸了没人知道）；/api/metrics 裸端点无鉴权护栏仍未收口（README 附录 task123 自检登记）（完整批判见原文件）

## 修复措施

① deploy.mjs 加 `security-check` 子命令：聚合无 token 401/垃圾 token 401/X-Force 无效/密钥非默认/metrics 鉴权/50301 脱敏六断言（直接复用 C3_api_assert.py 与 README 附录检查单）；② JWT_SECRET_FALLBACKS 支持（双密钥校验窗口）；③ 错误上报最小形态：500 事件写独立 error-stream 日志+可选 webhook

## 落点

待指派（由编排者分配子 agent 承接；文档模板见 `docs/history/tasks/` 既有 task 文档）

## 验收指标

`security-check` 在 prod 形态一次跑全绿、人为把 X-Force 改回 DEBUG 生效态时应红；fallback 窗口内旧 token 可用

## 竞品对标

https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/（2026-09-13）

## 引用

- 原批判文件：`C5-技术批判.md`
- 竞品 URL：https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/
- 任务文档：`docs/history/tasks/critique-C-22-task.md`
