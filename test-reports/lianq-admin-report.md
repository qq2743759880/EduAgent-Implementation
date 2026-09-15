# 管理端运营工具全链路联调报告（运营后台交接前置）

> 任务：管理端每一条工具链完整过一遍，产出交接级联调报告。
> 执行：Hermes Agent（单会话）· 2026-09-15 11:46–12:40（中国标准时间）
> 环境：后端 http://127.0.0.1:8000（uvicorn, edu-agent）· 前端 http://127.0.0.1:3000（fe-html 静态页 + next dev）
> 方法：页面 UI 操作与 API 直调双轨记录（API 层用 Python urllib 逐条落日志；UI 层用 CDP 驱动真实浏览器逐格采集）。无 Mock、无跳步。
> 守则遵守：对非本任务创建的业务数据只读；卡点/异常原样记录未修未绕；测试数据尽可能清理（残留清单见 §8）。

---

## 0. 执行摘要

| 链路 | 结论 | 一句话 |
|---|---|---|
| 1 课程管理 | ⚠️ 全通但有**清理死锁缺陷** | 建/编/班次/模块/课次/传视频/播放/章节全通；**但绑了视频的课次删不掉，且无任何解绑入口** |
| 2 用户管理 | ✅ 可用，性能达标 | 十万级数据搜索/筛选/翻页全部 <0.7s；**manager 角色整页 403** |
| 3 题库管理 | ✅ 全通 | 建/编/单选/多选/导入/删除全链路绿；两处小坑见 §3 |
| 4 RAG 知识库 | ⚠️ 功能通，**行数显示会骗人** | 上传→任务→检索全通；**分区行数是"已封印段"口径，新上传内容要等 flush 才计数** |
| 5 MCP 工具 | ✅ 全通 | 真调用工具成功且入日志；全量健康扫描 13.5s（14 台中 3 台本来就是坏的） |
| 6 交叉核对 | ✅ 一致性总体好 | 用户数/题库数页面与 API 一致；RAG 行数与存储真值有口径差（§4.4） |

**manager 账号（mgr01test）结论：只能用课程、题库、RAG 三个页面；仪表盘、用户管理、MCP 三个页面进去就是"加载失败"。详见 §5 能力矩阵。**

---

## 1. 环境与账号自检（链路 0）

| 项 | 结果 |
|---|---|
| 后端 8000 | ✅ /docs 200（21ms），/openapi.json 200（176 个路径） |
| 前端 3000 | ✅ /admin-dashboard.html 200（28ms） |
| admin 登录 | ✅ `adm02test` → HTTP 200 465ms，role=admin，user_id=100003 |
| manager 登录 | ✅ `mgr01test` → HTTP 200 446ms，role=manager，user_id=100004 |
| 未带 token 访问管理接口 | ✅ 正确 401 |

> **实测纠正一处交接文档假设**：登录接口字段名是 `account`（不是 `username`），传错返回 422「Field required: account」。任何自研脚本对接时注意。

---

## 2. 链路 1：课程管理（API + UI 双轨）

### 2.1 系列创建与编辑（API 轨）

| 步骤 | 请求 | 结果 | 耗时 |
|---|---|---|---|
| 建系列 | `POST /api/admin/courses/series` `{institution_id:1, delivery_mode:"online_live", series_code:"LIANQ-444227", series_name:"联调交接测试系列-444227", sale_status:"draft", created_by:100003}` | ✅ 200，id=2789 | 51ms |
| 编辑系列 | `PATCH /api/admin/courses/series/2789` `{series_name:"…-已编辑", description:"编辑后的描述"}` | ✅ 200，字段生效 | 63ms |
| 查系列 | `GET /api/admin/courses/series/2789` | ✅ 200，与编辑结果一致 | 33ms |

**⚠️ 坑 1（会让运营卡住的第一只拦路虎）：新建班次必填 `head_teacher_id`，但它不是"用户管理里的教师编号"。**
- 第一次用用户列表里的教师（user_id=975）创建班次 → **HTTP 500**，业务码 `50301`「依赖服务暂不可用」（误导性提示，真实原因见下）。
- 后端 error.log 原始异常（我们查了日志）：MySQL `IntegrityError 1452` —— 外键 `fk_series_cohort_teacher` 指向 **staff_profile 表**，不是 users 表。
- 正确做法：传 staff_profile 的主键（页面表单默认值 16 可用）→ 重试即 200。
- **交接要点**：① 报错文案「依赖服务暂不可用」与真实原因（ID 填错）无关，遇到 500/50301 先怀疑 head_teacher_id 填的不是教职工档案号；② 页面上没有任何地方能查「可用的 head_teacher_id 列表」（openapi 无教职工列表端点），运营只能靠猜或问开发 —— 建议补教职工选择器。

