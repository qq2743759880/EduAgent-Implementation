# TO-EXEC-GATE-V2 — 门禁工具第二批增强 + 基线刷新 + 前提修正

## 背景（编排者验收 PAGE-WAVES 三包时实测沉淀，全部有实测证据）

三包 25 页验收通过（G8 全站 0 failed / G3 全站 PASS / G1 断点 0）。本任务修门禁工具自身的已证缺陷与前提问题。

## 工作项（每项附验收口径）

1. **G7 tab-reachable 聚合判定**：同名 radio 组整组一个 Tab 停靠是 HTML 标准（admin-question-detail 4 radio 误报 31/34）；roving tabindex（WAI-ARIA tabs 规范，learning 页 task06 模式）方向键可达——门禁按「radio 组聚合 + roving tabindex 容器识别」判定，修复后 admin-question-detail 与 learning 两页 G7 应绿
2. **G7 aria-title-frozen settle**：dashboard 冻结快照存了「加载中」态标签（metrics 慢查询期采集）——快照采集与复验统一加 200ms settle（EDU_GATE_SETTLE_MS 已存在，确认 G7 aria 检查消费它），修复后 dashboard 11/11 绿
3. **achievements 基线刷新**：冻结快照期 logs_total=101+，现 33（DB 数据清理，数据漂移非回归）——执行 `node scripts/gates/viewport-a11y-gate.mjs --page http://127.0.0.1:3322/achievements.html --update-baseline` 刷新并复验绿
4. **G9/G8 N/A 白名单机制**：login-register（load 零 API）与 admin-users-refine-proto / admin-courses-recycle-proto（零 script 零 API）的 state-intercepted 结构性无法命中——门禁加 `--na <page>` 或白名单文件（N/A 页该项记 SKIP 不记 FAIL），三页 G9 应绿
5. **route-stable 前提钉死**：同一页在 3322 生产态（next start）下 auth 守卫页重定向链不同（实测 /chat.html→/login-register.html→/ 且 / 为 React 根路由，theme 检查读到错 DOM，G8 --all 曾 100 红）；dev 态下同页正常。修法二选一并写明：a) 门禁启动时探测 3322 形态非 dev 即 FAIL-FAST 提示 b) 门禁自校验首页渲染路径与预期一致才继续。另把 `verify_pages_cdp.mjs` 硬编码 3000/8000 旧端口改为 3322/9988 或环境变量
6. **console 诊断跟进**：G8 全站 18 条非阻断 console 诊断（me=14/dashboard=12/practice=12/coupons=8/courses=8 为头部）——逐条分类：静态资源 404/JS 异常=修；预存 API 行为噪声=登记豁免清单

## 铁律

只改 `scripts/gates/**`、`docs/`（基线与清单）；**生产页面 public/*.html 与 theme.css 零触碰**（发现页面真 bug → 停手上报，勿代改）；不 push；可多 commit（按工作项分）；报告 `.ai-hub/plans/artifacts/dispatch/REPORT-GATE-V2.md`（每项附修复前后门禁输出对比 + 资产消费证据 + 批判承接段）。开工前后 `git branch --show-current`=feature/opt-waves；3322 需 dev 态在跑（`node node_modules\next\dist\bin\next dev -p 3322`，AGENTS.md 已勘误）。
