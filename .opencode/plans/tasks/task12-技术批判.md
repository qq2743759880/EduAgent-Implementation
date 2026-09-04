# task12 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task12 course_admin 重写（Trae，未 commit；编排者补提交 2 处修复）
> 结论：**⛔ 验收不通过（P0 系统性缺陷）**——repo 层按旧表结构（含 yn）写 SQL，与 edu.sql 权威结构不符；已修 2 处（排序/JSON），yn 软删缺陷需 Trae 逐表修正

---

## 实证过程（真实 HTTP 验证，非采信报告）

| 端点 | 实测 | 根因 |
|------|------|------|
| GET /api/admin/courses/series（列表）| 最初 500 `Unknown column 's.id'` → **修复后 200 + 5 items** | 排序别名 `s.` 无表别名 |
| GET .../series（列表）| 修复后 200，target_learner 正确为 list | JSON 列解析（asyncmy 返回 str）|
| GET .../cohorts/1/modules | 500 `Unknown column 'yn'` | **series_cohort_course 无 yn 列** |
| GET .../cohorts/1/sessions | 404（路由未命中，另一问题）| 见批判 2 |
| 匿名访问 | 401 + 40101 + x-trace-id ✓ | 契约① 正常 |

## 批判 1（P0 阻塞）：repo 层按旧表结构（含 yn 软删）写 SQL，与 edu.sql 权威结构不符

**问题描述**：module_repo/session_repo/asset_repo/video_repo 共 **18 处 `yn = 1` / `yn = 0` SQL**，但 edu.sql 权威结构中这些表**无 yn 列**：
- `series_cohort_course`（模块）：无任何状态列
- `series_cohort_session`（课次）：仅 teaching_status
- `session_asset`：无状态列
- `session_video`：有 transcode_status/review_status

实测 `GET .../cohorts/1/modules` → 500 `Unknown column 'yn' in 'where clause'`。

**证据来源**：
- 实跑 HTTP 500（2026-08-18，最新代码服务 8001）
- `edu.sql` 逐表 CREATE TABLE 核对（无 yn 列）
- DB `SHOW COLUMNS` 实证（4 表均无 yn）
- repo 源码 grep（18 处 yn 引用）

**与正确做法差距**：task12 设计"全部软删 yn=0"（报告/契约声明）与权威表结构冲突。edu.sql 中仅 `series_cohort` 有 yn；其余子表无软删字段——软删语义需按表调整：①有状态字段的表（session_video.transcode_status、series_cohort_session.teaching_status）用状态机控制可见性；②无状态字段的表（series_cohort_course/session_asset）删除即物理 DELETE（或引入软删方案需改表结构，但不应改 edu.sql 权威）。

**优化方案**（需 Trae 按 edu.sql 逐表修正，见优化修改方案）：
- module_repo：移除 yn 过滤；soft_delete 改物理 DELETE（或加 status 字段——**不建议改权威表**）
- session_repo：移除 yn；soft_delete 用 teaching_status 或物理 DELETE
- asset_repo：移除 yn；物理 DELETE
- video_repo：移除 yn；transcode_status/review_status 控制
- 同步更新 schemas/service 的软删注释与逻辑

**最小验证方法**：修复后 module/session/asset/video 列表 + 删除 全链路无 500，测试套件全绿。

**预期收益与成本**：收益=对齐 edu.sql 权威，四类子表 CRUD 可用；成本=2~3h（逐 repo 修 SQL + 测试）。

---

## 批判 2（P1）：GET .../cohorts/{id}/sessions 返回 404（路由未命中）

**问题描述**：`GET /api/admin/courses/cohorts/1/sessions` 实测 404（module 500 是 yn 问题，session 是路由 404）。疑为 router 未注册该端点或路径不匹配（契约写 `/api/admin/courses/cohorts/{id}/sessions`？）。

**证据来源**：实跑 404（与 module 的 500 不同，说明是路由层问题非 SQL）。

**优化方案**：Trae 核对 router.py 路径注册与契约冻结③ 一致；补该端点测试。

**最小验证方法**：GET cohort sessions → 200（或明确的 404 语义）。

---

## 批判 3（P2）：测试文件 BASE 硬编码，无法多环境运行

**问题描述**：`test_course_admin.py` BASE 硬编码 `http://127.0.0.1:8000`，无法指向测试端口（本次用 8001 验证需改代码）。已由编排者改为 `os.environ.get("TEST_BASE", ...)`。

**证据来源**：测试源码 + 本次 8001 验证需改 BASE。

**优化方案**：已修复（编排者）；后续测试统一支持 TEST_BASE。

---

## 批判 4（P2）：task12 未 commit（沙箱 shell 引号问题）

**问题描述**：报告自述 git commit 失败，工作区改动未提交（git log 无 task12）。

**证据来源**：git status（untracked course_admin/）；git log（停在 task11）。

**优化方案**：编排者已补提交部分修复；Task 修复后 Trae 统一 commit。

---

## 汇总

| GWT | 结果 |
|-----|------|
| ① 四级 CRUD + 分片上传全链路 | ❌ module/session 500/404；series 部分可用 |
| ② 唯一约束 409 | ⚠️ 需修复 yn 后验证（409xx 码已定义）|
| ③ 软删 | ❌ 无 yn 表无法软删（设计冲突）|
| ④ 多租户 | ⚠️ 未完整验证 |

**结论：task12 验收不通过（P0 系统性 yn 缺陷）**。已修 2 处（排序/JSON，commit 已补），yn 软删 + session 路由需 Trae 按 edu.sql 修正后重验。契约冻结③ 暂缓解锁前端 task56/57。
