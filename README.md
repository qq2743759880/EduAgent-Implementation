<h1 align="center">Bili-Study</h1>

<p align="center">真实视频与 PDF → AI 学习资料与习题 → 带来源的课程答疑。</p>

Bili-Study 是面向学生、教师和课程管理员的 AI 学习系统。管理员导入本地视频、Bilibili 链接或 PDF；学生看课、读笔记、按章节回看、做相关练习，并向 Course Tutor 提问。

**技术核心：FastAPI / Python · Next.js / React · LangGraph / Harness · BGE-M3 / Milvus · MinerU / Neo4j · OpenTelemetry / Jaeger。**

## 阅读导航

[核心功能](#核心功能) · [系统架构](#系统架构) · [真实运行画面](#真实运行画面) · [25 页画廊](#学生端与管理端页面画廊) · [功能与边界](#功能全景与验证边界) · [首次运行](#快速开始) · [实际操作](#管理员生产与学生学习) · [模块职责](#模块职责与正式知识) · [配置](#配置与部署边界) · [失败恢复](#失败恢复与数据保护) · [开发历史](#开发历史与发布范围)

## 核心功能

| 使用者得到什么 | 系统怎样实现 |
|---|---|
| 视频自动成为可学习的课程 | 字幕 / ASR → 总结、笔记、章节、时间字幕、节点导图与本课习题 |
| 基于本课内容提问与回看 | 授权 StudyContext、正式版本检索、来源引用与视频时间跳转 |
| 上传讲义后即可基于材料答疑 | MinerU → Document IR → BGE-M3 → 既有 Milvus RAG；保留页与分块来源 |
| 练习、解析与错题复习 | 已发布题库、即时判分、解析、错题记录和原题重做 |
| 看清 AI 请求实际走了哪些步骤 | LangGraph / Harness、检索和模型调用的真实 OpenTelemetry / Jaeger Trace |
| 管理员可处理失败而保留课程 | 阶段状态、重试、不可变资料、旧 READY 版本保护；派生失败不影响原视频 |

## 系统架构

![Bili-Study 服务与存储架构：业务、Agent、视频与文档 RAG、存储和观测](docs/architecture/containers.png)

| 层 | 技术栈与职责 |
|---|---|
| 页面 / API | Next.js 16、React 19、TypeScript、静态业务页；FastAPI、Python 3.11、Pydantic、JWT、SSE |
| Agent | LangGraph 九节点、SixNodeHarness、LangChain Core / OpenAI-compatible 模型、MCP；上下文整理、压缩、缓存、记忆、Checkpoint / HITL |
| 视频 / 文档 | yt-dlp、ffmpeg / ffprobe、faster-whisper；MinerU、SourceAsset、Document IR、结构化 Artifact |
| RAG / 图谱 | BGE-M3、PyTorch CPU / CUDA、Milvus dense+sparse、Hybrid / RRF / reranker、Neo4j |
| 数据 | MySQL / SQLAlchemy / Alembic：业务与正式发布；Redis：上下文、任务、锁；MinIO：资产；MongoDB：事件 |
| 观测 / 验证 | OpenTelemetry / OTLP、Jaeger、Prometheus、日志；pytest、Vitest、Playwright、GitHub Actions |

```text
 管理员导入视频 / PDF                       学生学习 / 提问
          |                                      |
          v                                      v
 字幕 / ASR / MinerU                     FastAPI + 授权 StudyContext
          |                                      |
          v                                      v
 Artifact / Document IR --> BGE-M3 --> Milvus Hybrid / RRF / rerank
          |                                      |
          v                                      v
 MySQL: READY 正式版本权威                带来源回答 / 时间跳转
 Neo4j: 知识关联投影                      LangGraph / Harness: 普通问答
 MinIO: 原件与派生资料                    Redis / MongoDB: 状态与事件
          +--------- OpenTelemetry / Jaeger ---------+
```

LangGraph 控制九节点流程，六个核心节点委托 SixNodeHarness 实现；问候可短路，反思可循环。**本课答疑走授权课程分支，不把它描述成每次完整运行九节点。** Neo4j 是关联投影，Milvus 是主 RAG；两者不争夺正式发布权威。

## 真实运行画面

### 上传 PDF，学生引用新材料回答

2026-10-07 实机操作：管理员上传仓库提供的 [课堂 PDF](bili-study-frontend/public/samples/bili-study-cache-lab-20261007.pdf) → MinerU 解析 → Milvus 入库 / Neo4j 投影 → 学生提问。答案引用材料中的 **37 秒**，并解释为什么 TTL 不能保证一致性；37 秒是课堂练习参数，不是行业标准。

![真实管理员 PDF 解析：MinerU 版面块与 Neo4j 文档图谱](assets/showcase-evidence/pdf-rag.png)

![真实学生根据新上传 PDF 回答，并引用讲义来源](assets/showcase-evidence/student-answer.png)

### 视频生产与正式版本

管理员从现有课程管理页上传、选择已绑定视频或输入 Bilibili 链接，系统处理字幕 / ASR、资料、习题、发布与入库。向量已入库不等于学生已可见：只有 READY publication 成为正式视频证据，新版失败仍保留旧版和播放器。

![视频生产、失败恢复、RAG 入库与正式 READY 生命周期](docs/architecture/video-production.png)

### 图谱、Agent Trace 与错题

![Neo4j Browser 中的真实文档分块与知识点关系](assets/showcase-evidence/neo4j.png)

![真实 LangGraph 请求执行 Trace，展示检索、节点与模型调用](assets/showcase-evidence/langgraph.png)

![真实学生作答、判错、解析与错题记录；旧截图保留 EduAgent 标识](assets/showcase-evidence/quiz.png)

## 学生端与管理端页面画廊

下面直接展示 25 个 standalone 页面。**这些是匿名化离线接口快照，登录、写操作和聊天属于回放，不含真实视频与在线模型**；不能拿离线模拟成功代替上面的实机证据。旧快照的空态或失败状态按事实保留。


<table><tr><td width="50%"><b>登录注册</b><br><img src="assets/page-gallery/login-register.jpg" alt="登录注册：匿名化离线页面预览" width="560"></td><td width="50%"><b>学习仪表盘</b><br><img src="assets/page-gallery/dashboard.jpg" alt="学习仪表盘：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>课程中心</b><br><img src="assets/page-gallery/courses.jpg" alt="课程中心：匿名化离线页面预览" width="560"></td><td width="50%"><b>课程详情</b><br><img src="assets/page-gallery/course-detail.jpg" alt="课程详情：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>视频学习</b><br><img src="assets/page-gallery/learning.jpg" alt="视频学习：匿名化离线页面预览" width="560"></td><td width="50%"><b>AI 问答</b><br><img src="assets/page-gallery/chat.jpg" alt="AI 问答：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>题库与复习</b><br><img src="assets/page-gallery/practice.jpg" alt="题库与复习：匿名化离线页面预览" width="560"></td><td width="50%"><b>社区</b><br><img src="assets/page-gallery/community.jpg" alt="社区：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>帖子详情</b><br><img src="assets/page-gallery/community-post.jpg" alt="帖子详情：匿名化离线页面预览" width="560"></td><td width="50%"><b>优惠券</b><br><img src="assets/page-gallery/coupons.jpg" alt="优惠券：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>收藏</b><br><img src="assets/page-gallery/favorites.jpg" alt="收藏：匿名化离线页面预览" width="560"></td><td width="50%"><b>我的班次</b><br><img src="assets/page-gallery/my-cohorts.jpg" alt="我的班次：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>成就中心</b><br><img src="assets/page-gallery/achievements.jpg" alt="成就中心：匿名化离线页面预览" width="560"></td><td width="50%"><b>个人中心</b><br><img src="assets/page-gallery/me.jpg" alt="个人中心：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>退款申请</b><br><img src="assets/page-gallery/refund.jpg" alt="退款申请：匿名化离线页面预览" width="560"></td><td width="50%"><b>管理仪表盘</b><br><img src="assets/page-gallery/admin-dashboard.jpg" alt="管理仪表盘：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>课程管理</b><br><img src="assets/page-gallery/admin-courses.jpg" alt="课程管理：匿名化离线页面预览" width="560"></td><td width="50%"><b>课次与视频生产</b><br><img src="assets/page-gallery/admin-course-detail.jpg" alt="课次与视频生产：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>题库管理</b><br><img src="assets/page-gallery/admin-questions.jpg" alt="题库管理：匿名化离线页面预览" width="560"></td><td width="50%"><b>题目编辑</b><br><img src="assets/page-gallery/admin-question-detail.jpg" alt="题目编辑：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>用户管理</b><br><img src="assets/page-gallery/admin-users.jpg" alt="用户管理：匿名化离线页面预览" width="560"></td><td width="50%"><b>RAG 与文档解析</b><br><img src="assets/page-gallery/admin-rag-upload.jpg" alt="RAG 与文档解析：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>MCP 工具</b><br><img src="assets/page-gallery/admin-mcp.jpg" alt="MCP 工具：匿名化离线页面预览" width="560"></td><td width="50%"><b>会话审计</b><br><img src="assets/page-gallery/admin-chat-audit.jpg" alt="会话审计：匿名化离线页面预览" width="560"></td></tr></table>

<table><tr><td width="50%"><b>基础设施与技术演示</b><br><img src="assets/page-gallery/admin-infra.jpg" alt="基础设施与技术演示：匿名化离线页面预览" width="560"></td></tr></table>

全部 25 个页面已在上面直接展示。离线回放只用于体验界面布局，不连接真实后端；实机证据与运行操作在本页分别说明，不需要打开另一份文档。

## 功能全景与验证边界

以下按实际模块展开；“接口可读”“已有实机证据”“待专项复验”不混用。

### 学生产品

| 功能 | 已有实现 | 验证边界 |
|---|---|---|
| 账号与个人画像 | 注册、登录、刷新 Token、角色识别、个人资料、学习目标/身份/偏好与学员档案 | 登录与权限已有实证；资料接口可读 |
| 课程中心 | 分类、关键词、价格/交付模式筛选、排序分页、系列详情、班次、模块/课次与大纲 | 页面/接口存在；真实课程与历史代表课须区分 |
| 报名与我的班次 | 报名关系、班次访问鉴权、课程进度快照、模块/课次完成态、已下架课程已有报名兼容 | 真实学生免费报名/学习已验收 |
| 视频播放器 | 授权播放、Range、播放进度保存、暂停/拖动/章节跳转；原视频与派生资料独立 | 真实媒体已验收 |
| 视频 AI 学习资料 | Summary、AI 笔记、带时间字幕、章节；节点/连线导图、展开子节点、节点详情与回看 | 多视频已有闭环；导图当前有独立节点渲染器 |
| 本课答疑 | StudyContext 授权、课程背景、同课历史、正式版本精确检索、视频引用时间跳转、跨课/越权拒绝 | P1/P3/P26及新增视频已有实证；不是完整 Agent 工具循环 |
| 普通 AI 问答 | SSE 流式回答、非流式问答、多会话、历史、删除会话、引用、检索元数据、失败/降级提示 | 真实知识回答与历史持久化已有实证 |
| 课程题与独立题库 | 正式题库、题型选择、按课程/薄弱知识点取题、正式版本、学生权限、题库专项练习 | 已有实机题库闭环；本次题库列表可读 |
| 作答与错题复习 | 即时判分、解析、幂等作答、冲突答案拒绝、错题记录、到期复习、原题重做、复习时间 | 真实判错/重做已有实证；本次错题列表可读 |
| 视频自动练习 | 编译阶段生成本视频相关题，绑定课次/题库，随正式版本提供，支持补产习题 | 2026-10-07视频验收含 exercise_count=4；不代表所有旧课有题 |
| 词汇复习 | 今日新词/到期词、SM-2 质量评分、等级进度、打卡/正确率 | 前后端已接线；本次进度接口可读，整条学习闭环需专项复验 |
| 编程练习 | 挑战列表/详情、样例运行、隐藏用例提交、分数与递进提示 | 有实现及题目接口；Piston外部服务和完整执行尚需复验；非 Python fallback 含启发式模拟 |
| 数学互动 | 按话题/等级取题、分步反馈、整题规则讲解 | 目前3道内置规则题；不是通用数学推理/题库平台 |
| 学习看板与行动闭环 | 视频打点、学习时长/连续学习、作业提交、考试作答、正确率、掌握度、学习轮次/下一步行动回执 | 学习/作答链已有实证；本次看板与汇总可读；闭环长期收益未证明 |
| 学习路径与推荐 | 个性化路径、下一步学习推荐、难度/兴趣反馈、Neo4j先修路径与环诊断 | 代码及API存在；当前完整路径质量与新学员效果需复验 |
| 知识点思维导图 | 课程图、学科图、个人掌握度着色、前向/后向先修链 | API存在；依赖实际知识点/图谱数据；与视频导图区分 |
| 社区互助 | 版块/热度/关键词、发帖编辑、帖子详情、评论/回复、点赞、收藏、作者和管理员边界 | 前后端已接线，写流程本轮未重验 |
| 成就与激励 | 徽章解锁进度、积分/等级/流水、日周月总排行榜、合法动作触发徽章 | 本次徽章、积分、排行榜读取成功；不能把手动加分当学习效果 |
| 收藏、评价与个人资产 | 课程收藏/取消、已报名课程评价、我的订单/券/班次 | 本次收藏/券/订单可读；评价与取消等写路径需复验 |

### 课程与运营

| 功能 | 已有实现 | 验证边界 |
|---|---|---|
| 课程管理 | 系列→班次→模块→课次 CRUD，资源管理、章节管理、上下架、回收站恢复 | 生产管理员页已使用；不现场演示物理删除 |
| 视频上传与来源获取 | 本地分片上传、服务端 ffprobe/字节与播放格式校验、已有视频身份校验、Bilibili链接/分P、字幕优先/ASR | 真实管理员页面已跑通多类来源；任意平台链接不保证获取 |
| 视频生产生命周期 | 创建任务、自动刷新、真实阶段/失败原因、worker/租约、重试、预览、驳回/审核API、自动发布入库 | 已有正式生产闭环；历史人工审核接口保留 |
| 版本与正式发布 | 不可变 Artifact、SHA/lineage、明确重编、重复点击幂等、旧版本保护、READY唯一可见性、ANN前精确scope | 首次 pending 反例与 ready切换已有实证及回归 |
| 题库与考试管理 | 题库/题目CRUD、五类题型、答案解析编辑/预览、批量导入校验/幂等报告、学生发布/退役、考试组卷/题目快照冻结 | 题库导入和学生发布已有实证；组卷整链待专项复验 |
| 用户管理 | 分页搜索、角色分布、账户启停、角色调整、学员资料 | 管理页/API存在；角色/启停写操作需专用对象验收 |
| 管理员看板与审计 | 用户指标、课程/题库入口、学习事件分析、交易运营汇总；只读会话/历史审计 | 基础设施读取成功；其他聚合数据需按来源复核 |
| 优惠与免费履约 | 优惠券模板/领券/适用券、无限库存但每人一次；Zero-Pay订单 paid/报名active且不建payment_record；零元携券拒绝 | 已有真实验收与回归 |
| 订单、支付、退款和工单 | 服务端金额/库存/幂等、订单详情/取消；支付轮询/回调闸门/对账；退款申请撤销/HITL审批；工单/申诉/满意度 | 订单查询可读；真实支付渠道未验收；退款/工单有实现和部分过渡路径，不做真实资金演示 |

### 知识与数据

| 功能 | 已有实现 | 验证边界 |
|---|---|---|
| 文档上传/解析 | PDF、MD、TXT、DOCX；SourceAsset身份，MinerU文本PDF/OCR，Document IR页/块来源，解析预览 | 真实PDF/MD已有链路证据；复杂公式/表格/VLM未验收 |
| 既有 RAG 入库 | ImportCommand、SourceAsset、IR、chunk准备、BGE-M3、Milvus dense/sparse、tenant/generation/lineage；worker回执/幂等/恢复 | 真实新视频/PDF可召回；保留主RAG，无第二套索引 |
| 检索与答案证据 | Hybrid、RRF、中文分词、reranker、上下文预算、课程权限/元数据过滤、来源引用；轻量关键词扩展 | 真实RAG已有实证；当前HyDE不是完整LLM假设文档；独立reranker sidecar降级、本地CUDA工作 |
| RAG 管理控制台 | collections、检索preset、管理员搜索、审计、任务/分区、文档与graph预览 | 正式页面/API存在；重建/分区删除是管理写能力，本轮不执行 |
| Neo4j 知识投影 | 正式视频/章节/知识点/canonical chunk，文档MENTIONS/RELATED，版本身份；独立图同步；普通RAG有限邻居扩展 | PDF/视频图谱实证；精确视频Tutor不跨图回填；邻接不是推断先修 |

### Agent 实现

| 功能 | 已有实现 | 验证边界 |
|---|---|---|
| 九节点 LangGraph + 六节点 Harness | route/skill/compact/context_edit/plan/fan_out/merge/reflect/answer，问候短路、反思循环，六个核心节点委托Harness | 真实九节点Trace已验收；不是两条独立流水线，不是每请求九次模型调用 |
| 工具与多通道处理 | 意图分流、知识检索、只读NL2SQL、MCP/计算器/学习工具、并行分支汇总、答案/工具回执校验 | 有接线和部分真实请求；并行任务不是已证明多个自主LLM子Agent |
| 上下文与 Prompt Cache | 稳定前缀、前缀签名/缓存统计、context_edit轻量删冗余、token水位、compaction分预算压缩、最近轮保护 | 代码与观测接口存在；不能无实测宣称缓存命中率或成本收益 |
| 个人长期记忆 | 偏好/事实提取、异步记忆队列、同步提取、个性化注入、user_memory_event事件HEAD、历史/rewind、Dream整合 | 当前配置启用；曾有远端提取SSL降级，跨会话提取成功与Dream需新实机证据 |
| Checkpoint与HITL | Redis thread checkpoint/TTL/HMAC；人工确认pending→confirm/reject→resume；工具分类/角色/风险/超时/熔断；退款审批图 | 有实现与有界测试；高风险写工具、进程崩溃恢复不能由普通Chat通过推断 |

### 运行与保护

| 功能 | 已有实现 | 验证边界 |
|---|---|---|
| OpenTelemetry / Jaeger | Chat根span、九节点/Harness属性、retrieval/LLM/tool；视频阶段、PDF解析/embedding/load/Neo4j跨worker父子Trace | 真实Chat/PDF/视频Trace已有证据；旧内存Trace可能重启丢失 |
| Prometheus / 日志 / 基础设施面板 | 请求与耗时指标、缓存/上下文联合看板、OTel快照、按Trace观测事件、结构化日志；六存储与Redis队列/锁/熔断/worker心跳 | 管理端快照本次可读；模型/队列具体运行需对应数据证据 |
| 权限与运行安全 | JWT/bcrypt、admin/manager/student守卫、报名/对象/tenant scope、SSRF/SQL校验、限流/并发/token预算、错误隔离、签名与幂等 | DEBUG=false及越权边界已有实证；不是整体安全认证 |
| 一键启动 / worker恢复 | 模型/存储readiness、原Redis/Jaeger容器恢复、MinerU/Neo4j入口、文档worker心跳、隐藏启动、日志与有界drain停止 | 原生环境已实测；完整空环境Compose尚未验收 |

### 展示资源

| 功能 | 已有实现 | 验证边界 |
|---|---|---|
| 25页 standalone 离线预览 | 15学生/通用页 + 10管理页 + 导航；内联原页面样式/JS，接口快照回放 | 离线界面预览；模拟登录/写成功，不含真实视频/在线LLM，不作为业务PASS证据 |

当前查询扩展是轻量关键词方法，不宣称完整 LLM 假设文档 HyDE。图谱共现关联不等于自动推断先修知识；单次 Trace 时延不代表性能基准。

## 快速安装

当前发布重点是源码与已验证的本地运行方式。需要 **Python 3.11、uv、Node.js 22 或更新版本、npm、ffmpeg / ffprobe**，以及配置好的 MySQL、Milvus、MongoDB、Redis、MinIO、Neo4j、BGE-M3 / reranker 模型和 OpenAI-compatible 模型 API。MinerU 使用独立环境；源文件、模型权重、Cookie、数据库和密钥均不随源码提供。

```powershell
git clone https://github.com/qq2743759880/EduAgent-Implementation.git Bili-Study
cd Bili-Study
uv sync --project bili-study-agent --locked --extra cpu --no-dev
cd bili-study-frontend
npm ci
cd ..
Copy-Item bili-study-agent/.env.example bili-study-agent/.env
```

在私有 `.env` 填写自己的存储地址、凭据、模型路径和 LLM 配置，生成随机 JWT_SECRET 和 API_TOKEN。连接已有实例时必须沿用相同 BGE-M3 模型与业务 schema，不通过启动脚本重建数据库。GPU 环境选 `--extra gpu`，不能同时启用 cpu / gpu。

## 快速开始

已配置的 Windows 本地实例从根目录启动：

```powershell
.\start-bili-study.cmd --no-pause
.\start-bili-study.cmd --no-pause status
```

预期：后端 `/health/ready` 可用、前端 HTTP 200，前端位于 `http://127.0.0.1:3322`、后端 `http://127.0.0.1:9988`。脚本复用可确认的项目进程，真实检查模型、存储与 worker，失败返回非零；它不是空环境安装器。

获得第一个有用结果：管理员登录 → RAG 知识库 → 上传上面的课堂 PDF → 查看解析 / 入库状态 → 学生使用自己的账号在 AI 学习问答提问并查看文档引用。完整的视频、PDF 和练习操作继续在下面展开；停止与失败处理见本页对应段落。

## 管理员生产与学生学习

### 视频：从一个链接或本地文件到本课答疑

1. 管理员登录后进入「课程管理 → 课程详情」，选择班次，创建或展开模块与课次。新建课程只有系列信息，视频入口属于具体课次。
2. 在课次视频区域上传本地视频、选择已绑定视频，或填写有权使用的 Bilibili 链接和分 P。已绑定视频可以直接生成或明确重编，不需要重建课次、重复上传。
3. 点击「生成 AI 学习资料」。同一任务接口处理字幕优先 / ASR、总结、笔记、章节、字幕、思维导图与相关习题；页面自动刷新真实阶段、更新时间、worker 状态和失败原因。
4. 系统对当前资料版本完成自动授权、发布与既有 RAG 入库。普通重复点击保持幂等；明确重新生成产生可追踪的新版本。历史人工预览、驳回、批准接口保留，并绑定实际资料版本。
5. 区分“生成了资料”“资料已发布”“知识已可检索”。学生正式资料以 READY 为准；正在入库或失败的新版本不能挤占正式证据。
6. 学生使用自己的账号正常报名，在「我的班次 / 学习页」播放视频、查看笔记 / 字幕 / 导图，点章节或引用回到对应时间，再通过「本课答疑」提问。相关习题从「本课练习」或「题库 / 复习」使用。

原生字幕 P1 / P3、P26 显式真实 ASR、本地上传、已有视频重编，以及 Python、Agent 记忆、RAG 来源已有验收记录。它们证明通用生产链的复用，不表示所有历史目录都已有真实视频、资料与题目。Bilibili 被权限或网络拒绝时如实失败，不绕过平台限制，可改用有权使用的本地文件。

### PDF：上传讲义，回答讲义后面的具体内容

1. 管理员进入「RAG 知识库」，提交本页提供的课堂 PDF，查看上传和解析任务。
2. ParserWorker 调用独立 MinerU CLI，产生带页、版面块与来源的 Document IR；IngestWorker 用同一 BGE-M3 做分块向量化并加载 Milvus，Neo4j 同步关联投影。
3. 从任务记录查看处理状态、「解析与图谱」和本次 Trace；不要仅凭上传成功判断知识已经可检索。
4. 学生进入「AI 学习问答」，询问“讲义中的 TTL 是多少秒？为什么仅靠 TTL 不能保证一致性？single-flight 解决什么问题？”，核对答案是否引用新上传的文档。

本页实机结果包含 3 个 Milvus chunk，证明了从版面解析到来源引用的闭环。此前虽然召回了文档，知识快路径每段裁到 120 字符而漏掉后面的答案；修复后复用带预算的原文格式化，重复提问得到正确来源。这里的数值描述本次输入，不是系统性能或规模指标。

### 练习与错题：把一次学习变成可复习记录

学生从已发布题库或本课练习取题 → 提交答案 → 查看判分和解析 → 错题记录 → 到期复习或重做原题。视频编译会生成并绑定相关习题，已有验收包含一节视频的 4 道相关题；未补产的历史课程仍可能没有题。并发重复作答按幂等规则处理，冲突答案不会伪装成新一次成功提交。

### 看真实 Agent、图谱和文档执行

管理员「技术演示 / 基础设施」显示存储、模型、队列、worker 和观测状态，可打开实例配置的 Neo4j Browser 与 Jaeger。Neo4j 可以查看文档分块、知识点、视频和章节关联；Jaeger 选择本次任务记录的 Trace，检查检索、节点、模型调用与跨 worker 父子 span。MinerU 结果在 RAG 管理的解析预览中查看。历史 Trace 若采用内存存储，重启后可能丢失；不要把空的旧链接当成当前请求没有执行。

## 模块职责与正式知识

系统是一个模块化 FastAPI 后端与一个 Next 工程。静态业务页和 React 路由共享 API；LangGraph、Harness、视频 worker 是 API 内模块，不是另外三套独立产品。文档 Parser / Ingest / Reconciler 使用独立进程，MinerU 使用独立 CLI 环境，避免替换主 Python 3.11 环境的 PyTorch。

![学生、教师、内容来源与模型服务的系统上下文](docs/architecture/context.png)

| 模块 / 存储 | 负责什么 | 不承担什么 |
|---|---|---|
| MySQL | 用户、课程、报名、Chat 会话消息、生产任务、正式发布指针 | 不凭向量状态推断教学版本已经发布 |
| MinIO | 原视频、文档源文件、不可变 IR 与派生资料 | 不以生成资料覆盖原视频 |
| Milvus / BGE-M3 | dense / sparse 检索、来源、tenant、generation 与 lineage | 不另建第二套主 RAG；active 不等于正式可见 |
| MongoDB | 学习事件、既有文档与产物侧存储 | 不是 Chat 历史权威 |
| Redis | 队列、缓存、StudyContext、心跳、租约与锁 | 心跳或队列标记不能替代阶段成功回执 |
| Neo4j | 从正式 chunk 投影文档、视频、章节与知识点关联 | 不是业务权威，不替代 Milvus |
| LangGraph / Harness | 普通 Chat 的 route → skill → compact → context_edit → plan → fan_out → merge → reflect → answer | 不把九节点声称为九次模型调用，也不声称六节点是另一条平行流水线 |
| StudyContext / Tutor | 服务端授权、课程背景与正式版本精确检索 | 标题背景不能代替课程证据；不强行跑完整普通 Agent 工具循环 |
| OpenTelemetry / Jaeger | Chat、视频、Parser / Ingest / 图同步的 span 与跨阶段父 Trace | 静态架构箭头、旧截图不能证明一条新请求已经执行 |

视频版本的正式 authority 是 READY publication。ANN 候选产生前，按 **video_id、generation、artifact_sha256** 精确限制视频证据；普通课程和 Question 的合法兼容检索保留。

| 正式版本状态 | 学生资料 | Tutor 视频证据 | 播放器 |
|---|---|---|---|
| 首版 pending / failed，没有历史 READY | 尚无正式 AI 资料 | 排除 pending generation，普通课程知识仍可检索 | 原视频继续可播放 |
| A 已 READY，B pending / failed | 继续使用 A | 精确限制在 A，B 不进入候选 | 原视频继续可播放 |
| B 入库回执通过并完成 activation | 切换到 B | 精确限制在 B | 原视频保持独立 |

## 配置与部署边界

已验证路径是配置好存储、模型和权限的本地实例。源码安装不自带业务数据、原视频、模型权重或账户；`.env.example` 只给字段和占位，实际值写入不提交的私有 `.env`。

| 配置组 | 当前字段 | 配置要点 |
|---|---|---|
| 业务 / 身份 | `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_DATABASE`、`MYSQL_USER`、`MYSQL_PASSWORD`、`JWT_SECRET`、`API_TOKEN` | 指向自己的实例，生成随机密钥，实际管理员/学生验收使用 `DEBUG=false` |
| 事件 / 任务 / 对象 | `MONGO_URI`、`REDIS_URL`、`MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY` | 保留队列、对象与业务关系；不能只复制源码就声称迁移了资料 |
| 主 RAG / 模型 | `MILVUS_HOST`、`MILVUS_PORT`、`BGE_M3_PATH`、`RERANKER_PATH`、`EMBED_DEVICE`、`RERANKER_DEVICE` | 入库与查询使用同一个 BGE-M3；CPU/GPU extras 互斥，不混用不同 embedding 接管旧集合 |
| 生成模型 | `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL_FAST`、`LLM_MODEL_STRONG` | 使用自己的 OpenAI-compatible 服务与实际可用模型；不提交 API Key |
| Agent | `STREAM_VIA_GRAPH` | 普通 Chat 的流程开关；Course Tutor 保留授权课程分支 |
| 文档 / 图谱 | `MINERU_ENABLED`、`MINERU_EXECUTABLE`、`NEO4J_ENABLED`、`NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD` | MinerU 独立环境；图谱故障不能让已发布视频失去播放能力 |
| 观测 | `OTEL_EXPORTER_OTLP_ENDPOINT`、`JAEGER_UI_URL` | 分清 OTLP 接收地址与浏览器 UI；任务记录指向本次真实 Trace |
| Bilibili | `VIDEO_BILIBILI_COOKIE_FILE` | 需要登录时提供自己有权使用的 Cookie 文件；缺权限时如实失败，Cookie 不进 Git |

### 独立 Compose 方案：已有实现，完整首次启动待验收

可迁移方案旨在创建独立空环境，不接管旧数据库或向量。初始化生成私有配置、随机密码和首次管理员；只接受空库的 schema 校验，重复初始化拒绝覆盖。已有安装标记、卷和密码需保留，后续 schema 变化走审核过的迁移，不能靠删卷恢复。独立空 MySQL 初始化与重复启动已有通过记录，**完整 Compose 的视频 / PDF / RAG 首次启动尚未通过**，不能和已验证的原生运行路径混为一谈。

```sh
# 可选的独立环境方案，尚不是已完整验收的默认启动路径
python deploy/portable.py init
# 在私有 deploy/.env.portable 中配置自己的 LLM、模型目录与端口
python deploy/portable.py check
python deploy/portable.py up
python deploy/portable.py status
```

模型目录为 `models/bge-m3`、`models/bge-reranker-v2-m3`、`models/faster-whisper-base`，权重需自行合法获取。Compose 默认回环绑定；前端同源代理连接后端。该方案中的 Neo4j Browser / Jaeger / MinIO Console 默认端口分别为 17474 / 17686 / 19001，**不同于现有原生实例端口**，密码从私有配置读取。文档 workers 为独立服务，用真实 Redis 心跳判断状态。旧 MinIO 镜像不可拉取时方案从指定官方源码构建，保留 AGPLv3 归属。

扫描页 OCR 可能首次下载模型；复杂公式、表格和 VLM 解析没有完成验收。已有 Docker overlay2 / 引擎中断及依赖下载 hash mismatch 记录，不通过关闭校验、重置 Docker 或删除旧卷掩盖。开发依赖告警与完整容器实测仍需单独处理，不能由源码发布成功推断已解决。

## 失败恢复与数据保护

| 看到的情况 | 应怎么处理 | 必须保持的边界 |
|---|---|---|
| 来源探查 / 获取失败 | 在任务中查看实际原因，确认链接、分 P、权限和网络；必要时改用合法本地上传 | 不宣称任意 Bilibili 链接都能获取，不绕过平台限制 |
| 转写或编译失败 | 从记录中的失败阶段重试，检查 ASR / 模型服务 | 原视频独立；已有 READY 资料继续使用 |
| 产物已封存，RAG 入库失败 | 复用当前不可变产物重试入库；查看 Parser / Ingest 回执和 worker | 不重新采集已有原件，不把 pending 向量当正式资料 |
| worker 离线或租约过期 | 查看真实心跳与租约状态，使用项目恢复逻辑 | 不抢占仍在运行的任务，不用假百分比表示成功 |
| 旧预览发出审核请求 | 服务端按版本身份判断，过期请求拒绝 | 旧页面不能批准或驳回后来生成的新产物 |
| 图谱 / 资料 API / Trace 故障 | 分别诊断派生服务；Trace 使用本次任务记录 | 不禁用播放器；旧内存 Trace 消失不等于当前业务失败 |

停止原生实例前确认没有正在生产 / 入库的任务，遵守 drain 和租约，再执行 ` .\stop-bili-study.cmd app `。独立 Compose 保留数据卷，停止不使用 `down -v`；不要强杀入库或重新生成密码接管旧卷。

源码包不是业务数据备份。已有实例恢复需要同时保留 MySQL 业务关系、MinIO 对象、Milvus 数据和模型身份；Neo4j 与 AI 派生资料可从正式资产重建。密钥、Cookie 和备份单独保管。保护既有 ImportCommand / SourceAsset / IR / BGE-M3 / Milvus / StudyContext，不 DROP 集合、不批量删除旧向量、不全量重新 embedding、不建第二套主 RAG。

## 开发历史与发布范围

项目从 EduAgent 演进为 Bili-Study，沿用已有课程、报名、权限、交易和 RAG 契约，产品方向聚焦真实课程与 Video Knowledge Compiler。目录使用 `bili-study-agent` / `bili-study-frontend`；内部 `Edu`、`edu-agent`、`EAPI` 保留数据与代码兼容，不代表另一个旧产品入口。

原 TASK、旧设计、验收响应及改名前原件保存在项目外冷归档，带文件清单、SHA-256 与恢复工具，**没有删除**。它们用于按需核对开发历史，不自动成为当前规范，也不随公开源码发布敏感配置、业务行和过时机器路径。

GitHub 更新通过新增提交保留已有历史，不强推或改写旧提交。公开内容包括源码、MIT 许可、说明、架构和匿名化展示；不包含真实凭据、Cookie、课程媒体、权重、业务数据库或私有开发归档。发布源码、备份业务数据、完整跨机器部署是三种不同交付，当前不能用第一项成功代替后两项验收。

## 许可

Bili-Study 自有源码使用 [MIT](LICENSE)。课程视频、模型权重、MinerU、MinIO 和其他第三方组件遵循各自许可；这项授权不重新许可它们。[第三方声明](THIRD-PARTY-NOTICES.md)。[展示素材与归属清单](showcase/ASSETS.md)仅供素材核对，项目说明已经在本页完整展开。