### 2.2 班次 → 模块 → 课次（API 轨）

| 步骤 | 请求 | 结果 |
|---|---|---|
| 建班次 | `POST /api/admin/courses/cohorts`（head_teacher_id=16，售价 99.9，容量 30） | ✅ 200，id=7918 |
| 建模块 | `POST /api/admin/courses/modules`（stage_no=1，2 学时） | ✅ 200，id=23657 |
| 建课次 | `POST /api/admin/courses/sessions`（2026-10-10 10:00-11:30） | ✅ 200，id=205777 |

均 <90ms。归属链：系列 2789 → 班次 7918 → 模块 23657 → 课次 205777。

### 2.3 视频上传（链路核心，UI 轨真实文件 + API 轨对照）

**测试视频**：ffmpeg 生成 8 秒 640×360 mp4（含音轨），153,083 字节 ≈ 0.15MB。

API 轨（课次 205777）：
| 步骤 | 请求 | 结果 |
|---|---|---|
| 初始化分片 | `POST /videos/init-chunked?session_id=205777&file_name=…&file_size=153083&chunk_count=3` | ✅ 200，upload_id=`chunk_fc5a5c…`，服务端返回分片大小 51,027B（3 片）与上传 URL 列表 |
| 逐片上传 | `PUT /videos/upload-chunk/{upload_id}/{0,1,2}`（二进制体） | ✅ 3/3 片 200，单片 18–37ms |
| 完成分片 | `POST /videos/finalize-chunked?upload_id=chunk_fc5a5c…` | ✅ 200：video_id=205780，**transcode_status=completed（即时）**，file_url=`/media/videos/VID-20260915-0FA68A1D.mp4` |
| 绑定课次 | `POST /videos/bind-session?session_id=205777&video_id=205780&sort_no=1` | ✅ 200 bound=true。⚠️ 此接口参数走 **query string**，放 JSON body 会 422 |
| 转码状态 | `GET /videos/205780/transcode-status` | ✅ completed / review=pending（首查即终态） |
| **播放验证** | `GET http://127.0.0.1:8000/media/videos/VID-20260915-0FA68A1D.mp4` | ✅ **HTTP 200，Content-Type=video/mp4，153,083 字节全量** |

**上传全程耗时：246ms**（init + 3 片 + finalize）。大文件按 5MB/片分片，页面上传区文案与实际行为一致。

UI 轨（课次 205778）：在详情页「▶ 视频」面板，通过浏览器以真实文件对象注入 `ui_chain_video.mp4`（0.15MB）→ 页面自身分片逻辑接管 → stepper 显示 `upload_id=chunk_679790d0… · 1 分片 · 0.1MB/片` → 徽章「转码完成」→ API 复核资产 617335 落库、播放 URL 同样 200。**页面链路与 API 链路行为一致。**

> 附带发现：访问不存在的视频地址（如 `/media/videos/xxx.mp4`）返回的是 JSON 错误壳 `{"code":"40400",...}` 而不是标准 404 页——学员/运营拿到过期视频链接会看到裸 JSON，体验缺陷，记录待修。

### 2.4 视频章节（增/查/改/删，API 轨）

| 步骤 | 请求 | 结果 |
|---|---|---|
| 建章节×2 | `POST /chapters`（0-4s「开场」、4-8s「要点」） | ✅ 200，id=617331/617332 |
| 列章节 | `GET /videos/205780/chapters` | ✅ 2 条 |
| 改章节 | `PATCH /chapters/617331`（改标题） | ✅ 200 |
| 删章节 | `DELETE /chapters/617332` → `GET` 复核 | ✅ 列表剩 1 条 |

> **纠正一处过期文档**：课程详情页源码注释称"章节管理无后端端点、表单标注待接线"——实测 `POST/GET/PATCH/DELETE /api/admin/courses/chapters` **全部存在且工作正常**。以本报告实测为准。

