# W-NEXT-5 完成报告（⑧分支C假绿 + F8 角色门 + 记忆截断 salvage，三条 P1）

> 执行者：W-NEXT-5 单写者（锁 `edu-agent/scripts/eval/wnext5.lock`，完工已删）
> 分支：`feature/opt-waves`；日期 2026-09-16；批判源：`test-reports/critique-blind-t4-t9.md`（T5-C1 / T5-C2 / T5-C6⑧ / T7-C1 / T9-C1）
> 环境：后端 8000 本机不可达（未重启，遵守红线）；验证用 8010 临时实例（DEBUG=true 本机形态）+ 8011 临时实例（DEBUG=false 生产形态）；前端 3000 = next dev 运行中。

## 0. 改动清单（文件归属内）

| 文件 | 改动 | 对应批判 |
|---|---|---|
| `edu-agent/scripts/check-demo.mjs` | ⑧ 分支 C 真红 + ENV_NAME 安全缺省（=`null`）+ 分支 A 动态文案 + ⑤ 前端形态判别 + WARN 判定支持结果级 `e.__warn` | T5-C1 / T5-C2 / T5-C6⑧ |
| `edu-agent/app/domains/question_admin/router.py` | `delete_bank` 注入 `me: CurrentUser`，`force=true` 且 role≠ADMIN → `PermissionDeniedError`(40300) | T7-C1 |
| `edu-agent/app/ai/memory/extract_llm.py` | 新增 `_salvage_json_array` 截断尾部容错，整批解析失败时逐条 salvage 已闭合元素 | T9-C1 |
| `edu-agent/tests/test_f8_bank_guard.py` | +3 路由层角色门测试（离线，直接调端点协程） | T7-C1 |
| `edu-agent/tests/test_contract_task_r01.py` | +4 测试（salvage 纯函数边界 / 截断候选 / 队列落库不 degraded / 无完整元素仍 degraded） | T9-C1 |

---

## 1. 任务一： 分支 C 假绿修复 + 生产形态判别（T5-C1 + T5-C2 + T5-C6⑧）

### 1.1 修法落地
1. `readDevEnv()`：`ENV_NAME` 缺省/空值由 `"local"` 改为 `null`（**安全缺省=非 local**）；`DEBUG` 缺省仍 `null`。
2. `⑧` 三分支判定改为：
   - A：无 token `/api/users/me` 被 401/403 → PASS；**文案动态**（`DEBUG=true` 时打「.env 后门开关仍开启，按分支 B/C 语义判定」，不再打「DEBUG 安全」）。
   - B：200 + `DEBUG==='true'` + **`ENV_NAME==='local'`（确证读到）** → WARN（`e.__warn=true`，不阻断 exit 0）。
   - C：200 且（`DEBUG≠true` 或 `ENV_NAME` 缺省/≠local）→ **FAIL 阻断 exit 1**。
3. `check()` 的 WARN 判定改为 `!(ok) && (fn.__warn || r.err?.__warn)`，并**移除 ⑧ 的静态 `__warn:true`**——否则分支 C 会被静态软化继续假绿（这是 T5-C1 的假绿根因）。
4. `⑤` 并入「前端形态判别」：`GET /_next/static/development/_buildManifest.js` 200 → `e.__warn=true`（dev 开发形态，生产 build 未验收）；404 → PASS「生产 build 形态」。

### 1.2 GWT 实测（逐项数字）

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 合成 .env（DEBUG=true，无 ENV_NAME 行）→ ⑧ 红 exit 1 |  `[FAIL] 无 token 返回 HTTP 200 有数据(DEBUG=true,ENV_NAME=缺省(≠local))`；`汇总: 绿 7/9,红项 ⑧`；`EXIT=1` | ✅ |
| ② | （DEBUG=true，ENV_NAME=local）→ WARN exit 0 | ⑧ `[WARN] WARN 开发态虚拟管理员后门存在(DEBUG=true,ENV_NAME=local)`；`汇总: 绿 9/9,WARN ⑤、⑧ —— 演示环境就绪`；`EXIT=0` | ✅ |
| ③ | 本机回归 WARN 9/9 exit 0 | 与 ② 同跑：9/9 绿（WARN ⑤、⑧）exit 0；**但本机 `.env` 原态（DEBUG=true、无 ENV_NAME）实跑为红**（= ① 同态） | ⚠ 见 §4.1 |
| ④ | dev 形态前端 → 形态项 WARN | 探针实测 `_buildManifest.js → 200`；⑤ `[WARN] 前端为 next dev 开发形态(_buildManifest dev 探针 200),非生产 build,生产形态未验收`（4 次运行均复现） | ✅ |
| ⑤ | DEBUG=true 时分支 A 不打「安全」 | 8011（`DEBUG=false` 真实例，无 token → HTTP 401）跑：⑧ `[PASS] 无 token 被 401 拒绝(DEBUG=true:.env 后门开关仍开启,按分支 B/C 语义判定)`；整份输出 `CONTAINS_ANQUAN=False` | ✅ |

