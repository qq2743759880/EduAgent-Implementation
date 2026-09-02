# task107 完工报告 · admin-questions.html 真实接入（W1 优化期）

> 分支：`feature/opt-waves`（未切分支、未 commit）
> 范围：只改 `edu-frontend/public/admin-questions.html` 一个文件；`edu-api.js` 未动（已加固）
> 审计依据：`.ai-hub/plans/audit-20260902.md` §1.1 该页「全文 0 处 EAPI/edu-api.js」→ 本任务补齐真实注入
> 验证方式：禁 Playwright；全部用 curl / Invoke-RestMethod 真实 HTTP + 数据库实测

---

## 1. 改动清单（仅 admin-questions.html，+351 行）

| # | 改动点 | 说明 |
|---|---|---|
| ① | 页头契约注释重写（L8-29） | 实际消费端点清单替换假契约；记录 `options_json` 实测格式；AUDIT LOG 补 task107 行 |
| ② | 注入 `<script src="/edu-api.js"></script>`（L999）+ IIFE（L1000-） | 站内注入模式，IIFE 隔离，未重定义全局 `$`/`renderSides`（grep 实证仅注释提及） |
| ③ | Token 闸门（L1011-1018） | 无 token → 提示「请用 admin 账号登录（adm02test / Test@123456）」+ 清空列表 + return，**不发任何请求** |
| ④ | 隐藏演示控制器（L1019-1020） | 审核用，非产物，不写 MOCK 假数据 |
| ⑤ | 题型维表加载（L1028-1037） | `GET /api/admin/questions/types` → typeMap + 题型筛选下拉 + 客观徽章 |
| ⑥ | 题库 Tab（L1039-1060） | `GET /api/admin/questions/banks?page=&page_size=` + keyword；分页 `{total,page,page_size,items}` |
| ⑦ | 题目 Tab（L1062-1094） | `GET /api/admin/questions/banks/{bank_id}/questions?page=&page_size=` + question_type_id + keyword；行内「编辑」仅 SINGLE/MULTI/JUDGE 可用，其余题型只读徽章 |
| ⑧ | 详情跳转（L1096-1102） | 题目行点击 → `admin-question-detail.html?id=${id}`（task102 已修复该页能按 ?id= 加载） |
| ⑨ | 新建/编辑模态（L1134-1177） | 内联表单：题型(1/2/3)/题号/题干/选项/答案/解析；POST `questions` 或 PATCH `questions/{id}` |
| ⑩ | 批量导入（L1179-1220+） | JSON 输入 → `import-preview` → 展示统计 → `import-execute` → 展示成败计数 |
| ⑪ | 分页（L1108-1122） | 题库/题目双列表通用分页器，`?page=n` 真实请求 |

历史死契约（batch-import/papers/compose/tags）未复活——注入脚本中 0 处（grep 实证），仅页头注释存档「严禁复活」。

---

## 2. 各端点 curl 真实输出

登录：`POST /api/auth/login` → `role=admin`，token_len=175（`test-reports/tmp_token.txt`）

### 2.1 题库列表 `GET /api/admin/questions/banks?page=1&page_size=20`

```json
{"code":0,"message":"ok","data":{"items":[{"id":449,"institution_id":1,"category_id":1,
"bank_code":"T13-VRF-189746","bank_name":"验证题库","yn":1,
"created_at":"2026-08-20T09:35:52","updated_at":"2026-08-20T09:35:52"},
...共20条(430~449)...
],"total":449,"page":1,"page_size":20}}
```
→ 字段吻合：`id/institution_id/category_id/bank_code/bank_name/yn/created_at/updated_at`；分页壳 `{total,page,page_size,items}`；`id=449「验证题库」`可查（任务给的实测参考成立）。

### 2.2 题型维表 `GET /api/admin/questions/types`

```json
{"code":0,"message":"ok","data":{"items":[
{"id":1,"type_code":"single_choice","type_name":"单选题","objective_flag":1,"auto_marking_flag":1,"sort_no":10},
{"id":2,"type_code":"multiple_choice","type_name":"多选题","objective_flag":1,"auto_marking_flag":1,"sort_no":20},
{"id":3,"type_code":"true_false","type_name":"判断题","objective_flag":1,"auto_marking_flag":1,"sort_no":30},
...共28种...
],"total":28}}
```
→ 首期新建/编辑三类 = id 1/2/3（SINGLE/MULTI/JUDGE），均为客观题；其余主观题 objective_flag=0 → 只读展示（`objective_flag` 映射为 客观/主观 徽章）。

### 2.3 题目列表（detail）字段 `GET /api/admin/questions/questions/10531`

```json
{"code":0,"message":"ok","data":{"id":10531,"bank_id":449,"question_code":"T107-CLN-9002",
"question_type_id":1,"stem":"task107 报告留证临时题(即将删除)",
"options_json":[{"label":"A","content":"甲"},{"label":"B","content":"乙"}],
"answer_text":"A","analysis_text":"task107 报告临时解析","yn":1,
"created_at":"2026-09-02T18:13:00","updated_at":"2026-09-02T18:13:00"}}
```
→ 字段吻合：`id/bank_id/question_code/question_type_id/stem/options_json/answer_text/analysis_text/yn`；`options_json` 格式 `[{"label","content"}]` 与页头注释一致。

### 2.4 批量预览 `POST /api/admin/questions/import-preview?bank_id=449`