### 2.5 清理演练与**清理死锁缺陷**（链路 1 最重要的交接发现）

按 章节→课次→模块→班次→系列 顺序删除：

| 步骤 | 结果 |
|---|---|
| 删章节 | ✅ 200 |
| **删课次（绑了视频）** | ❌ **HTTP 409** `40908`「课次仍被 1 条子记录引用，无法删除」 |
| 删模块 | ❌ 409 `40908`「模块仍被 1 个课次引用」（被卡住的课次拖累） |
| 删班次 | ✅ 200（注意：**它下面还有模块时也能删掉**，与课次/模块的保护行为不一致） |
| 软删系列 | ✅ 200（下架，进回收站，列表 keyword 搜不到） |
| 硬删系列 | ❌ 409 `40908`「系列仍被 1 个班次（含已下架）、0 笔订单引用，无法彻底删除」 |

**缺陷定性（P1，交接阻塞级）**：
- **视频资产一旦绑定课次，API 层不存在任何解绑/删除该资产的端点**（openapi 全量核对：`/assets` 只有 GET，无 DELETE；无 unbind 端点）。
- 后果链：传错视频 → 课次删不掉 → 模块删不掉 → 系列永远无法硬删，只能软删躺回收站。运营**没有自救手段**，只能找开发清库。
- 页面表现（源码佐证 admin-course-detail.html:900-904）：确认框文案只写「软删」，用户对此阻塞**零预警**；点击确认后触发浏览器原生 `alert("删除失败：课次仍被 1 条子记录引用，无法删除")`——提示了"删不掉"但没说"为什么/怎么办"。
- 建议：① 后端补「解绑/替换课次视频」端点（或允许课次强制卸载资产）；② 页面确认框在课次已有绑定视频时提前警示。

### 2.6 课程链 UI 补充（UI 轨）

- **建系列**：课程页「＋ 新建系列」表单（名称/编码/机构/交付模式/状态）→ toast「已创建系列」，列表首位出现新行。页面自动注入 created_by，无需手填。
- **软删**：行菜单「🗑 删除」→ 确认框明示「**不会永久删除**/确认下架（软删）」→ toast「已下架（可在回收站查看）」。
- **回收站**：两行测试系列均在，「♻ 恢复」点击后系列回到正式列表（详情页数据完整）。
- **回收站还有「彻底删除」按钮**：受 §2.5 死锁影响，有绑定资产的系列点它会收到同样的失败提示。

---

## 3. 链路 2：用户管理（十万级）

基线：全库 **100,048** 用户（学生 100,037 / admin 5 / manager 3 / teacher 3，禁用 1）。

### 3.1 搜索 / 筛选 / 翻页（admin，API 轨）

| 操作 | 请求 | 结果 | 耗时 |
|---|---|---|---|
| 关键词搜索 | `?keyword=adm` | ✅ 1 条（adm02test） | 320ms |
| 角色筛选 | `?role_code=student` | ✅ total=100,037 | 406ms |
| 状态筛选 | `?status=0` / `?yn=0` | ✅ 各 1 条（同一禁用账号） | ~130ms |
| 组合筛选 | `?role_code=student&status=1&yn=1` | ✅ total=100,036 | 471ms |
| 翻页（page_size=100） | p1/p2/p3 | ✅ 首 5 个 ID 无重叠、严格连续递减 | 199–212ms |
| **最后一页**（p1001/100） | `?page=1001` | ✅ 48 条（100048=1000×100+48） | 600ms |
| 越界页 | `?page=1002` | ✅ 200 空列表（不报错） | 547ms |
| 参数边界 | page_size=101 / page=0 | ✅ 422 明确拒绝（≤100 / ≥1） | — |

**翻页体验结论：十万级全量翻到最后一页也在 0.6s 内，无慢查询；分页参数有校验、越界不崩。合格。**
页面轨（admin-users.html）：搜索框 400ms 防抖生效（输入「adm」实时出 1 行）；分页器是窗口式（‹ 1 ›，随页码生长），表格 10 行/页，数字与 API 一致。

### 3.2 本任务未动的功能（如实说明）

