# task13 完成报告 · admin-courses.html 系列管理全量接线 + 回收站 Tab（按 APPROVED 原型实施）

- 日期：2026-09-12
- 执行：fe-html 接线 agent（独立实证）
- 产出：
  - `edu-frontend/public/admin-courses.html`（改写：9 处 EAPI 全量接线 + 回收站 Tab 按 Gate A APPROVED 原型重做 + 清零演示控制器/MOCK）
  - `edu-frontend/public/admin-courses-recycle-proto.html`（仅 AUDIT LOG 一行：`DRAFT` → `APPROVED` + 追加签收行 `[2026-09-12] Gate A 用户签收 APPROVED;task13 按此实施`）
  - `test-reports/task13-lifecycle-probe.py`（可复跑写路径实证脚本，requests 真实 HTTP）
- commit：见文末（单独 commit，只含上述文件）

---

## 一、实测证据（真实 HTTP，账号 adm02test/Test@123456，后端 127.0.0.1:8000）

### 1. 只读列表契约（curl，2026-09-12）

| # | 请求 | 实测 | 结论 |
|---|---|---|---|
| L1 | `GET /series?page=1&page_size=3` | `{code:0,data:{total:2629,page:1,page_size:3,items:[…]}}`；item 字段 id/institution_id/delivery_mode/series_code/series_name/description/cover_url/target_learner_identity_codes/target_learning_goal_codes/target_grade_codes/sale_status/created_by/created_at/updated_at | 壳 {code:0,data:{items,total,page,page_size}}；默认列表排除 off_sale |
| L2 | `…&sale_status=off_sale` | total **56**，items 全部 `sale_status:"off_sale"` | **回收站载荷过滤**（sale_status 显式值覆盖默认排除，repo `series_repo.list_series` L84-89 同源） |
| L3 | `…&sale_status=off_sale&include_deleted=true` | total **56** | 与 L2 等价 → 按 APPROVED 原型接线清单传组合参数 |
| L4 | `…&include_deleted=true` | total **2685**（=2629+56） | 证实变更单 reshape-a2 #2：include_deleted 是「不过滤全量」，**不是回收站**（旧 C5 视图语义错误已修正） |
| L5 | `…?keyword=Python&sort=name_asc&page_size=100` | total 0（诚实空态）；page_size 回显 100 | keyword 匹配 name/description/code；sort 四值有效；page_size≤100 |
| L6 | `…?page_size=101` | HTTP 422 `{"code":"42200","message":"Input should be less than or equal to 100",…}` | page_size max 100 后端强制（UI 固定 20，不触发） |
| L7 | `GET /series/2654` | code 0，详情字段同 item | 编辑弹窗兜底取数端点 |
| L8 | `GET /series/99999999` | HTTP 404 `{"code":"40400","message":"系列不存在：99999999"}` | 404 错误形状 |

### 2. 写路径全生命周期（`python test-reports/task13-lifecycle-probe.py`，自建测试系列，真实 HTTP）

| # | 操作 | 实测 |
|---|---|---|
| W1 | POST /series（institution_id=1, delivery_mode=online_recorded, series_code=t13w1789187222a, series_name, created_by=100003←/me 实取） | HTTP 200，data.id=**2710**，sale_status=draft |
| W2 | 重复编码再建 | HTTP **409** `{"code":"40901","message":"系列编码 't13w1789187222a' 已存在"}` —— 40901 错误形状实证（与 restore 编码占用同错误类 `SERIES_CODE_CONFLICT`） |
| W3 | PATCH /series/2710 {series_name:"…-改名", description} | HTTP 200 回显新值 |
| W4 | 对未软删系列 POST /restore | HTTP 404 `"系列 2710 未处于回收站（已下架）状态，无法恢复"` |
| W5 | DELETE /series/2710（软删） | HTTP 200 `message:"系列已下架"`；detail → sale_status=**off_sale** |
| W6 | 回收站视图 `sale_status=off_sale&include_deleted=true&keyword=t13w…` | total≥1 且 items 含 2710（bin 过滤+keyword 组合有效） |
| W7 | POST /series/2710/restore | HTTP 200 `data={"series_id":2710,"status":"restored"}`；detail → sale_status=**draft** |
| W8 | 二次软删 + `DELETE /series/2710?hard=true` | HTTP 200 `message:"系列已彻底删除"`；detail → 404/40400（**自建数据已清理**） |
| W9 | POST /series/99999999/restore | HTTP 404 `{"code":"40400","message":"系列不存在：99999999"}` |

全部 PASS（脚本含 finally 兜底清理，重复执行安全）。

### 3. 前端静态验证（无 Playwright，按 AGENTS.md 教训②）

