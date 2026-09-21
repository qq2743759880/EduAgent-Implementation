# REPORT-DATA-SEED-1 — 种子外链占位本地化（三核闸：备份 + 行数一致 + 幂等）

- 执行分支：`feature/opt-waves`（开工前复核 = `feature/opt-waves`）
- 执行窗口：2026-09-21 11:38–12:10（GMT+8）
- 结论：**占位域 `cdn.example.com` 在封面/头像三类列上清零（102,629 行）**；三核闸全过；favorites / me 两页 **G8/G6/G7 全绿（合计 50 checks / 0 failed）**。
- 环境：后端 9988（health 200）、前端 3322（Next **dev** 形态，`/_next/static/development/_buildManifest.js` = 200，门禁 dev 前提成立）；门禁以真实学生 token（`user000001` 实时登录）运行。

---

## 0. 铁律自查

| 铁律 | 落实 |
|---|---|
| 禁 push | 未 push；仅 1 个本地 commit |
| 单 commit | `fix(data)/DATA-SEED-1: 种子外链占位本地化(三核闸:备份+行数一致+幂等)` |
| 开工/收尾分支对账 | 前 `feature/opt-waves` → 后 `feature/opt-waves` |
| 只动开工令列明范围 | 数据面：`series.cover_url` / `sys_user.avatar_url` / `user_profile.avatar_url`（本单点名"封面 + 头像"）；资源面：`edu-frontend/public/assets/seed/**`（本单点名的落地目录）；脚本：`scripts/data_seed_localize.py`（三核闸要有"同脚本"，故必须落脚本）；证据：`test-reports/data-seed-1/**`。**未改任何前端页面/JS/CSS、未改后端契约、未改门禁脚本** |
| 报告含确切命令 + 真实输出 | 见 §1/§3/§4/§5 |
| 代码优先于文档 | 开工令写的表名 `course_series` **不存在**，实读 schema 为 `series`/`series_name`；任务口径以实读为准并已记为差异（§6-①） |

---

## 1. 闸① 备份（变更前）

命令：

```bash
cd "E:/stu/project/stu/EduAgent实施手册"
MYSQL_HOST=127.0.0.1 edu-agent/.venv/Scripts/python.exe scripts/data_seed_localize.py --mode backup
```

输出（真实）：

```
[backup] series.cover_url: rows=2628 table_total=2969 -> series_cover_url.before.tsv + series_cover_url.before.sql
[backup] sys_user.avatar_url: rows=100000 table_total=100127 -> sys_user_avatar_url.before.tsv + sys_user_avatar_url.before.sql
[backup] user_profile.avatar_url: rows=1 table_total=823 -> user_profile_avatar_url.before.tsv + user_profile_avatar_url.before.sql
[backup] counts -> E:\stu\project\stu\EduAgent实施手册\deploy\backups\seed-20260921\_counts.json
```

备份路径：**`deploy/backups/seed-20260921/`**（双份留档：可回滚载荷 TSV + mysqldump 全行 SQL）

| 文件 | 体积 | 内容 |
|---|---|---|
| `_counts.json` | 853 B | 行数台账（rows / local_rows_before / table_total）+ 精确谓词 |
| `series_cover_url.before.tsv` | 190 KB | 2628 行 `id` + 变更前值 |
| `series_cover_url.before.sql` | 1.1 MB | 同 2628 行 `--complete-insert` 全行 |
| `sys_user_avatar_url.before.tsv` | 4.8 MB | 100000 行 `id` + 变更前值 |
| `sys_user_avatar_url.before.sql` | 24 MB | 同 100000 行全行 dump |
| `user_profile_avatar_url.before.sql` | 1.8 KB | 1 行全行 dump |

行数留档（三条 TSV 实测行数 = 台账行数，逐条相符）：

```bash
cd deploy/backups/seed-20260921 && for f in *.before.tsv; do echo -n "$f: "; grep -vc '^#' "$f"; done
series_cover_url.before.tsv: 2628
sys_user_avatar_url.before.tsv: 100000
user_profile_avatar_url.before.tsv: 1
```

