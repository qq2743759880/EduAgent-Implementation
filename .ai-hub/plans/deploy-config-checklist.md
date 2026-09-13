# EduAgent 部署配置项清单（taskC0）

> 真相源：`edu-agent/app/config.py`（Settings 全字段）。本清单逐键核对生成，
> 与 `edu-agent/.env.example` 一一对应（220 键全覆盖、零缺失、零多余，程序化比对）。
> 契约红线：零 API 契约变更（P3）——本清单仅覆盖部署配置项，非业务字段；`contracts/*.json` 禁改。
> 密钥零入库（P5）：所有密钥只写 .env（.gitignore 已忽略），.env.example 仅占位+生成指引。
>
> 生成日期：2026-09-13｜字段总数：220｜必填（无默认值）：2

## 0. 硬门禁键（启动 fail-fast 校验，必须最先核对）

| 校验器 | 触发条件 | 涉及键 | 后果 |
|---|---|---|---|
| `_security_guard` | DEBUG=false（生产）且 JWT_SECRET 为公开默认值 `dev-secret-key-change-in-production` 或空 | **JWT_SECRET** | ValueError 拒绝启动 |
| `_security_guard` | DEBUG=false（生产）且 API_TOKEN 为默认值 `edu-agent-dev-token` 或空 | **API_TOKEN** | ValueError 拒绝启动 |
| `_debug_env_gate`（H1b P1-8） | DEBUG=true 且 ENV_NAME 非 local（prod/staging/dev/qa 等） | **ENV_NAME**、**DEBUG** | ValueError 拒绝启动（虚拟管理员后门） |
| `_security_guard`（DEBUG=true 时） | 本机 dev 用默认密钥 | JWT_SECRET、API_TOKEN | 仅 warning 告警不阻断 |
| 存储初始化（lifespan） | DEBUG=false 下 MySQL/Milvus/MongoDB/MinIO/Neo4j/Redis 任一连不通 | MYSQL_*、MILVUS_URI、MONGO_URI、MINIO_*、NEO4J_*、REDIS_URL | 启动抛异常拒启（DEBUG=true 则降级继续） |

## 1. 全量配置项清单（220 键，按 config.py 分域）

### 应用基础配置

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| APP_NAME | `"EduAgent"` | 可选 | 应用基础配置 | 按需调整（默认值可直用） |
| APP_VERSION | `"0.3.0"` | 可选 | 应用基础配置 | 按需调整（默认值可直用） |
| DEBUG | `False` | 可选 | 全局调试开关：true 时未登录请求注入虚拟管理员 user_id=1（P1-8 后门） | 生产必须 false（硬要求） |
| ENV_NAME | `"local"` | 可选 | P1-8 门禁判据：DEBUG=true 且 ENV_NAME 非 local → 拒绝启动 | 生产填 prod；本机 dev 填 local |
| CORS_ORIGINS | `""` | 生产必配 | 前端跨域白名单；留空回退 DEBUG=* / 生产 http://localhost:3000 | 逗号分隔正式前端源，如 https://edu.example.com |
| HOST | `"0.0.0.0"` | 可选 | [应用基础配置] 服务配置 | 按需调整（默认值可直用） |
| PORT | `8000` | 可选 | 应用基础配置 | 按需调整（默认值可直用） |
| WORKERS | `1` | 可选 | uvicorn 进程数 | 生产可 2~4（视 CPU/显存），默认 1 |

### MySQL 配置

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| MYSQL_HOST | `"localhost"` | 可选 | MySQL 配置 | 按需调整（默认值可直用） |
| MYSQL_PORT | `3306` | 可选 | MySQL 配置 | 按需调整（默认值可直用） |
| MYSQL_USER | `"root"` | 可选 | MySQL 配置 | 按需调整（默认值可直用） |
| MYSQL_PASSWORD | `（无默认值，必填）` | 必填 | MySQL 主库凭据，缺失启动即失败 | 强密码，禁 root 弱密码公网暴露 |
| MYSQL_DATABASE | `"edu"` | 可选 | MySQL 配置 | 按需调整（默认值可直用） |
| MYSQL_CHARSET | `"utf8mb4"` | 可选 | MySQL 配置 | 按需调整（默认值可直用） |
| MYSQL_POOL_SIZE | `10` | 可选 | [MySQL 配置] task04 #2：池 maxsize=5 + acquire 无超时 → 并发写锁竞争时占满连接导致全后端挂死。；提高池容量 + acquire 超时 + 重试，避免单点并发写 DoS。 | 按需调整（默认值可直用） |
| MYSQL_POOL_MAX_OVERFLOW | `10` | 可选 | MySQL 配置 | 按需调整（默认值可直用） |
| MYSQL_POOL_RECYCLE | `3600` | 可选 | [MySQL 配置] 1小时回收连接 | 按需调整（默认值可直用） |
| MYSQL_POOL_ACQUIRE_TIMEOUT | `10.0` | 可选 | [MySQL 配置] 获取连接超时（秒），超时后重试，仍失败抛 DatabaseError | 按需调整（默认值可直用） |
| MYSQL_POOL_ACQUIRE_RETRIES | `2` | 可选 | [MySQL 配置] acquire 超时后的重试次数 | 按需调整（默认值可直用） |
| MYSQL_RO_USER | `"edu_ro"` | 可选 | [MySQL 配置] 只读账号（P4 NL2SQL 安全兜底） | 按需调整（默认值可直用） |
| MYSQL_RO_PASSWORD | `"edu_ro_pwd_2026"` | 可选 | NL2SQL 只读账号兜底 | 独立低权限账号+强密码 |

