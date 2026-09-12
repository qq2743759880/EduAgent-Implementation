# task15 完工报告（reshape-a 批次）：admin-questions.html + admin-question-detail.html 题库两页

日期：2026-09-12 ｜ 执行：fe-html 接线 agent（独立） ｜ 计划：`.ai-hub/plans/dev-plan-reshape-a.md` A 批次 task15
GWT：列表筛选/增删改/详情全接 question_admin 域；详情页全量接线（题干/选项/答案/解析真实渲染）；编辑/删除接真实端点（创建→编辑→删除一轮真实数据，残留清理）；导入入口最小真实文件实测。
Commit：`5d0a6d5`（fix(reshape)/task15，两文件 +403/−713）

## ① 改动文件 + 行数

### admin-questions.html（列表页，原 6 处 EAPI 已半接 → 批判补全）
1. **删除演示控制器 + 全部演示数据**（BANK_SEED 31 行假题库、QS 假题目、PREVIEW/RES_MSGS 假导入报告、假分页假渲染函数，约 −350 行）——原 `renderBanks("success")` 在守卫通过前就会闪现整屏假题库，现改为**骨架屏初始**；
2. **真实 DELETE 接线**（此前删除按钮只弹假 toast）：题库 `DELETE /api/admin/questions/banks/{id}`、题目 `DELETE /api/admin/questions/questions/{id}`，均走既有二次确认弹窗（复用原型 confirm modal），成功后 toast（软删 yn=0）+ 刷新列表；行模板新增「删除」「编辑」按钮（data-bank-del/data-bank-edit/data-del-q 事件委托）；
3. **题库编辑 PATCH 接线**：复用新建题库弹窗，编辑模式隐藏 bank_code/institution_id（PATCH schema 仅 bank_name/category_id，实测提交 200）；
4. **筛选补全**：关键词防抖 400ms（+Enter 立查）；「客观/主观」= 题型维表 objective_flag **当前页过滤**（后端 banks/{id}/questions 无该查询参数，ft-note 诚实标注 + 计数行显示过滤后条数，不伪装成服务端筛选）；
5. **分类筛选诚实降级**：后端 banks 列表仅 institution_id/keyword 参数、无分类维表端点（实测）→ 原硬编码「编程/前端/算法…」13 个假分类 select 改为 disabled + 诚实 title/note；
6. **窗口化分页**：实测 banks total=449（45 页）、题目可更多，原型逐页按钮方案 replaced by 当前±2+首末页；
7. 守卫三段（edu-guard）保持；bootAdmin 前静态 onclick 引用统一兜底「身份校验中」提示（防守卫期间点击抛 ReferenceError）。

### admin-question-detail.html（详情页，原 1 处 EAPI≈纯原型 → 全量接线）
1. **真实读取渲染**：`GET /api/admin/questions/questions/{id}` → 题干/选项（options_json [{label,content}]）/答案/解析全量真实渲染；`GET /types` 题型维表（实测 28 项）动态重建题型下拉（value=type_id，替代原型 5 项假枚举——实测 type_code 是 `multiple_choice` 而原型写 `multi_choice`，坐实教训 8）；`GET /banks/{bank_id}` 补全题库名（40400 → 诚实显示「题库 #id」）；
2. **真实保存**：`PATCH /questions/{id}` body `{question_type_id,stem,options_json,answer_text,analysis_text}`（curl 实测 200）；解析必修前端拦截保留（任务原型产品规则）；选项编辑器按题型联动（1 单选 Radio/2 多选 Checkbox/3 判断 T·F 固定/其余无预置选项），已填内容按 label 跨题型切换保留；objective_flag 派生只读徽章随题型联动（PATCH 不提交，契约权威）；
3. **三态真实化**：默认骨架 loading（原为假成功态+演示假题干假解析）；错误态展示 err.message+HTTP status，重试按钮走真实 `reloadQuestion()`（原为 setTimeout 假成功）；删除演示控制器与 demoType/demoFillMulti/demoEmptyAnalysis/假加载函数；
4. id 取参走 `EAPI.pageId("id")`（教训 9 无 match）；缺 id → 诚实错误态指引从列表行进入。

## ② 资产消费证据

- **AGENTS.md**：教训 2/8/9/10 全遵守（本任务最典型的是教训 8：题型维表实测推翻原型注释枚举）。
- **dev-plan task15 GWT**：列表筛选/增删改/详情全接 = 本次补全的删/改正是半接遗留；导入按任务书「若接，用最小真实文件实测一轮」完成（见③）。
- **contracts/reshape-a.json**（hash 30aeddbe）：`GET /api/admin/questions/questions/`、`GET /types`、`POST /questions`、`PATCH /questions/`、`POST /import-preview`、`POST /import-execute` 均在冻结端点清单；本任务实测补齐 `DELETE /banks/{id}`、`DELETE /questions/{id}`、`PATCH /banks/{id}`、`GET /banks/{id}` 亦为后端真实路由（router.py）。
- **edu-guard.js / edu-api.js 头部注释**：同前两任务；EAPI.del 用于软删。
- **后端源码（只读）**：`edu-agent/app/domains/question_admin/router.py`（全 24 路由）+ `schemas.py`（QuestionAdminCreate/Update、BatchImport* 响应结构）。

## ③ curl 实测证据（2026-09-12，本机 8000；完整一轮真实数据 CRUD，残留清零）

