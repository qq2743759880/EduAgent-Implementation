# 当前架构

Bili-Study 是模块化 FastAPI 后端与一个 Next.js 工程。静态业务页与 React 路由共用 API；Python 3.11。视频能力复用 BiliSum 的必要核心适配，没有另建认证、视频库或主 RAG。

## 事实源

| 存储 | 职责 |
|---|---|
| MySQL | 用户、课程、报名、Chat 会话消息、生产任务、正式发布指针 |
| MinIO | 原视频、文档源文件、不可变 IR 与派生资料 |
| Milvus | BGE-M3 dense / sparse 向量、来源与版本元数据 |
| MongoDB | 学习事件、已有文档与产物侧存储；不作为 Chat 历史权威 |
| Redis | 队列、缓存、StudyContext、worker 心跳及锁 |
| Neo4j | 从正式 chunk 投影的知识关联；非主 RAG、非业务权威 |

## 服务边界

后端 `app/main.py` 管理 API、模型与视频 worker；文档 Parser / Ingest / Reconciler 是独立进程，复用既有 ImportCommand / SourceAsset / IR。MinerU 在独立 CLI 环境解析 PDF，避免替换主环境的 PyTorch。OpenTelemetry SDK 向 Jaeger 发送 OTLP，跨 Parser / Ingest 保留父 Trace。

普通 Chat 在 `STREAM_VIA_GRAPH=true` 时进入 LangGraph。九个节点为 route、skill、compact、context_edit、plan、fan_out、merge、reflect、answer；六个核心节点委托 SixNodeHarness。问候可走短路，reflect 可循环；九节点不表示九次模型调用。Course Tutor 通过经授权的 StudyContext 使用独立课程分支，不执行完整工具循环。

## 正式知识与播放

学生读取与检索采用 READY publication。向量 active 不能单独使视频资料正式可见。ANN 前按 video_id、generation、artifact_sha256 限制视频证据；普通课程与题库兼容检索保留。新版本失败时旧 READY 继续可用。原视频播放不依赖转写、编译、图谱或入库成功。

架构细图：[系统上下文](architecture/c4-context.md)、[服务与存储](architecture/c4-containers.md)、[交互图与生产流程](architecture/README.md)。具体生产实现见 [视频知识能力](VIDEO-KNOWLEDGE-COMPILER.md)。

界面资源的用途与原文件见 [页面素材与课程封面](UI-ASSETS.md)。
