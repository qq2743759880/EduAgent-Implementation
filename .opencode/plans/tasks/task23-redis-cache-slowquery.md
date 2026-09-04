# task23: Redis 缓存落地（三防 + 热点 + 排行 ZSET）+ 慢查询索引治理

> **类型**：backend+infra ｜**执行工具**：Trae ｜**阶段**：P4 ｜**并行组**：W2 ｜**工作量**：L
> **前置**：task09, task11, task13 ｜**后置（联调节点）**：**契约冻结⑭ → 前端 task43（dashboard）、task48（学习页）性能验收**；task24 依赖

## 1. 选型依据
- tech-source-audit.md §四（缓存三防/TTL 分层：series 300s/question 600s/dashboard 60s/cohort:seats 10s/rank 600s；写后 DEL 旁路缓存；读写分离保留调参）
- doc-architect-tech-arch.md §6.1/§6.2（灰度范围：先开 course detail/cohort seats/profile，交易域暂缓）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev | 缓存点接入 + keyset 分页 + 日志缓冲 |
| 测试 | sd-tester + sd-challenger | 并发命中/失效验证 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
| 加固 | harden skill | DEL 覆盖穷尽审查 |
| 提交 | commit skill | — |

## 3. 执行方式（Trae 手动调度，无 Workflow API）

Trae Code 无 opencode 专属的 `Workflow()` API，按 `D:\.ai-hub\workflows\dev-standard.mjs` 的 8 阶段**手动调度**（效果等价）：
```
1. 开发阶段   -> 调 sd-dev + be-architect + be-validator（读任务文档 + tech-source-audit）
2. 测试阶段   -> 调 sd-tester（+ sd-challenger 对抗）；数据库校验用 RunCommand 跑 mysql CLI / Python 脚本（无 mysql MCP）
3. 修正阶段   -> 据测试报告回 sd-dev 修复
4. 审查阶段   -> 调 review-screener-1/2/3 -> review-moderator -> review-judge（SARIF）
5. 提交阶段   -> git commit（message 含 task 编号）
```

mysql MCP 未在 Trae 环境注册（当前 MCP 仅 integrated_code_mode / integrated_goal）：
- 数据库校验改用 **RunCommand + mysql CLI / Python 脚本**（先例：scripts/verify_schema.py、scripts/verify_task07_counts.py）
- 或手动在 设置->MCP 按 `D:\.ai-hub\mcp\index.json` 模板添加 mysql


## 4. 实现规划要点
- 缓存点：series 列表/详情/cohorts/modules/tree（300s）、question_bank/question（600s）、dashboard 聚合（60s）、gamification ZSET、cohort:seats（10s）
- 写后精确 DEL（旁路缓存，写路径清单穷尽：管理端直改含在内）
- 慢查询：keyset 分页、video_play_event/曝光日志 Redis List 缓冲（2s/500 条 executemany）、连接池 20/10 评估
- 索引治理对齐 task03 已建索引，补访问模式验证

## 5. 验收标准（Given/When/Then 全文）
- Given 课程详情缓存命中，When 100 并发请求同一系列，Then P95 ≤50ms 且 MySQL 主库 QPS 不随并发线性增长（对比报告）
- Given 管理端修改系列 sale_status，When 写操作完成，Then 相关缓存 key 精确 DEL，1s 内新值可见（无陈旧读）
- Given 慢查询监控，When 跑课程浏览/下单链路，Then 无 >500ms 热点查询；日志型高频写走批量缓冲（掉电容忍 ≤2s 数据）
- Given 空结果查询，When 反复请求，Then 空值 30s 缓存生效（穿透防护）；热点 key 并发重建仅 1 次（击穿防护）

## 6. 交接与记忆（契约冻结⑭）
- 完成 → 写 `handoffs/task23-contract.md`：缓存 key 清单 + TTL 表 + 失效策略（供 task39 压测与前端性能验收）
- 看板 task23=READY_FOR_FRONTEND → sync.ps1
- 交付物：缓存接入代码 + DEL 清单 + 压测对比报告 + 交接单
