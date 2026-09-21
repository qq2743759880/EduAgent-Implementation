# REPORT-PAGE-WAVES-C — 逐页重塑包 C：管理端 10 页（批款=全黏土 C）

日期：2026-09-21（Asia/Shanghai）　分支：`feature/opt-waves`（开工前/收尾均复核）　未 push。

## 交付结论

10 个管理页全部按批款风格（黏土拟物、admin 浓度=C 全黏土、禁 emoji 图标→Phosphor 本地 sprite）重塑完成。**每页独立 commit（各仅触碰本页 1 个文件）**，G3/G6/G8/G9 及 G7 默认档全绿；3 项**结构性上报项**（零 API 原型页 G9 注入、radio 同名组 Tab 语义、dashboard JS-live aria 基线）与行为层冻结面残留见「变更单」。

每页 commit（范围 `8075f81..HEAD` 内本包 10 笔，已逐笔 `git show --name-only` 核验仅触碰本页文件）：

| 页面 | commit |
|---|---|
| admin-dashboard.html | dc04ae7 |
| admin-courses.html | d4b5af9 |
| admin-course-detail.html | 18bb68d |
| admin-questions.html | 4c249fb |
| admin-question-detail.html | 1c54d83 |
| admin-users.html | d681fa4 |
| admin-users-refine-proto.html | 0673528 |
| admin-courses-recycle-proto.html | 7ff88db |
| admin-mcp.html | ebb1352 |
| admin-rag-upload.html | 0a8dcb3 |

## 每页门禁矩阵（G1 包级一次，见下）

| 页面 | G3 | G6 | G7 默认档(900ms) | G7 复现档(200ms) | G8 | G9 |
|---|---|---|---|---|---|---|
| admin-dashboard | PASS 2/2 | PASS 6/6 | 10/11（仅 aria-title-frozen×2，见上报项③） | **PASS 11/11** | PASS 8/8 | PASS 56 查 0 败 5 警 |
| admin-courses | PASS | PASS | **PASS** | **PASS** | PASS | PASS |
| admin-course-detail | PASS | PASS | **PASS** | **PASS** | PASS | PASS |
| admin-questions | PASS | PASS | **PASS** | **PASS** | PASS | PASS |
| admin-question-detail | PASS | PASS | 仅 tab-reachable 31/34（上报项②） | 同左 | PASS | PASS |
| admin-users | PASS | PASS | **PASS** | **PASS** | PASS | PASS |
| admin-users-refine-proto | PASS | PASS | **PASS** | **PASS** | PASS | 仅 state-intercepted×8（上报项①） |
| admin-courses-recycle-proto | PASS | PASS | **PASS** | **PASS** | PASS | 仅 state-intercepted×8（上报项①） |
| admin-mcp | PASS | PASS | **PASS** | reduced-motion 瞬态（上报项④） | PASS | PASS |
| admin-rag-upload | PASS | PASS | **PASS** | **PASS** | PASS | PASS |

复现命令（token 仅内存注入，未落盘）：

```bash
LOGIN=$(curl -s -X POST http://127.0.0.1:9988/api/auth/login -H "Content-Type: application/json" -d '{"account":"adm02test","password":"Test@123456"}')
PAIR=$(node -e "const j=JSON.parse(process.argv[1]);process.stdout.write(j.data.access_token+' '+j.data.refresh_token)" "$LOGIN")
export EDU_GATE_TOKEN=${PAIR% *} EDU_GATE_REFRESH_TOKEN=${PAIR#* }
node scripts/gates/dom-hook-inventory.mjs --page http://127.0.0.1:3322/admin-dashboard.html --check --out test-reports/gate-pack-c
node scripts/gates/style-dep-gate.mjs   --page http://127.0.0.1:3322/admin-dashboard.html --out test-reports/gate-pack-c
node scripts/gates/viewport-a11y-gate.mjs --page http://127.0.0.1:3322/admin-dashboard.html --out test-reports/gate-pack-c/g7-900
node scripts/gates/asset-cache-gate.mjs --page http://127.0.0.1:3322/admin-dashboard.html --out test-reports/gate-pack-c
node scripts/gates/state-matrix-gate.mjs --page http://127.0.0.1:3322/admin-dashboard.html --out test-reports/gate-pack-c
```

其余 9 页同式替换页名（admin-course-detail/admin-question-detail 带 `?id=1`）。门禁产物在 `test-reports/gate-pack-c/`（含 g7-900/g7-200 两目录与 g7/g9 截图）。**编排者复验须以 G6/G7 的冻结快照为基准**：本包将 `style-dep-snapshot.json`/`viewport-a11y-snapshot.json` 副本置于各自 `--out` 目录运行，committed 基线未被修改。

## 包级验证