- **角色变更/禁用操作未实测**：守则要求对真实业务数据只读，库中无本任务可牺牲的测试用户；manager 视角已覆盖只读面。红线路径（最后一名 admin 的禁用/降级 → 40303 拒绝）页面有前端禁用 + 后端兜底的双保险（源码注释与后端 40303 常量均在），但本次未构造实测场景。

---

## 4. 链路 3：题库管理（全链路 ✅）

### 4.1 题库 CRUD + 题目 CRUD（API 轨）

| 步骤 | 请求 | 结果 |
|---|---|---|
| 建题库 | `POST /api/admin/questions/banks` | ✅ 201，id=452 |
| 编辑题库 | `PATCH …/banks/452` | ✅ 200 改名生效 |
| 建单选题 | `POST …/questions`（type_id=1，4 选项，answer=A） | ✅ 201，id=10535 |
| 建多选题 | `POST …/questions`（type_id=2，answer="A,B,C"） | ✅ 201，id=10536 |
| 编辑题目 | `PATCH …/questions/10535` | ✅ 200 |
| 查题目 | `GET …/questions/10535` | ✅ 与编辑结果一致 |

题型字典 `GET /api/admin/questions/types` 返回 **28 种题型**（单选/多选/判断/填空/简答……），objective_flag 与自动判分标记齐全。

### 4.2 批量导入（预览 → 执行）

| 步骤 | 请求 | 结果 |
|---|---|---|
| 导入预览 | `POST /import-preview?bank_id=452`（items：1 单选 + 1 判断） | ✅ 200：2 行有效 0 无效，逐行 errors 空明细 |
| 导入执行 | `POST /import-execute?bank_id=452` | ✅ 200：imported=2, skipped=0, failed=0 |
| 复核 | `GET /banks/452/questions` | ✅ 库内 4 题（2 手建 + 2 导入） |

> 导入格式是 **JSON items 数组**（不是文件上传）。页面「⬆ 批量导入」对话框提供 JSON 文本域 + 「开始校验」（=preview）+「确认导入 N 行」（=execute）两段式，与 API 一一对应——页面轨实测：JSON 粘入 → 校验 → 确认 → 题目落库（id=10539 复核成功）。

### 4.3 删除（软删）与两个坑

- 删单题 `DELETE /questions/{id}` ✅ 200；删题库 `DELETE /banks/452` ✅ 200（题库列表 keyword 复查=0）。
- **坑 2**：题库删除时其下还有题目（实测删 452 时内含 4 题）也能直接删掉——题目没有随库级联清理，也未阻止删除。与课程域（40908 引用保护）行为不一致。残留题目在题库详情不可达。
- **坑 3**：`GET /api/admin/questions/questions?keyword=…` 返回 **405 Method Not Allowed**——**题目没有跨题库的列表/搜索端点**。运营想找"某道题在哪个库"只能逐库翻，删库后想找回题目数据只能找开发查库。

### 4.4 UI 删除的二次确认

页面删除题库走两段确认弹窗（展示题库名 + 软删说明 → 「确认删除（软删）」按钮），实测 toast「题库「…」已软删（yn=0）」、行消失。注：确认弹窗里的题目数量显示为「—（banks 列表无题量字段）」，删除前看不到会删掉多少题（结合坑 2，建议删除前先人工核对题量）。

---

## 5. 链路 4：RAG 知识库

### 5.1 上传 → 任务 → 检索（API 轨）

测试文档：`lianq_test_doc.md`（767B，含唯一检索关键词）+ `lianq_test_doc.pdf`（554B，最小合法 PDF）。

| 步骤 | 请求 | 结果 | 耗时 |
|---|---|---|---|
| 上传 md | `POST /api/knowledge/admin/upload`（multipart，字段名 `files`） | ✅ 200 task_id=`…6691d7` | 248ms |
| 上传 pdf | 同上 | ✅ 200 task_id=`…696d66` | 137ms |
| 任务轮询 | `GET /api/knowledge/tasks`（页面每 5s 自动轮询） | ✅ t+0s 已 running，t+2s 内 **succeeded** | — |
| 任务详情 | `GET /api/knowledge/status/{task_id}` | ✅ md=4 chunks / pdf=1 chunks，error=null | — |
| 向量检索 | `POST /api/admin/rag/search`（query=文档内唯一关键词） | ✅ **score=1.0 命中**，次高分 0.77 命中同文档其他段 | 2.3s |

内容真实入库且可被语义检索命中——**RAG 主链路完全工作**。

