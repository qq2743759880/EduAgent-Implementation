# task12 优化修改方案（基于技术批判，在现有产物上迭代）

> 依据：`task12-技术批判.md` 4 条批判 ｜ 原则：现有 repo 迭代，不另起炉灶
> **核心：按 edu.sql 权威结构修正 repo 层 SQL（移除不存在的 yn 列引用）**

## 方案总览

| # | 修改点 | 目标文件 | 优先级 | 工作量 |
|---|--------|---------|--------|--------|
| A | module_repo 移除 yn（物理 DELETE 或按表结构） | `module_repo.py` | **P0** | 40min |
| B | session_repo 移除 yn（teaching_status 控制） | `session_repo.py` | **P0** | 40min |
| C | asset_repo 移除 yn（物理 DELETE） | `asset_repo.py` | **P0** | 30min |
| D | video_repo 移除 yn（transcode/review 状态控制） | `video_repo.py` | **P0** | 40min |
| E | 补 cohort sessions 路由（批判②）| `router.py` | **P1** | 20min |
| F | 测试补 module/session/asset/video 列表用例 | `test_course_admin.py` | **P1** | 30min |

---

## A~D：按 edu.sql 逐表修正（核心）

### 表结构实证（edu.sql 权威，已核实）

| 表 | yn 列 | 软删/可见性机制 |
|----|------|----------------|
| series | ❌ | sale_status 状态机（draft/on_sale/off_sale）→ 已正确用状态机 |
| series_cohort | ✅ | yn=0 软删（可保留）|
| series_cohort_course（模块）| ❌ | **无状态列** → 软删改物理 DELETE |
| series_cohort_session（课次）| ❌ | teaching_status 控制 → 软删用 teaching_status 或物理 DELETE |
| session_asset | ❌ | **无状态列** → 物理 DELETE |
| session_video | ❌ | transcode_status/review_status → 状态机控制 |

### 修改示例（module_repo.py）

```python
# 原（bug）：list 用 yn=1 过滤（表无 yn）
#   "SELECT * FROM series_cohort_course WHERE cohort_id = %s AND yn = 1 ORDER BY stage_no, module_code, id"
# 改：移除 yn（该表无软删列）
"SELECT * FROM series_cohort_course WHERE cohort_id = %s ORDER BY stage_no, module_code, id"

# 原：soft_delete 用 yn=0（表无 yn）
#   "UPDATE series_cohort_course SET yn = 0, updated_at = NOW() WHERE id = %s"
# 改：物理 DELETE（表无状态列，软删需改表结构——不推荐动权威表）
"DELETE FROM series_cohort_course WHERE id = %s"
```

### 各表处理决策

- **module（series_cohort_course）**：无状态列 → **物理 DELETE**（service 层 delete_module 改调 hard_delete）
- **session（series_cohort_session）**：有 teaching_status → **物理 DELETE**（teaching_status 是教学状态非软删；删除即移除）
- **asset（session_asset）**：无状态列 → **物理 DELETE**
- **video（session_video）**：transcode_status 是转码状态、review_status 是审核状态（非软删）→ **物理 DELETE**；可见性由 status 控制（不是删）

### 同步修改

- `service.py` 中 delete_module/session/asset/video 注释从"软删 yn=0"改"物理删除"（或按表语义）
- `schemas.py` 注释同步
- 保留 series_cohort 的 yn=0 软删（该表有 yn，正确）

---

## E：补 cohort sessions 路由（批判②）

- 核对 `router.py` 是否注册 `GET /api/admin/courses/cohorts/{cohort_id}/sessions`
- 契约冻结③ 约定 5+5+5+5+4 = 24 端点，逐个核对是否全注册
- 补缺失路由 + 测试

---

## F：测试补全（批判③ 关联）

- test_course_admin.py 补：module 列表（cohort_id=1）→ 200、session 列表 → 200、asset/video 端点
- 断言 500 清零

---

## 量化指标（修复后）

- GET /api/admin/courses/series → 200 + items（已修复 ✓）
- GET .../cohorts/1/modules → 200
- GET .../cohorts/1/sessions → 200
- DELETE module/session/asset/video → 204/200 且 DB 行确实删除（无 500）
- 唯一约束冲突 → 409xx（模块 stage_no 冲突）
- 测试套件全绿（无 500）

## 新风险与应对

| 风险 | 应对 |
|------|------|
| 物理 DELETE 丢失可恢复性 | edu.sql 无软删字段，物理删除是权威设计；如需可恢复需改表结构（另议）|
| 影响用户端（task11 用同表）| module/session 移除 yn 过滤不影响用户端（用户端查的是有状态字段）|
| 级联删除孤儿 | DELETE 子表前检查引用（session_video_chapter 依赖 session_video）|

## 实施顺序

A→B→C→D（并行独立，各 repo 互不依赖）→ E（路由核对）→ F（测试补全）→ 重启 8001 全量验证
