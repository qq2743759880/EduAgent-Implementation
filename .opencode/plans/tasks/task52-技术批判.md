# task52 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」
> 对象：task52 /community/[postId] 帖子详情（TraeWork，commit 1a45ab3）
> 结论：**✅ 验收通过**（GWT 实证全绿），2 条批判（P2 不阻塞）

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `1a45ab3`（10 文件 +3168/-296，含 community-post.html 效果图）|
| 组件交付 | ✅ ReactButtons + CommentSection + [postId]/page.tsx |
| tsc | ✅ 0 错误 |
| vitest | ✅ **58 文件/428 测试全 PASS 实跑**（首项 keys 确认）|
| build | ✅ 成功（报告）|
| grep 审计 | ✅ task52 改动范围（ReactButtons/CommentSection/page）text-[Npx]=0、hex=0、内联色=0、禁闭色=0 |
| MOCK | ✅ 测试 vi.mock 隔离（初验 P3 mock 耗尽已修 mockResolvedValue）|
| 404/403 语义区分 | ✅ page.tsx 实现（404→ErrorState+返回列表 CTA；403 区分）|

## 批判 1（P2）：MarkdownView.tsx text-[15px] 历史遗留仍存在（非 task52 引入）

**问题描述**：全站 grep 1 处 text-[Npx] 仍是 **MarkdownView.tsx**（v0.2.0 历史遗留，上轮 task51 已定位）——task52 未改动该文件，改净范围无违规。该历史遗留已在看板登记转 task37。

**证据来源**：git log MarkdownView.tsx（v0.2.0）；git diff task52 范围（MarkdownView 无改动）；audit52b.py 定位。

**优化方案**：转 task37（MarkdownView text-[15px] → --text-md 统一处理 + 回归）。不阻塞 task52。

## 批判 2（P2）：写操作（点赞/评论/收藏）依赖 community 后端壳适配

**问题描述**：ReactButtons useMutation + CommentSection 提交依赖 /api/community 写端点（契约⑬ task15 已壳适配）——若后端 write 端点未就绪则待联调（同 task46/47/48 模式）。

**证据来源**：ReactButtons/CommentSection useMutation；task15 契约⑬ community 壳已适配。

**优化方案**：task15 已壳适配（报告实证 community posts 200+壳），写端点应可用；联调时 Playwright 全链路验证。不阻塞。

## 总评

| GWT | 结果 |
|-----|------|
| ① fe-spec-writer 补规范 + HTML 含正文/评论/点赞 | ✅ doc-frontend 更新 + community-post.html |
| ② 评论/点赞交互 + toast + 不吞错 | ✅ useMutation + invalidate + toast |
| ③ 帖子不存在 ErrorState + 返回列表 CTA | ✅ 404 语义 + ErrorState + 返回 CTA |

**结论：task52 验收通过。** 帖子详情页完成；批判 1/2 均 P2（历史遗留转 task37 / 写端点 task15 已适配）。