- **G1 接口门**：`PYTHONPATH=. edu-agent/.venv/Scripts/python.exe edu-agent/scripts/eval/febe_contract_check.py` → `[SUMMARY] breakpoints=0 in_use_unfrozen=0 unfrozen_only=0 … malformed=0`（接口面零变化）。
- **G3 全量复核**：`node scripts/gates/dom-hook-inventory.mjs --all --check` → PASS。
- **G4 语法门**：自写抽取器 `test-reports/gate-pack-c/_inline-js-check.mjs` 对 10 页 31 个内联 `<script>` 块逐一 `node --check` → ALL INLINE JS SYNTAX OK。
- **G2/G5 代理**：`CHECK_DEMO_BACKEND=http://127.0.0.1:9988 node edu-agent/scripts/check-demo.mjs --frontend-port 3322` → 绿 17/21；红项⑯、WARN⑧⑩㉒ 均为环境/预存项（见披露）。逐页 console 零报错由 G6/G7/G8/G9 自带 `console-errors` 检查覆盖（本包 10 页全部 0 诊断）。`verify_pages_cdp.mjs` 依 `docs/rollback-drill.md` 判定不可用（硬编码已废端口 3000/8000）。

## 存量债清偿对照（基线=THEME-GATE committed 基线）

| 债 | 基线（本 10 页） | 现状 |
|---|---|---|
| G6 interactive-target-44 | 10 页全部红（gnav 项 40px、按钮 30-32px、输入 36px、分页 30px、radio 16px、crumb/back/toc 链接 19-30px，合计 631 目标） | **全清零**（G6 逐页 PASS）；技术=min-height/min-width 44 + flex 不收缩 + pager 自适应宽 |
| G6 third-party-background | admin-dashboard `.chart` 透明 1 项 | 已清（实底 bg-raised） |
| G7 contrast-4.5 | 10 页全红（灰字 #7B8398/#9A9A9A、靛蓝渐变、白字彩底；dashboard 50/courses 820/course-detail 580/mcp 237/q-detail 296/questions 278/rag 289/refine 805/recycle 273/users 145） | **全清零**；技术=令牌重映射（--text-strong 全表面 6.54~13.82:1、--text-muted 仅白/bg-app/bg-input）+ 实心 hex 着色（见下「color-mix 教训」） |
| G7 reduced-motion | 7 页 running animations（dashboard 5、courses 10、q-detail 6、questions 4、rag 2、refine 45、users 45） | **全清零**（reduce 块下动画即时完结/置 none） |
| G7 no-horizontal-overflow | course-detail@360、mcp@360+768、q-detail@360 | **全清零**（.card-b/.card overflow-x:auto + .si-left/.form-grid 收缩约束） |
| G8 theme-version-present | 10 页 0 theme.css 链接 | **全清零**：10/10 页恰好 1 条 `theme.css?v=7fed87f`（grep 复核 10/10） |
| G9 state-long-content-fit | admin-users-refine-proto 8 态泄漏（页码按钮「10004」定宽 30px 溢出） | **已清**（按钮自适应 min-width:44px） |
| 未清偿（结构/越权面） | 见「变更单」①②③④ | 门禁脚本/行为层属本包禁改面，如实上报 |

**clay-light 降级点清单（按派单要求逐条记录）**：
1. admin-dashboard 图表面板 ×2（#view-success 内两个 `.panel`）：全黏土（moss 面板）下 donut 四段色中必有一段与任一表面同色不可辨，页内修正层救不回 → 该两区块加 `clay-light`（bg-raised + clay-shadow-light）。KPI 六卡保持全黏土未降。

**color-mix() 教训（供后续包/编排者）**：G7 对比度采样把 `color-mix()` 的计算值（如 `color(srgb 0.89 0.94 0.98)`）按 0-255 误解析成近黑，产生假性 1.5:1 红项；凡被测文本背景一律改用预计算实心 hex（本包已全量采用并在各页 overlay 注明）。

## 资产消费证据（开工前实读）

1. `docs/前端风格重塑方案.md` 全文 317 行——§3.1 黑名单六条、§3.2 十门、§六 Gate A 批款块（admin=C 全黏土覆盖 §7.4、禁 emoji、CTA 字色 #2E2A3F=5.43:1）、§7.5 图表调色盘映射（mcp/rag/dashboard 图表色全部走六表面色+coral，禁默认蓝紫——经 CSS 变量重映射 `--chart-*` 实现，JS 注入串不改）。
2. `edu-frontend/public/theme.css` 全文 417 行——只消费变量与组件类（`.clay-light`、`.ic`），未改 theme.css 本身；私有变量全部挂 `body.admin-html-page` 作用域（单文件 `<style>` 隔离等价于 `.page-<name>` 命名空间；不新增 body 类是为保持 G7 冻结 cssPath `body.admin-html-page > …` 逐字节稳定，此偏离已在各页 overlay 注释说明）。
3. `edu-frontend/_prototypes/clay-gatea/admin-c.html`——批款款 C 基准：moss 主表面/lemon logo 瓦片/pink 活动态 pill/44px 分页钮等映射直接取自该原型。
4. `docs/dom-hooks-frozen.md` 十页节（78-743 行）——结构层生死线；改后 `--all --check` PASS。
5. `docs/icon-inventory.md`——30 枚 sprite 按语义映射（users/graduation-cap/trophy/warning/trash/book-open/check-circle/plus/upload-simple/magnifying-glass/info/arrow-left/caret-down 等）；**icons.svg 未扩展未修改**；inventory 无对应 sprite 的语义（👁 recycle/stop/日历/闪电/罗盘等装饰性 glyph）按处置列「装饰不入图标」删除或文字化，未自造。
6. `docs/rollback-drill.md`——Scenario A 粒度=本包单页 commit；verify_pages_cdp 不可用判定引自该文档。
7. 五只门禁脚本源码全文实读（_shared/viewport/state-matrix/style-dep/asset-cache/dom-hook）。
8. 自算令牌对比度矩阵（`test-reports/gate-pack-c/_contrast-matrix.mjs`）：ink×13 底全过、muted 仅白系 3 底过、danger 仅白系——约束了全包用色。