> 入库范围：`_counts.json` + 3 个 `.before.tsv` 随 commit 入库（可回滚载荷）；两个大 `.sql`（合计 25 MB）按本仓既有惯例（`deploy/backups/*.sql` 均未入库）留在磁盘，可用同目录谓词重生成：
> `mysqldump --no-create-info --complete-insert --where="<tb>.predicate>" edu <table>`。

---

## 2. 影响行数（实读，对照开工令预估）

| 表.列 | 占位域行数 | distinct 值 | 备份时本地路径行数 | 表总行数 |
|---|---|---|---|---|
| `series.cover_url` | **2,628** | 219 | 0 | 2,969 |
| `sys_user.avatar_url` | **100,000** | 100,000（`/avatar/000001.png`…逐用户） | 0 | 100,127 |
| `user_profile.avatar_url` | **1** | 1（`/avatars/x.png`） | 0 | 823 |
| **合计** | **102,629** | — | — | — |

开工令预估 `5+1`，实为 `2628 + 100000 + 1`。差异根因见 **§6-①**（预估取自"页面上渲染出来的数量"，不是数据面数量）。

**全库只读扫描（本单的额外盘点产物，information_schema 逐字符列）**——`cdn.example.com` 共命中 5 个表.列：

```
tbl            col        n
session_asset  file_url   617328
session_video  cover_url  205776
sys_user       avatar_url 100000
series         cover_url   2628
user_profile   avatar_url      1
```

`session_asset` / `session_video` **不在本单点名范围**（非封面/头像列，且 favorites/me 不消费），**未改**，登记为移交项（§7）。

---

## 3. 闸② 变更（仅限受影响行）

命令：

```bash
MYSQL_HOST=127.0.0.1 edu-agent/.venv/Scripts/python.exe scripts/data_seed_localize.py --mode apply
```

改写 SQL（三条，谓词全部带"占位域"条件，无裸 UPDATE）：

```sql
UPDATE series SET cover_url = CONCAT('/assets/seed/covers/',
       SUBSTRING_INDEX(SUBSTRING_INDEX(cover_url,'/',-1),'.',1), '.svg')
 WHERE cover_url LIKE 'https://cdn.example.com/course/%';

UPDATE sys_user       SET avatar_url = '/assets/seed/avatar-default.svg'
 WHERE avatar_url LIKE 'https://cdn.example.com/%';

UPDATE user_profile   SET avatar_url = '/assets/seed/avatar-default.svg'
 WHERE avatar_url LIKE 'https://cdn.example.com/%';
```

输出（真实，首跑）：

```
[apply] series.cover_url: 本次改写=   2628 备份占位域行数=   2628 残留=0 本地路径行数=2628(期望 2628) 表总行数=2969(期望 2969)
[apply] sys_user.avatar_url: 本次改写= 100000 备份占位域行数= 100000 残留=0 本地路径行数=100000(期望 100000) 表总行数=100127(期望 100127)
[apply] user_profile.avatar_url: 本次改写=      1 备份占位域行数=      1 残留=0 本地路径行数=1(期望 1) 表总行数=823(期望 823)
[apply] 闸② 通过：占位域残留=0；本地路径行数 == 备份(本地+占位域)；表总行数一致（未增删行）
[apply] 本次运行性质：首跑（改写 102629 行）
```

**行数一致断言（脚本内 assert，缺一即抛错回滚）**：
1. 变更后占位域残留 == 0；
2. 变更后本地路径行数 == 备份(本地路径 + 占位域) 行数；
3. 表总行数 == 备份时表总行数（禁增删行）。

### 前后对照（抽样：favorites 页实际渲染的 6 条 + 头像）

