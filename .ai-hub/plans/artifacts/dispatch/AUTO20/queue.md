# AUTO20 队列（20 任务 · 唯一事实源 · 2026-09-21 起跑）

| # | 任务 | 开工令 | 状态 | 验收证据 | SHA |
|---|---|---|---|---|---|
| 1 | REWORK-1: P0-1+P0-6 记忆槽位 update 语义+召回最新优先+演示账号治理（三核闸） | REWORK-FEAT-WIRE-V2 §1 | **running** | 待验收 | — |
| 2 | REWORK-2: P0-2 chat 记忆反馈条（「已记住：…」） | REWORK-FEAT-WIRE-V2 §2 | pending | — | — |
| 3 | REWORK-3: P0-3 83 个 delegated 元素 CDP 点击差分+坏 handler 修复 | REWORK-FEAT-WIRE-V2 §3 | pending | — | — |
| 4 | REWORK-4: P0-4 ≥100MB 上传全链+失败注入+错误态 | REWORK-FEAT-WIRE-V2 §4 | pending | — | — |
| 5 | REWORK-5: P0-5 管理端会话审计只读视图（admin-only 端点+页面+角色硬校验） | REWORK-FEAT-WIRE-V2 §5 | pending | — | — |
| 6 | SEED-VIDEO: 120 真实视频生成+82 万行三核闸接线+播放验证 | TO-EXEC-SEED-VIDEO | pending | — | — |
| 7 | 限流前缀收窄：/api/trade/orders 被 /api/trade/order 规则误伤（429 无 CORS 假红根因） | 新写 | pending | — | — |
| 8 | F-W1-GUARD: 答案层捏造工具回执机检护栏（answer 提及工具名而凭据空→拦截/降级标） | tracker C-W1-② | pending | — | — |
| 9 | C-W1-③: mcp_tool_calls 六节点路径透传（SubagentResult.full_tool_outputs→响应体） | tracker C-W1-③ | pending | — | — |
| 10 | GATE-V3: 门禁数据就绪竞态机制化（courses 动画/my-cohorts/me 的 settle→数据就绪探测） | tracker 登记 | pending | — | — |
| 11 | R26: ⑯ BGE 冷启动 40s+ 诊断（崩溃后 GPU 态/进程级加载） | tracker 候选 | pending | — | — |
| 12 | ARKBAT-B: glm-5.3-flash 质量盲评（20 query×2 模型+DeepSeek judge）+故障转移演练 | kickoff-ARKAPI 残余 | pending | — | — |
| 13 | BLIND-WAVE: 执行盲测队列累积场景（随 1-12 完成滚动入队） | blind-test-queue.md | pending | — | — |
| 14 | 双前端对账表: React 路由面 vs 25 静态页功能对照（docs/ 入库） | FEAT-WIRE B6 残余 | pending | — | — |
| 15 | course_create batch-2: HITL 实弹（测试窗开 HITL_ENABLED→confirm/reject 全链→恢复） | 时光.md §四+变更单 | pending | — | — |
| 16 | 全站四门终扫+G10 再演（REWORK 全部消化后回归锁定） | GATE-V2 工具 | pending | — | — |
| 17 | Mimosa 全量审计重跑（消除 scanner_enobufs fail-open 窗口+验证排除门全链路） | MIMOSA-EXCL 披露 | pending | — | — |
| 18 | 文档同步: 用户使用手册/面试演示方案补新功能（记忆反馈/审计视图/上传/新门禁） | docs/ | pending | — | — |
| 19 | push GitHub 批量（18 单全部验证后；用户既有多轮 push 指令） | — | pending（user-gate 备注可绕） | — | — |
| 20 | 缓冲槽: 1-19 返工消化/新批判承接项（动态分配；无则执行盲测补充轮） | — | pending | — | — |

## user-gate（需用户在线，跳过不停轮）
- UAT 十场景（用户实测口径重跑）
- 重塑后续风格类裁定（如有）

## 汇报点
- 每满 20 个 verified 任务向用户全量汇报（含批判登记/盲测结果/挂起项）