### Redis 配置（Phase 1：缓存 + 限流 + 会话）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| REDIS_URL | `"redis://localhost:6379/0"` | 可选 | 缓存/限流/会话/队列；localhost 自动归一 127.0.0.1 | 生产指向 Redis Cluster/Sentinel，必要时带密码 |
| REDIS_MAX_CONNECTIONS | `20` | 可选 | [Redis 配置（Phase 1：缓存 + 限流 + 会话）] 连接池上限 | 按需调整（默认值可直用） |
| REDIS_SOCKET_TIMEOUT | `5.0` | 可选 | [Redis 配置（Phase 1：缓存 + 限流 + 会话）] 单次操作超时（秒） | 按需调整（默认值可直用） |
| REDIS_SOCKET_CONNECT_TIMEOUT | `3.0` | 可选 | [Redis 配置（Phase 1：缓存 + 限流 + 会话）] 建连超时（秒） | 按需调整（默认值可直用） |
| REDIS_RETRY_ON_TIMEOUT | `True` | 可选 | [Redis 配置（Phase 1：缓存 + 限流 + 会话）] 超时自动重试一次 | 按需调整（默认值可直用） |
| SCHEMA_REGISTRY_REDIS_ENABLED | `True` | 可选 | [Redis 配置（Phase 1：缓存 + 限流 + 会话）] Schema 注册表（C2-③：跨实例 Redis 共享，task-M2 协同）；False → 纯本地（向后兼容/无 Redis 环境） | 按需调整（默认值可直用） |
| SCHEMA_REGISTRY_CACHE_TTL | `30.0` | 可选 | [Redis 配置（Phase 1：缓存 + 限流 + 会话）] 本地缓存 TTL（秒），吸收 Redis 读延迟 | 按需调整（默认值可直用） |
| SCHEMA_REGISTRY_NAMESPACE | `"default"` | 可选 | [Redis 配置（Phase 1：缓存 + 限流 + 会话）] 同 namespace 多实例共享同一 schema 集合 | 按需调整（默认值可直用） |
| SCHEMA_REGISTRY_KEY_PREFIX | `"edu:schema"` | 可选 | [Redis 配置（Phase 1：缓存 + 限流 + 会话）] Redis key 前缀 | 按需调整（默认值可直用） |

### Milvus 配置（向量数据库，部署在虚拟机 Docker 上）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| MILVUS_URI | `"http://192.168.85.101:19530"` | 可选 | 向量检索主链路 | 指向 VM/集群 Milvus，开启认证则配 MILVUS_TOKEN |
| MILVUS_TOKEN | `""` | 可选 | Milvus 认证 token | 无认证留空；开认证用强 token |
| MILVUS_DB | `"default"` | 可选 | Milvus 配置（向量数据库，部署在虚拟机 Docker 上） | 按需调整（默认值可直用） |
| MILVUS_COLLECTION | `"edu_knowledge"` | 可选 | Milvus 配置（向量数据库，部署在虚拟机 Docker 上） | 按需调整（默认值可直用） |
| MILVUS_SEARCH_TIMEOUT | `8.0` | 可选 | [Milvus 配置（向量数据库，部署在虚拟机 Docker 上）] Milvus 混合检索超时（秒），超时降级不拖死链路（P1-4） | 按需调整（默认值可直用） |

### Neo4j 图谱数据库（P1 知识图谱 / P4 推荐 & 思维导图）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| NEO4J_URI | `"bolt://localhost:7687"` | 可选 | [Neo4j 图谱数据库（P1 知识图谱 / P4 推荐 & 思维导图）] -v $HOME/neo4j/data:/data -v $HOME/neo4j/plugins:/plugins \；neo4j:5-community | 按需调整（默认值可直用） |
| NEO4J_USER | `"neo4j"` | 可选 | Neo4j 图谱数据库（P1 知识图谱 / P4 推荐 & 思维导图） | 按需调整（默认值可直用） |
| NEO4J_PASSWORD | `"edu_neo4j_pwd_2026"` | 可选 | 知识图谱写入 | 禁默认密码，docker 启动时 NEO4J_AUTH 同步改 |
| NEO4J_DATABASE | `"neo4j"` | 可选 | Neo4j 图谱数据库（P1 知识图谱 / P4 推荐 & 思维导图） | 按需调整（默认值可直用） |
| NEO4J_CONNECT_TIMEOUT | `3.0` | 可选 | [Neo4j 图谱数据库（P1 知识图谱 / P4 推荐 & 思维导图）] DEBUG 模式下连不上就跳过，不阻塞启动 | 按需调整（默认值可直用） |

### jieba 自定义资源（P1 sparse 向量 / 关键词抽取）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| JIEBA_CUSTOM_DICT | `"custom_dict.txt"` | 可选 | [jieba 自定义资源（P1 sparse 向量 / 关键词抽取）] 相对路径以 DATA_DIR 为基准（即 ./data 下） | 按需调整（默认值可直用） |
| JIEBA_STOPWORDS_FILE | `"stopwords.txt"` | 可选 | jieba 自定义资源（P1 sparse 向量 / 关键词抽取） | 按需调整（默认值可直用） |

### MongoDB 配置（对话状态存储，部署在虚拟机 Docker 上）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| MONGO_URI | `"mongodb://192.168.85.101:27017"` | 可选 | 对话状态后端 | 指向 VM/集群 MongoDB，必要时 URI 内带凭据 |
| MONGO_DB | `"edu_agent"` | 可选 | [MongoDB 配置（对话状态存储，部署在虚拟机 Docker 上）] 数据库名 | 按需调整（默认值可直用） |
| STATE_BACKEND | `"mongo"` | 可选 | [MongoDB 配置（对话状态存储，部署在虚拟机 Docker 上）] 对话状态后端 | 按需调整（默认值可直用） |

