# task37 前端遗留项 — 完成报告（FE，差异单 task37-discrepancy）

> 执行者：前端开发者（TraeWork）｜基于最新 HEAD `c8e99d8`（GWT③ #task37）
> 范围：差异单 §1（MarkdownView 硬编码字号）与 §2（MutationCache 401/403 早退），§3（user_memory 512）后端已确认无需前端动作，未触碰。

## 一、改动概览（两项独立 commit，均含 task37-discrepancy 标识）

| Commit | 标识 | 文件 | 内容 |
|--------|------|------|------|
| `e3a1636` | task37-discrepancy ① | `edu-frontend/src/components/community/MarkdownView.tsx` | 去硬编码字号 `text-[15px]` → `text-sm` candy 语义类 |
| `5bfdda0` | task37-discrepancy ② | `query-client.ts` / `query-client.test.ts` / `EditUserDialog.tsx` / `EditUserDialog.test.tsx` / `UserTable.tsx` | MutationCache 401/403 统一 toast，移除组件级重复补偿 + 契约测试 |

> 注：首次提交①时误把先前误暂存的 143 个 fe-html 快照一并带入，已用 `git reset --mixed HEAD~1` 非破坏回退（工作区文件零影响）后仅暂存目标文件重提，保证每项 commit 最小、可评审。

## 二、差异单 §1 —— MarkdownView 硬编码字号（task59 批判①）

- 现状：`className` 字面量 `text-[15px]` 与 `prose-sm` 混用（`MarkdownView.tsx:27`）。
- 修复：替换为 `text-sm`（Tailwind 14px / 0.875rem，与 `prose-sm` 默认字号完全一致），消除魔法字号，层级对齐 prose-sm。
- 验收：
  - `grep -rn "text-\[15px\]" edu-frontend/src/` → **0 命中**。
  - `MarkdownView.test.tsx`（4 用例）通过，渲染视觉无回归（15px→14px，1px 降级，语义统一）。

## 三、差异单 §2 —— MutationCache 401/403 早退与组件级 onError 兜底一致性（task60 批判②）

### 根因
全局 `MutationCache.onError` 对 401/403 **早退不弹 toast**（注释自述依赖组件自行补偿），仅 `EditUserDialog` 补偿了 403，**401 完全静默** → 易遗漏。

### 修复（query-client.ts 拆分职责）
- `globalMutationError`（写操作 / MutationCache）：401/403 **统一 toast**（message + detail），不再早退；api-client 的 `onApiUnauthorized` 仍独立负责清 token + 跳登录，职责不重叠、零双弹。
- `globalQueryError`（读操作 / QueryCache）：401/403 **保持静默**（加载场景由 onApiUnauthorized / 管理员守卫处理跳转），避免加载时重复 toast 噪声；仅非认证错误 toast。
- 导出 `createQueryClient()` 供测试复用真实缓存（生产路径与单测一致）。
- 移除 `EditUserDialog` 组件级 403 补偿（`toastMutationError` + `onError`），删除未用 `ApiError` import；`UserTable`/`EditUserDialog` 顶部注释同步更新为「全局统一处理」。

### 契约测试覆盖
- 新增 `src/lib/query-client.test.ts`（9 用例）：
  - `globalMutationError`：401 / 403 / 403+detail / 409 均**单次** toast；
  - `globalQueryError`：401 / 403 **不 toast**（静默），500 toast；
  - `createQueryClient` 端到端：真实 `mutationCache.build().execute({})` 触发 401、403 各**恰好一次** toast（接线与生产一致）。
- `EditUserDialog.test.tsx`（6 用例，原 5 + 新增 1）：
  - `renderDialog` 接入真实 `MutationCache onError: globalMutationError`；
  - 40303 红线兜底 → 全局单次 toast，**无组件级双弹**（`toHaveBeenCalledTimes(1)`）；
  - 新增 401 登录失效 → 全局单次 toast。

## 四、纪律校验（全部通过）

| 项 | 结果 |
|----|------|
| 前端完整测试 | **495 通过（72 文件）** |
| TypeScript | `tsc --noEmit` exit 0 |
| ESLint | 触达文件 exit 0 |
| 生产构建 | `next build` 成功（路由表完整输出，无错误） |
| grep ① `text-[15px]` | 全仓 src 0 命中（本节 only） |
| grep 5 项（hex/内联色/禁闭色/任意字号/灰系）于所改文件 | 0 新增违规 |

## 五、环境备注
- 前端 `edu-frontend`（Next 3000）改动已提交；后端 8003 本节无动作。
- 所有 commit 已基于最新 HEAD `c8e99d8`，工作区其余后端修改（`edu-agent/app/ai/*.py` 等）与本项无关，未被带入，保持未暂存。

> 待编排者验收。