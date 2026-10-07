<h1 align="center">Bili-Study</h1>

<p align="center">真实视频与 PDF → AI 学习资料与习题 → 带来源的课程答疑。</p>

Bili-Study 是面向学生、教师和课程管理员的 AI 学习系统。管理员导入本地视频、Bilibili 链接或 PDF；学生看课、读笔记、按章节回看、做相关练习，并向 Course Tutor 提问。

## 阅读导航

[核心功能](#核心功能) · [系统架构](#系统架构) · [真实运行画面](#真实运行画面) · [25 页画廊](#学生端与管理端页面画廊) · [功能与边界](#功能全景与验证边界) · [快速开始](#快速开始)

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

下载后可直接打开 [完整 HTML 展示入口](showcase/index.html) 和 [离线页面说明](showcase/README.md)，进一步体验界面。也可在仓库根目录运行 `python -m http.server 18010`，访问 `http://127.0.0.1:18010/showcase/index.html`。静态页面不依赖业务后端。

## 功能全景与验证边界

| 领域 | 功能 | 当前边界 |
|---|---|---|
| 学生学习 | 账号画像、课程筛选与报名、班次、播放器、笔记/字幕/章节/导图、本课与普通问答、题库/错题、学习进度 | 视频、PDF、问答、题库已有实机证据；不是所有历史课程都已补齐内容 |
| 辅助学习 | SM-2词汇、编程挑战、数学分步反馈、学习推荐、先修链、掌握度知识图 | 需专项复验；数学目前少量规则题，非 Python 编程降级含启发式模拟 |
| 课程运营 | 课程/班次/模块/课次管理、视频导入、生产阶段、重试、自动发布、版本保护、题库导入/发布、考试快照 | 视频与题库生产已有实证；组卷整链需要专项复验 |
| 社区与激励 | 帖子/评论/回复/点赞、收藏/评价、徽章、积分、排行榜 | 前后端有接线；本轮主要验证读接口，未重验所有写操作 |
| 交易与服务 | 优惠券、无限库存每人一次、Zero-Pay、订单、支付闸门、对账、退款与工单 | 免费履约已验收；真实支付渠道未验收，不做真实资金演示 |
| Agent与记忆 | 工具/MCP、只读NL2SQL、上下文压缩与cache、长期记忆、历史/rewind/Dream、Checkpoint/HITL | 有实现和部分实证；长期记忆、崩溃恢复与成本收益需新专项证据 |
| 知识与运行 | MinerU/IR、RAG管理、Neo4j投影、Trace、指标日志、权限与隔离、一键启动/worker恢复 | 真实PDF/视频/Trace有证据；复杂PDF及完整空环境Compose未验收 |

[完整 43 组能力盘点与当前 API](docs/FEATURE-INVENTORY.md)。当前查询扩展是轻量关键词方法，不宣称完整 LLM 假设文档 HyDE。图谱关联不等于自动推断先修知识；单次 Trace 时延不代表性能基准。

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

获得第一个有用结果：管理员登录 → RAG 知识库 → 上传上面的课堂 PDF → 查看解析 / 入库状态 → 学生使用自己的账号在 AI 学习问答提问并查看文档引用。视频入口在课程详情的课次视频区域；创建课程后仍需创建模块与课次。停止使用 `.\stop-bili-study.cmd app`，遵守 worker drain，不强杀正在入库的任务。

## 深入文档

| 内容 | 入口 |
|---|---|
| 架构与交互图 | [系统架构](docs/architecture/README.md)、[模块职责](docs/ARCHITECTURE.md) |
| 实机操作与视频生产 | [操作说明](docs/DEMO.md)、[Video Knowledge Compiler](docs/VIDEO-KNOWLEDGE-COMPILER.md) |
| 全部界面与能力 | [25 页 HTML 展示](showcase/index.html)、[功能盘点](docs/FEATURE-INVENTORY.md) |
| 安装边界与开发历史 | [部署参考](docs/PORTABILITY.md)、[历史说明](docs/HISTORY.md) |

完整跨机器部署与复杂 PDF 公式 / 表格 / VLM 解析尚未完整验收。Bilibili 获取受权限与网络限制，不保证任意链接成功；本项目不包含原始课程媒体、模型权重、Cookie、业务数据库或私有凭据。

## 许可

Bili-Study 自有源码使用 [MIT](LICENSE)。课程视频、模型权重、MinerU、MinIO 和其他第三方组件遵循各自许可；这项授权不重新许可它们。[第三方声明](THIRD-PARTY-NOTICES.md)。
