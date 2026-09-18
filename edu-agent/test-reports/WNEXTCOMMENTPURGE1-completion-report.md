# W-NEXT-COMMENT-PURGE-001 完工报告

> 任务 ID：W-NEXT-COMMENT-PURGE-001（public/*.html 注释层测试账号/敏感快照残留整块清除）
> 执行 agent：W-NEXT-COMMENT-PURGE-001（yy 串行流水线单 agent，无并行派生）
> 派单：C-01 orchestrator（逐断言独立实证验收）
> 完工日期：2026-09-19
> 本批 commit：**`42a229d`**（fix(fe-html)/W-NEXT-COMMENT-PURGE-001，仅 6 个 public/*.html，+0/-177）
> lock：`edu-agent/scripts/eval/wnextcommentpurge1.lock` 已于 commit 前删除（rm + ls 复核 No such file）
> 用户裁定依据：2026-09-19「公开页注释层测试账号残留删除——FE-SPEC-CLEAN 披露的注释层命中全部清除」

---

## 一、承接说明（批判承接核对）

| 来源 | 承接项 | 本批处置 |
| --- | --- | --- |
| FE-SPEC-CLEAN 报告 §七 P0-① | 注释层测试账号残留（adm02test/mgr01test/user000001 位于顶部契约注释，curl 可见），建议「生产出包流水线加注释剥离」 | **用户裁定改为源级删除**（2026-09-19）：整块移除含敏感快照的注释段；流水线剥离仍可作纵深防御（见 P0-②） |
| `.opencode/plans/critique-backlog-tracker.md:608` | 「注释层残留处置=用户裁定删除（待派）」 | **本批即该待派项的执行**，至此闭环（tracker 更新属编排者权限，本 agent 未越权改 tracker） |

其余承接核对：grep `.ai-hub/plans/critique-tracker-v1.md` + `.opencode/plans/critique-backlog-tracker.md` 中 `COMMENT-PURGE/注释层/测试账号残留`，除上表 608 行外 **0 命中**，无其他未闭环承接项。本批新增自批判 5 条见 §七。

## 二、盘点清单（任务 #1：grep 6 pattern 注释层命中，分类）

盘点模式：`adm02test|mgr01test|user000001|Test@123456|100,034|2026-09-12 curl 实测`，对全部 25 个 `edu-frontend/public/*.html` 全文 grep（含注释层）。**实证命中 9 行 / 6 页**，另抓到 1 处无逗号变体 `total=100034`（refine-proto:27）。逐条分类：

| # | 位置 | 命中物 | 分类 | 处置 |
| --- | --- | --- | --- | --- |
| 1 | admin-users-refine-proto.html:12 | `2026-09-12 curl 实测 manager(mgr01test)` + 403 载荷原文 | ① 敏感快照注释块（顶部 `<!-- B3-proto…AUDIT LOG: DRAFT -->` L7-36） | 整块删除 |
| 2 | admin-users-refine-proto.html:26-27 | `adm02test/Test@123456` + `total=100034`（无逗号变体） | ① 同上块内 | 同上 |
| 3 | achievements.html:12 | `实测 user000001：total_points=314, logs_total=15`（真实账号+真实数据） | ① 敏感快照注释块（顶部契约注释 L2-19，含 `2026-09-06 curl 实测校准`） | 整块删除 |
| 4 | admin-courses.html:12 | `contract-change-reshape-a2.md #2（2026-09-12 curl 实测）` | ① 敏感快照注释块（顶部块 L7-37，另含真实总量 2629/2685/56） | 整块删除 |
| 5 | admin-courses-recycle-proto.html:12 | `2026-09-12 curl 实测，adm02test/Test@123456，后端 127.0.0.1:8000` | ① 敏感快照注释块（顶部依赖端点快照块 L7-53，含 total 2629/2685/56、404/409 载荷原文） | 整块删除 |
| 6 | admin-courses-recycle-proto.html:43-44 | `2026-09-12 curl 实测 GET /series…原样快照（total=56）` | ① 同上块内 | 同上 |
| 7 | admin-courses-recycle-proto.html:422-424 | JS 注释 `/* 回收站 6 行 = 2026-09-12 curl 实测原样快照：…（total=56…）*/` | ① JS 层敏感快照注释块 | 整块删除（3 行） |
| 8 | favorites.html:10 | `接口契约（curl 实测 2026-09-05，user000001）` | ① 敏感快照注释块（顶部契约注释 L7-18） | 整块删除 |
| 9 | coupons.html:10 | `接口契约（curl 实测 2026-09-05/06，user000001）` | ① 敏感快照注释块（顶部契约注释 L7-42，另含真实订单号 6-260906172441-86dcaa、真实券 id 51001、真实金额 1999-100=1899） | 整块删除 |

**② 保留类（纯代码标识符注释，0 命中 6 pattern，未碰）**：`community.html:427 boards.dataset.task118Bound="1"`、`loadFavState(); /* task04 */` 行尾注释、`admin-courses-recycle-proto.html:421 /* task13 静态原型数据 */` 头注释、各页 taskNN toast/模块注释等（即 FE-SPEC-CLEAN 披露的 code-ident/tail=21 类）。
**③ 功能代码（禁碰，0 改动）**：`const BIN_META={total:56,...,captured:"2026-09-12"}`、`const BIN=[...]` 样例行、全部 fetch/EAPI 调用——注意 `BIN_META.captured="2026-09-12"` 含快照日期，因属 ③ 禁碰（见 P0-④）。
**变体复扫**：`100034`（无逗号）、`100003|100004|100038|100039`（真实 UID）、`Test@123456` 大小写不敏感、裸 `123456`（排除 Test@123456 后）——删除后全部 0 命中；真实 UID 在 FE-SPEC-CLEAN 批已合成化，本批复扫确认 0。

## 三、删除清单（任务 #2）

整块删除含敏感快照的注释段（顶部审核稿快照注释整体移除；契约权威=schemas.py+contracts/*.json，页内快照已过时无保留价值）：

| 文件 | 删除块 | 原行区间 | 行数 |
| --- | --- | --- | --- |
| admin-users-refine-proto.html | 顶部 `<!-- B3-proto · admin-users Refine 版…AUDIT LOG: DRAFT -->` 整块（含权限口径 curl 快照/示例行快照/C15 判据） | L7-36 | 30 |
| achievements.html | 顶部 `<!-- STYLE…契约⑬ curl 实测…AUDIT LOG -->` 整块（含 user000001 实测数据行） | L2-19 | 18 |
| admin-courses.html | 顶部 `<!-- task56 原型…reshape-a2 #2 curl 实测…AUDIT LOG -->` 整块（含真实总量 2629/2685/56） | L7-37 | 31 |
| admin-courses-recycle-proto.html | 顶部 `<!-- task13 原型…依赖端点 curl 实测…AUDIT LOG: APPROVED -->` 整块 + JS `/* 回收站 6 行 curl 实测原样快照 */` | L7-53 + L422-424 | 47+3 |
| favorites.html | 顶部 `<!-- 接口契约 curl 实测 2026-09-05 user000001 -->` 整块 | L7-18 | 12 |
| coupons.html | 顶部 `<!-- 接口契约 curl 实测 2026-09-05/06 user000001（券/下单/订单全量快照） -->` 整块 | L7-42 | 36 |

