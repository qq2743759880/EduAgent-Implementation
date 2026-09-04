# task46 课程详情页 独立审查报告（fe-a11y-auditor + fe-perf-auditor + fe-visual-auditor）

> 审查人：fe 独立审查子代理（只读审查，不改代码）
> 被测对象：`/courses/[seriesId]` 课程详情页 React 实现（task46）
> 审查时间：2026-08-20
> 对照基准：`.claude/specs/frontend/tokens/design-tokens.json`（糖果色 tokens）+ `test-reports/fe-html/course-detail.html`（已 APPROVED，R2）
> 审查范围：page.tsx / CourseDetailClient.tsx / CohortList / FavoriteButton / CouponPicker / CourseDetailHero / CourseDetailSyllabus / CohortDetailPanel / CourseDetailTabs / lib/api/coupons.ts / 两个测试文件

## 结论：NEEDS_FIX

存在 **1 个 P1 功能偏差**（默认班次选择未排除满员班次，与已 APPROVED 效果图 R2 修复②直接矛盾），必须修复；另有若干 P2 a11y / visual 问题建议修复。P1 修复后即可 APPROVED。

---

## 一、a11y 审查

| # | 检查项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | 班次选择 RadioGroup 语义/键盘 | ✅ 通过 | 自研 RadioGroup 用 `role="radiogroup"` + 原生 `<input type="radio">`（sr-only），同 `name` 组内方向键/空格原生可用；满员 `disabled`；label 包裹整卡，点击区大。小问题：radio 可访问名 = 整卡文本（冗长但信息完整，可接受）；`aria-checked` 对原生 radio 冗余但无害 |
| 2 | FavoriteButton aria-pressed 双通道 | ✅ 通过 | `aria-pressed={favorited}` + `aria-label` 随状态切换（"收藏/取消收藏 系列名"）+ `fill-candy-red` 颜色通道 + focus-visible 蓝色焦点环 |
| 3 | CouponPicker Dialog 语义/焦点/Escape/aria-modal | ✅ 基本通过 | Base UI Dialog（modal 默认 true）：`role="dialog"` + `aria-labelledby`/`aria-describedby` 自动关联 Title/Description + FloatingFocusManager 焦点陷阱 + Escape 关闭 + 背景 `aria-hidden`。**注意**：Base UI 未显式输出 `aria-modal="true"` 属性，靠背景 aria-hidden + 焦点陷阱实现等效模态语义（可接受，P3 记录） |
| 4 | Tabs tablist/tab/tabpanel + 方向键 | ✅ 通过 | Base UI Tabs 原生实现 `role="tablist"` / `role="tab"` + `aria-selected` / `role="tabpanel"` + roving tabindex 方向键切换（已核对 node_modules 源码） |
| 5 | 图片 alt / 按钮可访问名 / 对比度 | ⚠️ 部分通过 | 无 `<img>`（封面为渐变+emoji，emoji 已 `aria-hidden`）；按钮均有文本/aria-label。**对比度问题 P2**：candy-red/candy-orange 小字 < 4.5:1（详见问题清单 #3） |
| 6 | 四态 aria-live / role=status | ⚠️ 部分通过 | error → `role="alert"` ✅；empty → `role="status"` ✅；**loading → ❌** 骨架 `aria-hidden="true"` 无任何 live 播报（详见问题清单 #2） |

## 二、perf 审查

| # | 检查项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | 数据请求并行 | ✅ 通过 | `detailQ` / `cohortsQ` / `mindmapQ` 挂载即并行（React Query 同批触发）；`modulesQ` 依赖 `effectiveCohortId`（必要串行）；`templatesQ` 弹窗打开才懒加载；`myCouponsQ`/`favQ` 登录后并行。无重复请求 |
| 2 | useMemo/useCallback | ✅ 通过 | `cohorts`/`defaultCohort` useMemo 合理；无缺失必要 memo（组件树小，重渲染成本低）；无过度优化 |
| 3 | 列表 key 稳定 | ✅ 通过 | `c.id` / `m.id` / `s.id` / `coupon_template_id` / `r.id` 均稳定 |
| 4 | 大列表虚拟化 | ✅ 通过 | 课次按模块分组（每模块约 4 条），规模小，无需虚拟化 |
| 5 | 其他 | ⚠️ P3 | `CourseMindmapView` 空态/错误态也执行 `echarts.init`（浪费一次初始化，可延迟到 ready 再 init） |