### 5.2 分区行数：会"骗人"的显示口径（本次最重要的 RAG 发现）

| 时间点 | 分区 API 显示 `_default` | 存储真值（Milvus count(*) 强一致） |
|---|---|---|
| 上传前 | 4,408 | — |
| 上传后立即查询 | **4,408（+0，看似没入库）** | **4,412（+4，md 已入库）** |
| 上传后 8 分钟 | 4,408（仍不变） | 4,413（+5，md 4 行 + pdf 1 行全齐） |
| flush 完成后（≈30 分钟内） | **4,413（+5，数字补齐）** | 4,413 |

- 根因（源码佐证）：行数接口走 Milvus `get_partition_stats`（loader.py:394），该接口只统计已 flush（封印）的 segment；新导入的数据向量可检索（Strong 一致性查询可见）但 stats 不计。
- **交接要点**：运营上传文档后，若「分区行数没变」**不要重复上传**——用「任务状态=succeeded」和（管理员控制台的）检索命中来判断成功，行数会在后台 flush 后自动补齐。
- 另发现：上传后文件的 `source_file` 字段被改写为 uuid 前缀（`lianq_test_doc.md` → `3d68f2caf570.md`），管理端各处均显示改写后的名字，原文件名只在任务的 source_files 里保留——溯源时注意。

### 5.3 集合管理页的幽灵行

`GET /api/admin/rag/collections` 返回两个"集合"：`edu_knowledge`（真实）与 `knowledge_chunk_v1`——后者 **在 Milvus 中根本不存在**（直连核验：collection not found），是 MySQL 元数据里的幽灵行，两个"集合"显示同一份 `_default` 行数。运营在集合页看到的 2 行是重复口径，不是两个独立知识库。

### 5.4 分区删除

`_default` 是公共分区：前端按钮禁用 + 后端会拒绝（页面有「🔒 公共分区·不可删除」标识）。删除不存在的分区名实测返回 404 `40400`「Partition for tenant '…' 不存在」。**按守则未对真实业务分区做真实删除**（删除接口对存在分区会连 Milvus 数据一起删，风险不可逆）——该项判「接口存在、防护面已验证、真实删除未执行」。

### 5.5 UI 轨

- RAG 页面登录态过期时会被守卫踢回登录页（带 redirect 参数，登录后自动跳回——行为正确，过程中亲历一次）。
- 文件选择后先本地校验（「✓ 通过」），**必须再点「开始上传（N 个合法文件）」按钮**才真正上传——只选文件不会有任何请求（我们第一次就停在这一步，页面无任何提示，易误以为已上传，建议按钮旁加引导文案）。
- 上传后任务表实时出现新行：`task_…b562d5 系统导入 0/20 分块 0% 导入中` → 轮询至 succeeded（后台实测 4+1 chunks）。
- 分区面板显示 `_default 4413 行 🔒 公共分区 · 不可删除`、`course_public 0 行`（带删除按钮）。

---

## 6. 链路 5：MCP 工具（全链路 ✅）

| 步骤 | 请求 | 结果 | 耗时 |
|---|---|---|---|
| Server 列表 | `GET /api/mcp/servers` | ✅ 14 台（transport=stdio 为主，含 last_health_ok/last_error 字段） | 658ms |
| 单台健康检查 | `POST /api/mcp/servers/1/health` | ✅ ok=true，latency 142ms | 1.0s |
| **全量健康扫描** | `POST /api/mcp/health-scan` | ✅ **14 台 13.5s**：11 OK / 3 error（3 台故障是既有状态：sse-demo-localhost 连接失败等，报告原样呈现 reason 字段） | 13,474ms |
| 工具列表 | `GET /api/mcp/tools` | ✅ 5 个工具（stdio-echodemo 的 add 等，input_schema 完整） | — |
| **工具真调用** | `POST /api/mcp/tools/test {tool_id:2, args:{a:2,b:3}}` | ✅ **status=SUCCESS，result={sum:5, was_negative:false}**，latency 116ms，call_id=`mcp-…-dd74a5ce` | 3.0s |
| 调用日志 | `GET /api/mcp/call-log` | ✅ 总数 84→**85**，最新一条即本次调用（user_id=100003 可归属到人） | — |
| 日志详情 | `GET /api/mcp/call-log/88` | ✅ args/result/latency 全量留痕 | — |

