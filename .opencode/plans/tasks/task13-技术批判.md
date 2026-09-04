# task13 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task13 question 域（Trae，报告 15/17；编排者复验 18/18）
> 结论：**✅ 验收通过**（业务全绿），3 条批判（P2 不阻塞）

---

## 实证结果（8001 最新代码服务）

| 项 | 实测 |
|----|------|
| 批量导入预览/执行/幂等 | ✅ 预览 total=4 valid=1 invalid=3 逐行报告；幂等 skipped=1 |
| 题型维表 | ✅ GET /types 200（5+ 题型 type_code/type_name）|
| 创建/查询 question | ✅ 201/200，analysis_text 贯通 |
| 组卷快照 | ✅ create exam 201 → publish 快照 → get 含快照题目 |
| 409 唯一约束 | ✅ dup question_code → **409 + code=40922**（非 500）|
| 匿名 401 | ✅ 401 + 40101 |
| keyword 检索（LIKE 替代标签）| ✅ 200（修复脚本后验证 total=1）|
| quiz 出题源 | ✅ `_load_by_code_or_id` 从 `question` 表 + `dim_question_type` 映射（源码确认）|

## 批判 1（P2）：验证脚本 _verify_task13.py 有 2 个缺陷（已由编排者修复）

**问题描述**：原脚本"15/17"的 2 个失败均为**脚本自身 bug**，非业务缺陷：
1. `check("not found bank 404", status, j, 404)` —— expected_code 默认 0，但 404 业务壳 code 是 "40400" → 误判 FAIL
2. `GET ?keyword=验证题目` —— 中文 query 未 urlencode → UnicodeEncodeError（urllib ascii 编码）

**证据来源**：实跑复现；脚本源码第 202/210 行。

**优化方案**：编排者已修复（404 断言改 "40400" + `urllib.parse.quote`）→ 重跑 **18/18 PASS**。后续所有 HTTP 验证脚本须：①失败壳断言用字符串错误码 ②中文 URL 参数 quote 编码。

**预期收益与成本**：收益=验证脚本可信；成本=已修。

## 批判 2（P2）：task13 未 git commit + 报告路径在 edu-agent/test-reports

**问题描述**：git log 停在 67b0a7b（task41），task13 代码未提交；报告在 `edu-agent/test-reports/`（沙箱路径）而非项目根 `test-reports/`。

**证据来源**：git status（question_admin untracked）；报告位置。

**优化方案**：编排者补 commit（含 domains/question_admin + quiz 改造 + error_codes + 契约 + 报告 + 修复后脚本）。

## 批判 3（P2）：pytest 套件 9 skipped（依赖真实服务）

**问题描述**：test_question_admin.py 仅 1 passed 9 skipped（skipped 用例需真实 HTTP 服务环境）。HTTP 验证脚本已覆盖全部 GWT（18 项），pytest 的 skipped 不阻塞，但测试基建依赖运行中服务。

**证据来源**：pytest 实跑（1 passed 9 skipped）。

**优化方案**：test_question_admin.py 改为自带 mock/TestClient（不依赖真实服务）或纳入 task98 verify.py 框架统一管理。

## 总评

| GWT | 结果 |
|-----|------|
| ① 批量导入 1752 + 幂等 | ✅ 预览/执行/幂等全通过（18 项含）|
| ② quiz 出题源 question 表 + analysis_text | ✅ 源码 + HTTP 验证 |
| ③ 组卷快照 | ✅ publish 快照生效 |

**结论：task13 验收通过。** 契约冻结④ 生效 → 解锁前端 task58/59/49。批判 1/2/3 均 P2（脚本已修、commit 待补、pytest 基建转 task98）。