### MinIO 对象存储（管理端视频/课件/习题附件）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| MINIO_ENDPOINT | `"localhost:9000"` | 可选 | [MinIO 对象存储（管理端视频/课件/习题附件）] minio/minio server /data --console-address ":9001"；API 端口（非控制台 9001） | 按需调整（默认值可直用） |
| MINIO_SECURE | `False` | 可选 | 对象存储 TLS 开关 | 生产 true |
| MINIO_ACCESS_KEY | `"minioadmin"` | 可选 | 对象存储凭据 | 禁用默认 minioadmin，改独立账号 |
| MINIO_SECRET_KEY | `"minioadmin"` | 可选 | 对象存储凭据 | 强随机密码；MINIO_SECURE=true |
| MINIO_BUCKET_COURSE | `"edu-course"` | 可选 | [MinIO 对象存储（管理端视频/课件/习题附件）] 课程视频/课件 bucket | 按需调整（默认值可直用） |
| MINIO_BUCKET_QUESTION | `"edu-question"` | 可选 | [MinIO 对象存储（管理端视频/课件/习题附件）] 题库附件/图片 bucket | 按需调整（默认值可直用） |
| MINIO_BUCKET_UPLOAD | `"edu-upload"` | 可选 | [MinIO 对象存储（管理端视频/课件/习题附件）] 用户/管理员临时上传 bucket | 按需调整（默认值可直用） |

### 模型配置

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| BGE_M3_PATH | `"C:/ai-models/bge-m3"` | 可选 | 本地嵌入模型路径（EMBED_BACKEND=cuda 时用） | 无 GPU 时走 cloud 通道 |
| EMBED_DEVICE | `"cuda"` | 可选 | 模型配置 | 按需调整（默认值可直用） |
| EMBED_BATCH_SIZE | `8` | 可选 | 模型配置 | 按需调整（默认值可直用） |
| EMBEDDING_DIM | `1024` | 可选 | 模型配置 | 按需调整（默认值可直用） |
| RERANKER_PATH | `"C:/ai-models/bge-reranker-v2-m3"` | 可选 | 本地重排模型路径 | 同上 |
| RERANKER_DEVICE | `"cuda"` | 可选 | 模型配置 | 按需调整（默认值可直用） |
| RERANKER_BATCH_SIZE | `16` | 可选 | 模型配置 | 按需调整（默认值可直用） |
| RERANKER_PRECISION | `"fp16"` | 可选 | [模型配置] R1-① fp32 批处理：默认 fp16（省显存，历史行为零回归）；置 "fp32" 启用高精度路径；（跳过 .half()，分数噪声 < 1e-4，跨请求批处理排序更稳定，对排序敏感场景更稳）。 | 按需调整（默认值可直用） |
| LLM_API_KEY | `（无默认值，必填）` | 必填 | 聊天 LLM 调用凭据（pydantic 必填），缺失启动即失败 | 服务商控制台获取（DashScope/DeepSeek/火山 Ark），只写 .env |
| LLM_BASE_URL | `"https://dashscope.aliyuncs.com/compatible-mode/v1"` | 可选 | 模型配置 | 按需调整（默认值可直用） |
| LLM_MODEL_FAST | `"qwen-flash"` | 可选 | [模型配置] 快速模型（意图识别、简单问答） | 按需调整（默认值可直用） |
| LLM_MODEL_STRONG | `"qwen-plus"` | 可选 | [模型配置] 强力模型（NL2SQL、复杂推理） | 按需调整（默认值可直用） |
| LLM_TEMPERATURE | `0.0` | 可选 | [模型配置] 0=确定性输出 | 按需调整（默认值可直用） |
| LLM_MAX_TOKENS | `2000` | 可选 | 模型配置 | 按需调整（默认值可直用） |
| LLM_FAST_BASE_URL | `""` | 可选 | [模型配置] 留空时回退 LLM_BASE_URL/LLM_API_KEY（同源，旧行为）。；FAST 专属 base（火山引擎 https://ark.cn-beijing.volces.com/api/plan/v3） | 按需调整（默认值可直用） |
| LLM_FAST_API_KEY | `""` | 可选 | FAST 模型独立源凭据 | 火山 Ark 控制台获取（ark-...），只写 .env |
| LLM_STRONG_BASE_URL | `""` | 可选 | [模型配置] STRONG 专属 base（DeepSeek 官方 https://api.deepseek.com） | 按需调整（默认值可直用） |
| LLM_STRONG_API_KEY | `""` | 可选 | STRONG 模型独立源凭据 | DeepSeek 控制台获取（sk-...），只写 .env |

### Agent 循环（P2 增强）：LLM 意图决策 → 按需检索 → 生成

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| USE_AGENT_LOOP | `True` | 可选 | [Agent 循环（P2 增强）：LLM 意图决策 → 按需检索 → 生成] 总开关；False 回退「检索先行」 | 按需调整（默认值可直用） |
| AGENT_DECISION_ENABLED | `True` | 可选 | [Agent 循环（P2 增强）：LLM 意图决策 → 按需检索 → 生成] 决策层开关；False 则直接检索 | 按需调整（默认值可直用） |
| RULE_ROUTING_ENABLED | `True` | 可选 | [Agent 循环（P2 增强）：LLM 意图决策 → 按需检索 → 生成] route/decide_agent_plan 规则分类先行（命中 0 LLM；未命中默认 knowledge） | 按需调整（默认值可直用） |
| KNOWLEDGE_DIRECT_RETRIEVAL_ENABLED | `True` | 可选 | [Agent 循环（P2 增强）：LLM 意图决策 → 按需检索 → 生成] L1 knowledge：fan_out 直连检索，跳过子代理 LLM 循环 | 按需调整（默认值可直用） |
| SUBAGENT_DIRECT_TOOL_ENABLED | `True` | 可选 | [Agent 循环（P2 增强）：LLM 意图决策 → 按需检索 → 生成] 单工具子代理：turn-1 预执行唯一工具，LLM 仅总结轮 | 按需调整（默认值可直用） |