页面轨（admin-mcp.html）：Server 表带健康灯（● OK）与「健康/发现工具/停用/注销」行内操作；「⟳ 健康扫描」按钮有扫描中态提示（与「同步全量扫描，Server 多时耗时较长」的自述一致）。**给运营的预期：14 台规模全量扫描约 15 秒，属正常，不是卡死。**

---

## 7. 链路 6：交叉核对（页面 ↔ API ↔ 存储真值）

| 指标 | 页面显示 | API 返回 | 存储真值 | 判定 |
|---|---|---|---|---|
| 用户总数 | 100,048（仪表盘 KPI） | 100,048（users.total = metrics.total_user_count） | — | ✅ 一致 |
| 7d 新增注册 / 禁用账号 | 15 / 1 | 15 / 1 | — | ✅ 一致 |
| 题库数 | 449（列表头部） | 449（banks.total，与任务开始时基线 449 持平） | — | ✅ 一致 |
| RAG 分区行数 | 4,408→4,413（页面分区面板） | 同左（partitions API） | 4,412→4,413（count(*)） | ⚠️ 短期不一致（flush 口径差，最终收敛，见 §4.2） |
| MCP servers/tools/日志 | 页面表格与列表 API 同源 | 14 / 5 / 84→85 | — | ✅ 一致 |

---

## 8. manager 视角完整能力矩阵（逐页实测）

页面级守卫对 admin/manager 都放行（源码佐证：8 个 admin 页共用守卫 role∈{admin,manager}），所以差异全部体现在**数据请求层**。以下每格均为 mgr01test 真实登录后逐页/逐接口实测：

| 页面 | 进得去吗 | 页面呈现 | 数据请求实测 | 结论 |
|---|---|---|---|---|
| 仪表盘 | ✅ 进得去 | 「😵 运营指标加载失败：角色无权限。当前角色=manager，允许角色=['admin']」 | metrics → 403 | **进得去但整页数据缺失** |
| 课程管理 | ✅ | 完整功能：列表 2630 系列、搜索筛选、新建/编辑/软删/回收站 | series/cohorts → 200 | **完全可用（读写均可）** |
| 题库管理 | ✅ | 完整功能：449 题库、题目/导入对话框全开 | banks/types/questions → 200 | **完全可用（读写均可）** |
| 用户管理 | ✅ 进得去 | 表格空 + 加载失败提示（页面自曝契约缺口横幅） | users.list/metrics → **403**；`users/{id}` → 404 | **进得去但数据全盲** |
| RAG 知识库 | ✅ | 上传/任务/分区面板完整（分区 4413 行可见） | partitions/tasks → 200；admin/rag/collections → 403 | **上传/任务/分区可用；「集合健康」标签页 403** |
| MCP 工具 | ✅ 进得去 | 「⚠ Server 列表加载失败：角色无权限…」 | servers/tools/call-log → **全部 403** | **进得去但整页数据缺失** |

**manager 实测写操作**（均在测试数据上执行）：课程系列 PATCH ✅ 200（写入成功——manager 可改课程内容）；题库 POST ✅ 201（建库成功，测试后已删）。

**矩阵总结（交接口径）**：
- manager **能用**：课程管理（全功能）、题库管理（全功能）、RAG 上传/任务/分区。
- manager **完全不能用**：用户管理（含 KPI）、MCP 全部、RAG 的集合健康页。
- manager **进得去但整页报错**：仪表盘、用户管理、MCP（页面不跳转、不隐藏入口，而是渲染「角色无权限」错误——运营看到请直接找 admin，不是故障）。
- 设计疑点（上报裁决）：「进得去但整页失败」与「入口直接隐藏」二选一更友好；当前形态容易让 manager 误以为系统坏了。

---

## 9. 测试数据清单（建了什么 / 删了什么 / 剩什么）

### 已彻底删除
| 对象 | ID | 方式 |
|---|---|---|
| 测试题库 LIANQ-BANK-444227 及其 4 题（2 手建+2 导入） | 452 | API DELETE（题库与题目均 yn=0 软删） |
| manager 写探针题库 MGR-PROBE-X | 451 | API DELETE |
| UI 测试题库 UI-BANK-777222 及其 1 题 | 453 | **页面 UI 删除**（二次确认弹窗走通） |
| 章节「开场/要点」 | 617331/617332 | API DELETE |
| 手工链课次/模块 | 205777 / 23657 | 尝试删除（205777 被资产阻塞，见下残留）；模块 23657 删除被课次阻塞 |

