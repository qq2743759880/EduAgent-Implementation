# task12: course_admin 重写（四级 CRUD + 视频三表 + 分片上传）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P3 ｜**并行组**：W2 ｜**工作量**：XL
> **前置**：task11 ｜**后置（联调节点）**：**契约冻结③ → 前端 task56（/admin/courses）、task57（系列详情）**

## 1. 选型依据
- tech-source-audit.md §一（repository 四层；MinIO 对象 URL 管理）
- edu-data-refactor-plan.md FR-API-02（管理端四级 CRUD + 视频三表）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev + be-validator | 四级 CRUD + 分片上传端点 |
| 测试 | sd-tester + RunCommand+mysql CLI | 全链路 + 唯一约束冲突 |
| 审查 | review-screener-1/2/3 → review-moderator → review-judge | — |
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
- 四级 CRUD：series（sale_status 状态机）/cohort（容量/价格/起止）/module（stage_no 唯一 cohort_id+stage_no）/session（session_no 唯一），全部软删 yn=0
- 视频三表：session_asset（material_category/access_scope）→ session_video（transcode_status 状态机）→ session_video_chapter（start_second/end_second）
- 分片上传：init → 分片 PUT → finalize → bind 到课次；转码状态轮询端点

## 5. 验收标准（Given/When/Then 全文）
- Given admin 登录，When 创建系列→班次→模块→课次→上传视频（分片 init→finalize）→bind 到课次，Then 全链路落库正确、transcode_status 从 pending→in_progress→completed/failed 可查询、章节起止秒持久化
- Given 重复创建同 cohort_id+stage_no 模块，Then 唯一约束冲突返回 409xx 业务码而非 500
- Given 删除系列，When 执行 DELETE，Then yn=0 软删、用户端立即不可见、子级数据保留可恢复
- Given institution/delivery_mode 字段，When 创建系列，Then 多租户分片（institution_id）与交付模式正确落库

## 6. 交接与记忆（契约冻结③）
- 完成 → 写 `handoffs/task12-contract.md`：四级 CRUD 端点 + 视频 init/finalize/bind + 转码轮询 + 错误码
- 看板 task12=READY_FOR_FRONTEND（解锁 TraeWork task56/57）→ sync.ps1
- 交付物：course_admin 重写 + pytest + 交接单