## 三、visual 审查（对照 course-detail.html APPROVED 效果图）

| # | 检查项 | 结果 | 说明 |
|---|--------|------|------|
| 1 | 布局结构 | ⚠️ 部分一致 | Breadcrumb / Hero 2:3 分栏 / CohortList / Tabs 四栏骨架一致；但**购买面板内部顺序与效果图不符**（P2，见 #5） |
| 2 | 糖果色 tokens | ✅ 通过 | 全语义 class（bg-card / text-candy-orange / border-candy-purple 等），无 `bg-[#...]` 硬编码；仅 2 处 `style={{width}}` 动态宽度（CohortList 进度条 / ReviewList 评分条），非色值，合理 |
| 3 | 响应式 | ⚠️ 有断裂风险 | **375px 下 Tabs 四栏可能溢出**（P2，见 #8）；Hero 2 栏断点 1024 vs 效果图 900（P3） |
| 4 | teaching_status 徽章双通道 | ✅ 通过 | StatusBadge 文字 + tone 颜色双通道（text 为信息主通道），非纯色块 |
| 5 | 封面渐变 | ⚠️ P2 | 效果图：三色渐变 `orange→pink→purple`；React：`coverGradient` 单色 fade（from-candy-X to-candy-X/30）。视觉强度明显弱于 APPROVED 效果图 |
| 6 | 选中班次边框/radio 色 | ⚠️ P2 | 效果图选中态为 candy-orange 边框+radio；React 为 `border-candy-purple` + `text-candy-purple`（紫） |
| 7 | hot 席位条 / 满员徽章样式 | ⚠️ P2 | 效果图 hot 席位条 candy-orange、徽章实底白字；React hot 用 candy-red、徽章描边浅底 |
| 8 | 购买面板顺序 | ⚠️ P2 | 效果图：班次列表 → **[立即报名 + 收藏] 同行** → 领券(全宽) → 汇总 → 提示；React：班次列表 → **[收藏 + 领券] 同行** → 立即报名(全宽) → 未登录提示 → 汇总。主 CTA 位置与效果图不同 |

---

## 四、问题清单

### P1（必须修复）

| # | 位置 | 行 | 问题 | 修复建议 |
|---|------|----|------|----------|
| 1 | `src/app/(user)/courses/[seriesId]/_components/CourseDetailClient.tsx` | 101-106 | **默认班次选择未排除满员班次**。`defaultCohort` 仅按 `(c.yn ?? 1) === 1` 过滤，未过滤 `current_student_count >= max_student_count`。若最低价在售班次已满员，页面默认选中满员班次（报名按钮 disabled「该班次已满员」+ 加载该班次大纲），与 APPROVED 效果图 R2 修复②「默认选中最低价**有席位**班次」直接矛盾。现有测试数据中最低价班次恰好有席位，未覆盖该场景 | 在 sort 前追加 `.filter((c) => c.current_student_count < c.max_student_count)`；若全部满员再回退 `onSale[0]`（保持现有 fallback）。并补一条「最低价班次满员时默认选中次低价有席位班次」的测试 |

### P2（建议修复）

