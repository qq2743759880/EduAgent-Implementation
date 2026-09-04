# task56 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task56 /admin/courses 管理端课程总览（TraeWork，commit dfb60ee）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `dfb60ee`（15 文件 +992/-305，含 admin-courses.html + 截图矩阵）|
| 交付物 | ✅ admin courses page + SeriesForm + courses.test + HTML 原型 |
| tsc | ✅ 0 错误 |
| vitest | ✅ **66 文件/450 测试全 PASS 实跑** |
| grep 审计（task56 改动范围）| ✅ page.tsx(courses列表)/courses.test/SeriesForm：slate 灰系=0、旧契约(subject_code/level_code)=0、text-[Npx]/hex/内联色/禁闭色=0 |
| 契约对齐 | ✅ delivery_mode(19)/institution_id(14) 新契约 |
| Base UI DropdownMenu | ✅ render={<Button/>} 修正（非 Radix asChild/align）|

## 批判 1（P2）：[seriesId]/page.tsx 含 5 处 slate 灰系 + 2 处旧契约（历史遗留，非 task56）

**问题描述**：grep 定位 `app/(admin)/admin/courses/[seriesId]/page.tsx` 有 5 处 slate 灰系（bg-slate-100/text-slate-500/900/600）+ 2 处旧契约（subject_code/level_code）——但 **git 历史确认该文件为 v0.2.0 引入（83a9531），非 task56 新增**。task56 改动范围（page.tsx 列表页/courses.test/SeriesForm）无违规。

**证据来源**：git log [seriesId]/page.tsx（83a9531 v0.2.0）；task56 diff 范围无该文件新增；grep 甄别文件归属。

**优化方案**：不阻塞（历史遗留，task57 将重写此页）。task57（详情页）重写时一并清理 slate 灰系 → candy token + 旧契约 → 新契约（对齐 task12）。

## 批判 2（P2）：sale_status 三色枚举映射未独立验证（依赖 task55 色板经验）

**问题描述**：GWT③ sale_status 三色渲染（draft→muted/on_sale→success/off_sale→muted）由实现 + 测试覆盖，但未像 task53（徽章色）那样有独立 StatusBadge 映射验证。前端 task57（详情页）复用时可再确认。

**证据来源**：task56 报告 GWT③；task53 StatusBadge 双通道经验。

**优化方案**：不阻塞（实现 + 测试覆盖）。task57 复用 StatusBadge（C3）时统一三色映射。

## 总评

| GWT | 结果 |
|-----|------|
| ① 系列 CRUD 软删全通 + J23 跳转 | ✅ courses.test + page |
| ② RBAC AdminGuard + filterAdminNav | ✅ (admin)/layout |
| ③ sale_status 三色枚举 | ✅ 实现 + 测试 |

**结论：task56 验收通过。** 管理端课程总览完成；批判 1/2 均 P2（[seriesId] 历史遗留转 task57 / 三色映射 task57 复用 C3 确认）。
