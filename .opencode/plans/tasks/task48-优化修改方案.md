# task48 优化修改方案（基于技术批判，在现有产物上迭代）

> 依据：`task48-技术批判.md` 3 条批判 ｜ 原则：现有组件迭代，不另起炉灶
> **核心：18 处 text-[Npx] 硬编码字号 → 项目 tokens（tokens 单源红线）**

## 方案总览

| # | 修改点 | 目标文件 | 优先级 | 工作量 |
|---|--------|---------|--------|--------|
| A | 18 处 text-[Npx] → token | task48 7 组件 | **P1** | 30min |
| B | grep 审计补字号维度（4 项固定）| 报告/审计脚本 | P2 | 10min |

---

## A. P1：字号 token 化

### 映射表（globals.css 已有 tokens）

| 硬编码 | token | 值 |
|--------|-------|-----|
| text-[11px] | `text-3xs` | 0.6875rem (11px) |
| text-[13px] | `text-sm-table` | 0.8125rem (13px) |
| text-[10px] | `text-4xs` | 0.625rem (10px) |
| text-[15px] | 加 `--text-md: 0.9375rem` 或改 `text-sm`/`text-base` | 15px |

### 涉及文件（18 处）

| 文件 | 处数 | 说明 |
|------|------|------|
| CandyVideoPlayer.tsx | 2 | 倍速徽标/打点提示 text-[11px]→text-3xs |
| ExamPanel.tsx | 4 | 本节考试 text-[11px]/[15px]/[11px] |
| HomeworkPanel.tsx | 4 | 本节作业 text-[11px]/[13px]/[11px] |
| LearningPlayClient.tsx | 1 | text-[13px]→text-sm-table |
| LearningTabs.tsx | 2 | 课程简介 text-[13px]/徽标 text-[11px] |
| LearningToolbar.tsx | 3 | 底部栏 text-[11px]×3 |
| SyllabusPanel.tsx | 3 | 状态徽标 text-[10px]/text-[11px]×2 |

### 修改示例

```tsx
// 原
className="rounded bg-white/20 px-2 py-0.5 text-[11px]"
// 改
className="rounded bg-white/20 px-2 py-0.5 text-3xs"
```

### 15px 处理
- 优先加 token `--text-md: 0.9375rem`（globals.css @theme + design-tokens.json 同步），用 `text-md`
- 或语义化：15px 用于考试分数展示（font-extrabold），可用 `text-base`(16px) 近似或 `text-md`(15px)

---

## B. P2：grep 审计固定 4 项

- 后续前端任务 grep 审计固定：①hex `bg-[#` ②内联 style 色值 ③禁用色（sky/violet/cyan/teal/fuchsia）④**任意字号 text-[Npx]**——4 项必须全 0
- task48 修复后报告补字号维度结果

---

## 量化指标（修复后）

- grep `text-\[\d+px\]` 在 task48 7 组件 = **0**
- tsc 0 错误、vitest 380 全绿、build 成功（回归）
- 视觉无变化（token 值与原 px 等价）

## 新风险与应对

| 风险 | 应对 |
|------|------|
| text-sm-table 语义（表格用）用于正文 | 若语义不适配，改用 text-3xs/2xs 或加通用 token；以视觉等价为准 |
| 15px token 影响设计系统 | 加 --text-md 进 design-tokens.json（font-size 阶梯扩展），不破坏既有 |

## 实施顺序

A（30min）→ B（10min）→ 重启前端 → grep 验证 0 → vitest/build 回归