| # | 位置 | 行 | 问题 | 修复建议 |
|---|------|----|------|----------|
| 2 | `CourseDetailClient.tsx`（DetailSkeleton） | 365-381（`aria-hidden` 367） | loading 态无 `role="status"` / `aria-live` 播报，读屏用户在加载期间无任何反馈（WCAG 4.1.3） | 骨架容器外层加 `role="status"` + 视觉隐藏文本「正在加载课程详情」，或 `aria-busy` + live region。Tabs 内 modules 加载骨架（CourseDetailTabs.tsx:39-44）同理 |
| 3 | `CohortList.tsx` / `CourseDetailHero.tsx` | CohortList 62,86；Hero 110,179 | 对比度不达标：candy-red `#FF4B4B`（≈3.3:1）与 candy-orange `#FF4D00`（≈3.3:1）在白底上均 < 4.5:1，用于 11px 徽章文字 / 20px 价格 / 12px 实付等非大字号场景，不满足 WCAG AA | 文字场景改用派生深阶（如 `#C74000` candy-orange-deep，效果图 R2 已用该色修 warn 提示）；或加大到 large-text 阈值（≥18.66px bold / 24px） |
| 4 | `CouponPicker.tsx` | 113-127 | 「抵扣」radio 可访问名仅「抵扣」，读屏用户无法区分对应哪张券（多张已领券时尤其明显）；且无 fieldset/radiogroup 分组 | radio 加 `aria-label={`使用 ${t.coupon_name} 抵扣`}`，或把券名纳入 label 文本 |
| 5 | `CourseDetailHero.tsx` | 117-183 | 购买面板内部顺序与 APPROVED 效果图不符（主 CTA「立即报名」被下移，领券/收藏先行） | 按效果图调整：`[立即报名 + 收藏]` 同行 → 领券全宽 → 汇总 → 未登录提示 |
| 6 | `CourseDetailHero.tsx` | 63-67 | 封面为单色 fade 渐变，与效果图三色渐变（orange→pink→purple）视觉强度差距明显 | 详情页 Hero 封面改用多色糖果渐变（可新增 detail 专用渐变 token 或内联三色），或确认沿用共享 coverGradient 为有意决策 |
| 7 | `CohortList.tsx` | 49,56 | 选中班次边框/radio 为紫色，效果图为橙色 | 改 `has-[:checked]:border-candy-orange` + `text-candy-orange`（对齐效果图） |
| 8 | `CourseDetailTabs.tsx` | 31-36 | 375px 下 4 个 tab（含 emoji + nowrap 文本）在 `w-full` + `flex-1` 列表内可能溢出/重叠（效果图 `.tabs` 有 `flex-wrap:wrap`） | TabsList 加 `flex-wrap`，或 375 断点下缩小字号/隐藏 emoji；建议 375 实测截图确认 |
| 9 | `CourseDetailHero.tsx` | 52 | `payAmount = price - coupon.face_value` 未 clamp，若 `face_value > price`（契约未保证 face_value ≤ min_spend）会出现负实付「立即报名 -¥200」 | `Math.max(0, ...)` 或 `usable` 条件追加 `price >= face_value` |
| 10 | `CohortList.tsx` | 76 | hot 席位条（ratio>80）用 candy-red，效果图为 candy-orange | 改 `bg-candy-orange` 对齐效果图 |

### P3（记录项，不阻断）

| # | 位置 | 说明 |
|---|------|------|
| 11 | `components/ui/dialog.tsx` | Base UI 未显式输出 `aria-modal="true"`（靠背景 aria-hidden + 焦点陷阱等效实现）；关闭按钮 sr-only 文案为英文 "Close"，建议改「关闭」 |
| 12 | `CourseDetailClient.tsx:353` | 面包屑中间项为「搜索」（/courses/search），效果图为分类名「编程」——属合理适配（真实路由），记录 |
| 13 | `CourseDetailHero.tsx:60` | Hero 2 栏断点 lg=1024，效果图为 ≥900px；900-1024 区间布局不同，记录 |
| 14 | `components/ui/status-badge.tsx:69` | 每个徽章 `role="status"`（live region），课次列表多实例会形成多个常驻 live region，语义上建议静态徽章用普通 span（文字已承载信息） |
| 15 | `CourseMindmapView.tsx:48-59` | 空态/错误态也 `echarts.init`，建议 ready 后再初始化 |

---

## 五、审查总结

