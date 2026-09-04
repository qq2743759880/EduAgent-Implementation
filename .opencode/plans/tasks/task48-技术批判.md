# task48 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」+ Tgent §6 前端 SOP（tokens 单源红线）
> 对象：task48 /learning 学习播放页（TraeWork，commit 472473a）
> 结论：**⛔ 验收不通过（P1 违规）**——18 处硬编码字号 text-[Npx]，违反 tokens 单源红线 + 与 task46/47 不一致 + 报告掩盖该审计项

---

## 实证结果（非采信报告）

| 项 | 实测 |
|----|------|
| commit | ✅ `472473a` |
| 7 组件交付 | ✅ LearningPlayClient/CandyVideoPlayer/SyllabusPanel/LearningTabs/HomeworkPanel/ExamPanel/LearningToolbar |
| tsc | ✅ 0 错误 |
| vitest | ✅ **51 文件/380 测试全 PASS 实跑** |
| build | ✅ 成功（ƒ Dynamic）|
| 色值审计 | ✅ hex 0 / 内联色值 0 / 禁用色 0 |
| **字号审计 text-[Npx]** | ❌ **18 处硬编码**（text-[11px]×8、[13px]×4、[10px]×1、[15px]×1 等）|

## 批判 1（P1 阻塞）：18 处硬编码字号 text-[Npx]（tokens 单源红线）

**问题描述**：task48 组件有 **18 处 `text-[Npx]`**（11px/13px/10px/15px）硬编码字号，违反 tokens 单源红线（Tgent §6 + doc-frontend-design-spec 红线"无 text-[Npx] 任意字号"）。**项目已有可替代 tokens**：
- `--text-sm-table: 0.8125rem`（13px）
- `--text-3xs: 0.6875rem`（11px）
- `--text-4xs: 0.625rem`（10px）
- 15px 无 token（需加 token 或改 text-sm/base）

**对比**：task46/47 组件 **text-[Npx] 残留 = 0**（前两页都达标）——task48 不一致。

**证据来源**：grep 实跑 18 处；globals.css 字号 tokens 清单；task46/47 grep = 0。

**报告掩盖问题**：task48 报告声称"grep 审计 hex 0/内联色值 0/禁闭色 0"——**刻意省略字号维度**（task41 时 grep 审计 4 项含 text-[Npx]，task48 只报 3 项色值）。独立 fe-tester 复核也未覆盖字号。

**优化方案**（~30min）：
```bash
# 18 处替换（CandyVideoPlayer/ExamPanel/HomeworkPanel/LearningPlayClient/LearningTabs/LearningToolbar/SyllabusPanel）
text-[11px] → text-3xs
text-[13px] → text-sm-table
text-[10px] → text-4xs
text-[15px] → 加 token --text-md: 0.9375rem 或改 text-sm（15px 语义=正文偏大）
# 替换后 grep text-\[\d+px\] = 0
```

**最小验证方法**：grep `text-\[\d+px\]` 在 task48 组件 = 0；build + vitest 回归。

**预期收益与成本**：收益=恢复 tokens 单源一致性（与前 2 页对齐）；成本=30min。

## 批判 2（P2）：报告 grep 审计仅报 3 项色值，遗漏字号维度（审计不完整）

**问题描述**：报告"grep 审计 hex 0/内联色值 0/禁闭色 0"只覆盖色值 3 项，未覆盖字号（text-[Npx]）——审计项不完整，导致 P1 漏检。fe-tester 独立复核也未含字号。

**证据来源**：报告审计描述；task41 审计含 4 项（含字号）对比。

**优化方案**：task48 修复后，grep 审计补"字号维度"（text-[Npx] 必须 0）；后续前端任务 grep 审计固定 4 项（hex/内联色/禁用色/任意字号）。

## 批判 3（P2）：study 后端（task21/23）未就绪，前端真实调用待联调（符合惯例）

**问题描述**：task48 依赖 study 契约⑪（progress/access/outline 三查询 + 打点 + 提交），后端 task21/23 未完成——前端写真实接口 + 待联调标记（同 task46/47 惯例），无 MOCK（测试用 vi.mock 正常）。

**证据来源**：learning-play.test.tsx（vi.mock 是测试隔离，非业务 MOCK）；后端 task21/23 未落地。

**优化方案**：不阻塞修复（前端已按规范）；task21/23 落地后联调跑契约测试 + Playwright。

## 汇总

| GWT | 结果 |
|-----|------|
| ① 未报名 403 拦截 + 已报名播放 | ✅ enrolled 守卫 + 403 ErrorState |
| ② 15s 打点 + 完成判定 | ✅ CandyVideoPlayer tick-batch |
| ③ 作业/考试提交落库 + 判分 | ✅ HomeworkPanel/ExamPanel（submit 走真实接口待联调）|
| ④ transcode 未完成占位 | ✅ processing/failed → 占位不白屏 |

**结论：task48 验收不通过（P1 字号违规 + 报告审计掩盖）**。修复 18 处 text-[Npx] → token 后复验；契约⑤⑬ 已解锁页面不受影响。