### 子代理（task92 R1 独立上下文）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| SUBAGENT_ARTIFACT_TTL | `3600` | 可选 | [子代理（task92 R1 独立上下文）] 子代理 artifact 完整输出 TTL（秒，对齐 Claude Code 1h） | 按需调整（默认值可直用） |
| SUBAGENT_SUMMARY_BUDGET | `2000` | 可选 | [子代理（task92 R1 独立上下文）] 主 state 仅收的摘要 token 预算上限 | 按需调整（默认值可直用） |

### AI 助手 LangGraph 图（task24）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| MAX_REFLECT_ITERATIONS | `2` | 可选 | [AI 助手 LangGraph 图（task24）] LLM-as-judge 最大回 plan 轮数，超限 answer 标 degraded_reason="reflect_max_iter" | 按需调整（默认值可直用） |
| COMPACTION_TOKEN_THRESHOLD | `6000` | 可选 | [AI 助手 LangGraph 图（task24）] 消息流超此阈值 → plan_node 前压缩至 ≤6000 | 按需调整（默认值可直用） |
| COMPACTION_REFRESH_THRESHOLD | `3000` | 可选 | [AI 助手 LangGraph 图（task24）] compaction 后新增超此值再触发 | 按需调整（默认值可直用） |
| COMPACTION_KEEP_ROUNDS | `6` | 可选 | [AI 助手 LangGraph 图（task24）] 压缩后保留最近 K 轮原文 | 按需调整（默认值可直用） |
| COMPACTION_TOOL_OUTPUT_THRESHOLD | `1500` | 可选 | [AI 助手 LangGraph 图（task24）] 单条工具输出超此 token → 立即蒸馏 | 按需调整（默认值可直用） |
| ARTIFACT_TTL | `3600` | 可选 | [AI 助手 LangGraph 图（task24）] artifact 完整输出 TTL（秒，对齐 1h） | 按需调整（默认值可直用） |
| CHECKPOINT_TTL | `604800` | 可选 | [AI 助手 LangGraph 图（task24）] LangGraph checkpoint TTL（7 天 = 604800s，对齐 task26 防过载） | 按需调整（默认值可直用） |
| CONTEXT_WINDOW_TOKENS | `32000` | 可选 | [AI 助手 LangGraph 图（task24）] 上下文窗口预算（使用率分母；按实际模型窗口调整） | 按需调整（默认值可直用） |
| CONTEXT_USAGE_WARN_RATIO | `0.6` | 可选 | [AI 助手 LangGraph 图（task24）] 使用率告警水位，≥此比例记 warn 快照并打日志 | 按需调整（默认值可直用） |
| CONTEXT_EDIT_ENABLED | `True` | 可选 | [AI 助手 LangGraph 图（task24）] 灰度开关；False → 跳过轻量编辑直接走 compaction | 按需调整（默认值可直用） |
| CONTEXT_EDIT_KEEP_RECENT_ROUNDS | `0` | 可选 | [AI 助手 LangGraph 图（task24）] 保护最近 N 轮工具对不被删（0=删除全部已完成对） | 按需调整（默认值可直用） |
| CONTEXT_EDIT_DROP_REDUNDANT_REASONING | `True` | 可选 | [AI 助手 LangGraph 图（task24）] 顺带删除紧邻被删工具对的填充式中间推理 | 按需调整（默认值可直用） |
| CONTEXT_STRATEGY_ORDER | `"context_edit,compaction"` | 可选 | [AI 助手 LangGraph 图（task24）] 阈值策略顺序（轻量优先，重量兜底） | 按需调整（默认值可直用） |
| CONTEXT_USAGE_MONITOR_MAX | `50` | 可选 | [AI 助手 LangGraph 图（task24）] 使用率快照环形缓冲条数上限 | 按需调整（默认值可直用） |

### 【task96 新增段结束】

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| COMPACTION_BUDGET_RATIOS | `{ "system": 0.10, # 系统/可缓存前缀 "user_query": 0.20, # 用户问题 "...` | 可选 | 【task96 新增段结束】 | 按需调整（默认值可直用） |
| ANCHOR_ROUND | `3` | 可选 | [【task96 新增段结束】] 锚定闸门轮数（闸门前字节零改动） | 按需调整（默认值可直用） |
| COMPACTION_LLM_SELECT | `True` | 可选 | [【task96 新增段结束】] LLM 动态选片段总开关（未注入 llm 时回退规则） | 按需调整（默认值可直用） |
| FREEZE_ZONE_MAX_RATIO | `0.5` | 可选 | [【task96 新增段结束】] C1-③ 冻结区 token 占比阈值；占比>此值触发告警+建议降 ANCHOR_ROUND | 按需调整（默认值可直用） |

### 【task-C1 新增段结束】

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| HITL_REFUND_ENABLED | `True` | 可选 | [【task-C1 新增段结束】] True=走 HITL 审批图；False=退回 task19 stub | 按需调整（默认值可直用） |
| HITL_ESCALATION_HOURS | `72` | 可选 | [【task-C1 新增段结束】] 审批无动作超时（小时）→ 升级 high 工单并通知(GWT③) | 按需调整（默认值可直用） |
| HITL_ESCALATION_INTERVAL | `1800` | 可选 | [【task-C1 新增段结束】] 后台超时扫描间隔（秒） | 按需调整（默认值可直用） |
| HITL_ESCALATION_AUTO | `True` | 可选 | [【task-C1 新增段结束】] 服务启动时是否自动拉起超时扫描后台任务 | 按需调整（默认值可直用） |

### Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| LLM_GLOBAL_CONCURRENCY | `8` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 全局 LLM 并发闸上限（信号量 + Redis 分布式计数） | 按需调整（默认值可直用） |
| USER_MAX_CONCURRENT | `2` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 单用户最大并发请求，第 3 个被拒 | 按需调整（默认值可直用） |
| QUEUE_POP_TIMEOUT | `10.0` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] chat:queue BLPOP 阻塞上限，>此秒返回友好提示 | 按需调整（默认值可直用） |
| QUEUE_KEY | `"chat:queue"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] LLM 请求排队 Redis list key | 按需调整（默认值可直用） |
| CONCURRENT_KEY_PREFIX | `"chat:concurrent"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 单用户并发计数 key 前缀（INCR/DECR） | 按需调整（默认值可直用） |
| GLOBAL_CONCURRENT_KEY | `"ai:llm:concurrent"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 全局并发计数 key（原子 Lua INCR/DECR） | 按需调整（默认值可直用） |
| ZSET_SHARD_SIZE | `50` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] ZSET 单分片条目上限，超限按 member 哈希分片 | 按需调整（默认值可直用） |
| BIGKEY_THRESHOLD_BYTES | `1048576` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] bigkey 扫描告警阈值（1MB = 1024*1024） | 按需调整（默认值可直用） |
| LLM_TOKEN_RATE_LIMIT_PER_MIN | `600000` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 全局 LLM 预估 token 速率上限（/分钟），超限进队列不拒绝 | 按需调整（默认值可直用） |
| USER_TOKEN_QUOTA_PER_MIN | `30000` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 单用户单分钟 token 配额，超配额返回 user_token_quota_exceeded | 按需调整（默认值可直用） |
| ESTIMATE_DEFAULT_TOKENS | `2000` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] request_meta 缺失时的兜底预估 token | 按需调整（默认值可直用） |
| QUEUE_POP_TIMEOUT_L3 | `30.0` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] L3 大请求排队超时（秒），容忍更长排队 | 按需调整（默认值可直用） |
| QUEUE_PRIORITY_ORDER | `["L3", "L2", "L1"]` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 消费者轮询优先级顺序（L3 先出队） | 按需调整（默认值可直用） |
| TOKEN_RATE_KEY | `"ai:llm:token_rate"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 全局 token 速率计数 key（INCRBY + EXPIRE 60s 窗口） | 按需调整（默认值可直用） |
| USER_TOKEN_KEY_PREFIX | `"chat:user_token"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 单用户 token 配额计数 key 前缀（INCRBY + EXPIRE 60s） | 按需调整（默认值可直用） |
| TOKEN_BUCKET_ENABLED | `False` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 默认关闭以保持既有生产窗口行为不变；开启后全局速率改用令牌桶，消除窗口边界 2× 突发。；True=全局速率走令牌桶平滑；False=保持固定 60s 窗口 | 按需调整（默认值可直用） |
| TOKEN_BUCKET_BURST_RATIO | `1.0` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 令牌桶容量 / 速率（=1.0 表示突发上限 = 1 分钟速率） | 按需调整（默认值可直用） |
| TOKEN_BUCKET_REFILL_WINDOW_SEC | `60.0` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 令牌桶重填窗口（秒），与速率/分钟对齐 | 按需调整（默认值可直用） |
| OTEL_EXPORT_ENDPOINT | `""` | 可选 | OTLP HTTP 导出地址；空=JSONL 落盘 | 有 collector 时配 http://otel-collector:4318 |
| OTEL_JSONL_DIR | `"logs/otel"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] JSONL 落盘目录（OTEL_EXPORT_ENDPOINT 空时生效） | 按需调整（默认值可直用） |
| OTEL_SAMPLE_RATE | `1.0` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 埋点采样率（0~1，1=全量） | 按需调整（默认值可直用） |
| TRACE_SESSION_LEVEL | `True` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 会话级 trace_id：同一会话多次请求复用同一 trace_id（span_id 各异） | 按需调整（默认值可直用） |
| MEMORY_CAPACITY_PER_USER | `500` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 默认档（normal）每用户记忆容量上限，超限触发遗忘淘汰 | 按需调整（默认值可直用） |
| MEMORY_CAPACITY_TIERS | `{ "inactive": 200, # 长期不活跃：收紧容量，省存储 "normal": 500, # 普通活跃...` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 按用户活跃度分档的容量上限（配置化，取代单值硬编码）：部署时可按活跃度/高价值精调 | 按需调整（默认值可直用） |
| MEMORY_CAPACITY_DEFAULT_TIER | `"normal"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 未指定档时的默认档 | 按需调整（默认值可直用） |
| MEMORY_CAPACITY_USER_OVERRIDE | `{}` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 指定用户的容量覆盖（user_id -> 容量），用于高价值/灰度用户按活跃度精调 | 按需调整（默认值可直用） |
| MEMORY_SOFT_DELETE_SCORE | `0.1` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 综合分 < 此值 → 软删遗忘（时间衰减非误删） | 按需调整（默认值可直用） |
| MEMORY_DECAY_LAMBDA | `0.01` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 遗忘曲线衰减系数（Δt 单位天）：exp(-λ·Δt) | 按需调整（默认值可直用） |
| MEMORY_RECENCY_WEIGHT | `2.0` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] recency_bonus = W/(1+0.1·days_since_access) | 按需调整（默认值可直用） |
| MEMORY_RECENCY_SLOPE | `0.1` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] recency_bonus 分母斜率 | 按需调整（默认值可直用） |
| MEMORY_IMPORTANCE_THRESHOLD | `4` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 会话结束落库的重要性下限（≥4 才写长时记忆） | 按需调整（默认值可直用） |
| MEMORY_TOP_K | `3` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 向量召回 top-k 进 lead plan prompt | 按需调整（默认值可直用） |
| MEMORY_QUEUE_KEY | `"edu:mem_queue"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 异步写队列 Redis list key | 按需调整（默认值可直用） |
| MEMORY_QUEUE_MAX_RETRY | `3` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 单条写失败最大重试次数（异步隔离） | 按需调整（默认值可直用） |
| MEMORY_VECTOR_DIM | `512` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 内存向量降级维度（Milvus 时用 EMBEDDING_DIM=1024） | 按需调整（默认值可直用） |
| MILVUS_MEMORY_COLLECTION | `"user_memory"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 记忆向量 collection（用户分区/过滤） | 按需调整（默认值可直用） |
| MEMORY_EVENT_ENABLED | `True` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 事件溯源总开关（True=写路径走 user_memory_event） | 按需调整（默认值可直用） |
| MEMORY_EVENT_TTL_DAYS | `180` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 容量压缩器保留近期高保真天数（TIME_COMPRESS） | 按需调整（默认值可直用） |
| DREAM_SESSION_INTERVAL | `5` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 每 N 会话触发一次 Dream 巩固 | 按需调整（默认值可直用） |
| DREAM_MIN_AGE_HOURS | `24` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] Dream 最小间隔（小时），防抖动频繁巩固 | 按需调整（默认值可直用） |
| DREAM_LOCK_TTL_S | `600` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] Dream 分布式锁 TTL（秒），SET NX EX 窗口锁 | 按需调整（默认值可直用） |
| DREAM_MAX_ENTITIES_PER_RUN | `200` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 单次 Dream 最多处理实体数（防长尾阻塞） | 按需调整（默认值可直用） |
| DREAM_MODEL | `"fast"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] Dream 巩固子代理模型（cost 友好；生产可切 opus） | 按需调整（默认值可直用） |
| PROMPT_CACHE_MIN_TOKENS | `2048` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 可缓存前缀最小 token（火山 ark 实测缓存按 2048-token 分块，1024 永远命中 0 块） | 按需调整（默认值可直用） |
| CACHE_FILLER_VERSION | `"v3"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 静态填充注释版本号（逐字节稳定，随版本升级） | 按需调整（默认值可直用） |
| TOOL_DEFERRED_MODE | `True` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] True=决策前缀只放 tool_name+summary，schema 被选中才展开 | 按需调整（默认值可直用） |
| CACHE_HIT_RATE_SEV | `0.5` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 缓存命中率 < 此值记 SEV（对齐 Claude 把命中率当 uptime） | 按需调整（默认值可直用） |
| EMBEDDING_API_URL | `""` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 空 → 复用 LLM_BASE_URL | 按需调整（默认值可直用） |
| EMBEDDING_API_KEY | `""` | 可选 | 云端 embedding 凭据 | 硅基流动控制台获取，只写 .env |
| EMBEDDING_MODEL | `"BAAI/bge-m3"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 硅基流动默认；DashScope 用 text-embedding-v3 | 按需调整（默认值可直用） |
| EMBED_BACKEND | `"cloud"` | 可选 | embedding 通道 cloud/cuda；查询与入库必须同通道（教训 7） | 有本地 GPU 且空间已建用 cuda，否则 cloud+硅基流动 key |
| RERANK_API_URL | `""` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 云端 rerank（硅基流动等 OpenAI 兼容 rerank 端点）；空 → 复用 EMBEDDING_API_URL | 按需调整（默认值可直用） |
| RERANK_API_KEY | `""` | 可选 | 云端 rerank 凭据 | 硅基流动控制台获取，只写 .env |
| RERANK_MODEL | `"BAAI/bge-reranker-v2-m3"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] 硅基流动 rerank 模型 | 按需调整（默认值可直用） |
| RERANK_BACKEND | `"cloud"` | 可选 | [Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）] "cloud" → 优先云端 API；"cuda" → 本地优先 | 按需调整（默认值可直用） |

### P8 MCP 工具调用开关

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| USE_MCP_TOOL_CALLING | `True` | 可选 | [P8 MCP 工具调用开关] 总开关：False 时聊天流程跳过 MCP 工具调用 | 按需调整（默认值可直用） |
| MCP_TOOL_MAX_TRIES | `1` | 可选 | [P8 MCP 工具调用开关] 单轮最多触发几次工具（避免反复调用） | 按需调整（默认值可直用） |
| MCP_HC_USE_POOL | `True` | 可选 | [P8 MCP 工具调用开关] B1（reshape-b）：stdio 单台健康检查复用 sessions 池长连会话（池内仅发一条 ping）。；False = 回滚开关：退回一次性 spawn 全握手旧路径（行为与 B1 前完全一致）。 | 按需调整（默认值可直用） |
| MCP_HC_SESSION_TTL_S | `600` | 可选 | [P8 MCP 工具调用开关] hc 专用会话空闲 TTL（秒），session_create 内钳制 30~1800 | 按需调整（默认值可直用） |
| TOOL_FALLBACK_MAP | `{ "web_search": ["calculator", "search_knowledge"], "code...` | 可选 | P8 MCP 工具调用开关 | 按需调整（默认值可直用） |
| MAX_TOOL_ATTEMPTS | `4` | 可选 | [P8 MCP 工具调用开关] 闭环步数：第 4 步 = 结构化人工操作指南并停止 | 按需调整（默认值可直用） |
| TOOL_CONSECUTIVE_REJECTIONS | `3` | 可选 | [P8 MCP 工具调用开关] 同会话连续被拒 3 次 → 第 4 次中断回合工具循环 | 按需调整（默认值可直用） |
| TOOL_REJECT_TTL_S | `300` | 可选 | [P8 MCP 工具调用开关] 拒绝计数 Redis TTL（秒） | 按需调整（默认值可直用） |
| TOOL_RETRY_LLM_REWRITE | `True` | 可选 | [P8 MCP 工具调用开关] 第 2 步是否尝试 LLM 改写 args（关闭则走规则跳级兜底） | 按需调整（默认值可直用） |

### 【task-T1 新增段结束】

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| HITL_ENABLED | `False` | 可选 | 全流程 HITL 护栏总开关（默认关） | 接入 executor 后由运维显式开启 |
| HITL_RISK_THRESHOLD | `"L2"` | 可选 | [【task-T1 新增段结束】] 仅风险等级 >= 此值的动作过 Gate | 按需调整（默认值可直用） |
| HITL_PENDING_TTL_S | `600` | 可选 | [【task-T1 新增段结束】] pending 超时自动拒绝窗口（秒） | 按需调整（默认值可直用） |
| HITL_AI_REVIEW | `False` | 可选 | [【task-T1 新增段结束】] 是否启用 AI 审查子代理（仅测试窗口内开） | 按需调整（默认值可直用） |
| HITL_REJECT_BREAKER | `3` | 可选 | [【task-T1 新增段结束】] 同动作类型连续被拒达此数 → 第 N+1 次熔断升级（需管理员） | 按需调整（默认值可直用） |
| HITL_OPERATOR | `""` | 可选 | [【task-T1 新增段结束】] 默认操作者标识（executor 接入时由 user_id 覆盖） | 按需调整（默认值可直用） |

### 【task-S1 新增段结束】

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| RERANK_SERVICE_PORT | `8601` | 可选 | [【task-S1 新增段结束】] 不阻塞主事件循环）；sidecar 不可达自动回退进程内直连（task31 现状），再失败走规则兜底。；sidecar 监听端口 | 按需调整（默认值可直用） |
| RERANK_SERVICE_URL | `"http://127.0.0.1:8601"` | 可选 | [【task-S1 新增段结束】] 主链路调用地址 | 按需调整（默认值可直用） |
| RERANK_BATCH_WINDOW_MS | `20` | 可选 | [【task-S1 新增段结束】] 攒批窗口：窗口内到达的请求合并成一批 | 按需调整（默认值可直用） |
| RERANK_MAX_BATCH_PAIRS | `64` | 可选 | [【task-S1 新增段结束】] 单批最大 (query,content) 对数，超则拆下一批 | 按需调整（默认值可直用） |
| RERANK_MAX_WAIT_MS | `50` | 可选 | [【task-S1 新增段结束】] 单请求排队延迟上限（到时强制 flush） | 按需调整（默认值可直用） |
| RERANK_QUEUE_MAX | `200` | 可选 | [【task-S1 新增段结束】] 内存队列上限，超则调用方走降级（返回 503/None） | 按需调整（默认值可直用） |
| RERANK_HTTP_TIMEOUT | `10.0` | 可选 | [【task-S1 新增段结束】] 主链路调 sidecar 超时（秒）：2.0 在 6 并发×20docs 批处理+GPU 竞争下过紧，易误触发进程内回退→事件循环阻塞→雪崩链（2026-08-29 周末复测实测 44 次 ConnectTimeout/ | 按需调整（默认值可直用） |
| RERANK_SIDECAR_ENABLED | `True` | 可选 | [【task-S1 新增段结束】] False → 主链路直接进程内 rerank（平滑切换/降级调试） | 按需调整（默认值可直用） |
| RERANK_QUEUE_REDIS | `False` | 可选 | [【task-S1 新增段结束】] 可选：Redis list 缓冲峰值（默认直连 batcher） | 按需调整（默认值可直用） |

### 【task-R1 新增段结束】

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| HARNESS_IMPL | `"sixnode"` | 可选 | [【task-R1 新增段结束】] 可插拔实现选择；"sixnode" 为默认（重构前行为零差异） | 按需调整（默认值可直用） |
| MEMORY_VECTOR_BACKEND_ORDER | `["milvus", "redis", "memory"]` | 可选 | 【task-R1 新增段结束】 | 按需调整（默认值可直用） |
| MEMORY_REDIS_VEC_KEY_PREFIX | `"memory:vec"` | 可选 | 【task-R1 新增段结束】 | 按需调整（默认值可直用） |
| MEMORY_REDIS_SCAN_LIMIT | `2000` | 可选 | [【task-R1 新增段结束】] 单用户向量枚举上限，防大 key | 按需调整（默认值可直用） |
| CONTEXTUALIZE_ENABLED | `False` | 可选 | RAG Contextual Retrieval（默认关，烧 LLM 额度） | 确认模型额度后再开 |
| CONTEXTUALIZE_MODEL | `"fast"` | 可选 | [【task-R1 新增段结束】] 生成前缀用便宜快速模型（省 DeepSeek 额度） | 按需调整（默认值可直用） |
| CONTEXTUALIZE_MAX_CONCURRENCY | `8` | 可选 | [【task-R1 新增段结束】] 前缀生成最大并发（GWT③ 并发 ≤8） | 按需调整（默认值可直用） |
| CONTEXT_PREFIX_TOKEN_BUDGET_MIN | `50` | 可选 | [【task-R1 新增段结束】] 前缀 token 下限（CONTEXT_PROMPT 约束） | 按需调整（默认值可直用） |
| CONTEXT_PREFIX_TOKEN_BUDGET_MAX | `100` | 可选 | [【task-R1 新增段结束】] 前缀 token 上限 | 按需调整（默认值可直用） |

### 日志配置

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| LOG_LEVEL | `"INFO"` | 可选 | 日志级别 | 生产 INFO（勿 DEBUG） |
| LOG_DIR | `"./logs"` | 可选 | 日志配置 | 按需调整（默认值可直用） |
| LOG_ROTATION | `"100 MB"` | 可选 | [日志配置] 单文件最大大小 | 按需调整（默认值可直用） |
| LOG_RETENTION | `"7 days"` | 可选 | [日志配置] 保留时长 | 按需调整（默认值可直用） |

### 鉴权配置 —— 密码哈希 + JWT 双 Token

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| JWT_SECRET | `"dev-secret-key-change-in-production"` | 生产必配 | 【_security_guard 硬校验】DEBUG=false 下用公开默认值 → 拒绝启动 | 强随机 32 字节 hex：python -c "import secrets; print(secrets.token_hex(32))" |
| JWT_ALGORITHM | `"HS256"` | 可选 | JWT 签名算法 | 保持 HS256 |
| JWT_ACCESS_TOKEN_EXPIRE_MINUTES | `60 * 24` | 可选 | [鉴权配置 —— 密码哈希 + JWT 双 Token] access_token：用于日常接口调用，过期要拿 refresh_token 换新；24 小时（默认） | 按需调整（默认值可直用） |
| JWT_REFRESH_TOKEN_EXPIRE_DAYS | `7` | 可选 | [鉴权配置 —— 密码哈希 + JWT 双 Token] refresh_token：用于换新 access_token，实现「7 天滑动过期」；7 天（默认） | 按需调整（默认值可直用） |
| JWT_EXPIRE_MINUTES | `60 * 24` | 可选 | [鉴权配置 —— 密码哈希 + JWT 双 Token] 兼容老字段（其他模块还在用 JWT_EXPIRE_MINUTES） | 按需调整（默认值可直用） |
| PASSWORD_HASH_ROUNDS | `12` | 可选 | [鉴权配置 —— 密码哈希 + JWT 双 Token] bcrypt 哈希轮次（12 轮 ≈ 250ms，防暴力破解；服务器 CPU 强可升 13/14） | 按需调整（默认值可直用） |
| API_TOKEN | `"edu-agent-dev-token"` | 生产必配 | 【_security_guard 硬校验】DEBUG=false 下用默认值 → 拒绝启动 | 随机值：python -c "import secrets; print(secrets.token_urlsafe(24))" |

### 检索参数（P2 调优时改这里，不用改代码）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| CHUNK_SIZE | `512` | 可选 | 检索参数（P2 调优时改这里，不用改代码） | 按需调整（默认值可直用） |
| CHUNK_OVERLAP | `64` | 可选 | 检索参数（P2 调优时改这里，不用改代码） | 按需调整（默认值可直用） |
| TOP_K_RECALL | `20` | 可选 | 检索参数（P2 调优时改这里，不用改代码） | 按需调整（默认值可直用） |
| TOP_K_RERANK | `5` | 可选 | 检索参数（P2 调优时改这里，不用改代码） | 按需调整（默认值可直用） |
| CLIFF_MIN_KEEP | `3` | 可选 | 检索参数（P2 调优时改这里，不用改代码） | 按需调整（默认值可直用） |
| CLIFF_MAX_KEEP | `8` | 可选 | 检索参数（P2 调优时改这里，不用改代码） | 按需调整（默认值可直用） |
| CLIFF_RATIO | `0.4` | 可选 | 检索参数（P2 调优时改这里，不用改代码） | 按需调整（默认值可直用） |
| RETRIEVER_RECALL_TOPK | `150` | 可选 | [检索参数（P2 调优时改这里，不用改代码）] RRF 融合后召回候选（GWT② 12→150） | 按需调整（默认值可直用） |
| RETRIEVER_RERANK_TOPK | `20` | 可选 | [检索参数（P2 调优时改这里，不用改代码）] rerank 后保留 top-n 再断崖 | 按需调整（默认值可直用） |
| COURSE_PUBLIC_PARTITION | `"course_public"` | 可选 | [检索参数（P2 调优时改这里，不用改代码）] course_public 保留分区：课程知识隔离用户上传（GWT③），检索期排除下列 content_type 防促销/班次混入 | 按需调整（默认值可直用） |
| RETRIEVER_EXCLUDE_CONTENT_TYPES | `( "promotion", "schedule", "announcement", "marketing", )` | 可选 | 检索参数（P2 调优时改这里，不用改代码） | 按需调整（默认值可直用） |

### P7 管理端 RAG：rebuild 状态机（task04 #3/#8）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| RAG_REBUILD_TIMEOUT_SECONDS | `120` | 可选 | [P7 管理端 RAG：rebuild 状态机（task04 #3/#8）] rebuilding 超过此时长（秒）未完成 → list_collections 自动回置 error | 按需调整（默认值可直用） |

### SQL 安全（P4）

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| SQL_MAX_ROWS | `1000` | 可选 | SQL 安全（P4） | 按需调整（默认值可直用） |
| SQL_TIMEOUT | `30` | 可选 | SQL 安全（P4） | 按需调整（默认值可直用） |
| SQL_MAX_REPAIR | `2` | 可选 | SQL 安全（P4） | 按需调整（默认值可直用） |
| SHADOW_MODE_ENABLED | `False` | 可选 | SQL 安全（P4） | 按需调整（默认值可直用） |
| SHADOW_MODE_RATIO | `1.0` | 可选 | SQL 安全（P4） | 按需调整（默认值可直用） |
| CANARY_RATIO | `0.01` | 可选 | SQL 安全（P4） | 按需调整（默认值可直用） |
| CANARY_DAYS | `3` | 可选 | SQL 安全（P4） | 按需调整（默认值可直用） |
| JUDGE_DIMENSIONS | `["fact_correctness", "completeness", "harmlessness", "coh...` | 可选 | SQL 安全（P4） | 按需调整（默认值可直用） |

### 路径配置

| 键 | 默认值 | 必填性 | 影响面 | 生产值指引 |
|---|---|---|---|---|
| DATA_DIR | `"./data"` | 可选 | 路径配置 | 按需调整（默认值可直用） |
| KNOWLEDGE_SOURCE_DIR | `"C:/Users/Administrator/Desktop/edu"` | 可选 | 知识库源文件目录 | 按部署机路径调整 |

## 2. 双形态对照（同一 .env.example）

| 键 | 本机 dev 形态 | 生产形态 |
|---|---|---|
| ENV_NAME | local | prod |
| DEBUG | true | false |
| JWT_SECRET / API_TOKEN | 默认值仅告警 | 强随机（硬校验拒默认） |
| CORS_ORIGINS | 留空 → `*` | 正式前端源 |
| 存储初始化失败 | 降级继续 | 拒绝启动 |

## 3. 核对结论（C0 实证）

- config.py Settings 字段 220 个，.env.example 覆盖 220 个，缺失 0，多余 0（正则比对 `app/config.py` vs `.env.example`）。
- scratch 生产形态（ENV_NAME=prod, DEBUG=false, 强随机密钥）8002 临时实例启动验证：见 `test-reports/C0-completion-report.md`。