- `http://127.0.0.1:3000/admin-courses.html` → HTTP 200（next dev 直接盘供给，含 task13 标记、`sale_status=off_sale` 接线、demo-ctrl 计数 **0**）
- `http://127.0.0.1:3000/admin-courses-recycle-proto.html` → HTTP 200，`AUDIT LOG: APPROVED` 在位
- 4 段内联脚本 `new Function()` 语法全过；`getElementById` 36 处引用与 DOM id 全对上；**无重复 id**；无 `alert(/confirm(/prompt(/.match(` 代码调用（AUDIT LOG 注释中的「confirm()」为变更记述文字）
- 核心查询构造 `buildSeriesQuery` 以桩件单测：list 干净=`page=1&page_size=20`；list 全筛选=`page=2&page_size=20&keyword=Py%20thon&delivery_mode=online_live&sale_status=on_sale&sort=newest`；bin=`page=1&page_size=20&keyword=Py%20thon&delivery_mode=online_live&sale_status=off_sale&include_deleted=true`（状态/排序在 bin 正确忽略）

### 4. 最终 EAPI 调用面（grep 全量，10 处）

```
GET  /api/admin/courses/series?…        （列表/回收站，三态）
GET  /api/admin/courses/series/{id}     （编辑兜底取数）
GET  /api/auth/me                       （created_by 实取）
POST /api/admin/courses/series          （新增，40901 诚实透出）
PATCH /api/admin/courses/series/{id}    （编辑：SeriesUpdateAdmin 字段集）
PATCH /api/admin/courses/series/{id}    （上架/下架 sale_status）
DELETE /api/admin/courses/series/{id}   （软删→off_sale）
POST /api/admin/courses/series/{id}/restore（恢复，404/40901 诚实透出）
DELETE /api/admin/courses/series/{id}?hard=true（彻底删除，409/40908 诚实透出）
```

## 二、资产消费证据

| 资产 | 消费方式 |
|---|---|
| AGENTS.md 关键教训 1-10 | 教训③SSE 不涉及；教训④注入模式沿用（`edu-api.js`+`edu-guard.js` 尾部注入，未重定义全局）；教训⑧真实契约优先于页面注释（原型注释称回收站按 updated_at 倒序——实测 `_SORT_MAP` 无 updated_at 排序项，UI 文案改为「按后端默认排序」，见偏差 #1）；教训⑨参数提取零 `match()` 正则（行 id 经 data 传参，弹窗行记录 `window.__restoreId/__purgeId`）；教训⑩守卫三段在位（`eduGuard.requireAdmin()` → bootAdmin → loadSeries） |
| `.ai-hub/plans/dev-plan-reshape-a.md` task13 GWT | 系列 CRUD+restore 全接、40901 冲突提示、回收站 Tab 按 P6' APPROVED 原型后实施——全部满足 |
| `contracts/reshape-a.json`（冻结 30aeddbe） | 端点面（GET/POST/PATCH/DEL series、restore）逐一对上；分页壳 {total,page,page_size,items} 直读外层 triple |
| `.ai-hub/plans/contract-change-reshape-a2.md` 变更2 | bin 视图过滤由 `include_deleted=true` 修正为 `sale_status=off_sale&include_deleted=true`（L2/L3/L4 实测背书） |
| `admin-courses-recycle-proto.html`（Gate A APPROVED） | 恢复确认弹窗（confirm-restore）/彻底删除两步确认（confirm-purge-1+2，编码输入匹配解锁）/bin 空态文案与图标/「最近变更」updated_at 列/em-toast 形态，逐项落进 admin-courses.html；头部 AUDIT LOG 置 APPROVED+签收行 |
| `test-reports/task13-proto-completion-report.md` | 原型 agent 的登录字段纠错（`account`）、字段快照、409 冲突文案直接复用为接线依据 |
| 后端权威源码（只读） | `schemas.py` SeriesCreateAdmin 必填 institution_id/delivery_mode/series_code/series_name/created_by（创建表单+payload 对齐）；SeriesUpdateAdmin 无 series_code/institution_id（编辑态置灰，偏差 #5）；`error_codes.py` 40901/40908；`service.py` restore/软删/硬删语义 |

## 三、批判承接核对段（v3 批判承接核对表 + 规划自审落点）

| 批判/自审条目 | task13 落点 | 核对结果 |
|---|---|---|
| C15-C18（核对表） | 落点分别为 taskB0/B3、task18、taskB2、taskB1a | 均不在 task13 范围，无遗漏承接（本 task 不越界吞 B 批） |
| Design finding2（A 批每页 GWT 三态必查，防 UX 病灶残留） | loading 骨架（injectSkeleton，bin/list 列数自适应 6/5）/空态（list「暂无系列」/bin「回收站为空」♻️ 图标+文案切换）/错误态（#err-msg 消费 errMsg+重试保留当前视图） | ✅ 三态齐全且按视图分化 |
| 教训⑧「页面注释只是初稿」 | 原型注释两处与实测/源码不符处已按实测纠正（bin 排序文案、409 SERIES_IN_USE→40908），记入偏差清单 | ✅ |
| C5 历史批判（include_deleted 误用，本批变更单 #2 动机） | bin 过滤语义已修正并附 L2-L4 实测证据 | ✅ |
| 「只批判不修复」防漏（TT §5.6） | 本页 9 处 EAPI 半接状态一次性收口；`git grep demo-ctrl admin-courses.html`=0、静态 SERIES MOCK 数组已删 | ✅ |

## 四、三视角自检