**合计：6 文件，-177 行，+0 行（git numstat 实证纯删除）。**

红线遵守实证：
- `git diff --numstat`：6 文件全部 `0 insertions`——可见文本/S0-S8 结构/JS 逻辑零改动（改动只可能是注释整块消失）。
- `git diff -U0 | grep "^+[^+]"`：0 命中（无任何新增行）。
- refine-proto Gate A 审核稿**页面结构未动**：仅删顶部注释块，标注条/场景卡/token 表原样（check-demo ⑨ PASS 佐证页面 200）。
- 未新增/删除任何 `<script>` 标签；edu-api.js 注入模式未动。
- 0 改动于 src/**、app/**、contracts/**、scripts/**（lock 文件按授权创建并于 commit 前删除）。

## 四、终态机验（任务 #3，机扫输出原文）

```
=== 任务书指定 4 pattern（adm02test|mgr01test|Test@123456|100,034）===
$ grep -rn "adm02test\|mgr01test\|Test@123456\|100,034" edu-frontend/public/*.html
（无输出）exit=1  → 0 命中

=== 6 pattern + 变体（+user000001 +2026-09-12 curl 实测 +100034）===
$ grep -rnE "adm02test|mgr01test|user000001|Test@123456|100,034|2026-09-12 curl 实测|100034" *.html
（无输出）exit=1  → 0 命中

=== 大小写不敏感密码 ===
$ grep -rniE "test@123456" *.html → exit=1（0 命中）
=== 裸 123456（排除 Test@123456）→ 0 命中；真实 UID 100003/100004/100038/100039 → 0 命中 ===
```

**curl 证据（3000 生产形态直出，2026-09-19 02:0x）**：

```
achievements.html              -> 200
admin-courses.html             -> 200
admin-courses-recycle-proto.html -> 200
admin-users-refine-proto.html  -> 200
coupons.html                   -> 200
favorites.html                 -> 200
服务面防缓存假象（curl 直出内容 grep 敏感 6 pattern+变体）：6 页 sensitive-hits 全部 =0
```

**内联 JS 语法（抽 3 页，含唯一 script 层改动页 recycle-proto）**：

```
admin-courses-recycle-proto.html blocks=2 fails=0
admin-courses.html              blocks=4 fails=0
achievements.html               blocks=3 fails=0
TOTAL FAILS: 0
```

（其余 3 页 favorites/coupons/refine-proto 仅删 `<head>` 区注释未触 script，refine-proto 本身零 script 标签，按任务书豁免。）

## 五、回归（任务 #4：check-demo）

`node scripts/check-demo.mjs`（2026-09-19 02:08，耗时 164.8s）：

- **⑤ PASS**：前端 3000 /login-register.html + 生产 build 形态判别（`_buildManifest` dev 探针 404 = 生产形态直出）
- **⑦ PASS**：8 核心页 200（8/8）
- **⑨ PASS**：/admin-users-refine-proto.html 200（C5-D2 扩清单）

**三守卫全绿。** 全单其余：绿 16/21；红 ⑪⑲（VEC-LOCK embed 一致性/守门，向量域预存问题，本批红线禁碰 app/scripts，与本批纯注释删除无关——本批 diff 0 插入不可能影响向量域；FE-SPEC-CLEAN 批当时红 ⑯，本轮 ⑯ 已转绿、⑪⑲ 转红，属环境漂移非本批引入）；WARN ⑧（DEBUG 后门提示，预存）/⑩（契约对账，预存）/㉒（MinIO 历史审计，预存）。febe 契约面：未动任何契约（仅删注释），⑱ febe root path PASS、unfrozen_only=0 佐证不受影响。

## 六、commit 纪律

- commit 前 `git symbolic-ref HEAD`（feature/opt-waves）+ `git rev-parse HEAD`（tip=2c192e2 未前移）先查后提。
- 暂存精确 add 6 文件，`git diff --cached --name-only | wc -l`=6 复核后提交；预存脏文件（dualrun-baseline.md、next-env.d.ts 等）未混入。
- 本批 commit `42a229d`；报告随单独 commit 入库（见文首）。

## 七、P0 自批判（5 条）

1. **「curl 实测」注释残留未清零（口径边界遗留）**：本批按授权只清 6 pattern 命中块；复扫发现 `curl 实测` 字样仍存于其余 12+ 页注释层（admin-dashboard×3、admin-questions×3、community×3、admin-question-detail×2、chat×2、admin-users×2、course-detail×2、login-register×2、dashboard×2、me/learning/courses×1 等），这些块不含测试账号故不在授权内，但其中可能仍有真实总量/记录 id 类半敏感数据**未经逐条审计**。「页内快照过时无保留价值」的裁定逻辑若贯彻到底，这些块同样应清——建议后续单全量清剿或提高清剿授权，本 agent 未越权。
2. **机扫是模式有界的，语义变体未穷举**：终态 0 命中仅对 6 pattern+已枚举变体（100034/UID/大小写密码/裸 123456）成立；`adm02 test`（加空格）、全角变体、base64/拼接形态等未枚举。机验可证伪的断言范围=模式表范围，非「无任何账号痕迹」的全称断言。纵深防御建议：出包流水线 html-minify 注释剥离（FE-SPEC-CLEAN P0-① 原建议，仍有效）。
3. **整块删除连带移除了非敏感审计线索**：STYLE frozen 用户签收记录、AUDIT LOG（Gate A APPROVED 签收史、DRAFT 流转）随块消失，页内不可追溯，仅存 git 历史（c44768a 之前可考）。若有角色依赖页内 AUDIT LOG 而非 git log 追溯审批链，会断链——裁定已明示「无保留价值」，风险接受，但登记为不可逆删除。
4. **BIN_META/BIN 功能代码即快照本体（③禁碰的两难）**：`const BIN_META={total:56,...,captured:"2026-09-12"}` 与 6 行 BIN 样例正是被删注释所称「2026-09-12 curl 实测原样快照」的数据本体（view-source 可见 rst17886… 系列码与实测时间戳）。FE-SPEC-CLEAN 已将其声明为「示例数据」并合成化账号/姓名，且本批授权禁碰功能代码，故保留；但严格读「敏感快照全部清除」者可主张 JS 数据亦属快照残留——属结构性决策（需改页面数据非注释），授权外，留给承接方裁定。
5. **check-demo ⑪⑲ 红未处置**：向量域预存问题，红线禁碰 app/scripts，只能登记；若 C-01 要求全绿回归需另派后端单。另注：check-demo ⑥ 工具本身消费测试账号（adm02test/user000001 真实登录探针），属合法测试基建，不在公开页清污范围。

## 八、资产消费证据

| 资产 | 消费方式 |
| --- | --- |
| 用户裁定（2026-09-19，任务书） | 删除口径与范围（6 pattern 盘点/整块删除/终态 0 命中判据）的直接依据 |
| `test-reports/WNEXTFESPECCLEAN1-completion-report.md` | 前例口径：comment=80/code-ident=21 分类、curl 防缓存假象验法、P0-① 即本批承接项、commit 纪律范式 |
| AGENTS.md | 教训 2（禁 Playwright→curl/node --check 独立实证）、测试账号清单（盘点模式来源）、启动与验收纪律 |
| `edu-agent/scripts/check-demo.mjs` | ⑤⑦⑨ 守卫实跑（非推断） |
| `git show c44768a`/`e0c8de4` | 前批改动范围对账（可见文本已清、注释层即本批范围）、commit message 范式 |
| `.opencode/plans/critique-backlog-tracker.md` + `.ai-hub/plans/critique-tracker-v1.md` | 承接核对（608 行待派项=本批；其余 0 命中） |
| lock `wnextcommentpurge1.lock` | 独占执行标识，commit 前 rm+ls 复核删除 |
| 红线遵守 | commit `42a229d` 经 `git diff --cached --name-only` 复核仅 6 个 public/*.html；0 改动 src/app/contracts/scripts |