实测命令（可复跑）：
```powershell
$env:CHECK_DEMO_BACKEND="http://127.0.0.1:8010"; node scripts/check-demo.mjs --no-color   # 分支 C（本机 .env 原态）
# 分支 B：cp .env .env.bak → Add-Content .env "ENV_NAME=local" → 跑 → 还原 .env（已校验 SHA256 前后一致）
$env:CHECK_DEMO_BACKEND="http://127.0.0.1:8011"; node scripts/check-demo.mjs --no-color   # 分支 A（生产形态 401）
node scripts/check-demo.mjs --fail-drill --no-color                                       # drill 回归：红项 ①、②、③
```

回归：`--fail-drill` 仍 `红项 ①、②、③`（语义不变）；合成 .env 跑完已还原，`.env` SHA256 前后一致（`C39A51CA…C961`）。

---

## 2. 任务二：F8 force 仅 ADMIN 角色门对齐 F9（T7-C1）

### 2.1 修法落地
`question_admin/router.py::delete_bank` 补注入 `me: CurrentUser = Depends(get_current_user)`，`force and me.role != UserRole.ADMIN → PermissionDeniedError("强制级联删除仅 ADMIN 可执行")`（HTTP 403 / code `40300`）；`force=False` 行为不变；service 层未改（角色门在路由层，对齐 `course_admin` F9 风格）。summary/参数说明同步改为「force 仅 ADMIN」。

### 2.2 GWT 实测（8010 真 HTTP，真实 MySQL，实测摘录）

| # | GWT | 实测（HTTP / code / data） | 结论 |
|---|---|---|---|
| ① | MANAGER × delete_bank(force=true) → 403 | bank 465（非空，1 题）→ `HTTP 403 code=40300 msg=强制级联删除仅 ADMIN 可执行`；复验 `questions total=1`（库与题**零改动**） | ✅ |
| ② | ADMIN × delete_bank(force=true) 非空 → 级联软删 | `HTTP 200 code=0 data={'deleted':True,'id':465,'forced':True,'questions_removed':1}`；复验 `questions total=0` | ✅ |
| ③ | MANAGER/ADMIN × delete_bank(force=false) 空库 → 正常删 | 空库 466：MANAGER `HTTP 200 forced=False questions_removed=0`；空库 467：MANAGER `force=true → 403`（角色门先于业务）后 ADMIN `force=false → 200` | ✅ |
| ④ | 既有 F8 测试（40924 保护）不破坏 | 真 HTTP：MANAGER 非空库 `force=false → HTTP 409 code=40924 msg=题库内仍有 1 道有效题目，无法删除…`；离线 `tests/test_f8_bank_guard.py` 4 项原测全绿 | ✅ |

数据影响声明：仅对本次新建的一次性库操作（id 465 经 ADMIN force 级联软删；466/467 空库软删），**无既有数据被触碰**。

---

## 3. 任务三：记忆抽取截断容忍 salvage（T9-C1）

### 3.1 修法落地
`extract_llm.py` 新增 `_salvage_json_array(text)`：从首个 `[` 起做**括号 + 字符串状态**扫描，逐个收集**已闭合**的顶层 `{...}` 元素并单独 `json.loads`；未闭合尾部元素丢弃；字符串内的 `}{` 与 `\"` 不参与计数。
`extract_candidates_llm` 解析流程改为：整批 `_extract_json_array` 失败 → 合法空数组判定 → **salvage** → salvage 出 ≥1 条则按候选入库（`error=None`，日志标 `partial=true`）→ 连一条都取不出才 `llm_unparseable_output` 落 degraded。公共返回值签名未改（`queue.py` 非本批领地）。