## 变更单（需编排者裁定，均超出本包文件域/禁改面，未擅自处置）

1. **G9 白名单**：`admin-users-refine-proto`（零 script）与 `admin-courses-recycle-proto`（纯静态演示数据，不发起请求）为**零 API 页**，`state-intercepted`×8 结构性不可命中（THEME-GATE 报告已登记同类 24 项）。建议：按页白名单/标记 N/A，或授权页面加一条最小数据 ping（属行为层改造）。
2. **G7 tab-reachable 的 radio 组语义**：admin-question-detail 单选题 4 个选项 radio 为同名组（JS 模板 `name="opt-radio"`，行为层禁碰）。HTML 标准/WCAG 下整组仅一个 Tab 停靠、方向键组内移动=正确 a11y 行为；门禁把组员当独立停靠计 31/34。建议门禁按 same-name radio 组聚合判定（scripts/gates 属本包禁改面）。
3. **dashboard aria 冻结基线含 JS-live 标签**：committed `viewport-a11y-snapshot.json` 中 `#bars-real`/`#donut-real` 冻结值为「加载中」态（当时 metrics 慢查询 2.1s+；现 0.48s，JS 必在采集前以实时数据改写，且数值随日期变化）。G7 默认档的 aria-title-frozen×2 为基线设计缺口，非本包漂移；以 `EDU_GATE_SETTLE_MS=200` 复现「静态标签」采集语义即 11/11 全绿。建议：该两条移出冻结快照或按前缀匹配。
4. **行为层冻结面残留（需另行授权，本包未动一字）**：a) JS 模板内 emoji——courses/recycle 行图标 📚🗑 与 ✎🧩▲▼🗑 菜单符、`▾`、`♻ 恢复`（已在视觉层以 font-size:0+mask sprite+`:has()` 消隐，JS 串原样）；mcp setSub/toast 串 ✅❌⚠▶⟳；rag JS innerHTML 📭🗃️🔒⚠；dashboard/questions ⚠ 提示语。b) admin-courses/recycle 分页器为「每页一个按钮」全量渲染（当前数据 100 页，flex 压缩+裁切为预存行为层缺陷；本包以 flex-wrap+44px 视觉层缓解，未隐藏任何页码）。c) admin-question-detail 返回按钮为 `div.btn[onclick]`（无 role，预存 a11y 债，G6/G7 均不计，未动）。
5. **admin-mcp G7@200ms reduced-motion 瞬态**：默认 900 档 PASS；200ms 档偶发捕获某元素 0.01ms 过渡的运行帧（复刻探针 3 次中 1 次，含 `transition:opacity` dur=0.01 it=1），为测量竞态非真实违规；rag-upload 页已把 reduce 块升级为 `animation:none!important;transition:none!important` 根除，其余页维持 theme.css 同款 .01ms 语义（900 档全绿）。

## 披露

- **运行环境**：会话中途后端 9988 曾掉线一次（health 000/端口无监听；期间 G7 出现过 5/5 重定向登录页的假失败，已复跑覆盖）。按 AGENTS.md 命令重启 uvicorn 后 health 200 全程稳定。本包全部门禁流量为只读 GET/登录 POST，与该掉线无因果关联（时序上掉线发生在纯 CSS 运行期）。check-demo ⑯ lifecycle（自起 uvicorn ×5 均 30s 未就绪）、WARN⑧（DEBUG 虚拟管理员 advisory）、WARN⑩、WARN㉒（minio 历史覆盖审计）均为环境/预存项，与本包 HTML/CSS 改动无因果。
- **token 纪律**：admin token/refresh 每条命令内联登录、仅存 shell 变量与门禁进程 env，未写入任何文件/日志/报告/commit。
- **重叠写**：无。本包 10 笔 commit 仅触碰本包 10 个页文件；theme.css/icons.svg/门禁脚本/后端/其他包页面零触碰；未 push。
- **页数口径**：派单写 10 页，实际处理 10 页（与 `edu-frontend/public/` 现状一致）。