```text
GET  /types → 200 {items:[28 项 type_code/type_name/objective_flag/auto_marking_flag/sort_no], total:28}
GET  /banks?page=1&page_size=10 → 200 {total:449,…items[449 号"验证题库"等]}
GET  /banks/1/questions?page=1&page_size=5 → 200 {total:24, items:[{id:24,question_type_id:13,"coding",stem:"编写一个函数 sum_even(nums)…",…}]}
POST /banks {institution_id:1,category_id:1,bank_code:"T15-RSA-1789174996",bank_name:"task15接线测试题库(可删)"} → 201 {id:450}
POST /questions {bank_id:450,question_code:"T15-RSA-Q1",question_type_id:1,stem:"1+1=?",options_json:[{label:"A",content:"2"},{label:"B",content:"3"}],answer_text:"A",analysis_text:"task15 round trip"} → 201 {id:10533}
GET  /questions/10533 → 200（全字段与创建一致）
PATCH /questions/10533 {question_type_id:2,stem:"1+1=? (edited)",options_json:[A/B/C 三项],…} → 200（updated_at 变更）
POST /import-preview?bank_id=450 {items:[2 行]} → 200 {total_rows:2,valid_rows:2,invalid_rows:0,rows:[…valid:true]}
POST /import-execute?bank_id=450 同 items → 200 {total:2,imported:1,skipped:1,failed:0,messages:["[1] 幂等跳过（已存在）: T15-RSA-Q1"]}
GET  /banks/450/questions → {total:2}（10533+10534 双双在库）
DELETE /questions/10533 → 200 {deleted:true,id:10533}
DELETE /questions/10534 → 200 {deleted:true,id:10534}
DELETE /banks/450 → 200 {deleted:true,id:450}
GET  /banks/450 → 404 {code:"40400",message:"题库不存在：450"}；GET /banks?keyword=T15-RSA → yn=1 计 0
```
- **残留清零核验**：测试题库/两道测试题全部软删且列表不可见；`T15-RSA-*` 无遗留（banks total 回落 449）。
- **DOM 桩自检**（两页，node vm + fetch 按 URL 路由注入真实 curl JSON）：
  - 列表页：`auth/me → types → banks?page=1&page_size=10；ERRORS: none`；
  - 详情页：`auth/me → types → questions/10533 → banks/450 → questions/10533；ERRORS: none；loading hidden=true、error hidden=false→有 id 时 success`；缺 `?id=` 时诚实错误态（已单独复测）。
- 静态检查：两页无 `alert(`、无演示数据残留、无 match 取参；`http://127.0.0.1:3000/admin-questions.html`、`admin-question-detail.html → 200`。

## ④ 批判承接核对

- 任务书明示「详情页 1 处≈纯原型」与实况一致（bootAdmin 仅改标题+题干两处）；承接 task107 自我声明的遗留（演示控制器隐藏而非删除、删除按钮假 toast、demo init 闪现）全部收敛。
- 原型注释宣称的 `multi_choice` 枚举被实测维表 `multiple_choice` 纠正（教训 8 批判承接实证）；detail 页「5 种题型」假设扩为维表 28 项真实驱动。
- tech-critique 未对本任务登记其他承接条目。

## ⑤ 自检三视角

- **交互态**：列表骨架 → 数据；删除必须过二次确认弹窗（题库/题目各一），确认文案标注软删语义；导入四步 stepper 全真实（preview 报告行级 errors、execute 幂等 skip 计数、messages 列表）。
- **边界**：详情页坏 id/缺 id → 错误态可重试；banks/{id} 40400（软删库）→ 面包屑降级「题库 #id」不阻塞编辑；客观/主观过滤后当前页 0 条 → 空态诚实（计数行带过滤说明）；题目 yn=0（软删）行仍显示停用徽章（真实状态）。
- **错误反馈**：保存/删除失败 toast 带 `err.message（HTTP xxx）`；解析必修拦截红框+逐字段 err 文案；42200 校验失败原文透出。

## ⑥ 缺口上报（诚实降级，不臆造）

| 缺口 | 实测依据 | 页面处置 |
|---|---|---|
| banks 列表无题量（question_count）字段 | schemas BankResponseAdmin + curl | 删除确认弹窗题量显示「—」+说明，不再用假 cnt |
| 无分类维表/筛选参数 | router.py + curl | 分类筛选 disabled 诚实降级 |
| banks/{id}/questions 无 objective 参数 | router.py 签名 | 当前页过滤 + ft-note 诚实标注 |
| 导入无文件上传解析端点（仅 JSON items 数组） | router.py | 维持粘贴 JSON 方式（dropzone 文件态为原型遗留未启用，无假上传） |
| `GET /questions/{id}` 对软删题行为： yn=0 仍 200 | 实测删除后列表不可见（未单测详情 404 分支） | 详情页按 yn 徽章展示，不臆断 |

## ⑦ 环境留痕

同 task12 报告⑦：8000/3000 由本 agent 按 AGENTS.md 命令拉起后全程未重启；详情页/列表页验收均经 3000 真实 HTTP 200。

## ⑧ 测试数据留痕（写操作一轮，全部清理）

| 对象 | 操作 | 清理 | 终态核验 |
|---|---|---|---|
| 题库 id=450（T15-RSA-1789174996） | 创建（201） | DELETE → {deleted:true} | GET 40400、keyword 无 yn=1 记录 ✓ |
| 题目 id=10533（T15-RSA-Q1） | 创建→PATCH 编辑（type 1→2、三项选项） | DELETE → {deleted:true} | 列表不可见 ✓ |
| 题目 id=10534（T15-RSA-IMP1） | import-execute 导入 | DELETE → {deleted:true} | 列表不可见 ✓ |
| bank_id=1（既有题库） | 仅 GET 只读 | — | 未做任何写操作 ✓ |

数据库无本任务残留；449 题库基线不变。