### 3.2 GWT 实测（逐项数字）

| # | GWT | 实测 | 结论 |
|---|---|---|---|
| ① | 截断输出（前 2 条合法 + 第 3 条截断）→ 前 2 条入库不落 degraded | 实测：`整段解析 _extract_json_array = []`（修复前整批判 degraded）；`salvage 回收 = ['用户目标是雅思 6.5','用户零基础']`；`error = None`；`入库候选 = [('用户目标是雅思 6.5','goal','learning-goals',5), ('用户零基础','profile','profile',4)]`；日志 `已 salvage 2 条完整合法元素入库(partial=true)`；队列级测试 `degraded == 0` 且候选落库成功 | ✅ |
| ② | 完全不可解析 → 仍 degraded | 纯函数 `_salvage_json_array("抱歉，@@@无法解析的散文，没有数组") == []`、`_salvage_json_array('[{"content": "截') == []`；队列级 `test_no_complete_element_still_degraded`：`degraded == 1` 且 `reason.startswith("llm_unparseable_output")`；既有 `garbled` 参数化用例仍 degraded | ✅ |
| ③ | 既有 R01 测试（13 项）不破坏 | `pytest tests/test_contract_task_r01.py` → **17 passed**（13 原有 + 4 新增）；`pytest tests/test_f8_bank_guard.py` → **7 passed**（4 原有 + 3 新增）；两文件合计 **24 passed in 2.55s** | ✅ |

---

## 4. 偏差与待裁定（诚实登记）

1. **GWT③「本机回归 WARN 9/9 exit 0」与 ① 互斥**：本机 `edu-agent/.env` 现状 = `DEBUG=true` + **无 `ENV_NAME` 行**，按 T5-C1 要求的「安全缺省=非 local」必然判 **红**（实跑 `红项 ⑧，EXIT=1`）。③ 只能在 `.env` 显式写 `ENV_NAME=local` 时成立（已按合成态实测 9/9 绿 exit 0）。`.env` 不在本批文件归属内，**未改**；若编排者要求本机常绿，需在 `.env` 补 `ENV_NAME=local`（或接受本机 ⑧ 常红作为「未声明环境」的告警）。
2. **口径有意分歧需知悉**：后端启动门 `config.py::_debug_env_gate` 仍把 `ENV_NAME` 缺省视为 `local`（DEBUG=true 照常启动）；check-demo 验收门改为缺省=非 local 报红。二者是「开发便利」与「验收安全」的有意取舍，建议后续在 README/AGENTS 登记。
3. **⑤ 生产 build 形态的 PASS 分支未实测**：本机只有 next dev（无 `.next-prod` 生产构建），`404 → PASS` 分支仅由 httpProbe 既有语义保证（`FRONTEND` 为硬编码常量，无 env 覆写点，无法用假 404 目标验证）；dev 侧 WARN 分支已实测。
4. **T5-C2 修法②（deploy.mjs 幂等跳过时显式 WARN 文案）未做**：`deploy.mjs` 属 W-NEXT-8 文件领地，本批未越界。
5. **T9-C1 修法②（`MEMORY_EXTRACT_MAX_TOKENS` 600→1500）未做**：`app/config.py` 属其它批领地；截断仍会发生，但已由 salvage 保证**不再整批丢弃**（本批交付的即召回韧性）。
6. **临时实例与锁**：8010（DEBUG=true）/8011（DEBUG=false 生产形态）为本次验证临时实例，验证完毕已停止；8000 全程未启动/未重启（核验开始时本机 8000 不可达，不改动）。

---

## 5. 完工回执

- commit：见下方 `git log`（三条 `fix(w)` + 一条报告 commit）
- 报告路径：`test-reports/WNEXT5-completion-report.md`
- GWT 数字汇总：任务一 5/5 达标（③ 附带 §4.1 口径说明）；任务二 4/4 达标（真 HTTP 403/40924/200 全实测）；任务三 3/3 达标（24 passed，salvage 2 条回收 + 1 条 degraded 边界）