# Bili-Study

真实视频课程、AI 学习资料、课程范围答疑与练习。FastAPI / Python 3.11、Next.js、既有 BGE-M3 + Milvus 混合检索、MongoDB、Redis、MinIO、Neo4j、LangGraph / Harness、MinerU 和 OpenTelemetry。

以下是待完整验收的可迁移部署方案。它设计为创建独立的空环境，不需要原作者的 VMware、Windows 盘符、数据库快照或私有账户。不会自带历史课程、学生记录、视频、向量或 API 密钥。真实内容通过项目管理员页面导入。

## 最短安装路径

首版可迁移部署面向 x86-64 Windows / Linux；其他架构尚未实测。

适用 Windows Docker Desktop（Linux containers）、Linux Docker Engine。Docker Compose v2、Python 3.11，建议给 Docker 至少 12GB 内存、30GB 可用磁盘。应用默认使用 CPU，因此不要求 CUDA；完整 ASR 的速度取决于机器。第一次构建会下载 Python/Node 依赖与镜像，需要网络。

1. 在项目根目录生成独立私有配置：

   ```sh
   python deploy/portable.py init
   ```

   编辑 `deploy/.env.portable`：填写自己的 `LLM_API_KEY`、OpenAI-compatible `LLM_BASE_URL` 和实际可用的 `LLM_MODEL_FAST / LLM_MODEL_STRONG`。数据库、JWT、管理员密码由初始化程序分别随机生成；重复初始化拒绝覆盖。此文件不能提交。

2. 准备模型目录，结构为 `models/bge-m3`、`models/bge-reranker-v2-m3`、`models/faster-whisper-base`。可以使用已合法下载的权重，也可以下载公共模型：

   ```sh
   uv sync --project bili-study-agent --locked --extra cpu --no-dev
   uv run --project bili-study-agent --frozen --extra cpu python bili-study-agent/scripts/download_models.py --models-dir models
   ```

   下载可能是数 GB；权重不进 Git。可以在 `init` 时传 `--models-dir /your/model/directory`，或编辑私有配置中的 `EDU_MODEL_DIR`。GPU 的原生安装使用 `--extra gpu`，CPU/GPU extras 互斥，不能同时启用。不能把不同 embedding 模型接入同一既有知识集合。

3. 检查并启动：

   ```sh
   python deploy/portable.py check
   python deploy/portable.py up
   python deploy/portable.py status
   ```

   默认前端 `http://127.0.0.1:3322`，后端 `http://127.0.0.1:9988`。若与已有项目冲突，在私有配置改 `FRONTEND_PORT / BACKEND_PORT`。浏览器 API 通过前端同源代理，后端在 Compose 网络内访问数据库。所有对宿主暴露的端口默认仅绑定回环地址。

4. 用私有配置的 `ADMIN_ACCOUNT / ADMIN_PASSWORD` 登录，在管理端创建课程／课次、上传视频或填写 Bilibili 链接；在 RAG 知识库上传 PDF 或文本。学生通过正常注册建立自己的账号，免费报名后进入学习页。

## 数据库与文件

MinIO 上游旧 Docker 镜像标签已无法拉取。安装包从官方 `RELEASE.2025-10-15T17-29-55Z` 源码构建，保留 AGPLv3 归属，避免依赖作者本地缓存或未知第三方镜像；首次构建需要下载 Go 工具链和模块。[官方发布与构建说明](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z)。

- 初始化器使用 `deploy/schema.sql`：当前运行 schema 的纯 DDL，包含列、索引与约束，不包含业务行或原数据库 AUTO_INCREMENT 计数。安装前校验 SHA-256，只接受空库。
- 创建一个初始管理员、一个本地机构和五种题型，不预置“已验收课程”。密码用 bcrypt 保存。
- MySQL、Milvus、Redis、MongoDB、MinIO、Neo4j 各有独立 Compose 命名卷；旧数据库／向量／图谱不会被接管。首次安装与已有业务数据迁移是不同操作。
- 已初始化环境通过安装标记识别，重复启动不会改密码或重置数据。源码 schema 更新后拒绝悄悄替换现有库；需明确迁移。历史 Alembic baseline 不完整且有两条分支，安装器对完整 schema 记录两条现有 heads，后续迁移应继续按实际版本审核。
- 同一机器重启已有可迁移实例时保留原 `deploy/.env.portable`。重新生成密码不能接管旧卷，初始化器会拒绝与已安装管理员不一致的配置；不要通过删除卷绕过这一检查。
- 视频原文件和派生资料独立。图谱或编译失败不影响原视频播放。新版只有 READY 后才成为学生正式资料。