- **CEO（范围）**：只改 2 个 HTML + 新增 2 个 test-reports 文件；未动后端/contracts/edu-api.js；无范围外页面。演示数据=真实库（2629/56），零 MOCK。✅
- **Eng（架构）**：响应壳/分页壳直读；401 由 edu-api 单飞 refresh 统一处理，页内未自造轮询；10 处 EAPI 与冻结契约一一对应；`?hard=true` 走 `EAPI.del(path+"?hard=true")`（del 签名无 body 参数，edu-api.js:300 实读）；破坏性操作均有 busy 防重入。confidence: high（查询构造有桩件单测，弹窗流为纯 DOM 状态机）。⚠ 残余风险：浏览器端实际交互未跑（Playwright 禁用），以静态机验+契约实证覆盖，演示前检查单（task18）会再兜底。✅
- **Design（体验）**：视觉 token 未动（P2' 只修不增）；新弹窗复用原型同款 c-msg/c-warn/mfoot 结构；恢复成功=绿色 ok toast、40901/404/40908=红色 err toast 且透出后端原始 message+错误码（诚实提示）；bin 内状态/排序 select 置灰带 title 说明。✅

## 五、测试数据留痕

| 项 | 值 |
|---|---|
| 自建测试系列 | id=**2710**，series_code=`t13w1789187222a`，institution_id=1，created_by=100003（adm02test 实取） |
| 生命周期 | 创建(W1)→重复编码冲突(W2)→改名(W3)→软删(W5)→恢复(W7)→再软删(W8a)→**硬删清理(W8b)** |
| 残留 | **零残留**（2710 已物理删除，W8b 后 GET=404/40400 实证）；此前一次 curl 中文 body 编码失败（HTTP 400 40000）未入库 |
| 存量真实系列 | 全程只读（L1-L8），未对任何存量 id 执行写操作/硬删 |
| 复跑 | `python test-reports/task13-lifecycle-probe.py`（幂等：code 取时间戳，finally 兜底清理） |
| 未做实测的分支（诚实披露） | ①restore-40901：live 不可达——series_code 唯一性由 `get_by_code`（无状态过滤）保证，软删系列编码仍占用创建位（W2 同理），且 PATCH 无 series_code 字段 → 环境内无法构造「编码被其它系列占用」的软删系列；UI 分支已按原型接线（errMsg toast），错误形状由 W2 同错误类 40901 背书。②hard-delete 40908 引用冲突：需给自建系列挂班次/订单引用，而班次仅软删（yn=0）仍计入 `count_references`，会使测试系列永久无法硬删清理 → 按测试数据卫生原则放弃 live 构造；UI 分支已接线，语义与 `service.delete_series` L136-148 源码比对一致 |

## 六、与 APPROVED 原型的偏差清单

1. **bin 排序文案**：原型置灰 select 的 title 写「回收站按最近变更倒序（updated_at）」——实测 `_SORT_MAP` 仅 default/newest/name_asc/name_desc，无 updated_at 排序。UI 改为「回收站内不提供排序切换（按后端默认排序）」（教训⑧：契约以实测为准）。
2. **409 错误码标注**：原型硬删弹窗写「409（SERIES_IN_USE）」——`error_codes.py:120` SERIES_IN_USE="40908"，弹窗文案改为「409（错误码 40908：系列仍被班次/订单引用）」；toast 消费后端原始 message（含具体班次/订单计数）。
3. **演示资产未移植（任务要求清零）**：原型 demo 控制器、`__demo_conflict` 模拟行、「模拟 409」chip、静态 BIN/SERIES 数组、原型标注条均不进正式页；409 分支由真实 API+errMsg 承担。
4. **bin 分页**：原型为快照单页示意（`<button class="cur">1</button>`），正式页按外层 triple 真翻页（任务硬性要求分页壳）。
5. **编辑表单置灰**（原型未覆盖编辑弹窗）：series_code/institution_id 编辑态 disabled+title 说明（SeriesUpdateAdmin 无此二字段，PATCH 传了也会被丢弃——置灰是诚实呈现）。
6. **恢复成功后行为**：原型本地移行模拟，正式页 restore 成功后重拉回收站列表（原型注释已预留「真实实现=重新拉列表」）。
7. **「视频上传（占位）」死按钮移除**：原 task56 表单脚部永久 disabled 按钮属死按钮，按本任务「清零死按钮」要求删除（视频绑定属 task57 详情页/后端未实现域，task16 诚实占位不适用于表单内）。
8. **恢复弹窗取消键行为**：与原型一致（data-close/scrim/Escape 关闭）；仅增加确认按钮 busy 态防双击重放。

## 七、Commit

```
fix(reshape)/task13: admin-courses 系列管理全量接线+回收站Tab按APPROVED原型（修正sale_status过滤语义，恢复/硬删两步确认+40901/40908诚实提示）
文件：edu-frontend/public/admin-courses.html · edu-frontend/public/admin-courses-recycle-proto.html · test-reports/task13-lifecycle-probe.py · test-reports/task13-completion-report-reshape-a.md
```
（hash 见提交后回显）
