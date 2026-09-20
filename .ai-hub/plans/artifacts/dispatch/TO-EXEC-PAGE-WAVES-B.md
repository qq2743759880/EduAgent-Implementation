# TO-EXEC-PAGE-WAVES-B — 逐页重塑包 B：学生端次级 + chat 7 页

## 使命（1 天工期主干，Gate A 已批款+底座已验收）

按已批款风格（黏土拟物；**chat 气泡=B 变体**）重塑 7 个生产页。**每页独立 commit**，每页门禁全绿才算完成。

## 你的页面（只许碰这 7 个文件）

`edu-frontend/public/` 下：chat / community / community-post / achievements / coupons / my-cohorts / refund（.html）

## 必读资产（开工前实读）

同 PACK-A 清单（`docs/前端风格重塑方案.md` §3.1 黑名单+Gate A 批款块、`theme.css` 令牌冻结、`docs/dom-hooks-frozen.md` 你 7 页节、`docs/icon-inventory.md`、`docs/rollback-drill.md`），另加：

- `edu-frontend/_prototypes/clay-gatea/chat-b.html` —— chat 页风格基准（批款款）
- **chat 页特别铁律（时光.md §五 同口径）**：HITL 确认卡（renderHitlCard）只换 class 与令牌，**id/结构/事件绑定禁动**（favorite_add 确认链已实测闭环，勿破坏）；流式消息/Markdown 渲染容器走 §7.5 第三方覆盖清单（容器底色继承令牌、代码块深色底）
- **chat 页 G3 风险最高**（SSE/确认卡/动态 DOM）——钩子冻结清单逐条核完才动样式

## 每页工序

同 PACK-A 六步（接入 `theme.css?v=7fed87f` 统一版本 → emoji 换 sprite → refund.html 移除 Google Fonts 外链 → 清 G6/G7/G9 存量债 → 六门全跑 → 单页 commit `style(fe)/<page>: clay 重塑+门禁绿(PACK-B)`）。

## 铁律

同 PACK-A 全部条款（结构层/行为层禁动、黑名单、禁改 theme.css/sprite/他包页面、不 push、分支对账、3322/9988 在跑）。报告写 `REPORT-PAGE-WAVES-B.md`（同 PACK-A 结构）。