## 技术演示入口

若 Bilibili 要求登录，在本机 `private/bilibili-cookies.txt` 放置自己有权使用的 Netscape Cookie，私有配置设置 `VIDEO_BILIBILI_COOKIE_FILE=/run/edu-secrets/bilibili-cookies.txt`。该目录只读挂载，Cookie 不进入镜像或 GitHub；Linux 下需让容器 UID 1000 可读。没有 Cookie 时尝试匿名获取，平台拒绝会在管理员页面如实报告，可改用本地上传。

管理员导航的「技术演示」提供真实服务入口和处理状态。

| 能力 | 可迁移部署中的位置 |
|---|---|
| MinerU | 后端镜像内独立 Python 3.11 运行时，版本 4.0.10；管理端 PDF 上传调用 |
| Neo4j Browser | `http://127.0.0.1:17474/browser/`；Bolt `127.0.0.1:17687`，账号 neo4j，密码取私有配置 |
| Jaeger | `http://127.0.0.1:17686`；应用发送真实 OTLP span，任务记录包含本次 Trace |
| MinIO Console | `http://127.0.0.1:19001`；凭据取私有配置 |
| 文档 worker | Parser / Ingest / Reconciler 独立服务，以真实 Redis 心跳判断健康 |
| RAG | 现有 ImportCommand → SourceAsset → IR → BGE-M3 → Milvus；不创建第二套主 RAG |

MinerU 的基础文本 PDF 不需要视觉大模型；扫描页 OCR 可能首次下载 ONNX 模型。复杂表格／公式／VLM 不在最小安装承诺内。Jaeger 当前采用内存存储，重启可能丢失旧 Trace。课程视频 Tutor 使用正式版本范围的 RAG，不意味着每次回答都执行图谱扩展。

## 停止与备份

先在管理员任务列表确认没有正在生产／入库的任务，再使用：

```sh
docker compose --project-name eduagent-portable --env-file deploy/.env.portable -f deploy/docker-compose.yml stop --timeout 3600
```

保留各卷，不使用 `down -v`。正在运行任务的停止仍需遵守项目现有 drain 与租约协议；不能用强杀代替。源码候选包不等于业务数据备份：迁移已有实例必须同时备份 MySQL 业务关系、MinIO 对象、Milvus 数据及模型身份，Neo4j 可以从正式资产重建。密钥、Cookie 与私有备份单独交付，不能上传 GitHub。

## 安全发布源码

2026-10-07 本轮验证：独立空 MySQL 初始化及重复启动通过；干净导出目录 `npm ci` + Next 16.3.6 production build（含 TypeScript）通过；CPU frozen lock dry-run 通过；生产 npm audit 为 0 告警。原生学生／管理员页面回归通过。**完整 Compose 首次启动尚未通过**：本机 Docker 的 overlay2 错误与引擎中断，以及依赖下载 hash mismatch 留在原始记录中；没有关闭 hash 校验、重置 Docker 或删除已有数据卷。需要在稳定 Docker 环境完成 backend / workers / RAG / 视频与 PDF 实测后，才能将此安装路径标为正式验收通过。开发依赖仍有 2 moderate / 7 high 告警，未用强制升级掩盖。

当前技术阻塞是完整容器实测，不是继续扩课程或重新编排旧 TASK。源码候选包与“全部发布条件满足”是不同状态。

```sh
python deploy/portable.py export --output /outside/worktree/Bili-Study-release
```

工具使用明确的源码范围、排除运行数据与历史验收响应，扫描私有配置的已知凭据和常见 token／私钥／带密码 URL。遇到疑似凭据拒绝导出，报告文件名而不输出凭据。输出包含 SHA-256 清单；目标目录必须全新且位于工作树外。旧 `.git` 历史与 Git index 不会被带入。

不要直接推送原工作区：它包含大量历史改动、报告和本地恢复点。候选包需要复核文件清单、许可证／第三方归属，并在该独立目录创建新的发布仓库。GitHub 仓库名和 public/private 在正式发布时确定；本工具不会替你推送或改变原仓库 refs。

设计参照：[uv 的 Docker 集成](https://docs.astral.sh/uv/guides/integration/docker/)、[Milvus 官方单机 Compose](https://github.com/milvus-io/milvus/blob/v2.5.27/deployments/docker/standalone/docker-compose.yml)、[MinerU 4.0 官方快速开始](https://github.com/opendatalab/MinerU/blob/master/docs/en/quick_start/index.md)。本仓库选定的运行版本和真实验证结果优先于上游随时变化的默认配置。