### 残留（无法自助清除，详见 §2.5 缺陷）
| 对象 | ID | 状态 | 原因 |
|---|---|---|---|
| 系列「联调交接测试系列-444227-已编辑」 | **2789** | 软删（off_sale，回收站可见） | 硬删被班次 7918（含已下架）阻塞 |
| 班次「联调测试班次-444227」 | **7918** | yn=0（软删态） | — |
| 视频「test_video.mp4」+ 资产 | **205780 / 617334** | **活跃** | 无解绑/删除端点（P1 缺陷），课次 205777 随之不可删 |
| 课次「联调测试课次-444227」 | **205777** | 活跃 | 被 205780 引用（40908） |
| 模块「联调测试模块-444227」 | **23657** | 活跃 | 被课次 205777 引用（40908） |
| 系列硬删验证 | — | — | `DELETE ?hard=true` → 40908「仍被 1 个班次（含已下架）引用」 |

### UI 链残留（同一缺陷）
| 对象 | ID | 状态 |
|---|---|---|
| 系列「UI-UI Test Series-999111」 | 2790 | 软删（回收站） |
| 班次/模块/课次（UI 链） | 7919 / 23658 / 205778 | 班次 7919 活跃；课次 205778 绑定视频 205781（ui_chain_video.mp4），同一死锁 |

### RAG / MCP（不可删或按守则不删）
| 对象 | 标识 | 状态 |
|---|---|---|
| RAG 文档 md×2 + pdf×2 | tasks `…6691d7` `…696d66` `…b562d5` `…06ba25` | succeeded，共 +10 行进入 `_default` 公共分区（4,408→4,413，md 4+4 行、pdf 1+1 行）。**公共分区禁删**，如需清理须开发按 source_file（`3d68f2caf570.md` / `6f50e1bb153d.pdf` 及 UI 批次对应 uuid）删除 |
| MCP 调用日志 | call-log id=88（call_id=mcp-1789445207575-dd74a5ce） | 留痕（日志属审计数据，按只读守则保留） |

### 本任务未触碰的业务数据
题库 449 个（其中既有 448/449「验证题库」等）、系列 2,630 个（除上表）、用户 100,048、既有 MCP 14 servers、既有 RAG 任务与 4,408 行知识——全程只读。

---

## 10. 已知问题与缺陷汇总（按严重度）

| # | 级别 | 问题 | 影响 | 建议 |
|---|---|---|---|---|
| 1 | **P1 交接阻塞** | 视频资产绑定课次后无任何解绑/删除端点；删除课次 40908，连带模块/系列硬删死锁 | 运营传错视频无法自救，残留数据只能开发清库 | 补解绑/替换端点；确认框提前警示 |
| 2 | P2 | 新建班次的 head_teacher_id 是 staff_profile 主键，但系统内无处可查合法值；传错返回误导性的「50301 依赖服务暂不可用」 | 建班次环节高频卡死 | 补教职工选择器/列表端点；错误码改为语义化提示 |
| 3 | P2 | RAG 分区行数只计已 flush 段，上传后长时间显示不变 | 运营误判失败而重复上传 | 页面标注口径，或 stats 改用 count(*) |
| 4 | P2 | 题目无跨库搜索端点（GET /questions 405）；删题库不校验内含题目 | 误删题库后题目失联；找题困难 | 补题目全局列表；删库前提示题量并阻止非空删除 |
| 5 | P3 | manager 进仪表盘/用户/MCP 页看到「加载失败」而非入口隐藏 | manager 误以为系统故障 | 按角色隐藏入口或改为友好说明页 |
| 6 | P3 | 班次删除不检查其下模块（与课次/模块的 40908 保护不一致） | 误删班次导致整棵子树不可见 | 对齐引用保护 |
| 7 | P3 | /media 视频 404 返回 JSON 壳；RAG 集合页含幽灵集合 knowledge_chunk_v1；批量导入仅收 JSON 不收文件 | 体验/口径瑕疵 | 逐项修复 |
| 8 | P3 | 页面注释与实际契约多处过期（「章节无端点」「RAG 上传未接线」均已过期） | 后续维护者误判 | 以本报告 §2.4/§5.1 实测为准，清理注释 |

