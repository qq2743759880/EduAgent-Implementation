<!-- 项目本地批判 tracker v1：供 tt/scripts/critique-backlog-next.mjs 优先读取（优先级高于 TT 技能全局回退）。
     权威叙事 tracker 在 .opencode/plans/critique-backlog-tracker.md（人工维护）；本文件为机验解析形态，新增条目按同列序追加。
     来源说明：C-16..C-24 于 2026-09-12/13 由 review-gate --auto-register 误登记至 TT 技能目录（D:/.ai-hub/skills/tt/plans/critique-backlog-tracker.md），
     2026-09-14 迁回本项目（docs/history/tasks/critique-C-1x-task.md 同步落位）；TT 目录内遗留副本待清理，以本文件为准。
     C-10..C-12 为 TT 工具链级批判（宿主/CLI/sdk 类），非本项目病灶，不在本表登记。 -->
| # | 批判（来源） | 级别 | 修复措施 | 落点任务 | 验收指标 | 状态 |
|---|---|---|---|---|---|---|
| C-16 | 演示可交付度仍被"VMware+Docker 双优先级依赖"绑架:check-d（来源：task19-技术批判.md，2026-09-12） | P1 | C 阶段 pgvector 收敛占位立即给出最小验证脚本(2629×2048 双引擎对比) | docs/history/tasks/critique-C-16-task.md | 跑通 pgvector 2629×2048 对比脚本;关 VM 后 chat 页应出降级文案而非异常 | ⬜ 待落地 |
| C-17 | 学生端核心读路径性能不达演示底线:GET /api/series/1 当日两次实测慢（来源：task19-技术批判.md，2026-09-12） | P1 | 定位 series/1 慢查询(explain/N+1)→套用既有 task39 缓存模式 | docs/history/tasks/critique-C-17-task.md | series/1 加缓存后压测 P95<500ms;无缓存时 explain 报告定位慢因 | ⬜ 待落地 |
| C-18 | 错误契约泄漏:Milvus 断链时 GET /api/knowledge/partitions 泄内部异常（来源：task19-技术批判.md，2026-09-12） | P1 | error_codes 增"依赖不可用"类目(如 50301 DEPENDENCY_UNAVAILABLE)并全局兜底 | docs/history/tasks/critique-C-18-task.md | 停 Milvus 调 /api/knowledge/partitions 应 503+脱敏 message;补一条 pytest 契约用例锁行为 | ⬜ 待落地 |
| C-19 | A 批 15 页全静态 IIFE 接线收口,但形态债未还:admin 仪表盘实测（来源：task19-技术批判.md，2026-09-12） | P2 | 立即启动 B0 审计(与 A 收口并行);B0 DEMO spike 量化 React 迁移收益 | docs/history/tasks/critique-C-19-task.md | B3 admin-users Refine 版代码量<静态页 1/3(可证伪);B0 审计文档含 spike 代码量对照表 | ⬜ 待落地 |
| C-20 | start"读 .env 形态原样、不做替换"是优点也是漏洞：无形态断言门（来源：C5-技术批判.md，2026-09-13） | P2 | deploy.mjs start 增加 `--profile prod或dev` 显式参数：prod 时断言 .env 满足 DEBUG=false+ENV_NAME=prod+密钥非默认+CORS 双源，不满足即 exit 2 拒绝启动 | docs/history/tasks/critique-C-20-task.md | prod 形态缺项启动被拒(exit 2)且报缺失项;dev 形态不受影响 | ⬜ 待落地 |
| C-21 | 进程治理是"裸 spawn"级：后端 uvicorn/前端 next start 无 PID 登记/健康复查/日志轮转（来源：C5-技术批判.md，2026-09-13） | P1 | start 拉起后登记 PID+一次性健康复查循环(可选 --watch 重拉)+stop 优雅终止+日志轮转 | docs/history/tasks/critique-C-21-task.md | kill -9 后端 PID，--watch 应重拉并记录事件；stop 后确认 uvicorn 退出码非强杀路径；日志轮转触发一次 | ⬜ 待落地 |
| C-22 | 安全清单有"点"无"面"：_security_guard 与 P1 修复分散，无聚合门（来源：C5-技术批判.md，2026-09-13） | P1 | deploy.mjs 加 `security-check` 子命令：聚合全部安全断言一次跑全绿/红 | docs/history/tasks/critique-C-22-task.md | security-check 在 prod 形态一次跑全绿、人为把 DEBUG 改回生效态时应红；fallback 窗口内旧 token 可用 | ⬜ 待落地 |
| C-23 | 部署包"最小"的代价是组件面最宽：演示一条链路要 MySQL+Redis+MinIO+Milvus 全家桶（来源：C5-技术批判.md，2026-09-13） | P2 | 附录头部加"未端到端验证"显著横幅+与 deploy.mjs 路线适用场景对照表 | docs/history/tasks/critique-C-23-task.md | compose 栈在一台有 Docker 的机器 up 后 /health/detail 全 ok + check-demo 8/8（含⑦关键页）；对照表落 README 附录 | ⬜ 待落地 |
| C-24 | "一键"只覆盖服务进程编排，不覆盖依赖自举：start 前置检查缺失（来源：C5-技术批判.md，2026-09-13） | P1 | 给 deploy.mjs 加 `doctor` 子命令：逐项检查 venv/node_modules/库表/服务可达并给处置 | docs/history/tasks/critique-C-24-task.md | 在干净目录 `node deploy.mjs doctor` 应逐项报"缺 venv/缺 node_modules/edu 库 0 表"并给处置；README 全流程计时报告一份 | ⬜ 待落地 |
