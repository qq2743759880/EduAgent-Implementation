# task11: 课程域改造：curriculum→series（C 端 5 端点 + 重定向 + repository）

> **类型**：backend ｜**执行工具**：Trae ｜**阶段**：P3 ｜**并行组**：W2 ｜**工作量**：XL
> **前置**：task10, task03, task07 ｜**后置（联调节点）**：**契约冻结② → 前端 task44（/courses）、task45（搜索）、task46（详情）**；task12/14/20/23 依赖

## 1. 选型依据
- tech-source-audit.md §一（asyncmy + repository 层：router→service→repository→infra 四层）
- edu-data-refactor-plan.md FR-API-02（C 端 5 端点定义）

## 2. Agent 调度链
| 步骤 | agent / skill / MCP | 说明 |
|------|--------------------|------|
| 开发 | sd-dev + be-architect + be-validator | domains/course 四层设计 + Pydantic schemas |
| 测试 | sd-tester + RunCommand+mysql CLI | 全筛选参数/分页/重定向测试 |
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
- `app/domains/course/`：router/service/repository（series_repo/cohort_repo/session_repo/video_repo）
- 端点：GET /api/series（学科/分类/交付模式/关键词/价格区间/排序/分页 page_size≤100）、GET /api/series/{id}、GET /api/series/{id}/cohorts、GET /api/cohorts/{id}（含模块）、GET /api/cohorts/{id}/modules（含课次）
- /api/curriculum/series 308 重定向；缓存点预留（task23 接入）
- schemas.py 全列 snake_case（series_name/institution_id/delivery_mode/sale_status/cover_url…）

## 5. 验收标准（Given/When/Then 全文）
- Given full 档数据就绪，When GET /api/series?category=编程&delivery_mode=online_live&keyword=Python&page=1&page_size=20，Then 返回 sale_status=on_sale 的系列、snake_case 字段、page_meta 分页元数据，P95 <200ms（命中缓存 <50ms）
- Given 旧前端调用 /api/curriculum/series，When 请求到达，Then 308 重定向至 /api/series 且参数保留
- Given 四级查询，When 沿 series→cohorts→modules→sessions 逐级请求，Then 每级数据与 edu.sql 层级语义一致（模块挂 cohort 而非 series，修复 P3 问题）

## 6. 交接与记忆（契约冻结②）
- 完成 → 写 `handoffs/task11-contract.md`：5 端点 curl 示例 + 字段表（snake_case 全列）+ 分页参数 + 308 说明
- 看板 task11=READY_FOR_FRONTEND（解锁 TraeWork task44/45/46）→ sync.ps1
- 交付物：domains/course/ + schemas.py + pytest + 交接单