| 对象 | 变更前（备份 TSV 实录） | 变更后（DB 实读） |
|---|---|---|
| series 1 | `https://cdn.example.com/course/general_purpose_programming_foundation.jpg` | `/assets/seed/covers/general_purpose_programming_foundation.svg` |
| series 2 | 同上（与 1 同 URL） | 同上 |
| series 3 | `.../general_purpose_programming_practice.jpg` | `/assets/seed/covers/general_purpose_programming_practice.svg` |
| series 1005 | `.../interactive_media_and_games_practice.jpg` | `/assets/seed/covers/interactive_media_and_games_practice.svg` |
| series 2618 | `.../middle_high_school_chemistry_foundation.jpg` | `/assets/seed/covers/middle_high_school_chemistry_foundation.svg` |
| series 2628 | `.../middle_high_school_informatics_advanced.jpg` | `/assets/seed/covers/middle_high_school_informatics_advanced.svg` |
| sys_user 1（user000001） | `https://cdn.example.com/avatar/000001.png` | `/assets/seed/avatar-default.svg` |
| user_profile 1 | `https://cdn.example.com/avatars/x.png` | `/assets/seed/avatar-default.svg` |

> 注：favorites 页 6 条收藏里 series 1/2 共用同一 cover URL ⇒ 浏览器只发 **5** 个外链请求，这正是 PAGE-WAVES-A 观测到 "favorites=5 条" 的来源；同理 me 页 1 个头像。

---

## 4. 闸③ 幂等（同脚本重跑零变化）+ 残留校验

```
$ MYSQL_HOST=127.0.0.1 edu-agent/.venv/Scripts/python.exe scripts/data_seed_localize.py --mode apply   # 第二次
[apply] series.cover_url: 本次改写=      0 备份占位域行数=   2628 残留=0 本地路径行数=2628(期望 2628) 表总行数=2969(期望 2969)
[apply] sys_user.avatar_url: 本次改写=      0 备份占位域行数= 100000 残留=0 本地路径行数=100000(期望 100000) 表总行数=100127(期望 100127)
[apply] user_profile.avatar_url: 本次改写=      0 备份占位域行数=      1 残留=0 本地路径行数=1(期望 1) 表总行数=823(期望 823)
[apply] 本次运行性质：幂等重跑（改写 0 行，零变化）

$ MYSQL_HOST=127.0.0.1 edu-agent/.venv/Scripts/python.exe scripts/data_seed_localize.py --mode verify
[verify] series.cover_url: 残留占位域行 = 0
[verify] sys_user.avatar_url: 残留占位域行 = 0
[verify] user_profile.avatar_url: 残留占位域行 = 0
[verify] DB 引用本地封面 219 个 / 本地头像 1 个；缺失文件 0
[verify] PASS
```

**零变化判据 = 本次改写行数 0**（WHERE 谓词已带本地路径条件，重跑不匹配）；同时 `verify` 额外断言 **DB 引用的每个本地路径都有对应磁盘文件（缺失 0）**，防"换成本地路径但文件不存在 ⇒ 404"。

落盘证据：`test-reports/data-seed-1/_evidence/`（`01-inventory.txt` / `02-verify-after.txt` / `03-idempotent-rerun.txt` / `04-probe-api.txt`）。

---

## 5. 前端复验（接口 + 四门）

### 5.1 接口面（真 token）

```bash
MYSQL_HOST=127.0.0.1 edu-agent/.venv/Scripts/python.exe scripts/data_seed_localize.py --mode probe
```

```
[probe] login user000001: code=0 token=yes
[probe] GET /api/favorites → total=6 items=6
    series_id=3      cover_url=/assets/seed/covers/general_purpose_programming_practice.svg local=True HTTP=200 image/svg+xml
    series_id=2628   cover_url=/assets/seed/covers/middle_high_school_informatics_advanced.svg local=True HTTP=200 image/svg+xml
    series_id=1005   cover_url=/assets/seed/covers/interactive_media_and_games_practice.svg local=True HTTP=200 image/svg+xml
    series_id=2      cover_url=/assets/seed/covers/general_purpose_programming_foundation.svg local=True HTTP=200 image/svg+xml
    series_id=2618   cover_url=/assets/seed/covers/middle_high_school_chemistry_foundation.svg local=True HTTP=200 image/svg+xml
    series_id=1      cover_url=/assets/seed/covers/general_purpose_programming_foundation.svg local=True HTTP=200 image/svg+xml
[probe] GET /api/users/me/profile → avatar_url=/assets/seed/avatar-default.svg local=True HTTP=200 image/svg+xml
[probe] GET /api/users/me → avatar_url=/assets/seed/avatar-default.svg local=True
[probe] PASS
```