- **a11y**：RadioGroup / FavoriteButton / Tabs / Dialog 核心语义与键盘交互均达标（Base UI 原生实现可靠）；主要缺口是 **loading 态无 live 播报**（P2）与 **candy 色小字对比度**（P2）、**抵扣 radio 可访问名**（P2）。
- **perf**：数据并行、memo、key、虚拟化全部通过，无实质问题。
- **visual**：tokens 使用合规（0 硬编码色值）；但存在多处与 APPROVED 效果图的视觉偏差（购买面板顺序、封面渐变、选中态颜色、375px Tabs 溢出），均为 P2 级视觉保真问题。
- **功能**：发现 1 个 P1 功能偏差（默认班次选择未排除满员班次），与效果图 R2 修复②矛盾且测试未覆盖。

**判定：NEEDS_FIX**。必须修复项：P1（#1 默认班次选择）。建议一并修复 P2 #2/#3/#4（a11y）与 #5/#6/#7/#8（视觉保真）。P1 修复 + 补测试后即可 APPROVED。

---

# 第 2 轮复验（2026-08-20）

> 复验人：fe 独立审查子代理（只读复验，不改代码）
> 复验范围：第 1 轮判定 NEEDS_FIX 的 P1 + 3 项 P2 修复，代码级复验 + 测试运行验证

## 六、P1 修复验证

| 项 | 位置 | 结果 |
|----|------|------|
| 默认班次排除满员 | `CourseDetailClient.tsx:104` 已追加 `.filter((c) => c.current_student_count < c.max_student_count)`，位于 `(c.yn ?? 1) === 1` 过滤之后、价格 sort 之前 | ✅ 正确：默认选中「在售 + 有席位 + 最低价」班次；全部满员时回退 `cohorts[0]`（保持原 fallback，符合修复建议） |
| 补测试 | `page.test.tsx:313-327` 新增「最低价班次满员时默认选中下一个有席位班次」：构造 fullB(2799 满) + cohortFull(2899 满) + cohortA(2999 有席位)，断言 `listCohortModulesMock` toHaveBeenCalledWith(11) | ✅ 通过（9/9） |

## 七、P2 修复验证（3 项）

| # | 位置 | 结果 |
|---|------|------|
| 1 | `CourseDetailClient.tsx:366-383` DetailSkeleton 外层 `role="status"` + `aria-live="polite"` + sr-only「正在加载课程详情…」，内部骨架块 `aria-hidden="true"` | ✅ 符合 WCAG 4.1.3；骨架无焦点元素，无副作用 |
| 2 | `CouponPicker.tsx:118` radio 加 `aria-label={`抵扣 ${t.coupon_name}`}` | ✅ 可访问名唯一可区分（多张已领券场景） |
| 3 | `CourseDetailHero.tsx:52` `payAmount = Math.max(0, price - coupon.face_value)` | ✅ 杜绝负实付 |

## 八、empty 测试修改合理性

原 `findByRole("status")` 在骨架新增 `role="status"` 后，loading 阶段即命中骨架 status 区域（false positive，未真正验证空态）。改为 `findByText("课程不存在")` + `closest('[role="status"]')`：先等待真实空态文案，再断言其位于 status 区域内（`EmptyState` 自带 `role="status"`，empty-state.tsx:24）。**✅ 合理且更严格**。骨架与空态为互斥渲染分支（`isLoading && !data` vs `!data`），无时序冲突。

## 九、测试运行结果

- `page.test.tsx`（详情页）：**9/9 通过**（含新增 P1 用例 + 修改后 empty 用例）
- `course-detail-components.test.tsx`：**7/7 通过**
- 全库无其他 `findByRole("status")` 依赖骨架（states / data-table / courses 列表页均为独立组件测试，不受影响）

## 十、新增问题

未发现新增 a11y / perf / visual 问题。第 1 轮 P2 未修复记录项（购买面板顺序 / 封面三色渐变 / 选中态颜色 / 375px Tabs 溢出 / hot 席位条颜色 / 对比度 3.3:1）维持原结论：视觉细节偏差，非阻断，本轮不处理。

## 复验结论：APPROVED

P1 功能偏差已修复并补测试；3 项 P2 a11y 修复正确无副作用；empty 测试修改合理；相关测试全量通过。剩余 P2 视觉细节为记录项，不阻断合入。