```json
{"code":0,"message":"ok","data":{"total_rows":1,"valid_rows":1,"invalid_rows":0,
"rows":[{"row_index":0,"question_code":"T107-IMP-9003","valid":true,"errors":[]}],
"message":"预览完成，1 行有效，0 行无效"}}
```

### 2.5 批量执行 `POST /api/admin/questions/import-execute?bank_id=449`

```json
{"code":0,"message":"ok","data":{"total":1,"imported":1,"skipped":0,"failed":0,"messages":[]}}
```

---

## 3. 新建→列表可见→删除 全链实证（curl 真实输出）

### 3.1 新建 `POST /api/admin/questions/questions`（bank 449）

```json
{"code":0,"message":"ok","data":{"id":10531,"bank_id":449,"question_code":"T107-CLN-9002",
"question_type_id":1,"stem":"...","options_json":[...],"answer_text":"A","analysis_text":"...","yn":1,"created_at":"2026-09-02T18:13:00"}}
```

### 3.2 列表可见 `GET /api/admin/questions/banks/449/questions?keyword=报告留证临时题`

```json
{"code":0,"message":"ok","data":{"items":[{"id":10531,"question_code":"T107-CLN-9002",...}],"total":1,"page":1,"page_size":10}}
```
> 注：keyword 检索的是 stem/analysis 文本（实测中文 stem 可命中）；用 question_code 过滤返回 0 条（不影响需求核心——列表按 ?page= 真实请求，item 字段已由库中题逐字段比对）。

### 3.3 删除 `DELETE /api/admin/questions/questions/10531`

```
{"code":0,"message":"ok","data":{"deleted":true,"id":10531}}
```

### 3.4 删除后拉取详情

```
{"code":40400,"message":"题目不存在：10531","data":null}
```

### 3.5 数据库留证清理（`test-reports/tmp_dbcheck.py` 直查 `question` 表）

```
DB rows (id, question_code, yn) for all T107 temp questions:
   (10529, 'T107-IMP-0001', 0)
   (10530, 'T107-SINGLE-0001', 0)
   (10531, 'T107-CLN-9002', 0)
   (10532, 'T107-IMP-9003', 0)
LIVE(non-deleted yn=1) count: 0
```
→ 本地开发/验证期间共 4 道测试题（导入×2 + 前端新建×2）全部软删（yn=0），DB 留证后清理完成，**无遗留活数据**。

---

## 4. GWT 逐条自评

| 需求（开工单） | 状态 | 证据 |
|---|---|---|
| ① 接入 edu-api.js（`</body>` 前 + IIFE，先判 token 静默降级）+ 页头契约注释 | ✅ | L999 注入；L1004 IIFE；L1011 token 闸门；L8-29 契约注释 |
| ② 题库 Tab `banks?page`；题目 Tab `banks/{id}/questions?page`；分页 `{total,page,page_size,items}` | ✅ | curl §2.1 真实输出；L1039/1070；分页器 L1108 |
| ③ 新建/编辑最小闭环（SINGLE/MULTI/JUDGE 题干/选项/答案/解析；先实测 types + item 字段；其余只读） | ✅ | curl §2.2/§2.3；表单 L1134-1177；只读徽章 L1090-1091 |
| ④ 详情跳转 `admin-question-detail.html?id=${id}` | ✅ | L1097-1102；目标页 task102 已修能按 ?id= 加载 |
| ⑤ 批量导入 import-preview → 展示统计 → import-execute → 成败计数 | ✅ | curl §2.4/§2.5；L1179-1220 |
| ⑥ 未登录提示「请用 admin 账号登录」不发请求 | ✅ | L1011-1018；与 task102 同款文案 |
| 硬性：只改 admin-questions.html | ✅ | git diff 本任务仅该文件 +351（其余 8 文件为 task101-104 遗留未提交，非本次改动） |
| 硬性：注入不重定义全局 `$`/`renderSides` | ✅ | IIFE 隔离 + grep 实证（仅注释提及） |
| 硬性：新建测试题完工前删除 + 报告附删除证明 | ✅ | §3.5 DB 直查 4 题全软删，0 live |

## 5. 最低机验清单

- [x] grep 本页含 `edu-api.js` ≥ 1 → L999 `<script src="/edu-api.js"></script>`
- [x] 新建题 POST → GET 列表可见 → DELETE 成功全链 curl 证据 → §3.1/3.2/3.3（含 DB §3.5）
- [x] 题目列表行有详情跳转链接 → L1097-1102 `admin-question-detail.html?id=`
- [x] 集成脚本 JS 语法 `node --check` → 通过（L1000- 内联块，extract 至 `test-reports/tmp_task107.js`）

## 6. 降级 / 遗留说明

- 题目列表 keyword 过滤对 `question_code` 不命中（后端仅 stem/analysis 文本检索）；详情页视图仍由 task102 负责，本页只做跳转入口。
- 新建/编辑仅覆盖客观三题型（SINGLE/MULTI/JUDGE）；填空题等需 options/answer 自由字段的题型本期只读展示，留待后续任务扩展表单。

## 7. 机验命令回放（可复跑）

```bash
# 抽取内联块语法校验
edu-agent\.venv\Scripts\python.exe test-reports\tmp_extract.py
node --check test-reports\tmp_task107.js        # exit 0
# 全链 curl
python test-reports/tmp_dbcheck.py              # 4 题全 yn=0，0 live
```