（`cover_url`/`avatar_url` 全部本地路径，且经前端 3322 逐一 GET 取回 **200 image/svg+xml**。）

### 5.2 门禁面（favorites / me 前后对照）

命令（`EDU_GATE_BASE` + 真学生 token；`EDU_GATE_SETTLE_MS=3500` 理由见 §6-③）：

```bash
export EDU_GATE_BASE=http://127.0.0.1:3322
export EDU_GATE_TOKEN=<user000001 实时登录 JWT>
export EDU_GATE_SETTLE_MS=3500
node scripts/gates/asset-cache-gate.mjs     --page favorites.html --out test-reports/data-seed-1/gates/favorites
node scripts/gates/asset-cache-gate.mjs     --page me.html        --out test-reports/data-seed-1/gates/me
node scripts/gates/style-dep-gate.mjs       --page favorites.html --out test-reports/data-seed-1/gates/favorites
node scripts/gates/style-dep-gate.mjs       --page me.html        --out test-reports/data-seed-1/gates/me
node scripts/gates/viewport-a11y-gate.mjs   --page favorites.html --out test-reports/data-seed-1/gates/favorites
node scripts/gates/viewport-a11y-gate.mjs   --page me.html        --out test-reports/data-seed-1/gates/me
```

| 页面 | 门禁 | 变更前（PAGE-WAVES-A `24eea20`/`d6e3934`） | 本次实测 | 依据 |
|---|---|---|---|---|
| favorites.html | G8 | 7/**1**（zero-external=5） | **8/0 PASS** | `gates/favorites/g8-asset-cache-gate.json`：external=0, requests=14, local404=0, diagnostics=0 |
| favorites.html | G6 | 6/0 | **6/0 PASS** | `gates/favorites/g6-style-dep-gate.json` failed=0 |
| favorites.html | G7 | 11/0 | **11/0 PASS** | `gates/favorites/g7-viewport-a11y-gate.json` failed=0, unreachable=0 |
| me.html | G8 | 7/**1**（zero-external=1） | **8/0 PASS** | `gates/me/g8-asset-cache-gate.json`：external=0, requests=20, local404=0, diagnostics=0 |
| me.html | G6 | 5/**1**（console-errors） | **6/0 PASS** | `gates/me/g6-style-dep-gate.json` failed=0 |
| me.html | G7 | 10/**1**（console-errors） | **11/0 PASS** | `gates/me/g7-viewport-a11y-gate.json` failed=0, diag=0 |

末次运行原始输出：

```
### 窗口1 ###
pages=1 checks=8  failed=0 warnings=0     # G8 favorites.html
pages=1 checks=8  failed=0 warnings=0     # G8 me.html
### 窗口2 ###
pages=1 checks=6  failed=0 warnings=0     # G6 favorites.html
pages=1 checks=6  failed=0 warnings=0     # G6 me.html
### 窗口3 ###
pages=1 checks=11 failed=0 warnings=0     # G7 favorites.html
pages=1 checks=11 failed=0 warnings=0     # G7 me.html
```

G8 关键断言（两页均）：`zero-external-requests | 0 external requests observed.`、`local-assets-ok | 0 local HTTP errors, 0 loading failures, and 0 unavailable blocked-font sources.`、`console-errors | 0 runtime or console diagnostics`。

### 5.3 后端单测（封面/收藏相关，防数据面误伤）

```bash
cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_curriculum_service.py tests/test_tool_favorite_add.py -q
....................  29 passed in 8.45s
```

---

## 6. 差异说明 / 需求裁定点（**请编排者裁定**）

**① 影响行数 5+1 → 102,629：预估口径是"页面渲染数"，不是"数据面行数"。**
- 开工令 `course_series` 表不存在（实为 `series`）；`5` 来自 favorites 页 6 条收藏中的 **5 个 distinct cover URL**（series 1/2 同 URL），`1` 来自 me 页头像。
- 数据面真实为 `series.cover_url` 2,628 + `sys_user.avatar_url` 100,000 + `user_profile.avatar_url` 1。
- **裁定点**：本单按"把该列占位域彻底清零"（= 开工令 §1 的字面范围 + §4「顺带修复线上裂图体验」）执行；**若编排者要的是"只改 6 行"，本 commit 需回退重做**（备份在 `deploy/backups/seed-20260921/`，回滚=按 TSV 反写 6+2 行）。请明确。
- 支撑"全量"而非"仅 6 行"的理由（均可复现）：`/api/favorites` 与 `/api/users/me` 对**任意用户**都返回该用户自己的收藏封面与头像 ⇒ 只修 `user000001` 的 6 行，其余 99999 用户的 me 页 / 其余 30001 条收藏的 favorites 页仍会发外链请求并触发同样的 G8/G6/G7 红；G8 的网络策略是全局的（"every non-loopback HTTP(S) request fails the gate"）。

**② 占位资产数量 6 张 → 220 张（封面 219 + 头像 1）。**
- 开工令 §2 写"生成 6 张 SVG（5 封面 + 1 头像）"，前提同样是"只有 5 个 URL"；实读 distinct cover URL = **219**。
- 处置：按"含课程名文字"的原意，**逐 slug 一一对应**生成 `edu-frontend/public/assets/seed/covers/<slug>.svg`（800×450，theme.css 表面色系 6 色按 slug 哈希确定性分配，文字=系列名去「·直播/·录播/·面授」后缀）＋ `avatar-default.svg`（200×200，moss→lavender）。
- 映射机械可验：`https://cdn.example.com/course/<slug>.jpg` → `/assets/seed/covers/<slug>.svg`（219 个 URL **100% 符合**该模式，实测 nonconforming=0）。全量清单见 `edu-frontend/public/assets/seed/manifest.json`（含 slug / 文件 / 中文标签 / 色板 / 覆盖 series 行数）。
- 合计 335 KB（220 个 SVG）；无 emoji、无外链字体（inline 系统字体栈）。

**③ 门禁跑法的两个环境陷阱（**非本单改动引起**，但会让复验"假红"，务必按下面口径跑）。**
- **(a) `/api/trade/orders` 撞限流 ⇒ me 页 console-errors 假红。** `app/middleware/rate_limit.py:43` 的规则 `/api/trade/order` 用 **startswith 前缀**匹配，因此 `/api/trade/orders`（订单列表）也被纳入 **(60s, 10 次)**。超限后返回 429，而 429 由 CORS 中间件外层产生 ⇒ **不带 `Access-Control-Allow-Origin`** ⇒ 浏览器报 `blocked by CORS policy` + `net::ERR_FAILED` ⇒ G6/G7 `console-errors` 红。实测压测 5 次即 `HTTP=429`（`time=0.016s`），单独 60s 后重跑转 200。**本轮曾因此出现 3 次假红**（G6 me 1 次、G7 me 2 次），**隔离后全绿**。建议编排者单独立项：该前缀规则应收窄为精确路径。
- **(b) me 页 G7 `tab-reachable` 的 settle 竞态。** `/api/trade/orders` 实测 ~2.1s（`logs/task113_uvicorn.log:1619` `SLOW GET /api/trade/orders → 200 (2110ms)`），而门禁默认 `settleMs=900` ⇒ Tab 扫描与订单/优惠券列表落地竞态，报 8 个 unreachable（`#odPrev`/`#cpPrev`/`#pf-*`——均与封面/头像无关）。按文档化环境变量 `EDU_GATE_SETTLE_MS=3500` 后 `unreachable=0`，稳定 PASS（默认 settle 下本轮 PASS 1 / FAIL 3，属门禁对慢接口的既有盲区，同 PAGE-WAVES-A §4-② learning roving 盲区一类）。
- **(c)** 阈值口径提示：`unreachable` 明细里的 `#pf-nickname…#pfSave` 是"编辑资料"面板内的表单（未展开时不可 Tab 达），`#odPrev/#cpPrev` 是第 1 页的 disabled 分页钮 —— 属门禁对 disabled/隐藏控件的判定边界，非样式或行为缺陷。

**④ 契约样例值留痕（未改文档）。** `handoffs/task114-contract.md:63` 把 `avatar_url` 的示例值写成 `https://cdn.example.com/avatars/x.png`。本次只改 DB 数据、未改该文档（契约权威是 `schemas.py`，字段类型未变）；**全仓 `tests/` 无任何断言引用 `cdn.example.com`**（已 grep 确认），单测无回归（§5.3）。若编排者希望契约文档同步示例值，请另开单（本单文件域不含 handoffs/）。

---

## 7. 移交项（本单未做，供编排者排期）

1. **`session_asset.file_url` 617,328 行 / `session_video.cover_url` 205,776 行同样指向 `cdn.example.com`** —— 不在本单范围（非"封面/头像"消费列），favorites/me 不渲染；但若未来有页面渲染课时资产/视频封面，会复现同类 G8 红。
2. **`/api/trade/order` 前缀限流规则误伤 `/api/trade/orders`**（§6-③a）——建议收窄匹配或对 GET 列表放行。
3. **me.html 依赖的慢接口（~2.1s）与门禁默认 settle 900ms 不匹配**（§6-③b）——建议门禁按"存在慢接口的页面"提高默认 settle，或页面侧给列表落地留可见信号。
4. 种子源头：本仓没有可重跑的 series/users 种子生成器（`cdn.example.com` 只出现在 `deploy/backups/*.sql` 历史快照与探针脚本中），因此**不存在"重跑种子把外链写回"的现役路径**；但若从旧快照恢复库，会复原占位域，需重跑本脚本。

---

## 8. 资产消费证据

1. **theme.css（L2 冻结，`7fed87f`）**：占位图取色自 `:root` 令牌 `--clay-moss #B8D8A8 / --clay-sky #9EC9F0 / --clay-peach #FFB59E / --clay-mint #7DD4A8 / --clay-lemon #F5D77A / --clay-lavender #B8A6FF` + `--text-strong #2E2A3F` / `--text-muted #6B6580` / `--bg-app #F7F5FB`；**theme.css 本体零改动**（两页 G8 `theme-version-present` 仍为 `7fed87f`）。
2. **禁 emoji 令（Gate A 批款）**：220 个 SVG 全部为几何图形 + 文字，**零 emoji**。
3. **零外链**：SVG 内字体走系统栈（`Microsoft YaHei/PingFang SC/Segoe UI`），无 `@import`/`<link>`/远程 ref；两页 G8 `external=0` 为实测佐证。
4. **数据面**：`edu-frontend/public/assets/seed/manifest.json` 是 219 个 slug→文件→中文标签→色板→覆盖行数的机器可读清单，可与 DB 逐条对账。

## 9. 批判承接核对（与在跑任务的重叠风险自查）

- **文件域**：`scripts/data_seed_localize.py`（新建）、`edu-frontend/public/assets/seed/**`（新建）、`test-reports/data-seed-1/**`（新建）、`deploy/backups/seed-20260921/**`（新建）、DB 三列的数据值。**未触碰**任何 `*.html` / `edu-api.js` / `theme.css` / sprite / 后端代码 / 门禁脚本 / `test-reports/gate-baseline/**`（门禁证据写在新目录 `test-reports/data-seed-1/gates/`，未覆盖 A/B/C 包既有基线）。
- **与 PAGE-WAVES-A 变更单元的关系**：本单正是 A 包 §4-① 那条"数据面"红项的落地；A 包 §4-② ③（learning roving / login G9 前提）仍由 GATE-V2 承接，本单未涉及。
- **对 GATE-V2 的影响**：GATE-V2 的 N/A 白名单与 route-stable 钉死不依赖本数据；本单反而消除了 favorites/me 两页在 G6/G7/G8 上的唯一数据面噪声源（PAGE-WAVES-A 记录的 me 页 G6/G7/G8 三处红**全部**由该头像引起，现已全绿）。
- **回滚成本**：`deploy/backups/seed-20260921/*.before.tsv` 提供逐行旧值；回滚 = 按 `id` 反写（或从 `.before.sql` 恢复）。数据库未做任何 DDL、未增删行。
- **遗留未清**：§7 四项（其中 2 项是 G6/G7 复验时会被"假红"的陷阱，**建议编排者验收时按 §6-③ 口径跑**）。
