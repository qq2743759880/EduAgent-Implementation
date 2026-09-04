# task51 社区列表 · community.html — SOP 完整返工完成报告（fe-* 子代理）

> 日期：2026-08-21 ｜ HTML：`test-reports/fe-html/community.html` ｜ 冻结点：R2 FINAL ｜ 调用链：风格定调 → frontend-design → prototype → colorize → polish → visual-validation → audit/critique
> 状态：**APPROVED**（独立 fe-auditor 从 REJECT 修复后复审通过）→ 可移交 fe-implementer 写 React（/community）

---

## 一、术语与数据契约
- 冻结风格：candy-playful（糖果色卡通风，Duolingo 系「学中玩」），tokens 全在 `:root`（`--candy-*`/`--ink-*`/`--tint-purple-*`/`--shadow-*`）。
- 数据契约⑬：`GET /api/community/posts` 壳解包 `data{total,page,page_size,items:[PostListItem],mine_total_posts}`；点击帖子 → `/community/[postId]`。
- 审核工具条 `.respbar`（视口 1440/1280/1024/768/520/375 + 四态）为效果图专属，不进入 React。

---

## 二、本轮整体情况与初版污染诊断（Step 0）

初版 `community.html`（v1 R1）结构方向已对（四态 + 筛选/排序/搜索/分页/FAB + @container 响应式），但被 **Trae 浏览器 inspect 工具严重污染**：

| 污染项 | 说明 |
|---|---|
| `<head>` 注入约 2500 行 | 浏览器预览调试样式/脚本（trae-browser-inspect / vite HMR / actionButton 等 IDE 产物填入 `:root` 之后的 `<style>`/`<script>`） |
| 内联几何污染 | `.hero/.filter/.toolbar/.mine` 被注入 `style="width/height/transform:matrix(...)"` 残值 |
| 垃圾 DOM | 帖子列表被压缩成单行、含空 `style=""` 属性、锁定帖多出 `<span class="undefined">undefined</span>` 节点 |
| **数据字段映射反** | 💬(comment) 与 👍(like) 显示对调：契约⑬ mock 置顶帖 `like_count:342, comment_count:18`，静态却渲染「💬342 · 👍18」 |

初版不可作为 APPROVED 交付，故采取**整体干净重写**（保留设计方向，清除全部污染）。

---

## 三、返工动作（Step 1–4，clean rewrite）

- **清污染**：剥离全部 IDE 注入样式/脚本；删除内联 `transform/width/height`；重排帖子列表为可读缩进；删除 `undefined`/空 `style`。
- **修字段映射**：置顶帖 → `👁1283 · 💬18 · 👍342`；锁定帖 → `💬0 · 👍89`，与契约⑬ mock 逐位一致。
- **补 a11y**：全局 `:focus-visible` 焦点环、`.visually-hidden`、搜索 `aria-label`、排序 `aria-label`、`boards[aria-live=polite]`、帖子卡 `tabindex=0`。
- **token 化**：新增 `--tint-purple-01/25/35` 回收 `.mine/.tag/.respbar:hover` 等紫色半透明 rgba，**业务色硬编码归零**。
- **响应式加固**：375 实测零水平溢出；`@container` 驱动 520 断点 chips 横向滚动、移动端桌面 CTA 隐藏 + FAB 交接（`postNewDesktop:none / fab:flex` 程序化验证）。

---

## 四、Step 5 visual-validation
- 新建并真跑 `shoot-community.js`：9 张截图矩阵（1440/1280/1024/768/520/375 × 成功 + loading/empty/error @1280）。
- 交互 probe：375 零溢出、四态驱动正常、chips 筛选可点、**无 `undefined` 污染**、无 console/page 错误。

## 五、Step 6 audit/critique（独立 fe-auditor，REJECT → 修复 → 复审通过）

独立审查判定 REJECT，命中 2×P2 必改 + 4×P3 建议，已全部修复并程序化复核：

| 严重度 | 审查项 | 修复 |
|---|---|---|
| **P2** | chips 用残缺 `role=tablist/tab` 却无 tabpanel，且语义是单选筛选 → 改 `role=group` + `aria-pressed` | ✓ 复核：无 `role=tablist`、恰 1 个 `aria-pressed=true` |
| **P2** | 错误态暴露内部调试枚举（壳解包失败/code 非 0/网络断）→ 用户导向文案 | ✓ 复核：文案不含内部枚举 |
| P3 | 锁定帖与普通帖同交互暗示 → 只读弱化 + `aria-disabled` + 去除 tabindex | ✓ `cursor:default` 无 hover 上浮、无焦点 |
| P3 | 空/错误 `.state` 缺角色 → 加 `role=status`（error 用 `role=alert`） | ✓ |
| P3 | 加载骨架无读屏文本 → 加 `visually-hidden`「正在加载帖子…」+ `role=status` | ✓ |
| P3 | 搜索冗余重复标注（label+aria-label）→ 去重 | ✓ 仅保留 `aria-label` |

---

## 六、验证结果一览

| 项 | 结果 |
|---|---|
| 截图矩阵 | 9 张全绿 + 交互 probe 通过 |
| 横向溢出 | 375/520/1280 均 0（scrollWidth===clientWidth） |
| 数据字段 | 置顶帖 💬18 👍342、锁定帖 💬0 👍89 与契约⑬逐位一致 |
| 业务色硬编码 | :root 外 0（新增 3 token 全回收） |
| 注入污染 | trae-browser/@vite/matrix/undefined 残留 = 0（仅 AUDIT LOG 注释提及描述） |
| a11y | chips `aria-pressed`、锁定帖只读、state role、loading 读屏文本 全验证通过 |
| console/page 错误 | none |

---

## 七、软肋与说明
- 数据契约⑬ 为后端接口，页面按「静态示意 + 局部交互」处理，未造假；错误态文案已清理内部实现细节，不泄露后端错误枚举。
- .respbar 为效果图审核工具，交付 React 时移除。
- 帖子卡为静态占位（无真实 onClick，点击跳 /community/[postId] 由 React 落地）。

## 八、交付物
- `test-reports/fe-html/community.html`（R2 FINAL，AUDIT LOG 已至 R2）
- `test-reports/fe-html/shoot-community.js`（截图矩阵脚本）
- `test-reports/fe-html/shot-c-*.png`（9 张矩阵截图）、`audit-c-*.png`（审查探针截图）
- 独立审查报告由 fe-auditor 子代理产出（见 Step 6）

**结论：community.html 已 APPROVED，可移交 fe-implementer 写 React 页面（/community）。**