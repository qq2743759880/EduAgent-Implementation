# task51 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task51 /community 社区列表（TraeWork，commit 8c36860 + 3de48ca）
> 结论：**✅ 验收通过**（GWT 实证全绿），1 条批判（P2 不阻塞，历史遗留）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `8c36860`（10 文件 +753/-337）+ `3de48ca`（报告回填）|
| 组件交付 | ✅ PostCard + CommunityFilterBar + page.tsx + 测试 + HTML 效果图 |
| tsc | ✅ 0 错误 |
| vitest | ✅ **57 文件/423 测试全 PASS 实跑**（18.29s）|
| build | ✅ 成功（报告）|
| grep 审计（task51 改动范围）| ✅ PostCard/CommunityFilterBar/page.tsx text-[Npx]=0、hex=0、内联色=0、禁闭色=0 |
| MOCK | ✅ 仅注释（PostCard 纯展示组件，字段与契约⑬ mock 一致说明）|

## 批判 1（P2）：MarkdownView.tsx 1 处 text-[15px] 为历史遗留（非 task51 引入）

**问题描述**：全站 grep 发现 `MarkdownView.tsx` 有 1 处 `text-[15px]` 硬编码字号——但 **git 历史确认该文件 v0.2.0 就存在此写法，task51 未改动**（git diff 88dc15f..8c36860 对该文件无变更）。task51 改动范围内（PostCard/CommunityFilterBar/page.tsx）**无 text-[Npx] 违规**。

**证据来源**：git log MarkdownView.tsx（v0.2.0 引入）；git diff task51 范围（无该文件改动）；grep 定位。

**优化方案**：不阻塞 task51（历史遗留，非本任务引入）。转 task37（清理/测试修复）统一处理：`text-[15px]` → `--text-md`（0.9375rem，task48 已加）或 `text-sm/base`。MarkdownView 是 task49/52 共用组件，修复影响面需回归。

## 总评

| GWT | 结果 |
|-----|------|
| ① fe-spec-writer 补规范 + HTML 含列表/筛选/空态 | ✅（task51 HTML 效果图 SOP 完整返工）|
| ② /api/community 壳解包 + 分页 + 空态「暂无帖子」| ✅ PostCard + CommunityFilterBar + page |
| ③ 点击跳 /community/[postId] | ✅ [postId] 路由存在 |

**结论：task51 验收通过。** 社区列表页完成；批判 1 为历史遗留（转 task37，不阻塞）。
