# task53 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判与优化修改」+ Tgent §6 tokens 单源红线
> 对象：task53 /achievements 成就中心（TraeWork，commit b8aa351 + bbf2c61）
> 结论：**⛔ 验收不通过（P1）**——RankingTabs 第 2 名奖牌 `bg-gray-200` 硬编码灰残留，报告声称"灰系 2 处改 candy token 归零"但实测未清零

---

## 实证结果

| 项 | 实测 |
|----|------|
| commit | ✅ `b8aa351`（11 文件 +4682/-471）+ `bbf2c61`（报告回填）|
| 组件交付 | ✅ RankingTabs + PointOverview + PointLogList + BadgeWall + page.tsx |
| tsc | ✅ 0 错误 |
| vitest | ✅ **59 文件/433 测试全 PASS 实跑** |
| build | ✅ 成功（/achievements 静态化，报告）|
| grep 审计 | ⚠️ text-[Npx]=0 / hex=0 / 内联色=0 / 禁闭色=0，但 **bg-gray-200 灰系硬编码 1 处残留** |

## 批判 1（P1 阻塞）：RankingTabs 第 2 名奖牌 bg-gray-200 硬编码灰（报告声称清零但未清零）

**问题描述**：`RankingTabs.tsx` 奖牌配置 `2: { noClass: "border-foreground bg-gray-200 text-foreground shadow-[0_3px_0_rgba(31,31,31,0.2)]" }`——**第 2 名奖牌用 `bg-gray-200` 硬编码灰**。报告声称"灰系 2 处改 candy token 归零"，但实测仍有 1 处残留（可能只改了 1 处，第 2 名奖牌漏改）。

**证据来源**：grep 定位 RankingTabs.tsx bg-gray-200；报告 §整改（灰系 2 处改 candy token 归零）与实测不符。

**与正确做法差距**：tokens 单源红线（Tgent §6 + doc-frontend）要求无硬编码灰系（bg-gray/slate/zinc）。第 2 名奖牌应改用 candy token（如 `bg-candy-silver` 或语义 token）。

**优化方案**（~10min）：
```tsx
// 原：2: { noClass: "border-foreground bg-gray-200 text-foreground shadow-[0_3px_0_rgba(31,31,31,0.2)]" }
// 改：用 candy 语义 token（银牌色）
2: { noClass: "border-foreground bg-candy-silver text-foreground shadow-[0_3px_0_rgba(31,31,31,0.2)]" }
// 若无 candy-silver token，加 --color-candy-silver 进 globals.css + design-tokens.json
```

**最小验证方法**：grep `bg-gray-200` 在 task53 组件 = 0；build + vitest 回归。

**预期收益与成本**：收益=恢复 tokens 单源（报告声称清零但未清零）；成本=10min。

## 批判 2（P2）：报告"灰系 2 处改 candy token 归零"与实测不符（审计不实）

**问题描述**：报告声称灰系已归零，但实测 1 处残留——报告审计结论与代码不符（同 task48 报告掩盖字号教训）。

**证据来源**：报告 §整改 vs 实测 grep。

**优化方案**：修复后报告补真实 grep 证据（灰系 0）；后续前端任务 grep 审计须含灰系维度（bg-gray/slate/zinc）。

## 总评

| GWT | 结果 |
|-----|------|
| ① fe-spec-writer 补规范 + HTML 含徽章/积分/排行 | ✅ doc-frontend 更新 + achievements.html |
| ② 徽章/积分/排名真实数据 + ZSET | ✅ RankingTabs/PointOverview/BadgeWall 实现 |
| ③ 未解锁徽章置灰 + 解锁条件 | ✅ BadgeWall 置灰 + 进度 |

**结论：task53 验收不通过（P1 灰系硬编码残留 + 报告审计不实）**。修复 RankingTabs bg-gray-200 → candy token + 报告补真实 grep 证据后复验。