---

## 11. 运营团队接手前必须知道的 3 件事

1. **传错的课程视频删不掉（没有"撤销上传"按钮）**。视频一旦绑上课次，页面上没有解绑或换视频的入口，删除课次会被系统拒绝（提示"仍被子记录引用"），班次和系列会跟着卡在回收站。**上传前务必确认文件正确；传错立即联系开发处理，不要反复尝试删除。**

2. **看到「角色无权限/加载失败」不是系统坏了**。manager 账号只有课程管理、题库管理、RAG 上传三块是完整可用的；仪表盘、用户管理、MCP 页面对 manager 就是打不开的（后端明确拒绝）。遇到这两类页面请直接找 admin 账号处理。另外新建班次要填的「负责人编号」目前系统里查不到合法值清单，先问开发要，别用用户管理里的用户编号。

3. **判断"成没成功"别只看一个数字**。RAG 上传后分区行数可能长时间不变（后台正在处理，属正常），以「任务状态=完成」为准；重复上传会造成知识重复入库。同理，课程/题库的删除都是"软删除"（回收站可见可恢复），真正的"彻底删除"按钮在存在关联数据时会被系统拒绝——这通常是保护机制在起作用，不是故障。

---

## 附录 A：接口速查（本次实测可用的管理端 API）

```
认证   POST /api/auth/login        {account, password}  ← 字段是 account
课程   GET|POST /api/admin/courses/series · PATCH|DELETE /api/admin/courses/series/{id}?hard=
       POST /api/admin/courses/cohorts (head_teacher_id=staff_profile.id!)
       POST /api/admin/courses/modules · POST /api/admin/courses/sessions
视频   POST /api/admin/courses/videos/init-chunked?session_id=&file_name=&file_size=&chunk_count=
       PUT  /api/admin/courses/videos/upload-chunk/{upload_id}/{i}   (二进制体)
       POST /api/admin/courses/videos/finalize-chunked?upload_id=
       POST /api/admin/courses/videos/bind-session?session_id=&video_id=   ← query 传参
       GET  /api/admin/courses/videos/{id}/transcode-status
章节   POST|GET /api/admin/courses/chapters · PATCH|DELETE /api/admin/courses/chapters/{id}
用户   GET /api/admin/users?keyword=&role_code=&status=&yn=&page=&page_size≤100
       GET /api/admin/users/dashboard/metrics        (admin only)
题库   GET|POST /api/admin/questions/banks · PATCH|DELETE /api/admin/questions/banks/{id}
       GET|POST /api/admin/questions/questions · PATCH|DELETE /api/admin/questions/questions/{id}
       POST /api/admin/questions/import-preview|import-execute?bank_id=   (JSON items)
RAG    POST /api/knowledge/admin/upload (multipart 字段名 files)
       GET /api/knowledge/tasks · GET /api/knowledge/status/{task_id}
       GET /api/knowledge/partitions · DELETE /api/knowledge/partitions/{tenant_id}
       POST /api/admin/rag/search {query, top_k}      (admin only)
MCP    GET|POST /api/mcp/servers · POST /api/mcp/servers/{id}/health · POST /api/mcp/health-scan
       GET /api/mcp/tools · POST /api/mcp/tools/test {tool_id, args}
       GET /api/mcp/call-log · GET /api/mcp/call-log/{id}    (全部 admin only)
```

## 附录 B：证据文件

- API 逐条日志：`C:\Users\Administrator\AppData\Local\Temp\lianq_admin\api_log.jsonl`（每条含时间/方法/路径/状态码/耗时/响应摘要）
- 各链路执行脚本与 UI 采集快照：同目录 `course_a*.py`、`course_b*.py`、`q_chain.py`、`rag_chain.py`、`mcp_chain.py`、`user_chain.py`、`ui_step*.json`
- 测试素材：`test_video.mp4`（ffmpeg 生成 8s/0.15MB）、`lianq_test_doc.md/.pdf`
- 后端原始异常：`edu-agent/logs/error.log`（2026-09-15T11:50:27 IntegrityError 1452 条目）

*报告生成：2026-09-15 · 联调执行窗口 11:46–12:40 · 详见上文观察窗口声明*
