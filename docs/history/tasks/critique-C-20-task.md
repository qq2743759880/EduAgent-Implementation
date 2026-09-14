# task C-20 · start"读 .env 形态原样、不做替换"是优点也是漏洞：**无形态断言门**——.env 是 dev 形态（DEBUG=true）时 start 照常拉起全栈且 exit 0（本次实测 WARN 后 8/8 全绿），一个不知情的运维会把 dev 形态当成"部署成功"交差；十二因子要求 build/release/run 三阶段分离、release 阶段固化 config，我们 release 阶段根本不存在，配置正确性全押在"用户自己读过 README §2"上

> 执行者：待指派子 agent。验收者：独立测试 agent。承接批判 C-20（来源：C5-技术批判.md，2026-09-13）。

## 目标

start"读 .env 形态原样、不做替换"是优点也是漏洞：**无形态断言门**——.env 是 dev 形态（DEBUG=true）时 start 照常拉起全栈且 exit 0（本次实测 WARN 后 8/8 全绿），一个不知情的运维会把 dev 形态当成"部署成功"交差；十二因子要求 build/release/run 三阶段分离、release 阶段固化 config，我们 release 阶段根本不存在，配置正确性全押在"用户自己读过 README §2"上（完整批判见原文件）

## 修复措施

deploy.mjs start 增加 `--profile prod

## 落点

待指派（由编排者分配子 agent 承接；文档模板见 `docs/history/tasks/` 既有 task 文档）

## 验收指标

dev` 显式参数：`--profile prod` 时断言 .env 满足 DEBUG=false+ENV_NAME=prod+密钥非默认+CORS 双源，不满足即 exit 2 拒绝拉起（不替改，只断言）；无参数维持现状（幂等兼容）；C3 生产验收脚本即复用此门

## 竞品对标

https://12factor.net/（2026-09-13）

## 引用

- 原批判文件：`C5-技术批判.md`
- 竞品 URL：https://12factor.net/
- 任务文档：`docs/history/tasks/critique-C-20-task.md`
