"""
配置管理 —— 读取环境变量并提供默认值。

设计原则：
1. 所有配置项集中在一个类
2. 用 pydantic-settings 自动从环境变量读取
3. 提供合理的默认值（本地开发可直接跑）
4. 敏感信息（密码/API Key）必须通过环境变量提供
"""
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator


class Settings(BaseSettings):
    """
    应用配置（自动从环境变量读取）。

    环境变量命名规则：
    - 直接匹配字段名（大小写不敏感）
    - 如 MYSQL_HOST 对应环境变量 MYSQL_HOST
    """

    # ============================================================
    # 应用基础配置
    # ============================================================
    APP_NAME: str = "EduAgent"
    APP_VERSION: str = "0.3.0"
    DEBUG: bool = False

    # CORS 允许来源（生产必配）：逗号分隔的完整源，如
    #   CORS_ORIGINS=https://edu.example.com,https://admin.example.com
    # 留空时回退：DEBUG → "*"；生产 → http://localhost:3000
    CORS_ORIGINS: str = ""

    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1                     # 开发模式用 1，生产可用 4

    # ============================================================
    # MySQL 配置
    # ============================================================
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str                   # 必填，无默认值
    MYSQL_DATABASE: str = "edu"
    MYSQL_CHARSET: str = "utf8mb4"

    # 连接池配置
    # task04 #2：池 maxsize=5 + acquire 无超时 → 并发写锁竞争时占满连接导致全后端挂死。
    # 提高池容量 + acquire 超时 + 重试，避免单点并发写 DoS。
    MYSQL_POOL_SIZE: int = 10
    MYSQL_POOL_MAX_OVERFLOW: int = 10
    MYSQL_POOL_RECYCLE: int = 3600        # 1小时回收连接
    MYSQL_POOL_ACQUIRE_TIMEOUT: float = 10.0   # 获取连接超时（秒），超时后重试，仍失败抛 DatabaseError
    MYSQL_POOL_ACQUIRE_RETRIES: int = 2        # acquire 超时后的重试次数

    # 只读账号（P4 NL2SQL 安全兜底）
    MYSQL_RO_USER: str = "edu_ro"
    MYSQL_RO_PASSWORD: str = "edu_ro_pwd_2026"

    # ============================================================
    # Redis 配置（Phase 1：缓存 + 限流 + 会话）
    # ============================================================
    # 本地开发：Windows 用 Memurai（https://www.memurai.com/）或 WSL Redis
    # 生产：Redis Cluster / Sentinel
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20          # 连接池上限
    REDIS_SOCKET_TIMEOUT: float = 5.0        # 单次操作超时（秒）
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 3.0 # 建连超时（秒）
    REDIS_RETRY_ON_TIMEOUT: bool = True      # 超时自动重试一次

    # ============================================================
    # Milvus 配置（向量数据库，部署在虚拟机 Docker 上）
    # ============================================================
    MILVUS_URI: str = "http://192.168.85.101:19530"
    MILVUS_TOKEN: str = ""                # 无认证时留空
    MILVUS_DB: str = "default"
    MILVUS_COLLECTION: str = "edu_knowledge"
    MILVUS_SEARCH_TIMEOUT: float = 8.0    # Milvus 混合检索超时（秒），超时降级不拖死链路（P1-4）

    # ============================================================
    # Neo4j 图谱数据库（P1 知识图谱 / P4 推荐 & 思维导图）
    # ============================================================
    # 本地开发可用 Docker 启动：
    #   docker run -d -p 7474:7474 -p 7687:7687 --name neo4j \
    #     -e NEO4J_AUTH=neo4j/edu_neo4j_pwd_2026 \
    #     -e NEO4J_apoc_export_file_enabled=true \
    #     -v $HOME/neo4j/data:/data -v $HOME/neo4j/plugins:/plugins \
    #     neo4j:5-community
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "edu_neo4j_pwd_2026"
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_CONNECT_TIMEOUT: float = 3.0    # DEBUG 模式下连不上就跳过，不阻塞启动

    # ============================================================
    # jieba 自定义资源（P1 sparse 向量 / 关键词抽取）
    # ============================================================
    # 相对路径以 DATA_DIR 为基准（即 ./data 下）
    JIEBA_CUSTOM_DICT: str = "custom_dict.txt"
    JIEBA_STOPWORDS_FILE: str = "stopwords.txt"

    # ============================================================
    # MongoDB 配置（对话状态存储，部署在虚拟机 Docker 上）
    # ============================================================
    MONGO_URI: str = "mongodb://192.168.85.101:27017"
    MONGO_DB: str = "edu_agent"           # 数据库名
    STATE_BACKEND: str = "mongo"          # 对话状态后端

    # ============================================================
    # MinIO 对象存储（管理端视频/课件/习题附件）
    # ============================================================
    # 本地开发可用 docker run minio：
    #   docker run -d -p 9000:9000 -p 9001:9001 \
    #     --name minio -v D:/minio-data:/data \
    #     minio/minio server /data --console-address ":9001"
    MINIO_ENDPOINT: str = "localhost:9000"        # API 端口（非控制台 9001）
    MINIO_SECURE: bool = False                     # 本地开发 HTTP，生产 HTTPS
    MINIO_ACCESS_KEY: str = "minioadmin"           # 登录用户名
    MINIO_SECRET_KEY: str = "minioadmin"           # 登录密码
    MINIO_BUCKET_COURSE: str = "edu-course"        # 课程视频/课件 bucket
    MINIO_BUCKET_QUESTION: str = "edu-question"    # 题库附件/图片 bucket
    MINIO_BUCKET_UPLOAD: str = "edu-upload"        # 用户/管理员临时上传 bucket

    # ============================================================
    # 模型配置
    # ============================================================
    # BGE-M3 嵌入模型
    BGE_M3_PATH: str = "C:/ai-models/bge-m3"
    EMBED_DEVICE: Literal["cuda", "cpu"] = "cuda"
    EMBED_BATCH_SIZE: int = 8
    EMBEDDING_DIM: int = 1024

    # BGE-Reranker 重排模型
    RERANKER_PATH: str = "C:/ai-models/bge-reranker-v2-m3"
    RERANKER_DEVICE: Literal["cuda", "cpu"] = "cuda"
    RERANKER_BATCH_SIZE: int = 16

    # LLM API（OpenAI 兼容：a6api 中转 / DeepSeek 官方 / DashScope 均可）
    LLM_API_KEY: str                      # 必填
    LLM_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL_FAST: str = "qwen-flash"    # 快速模型（意图识别、简单问答）
    LLM_MODEL_STRONG: str = "qwen-plus"   # 强力模型（NL2SQL、复杂推理）
    LLM_TEMPERATURE: float = 0.0          # 0=确定性输出
    LLM_MAX_TOKENS: int = 2000
    # FAST/STRONG 独立源（2026-08-22 用户裁定）：FAST=火山引擎 ark plan/v3
    # deepseek-v4-flash；STRONG=DeepSeek 官方 deepseek-v4-flash。
    # 留空时回退 LLM_BASE_URL/LLM_API_KEY（同源，旧行为）。
    LLM_FAST_BASE_URL: str = ""           # FAST 专属 base（火山引擎 https://ark.cn-beijing.volces.com/api/plan/v3）
    LLM_FAST_API_KEY: str = ""            # FAST 专属 key（ark-...）
    LLM_STRONG_BASE_URL: str = ""         # STRONG 专属 base（DeepSeek 官方 https://api.deepseek.com）
    LLM_STRONG_API_KEY: str = ""          # STRONG 专属 key（sk-...）

    # ============================================================
    # Agent 循环（P2 增强）：LLM 意图决策 → 按需检索 → 生成
    # ============================================================
    USE_AGENT_LOOP: bool = True          # 总开关；False 回退「检索先行」
    AGENT_DECISION_ENABLED: bool = True  # 决策层开关；False 则直接检索

    # ============================================================
    # 子代理（task92 R1 独立上下文）
    # ============================================================
    SUBAGENT_ARTIFACT_TTL: int = 3600    # 子代理 artifact 完整输出 TTL（秒，对齐 Claude Code 1h）
    SUBAGENT_SUMMARY_BUDGET: int = 2000  # 主 state 仅收的摘要 token 预算上限

    # ============================================================
    # AI 助手 LangGraph 图（task24）
    # ============================================================
    MAX_REFLECT_ITERATIONS: int = 2       # LLM-as-judge 最大回 plan 轮数，超限 answer 标 degraded_reason="reflect_max_iter"

    # ============================================================
    # compaction + R4 context editing + artifact 分流（task26）
    #   对齐 Anthropic《Effective Context Engineering》Compaction 章节：
    #   - 6000 token 阈值；新增 >3000 再触发
    #   - context_edit（轻量删消息保留缓存前缀）优先，仍超阈值才 compaction（重量）
    #   - tool result clearing：单条工具输出 >1500 token 立即蒸馏进 artifact（TTL 1h），流内仅 1 行结论
    # ============================================================
    COMPACTION_TOKEN_THRESHOLD: int = 6000    # 消息流超此阈值 → plan_node 前压缩至 ≤6000
    COMPACTION_REFRESH_THRESHOLD: int = 3000  # compaction 后新增超此值再触发
    COMPACTION_KEEP_ROUNDS: int = 6           # 压缩后保留最近 K 轮原文
    COMPACTION_TOOL_OUTPUT_THRESHOLD: int = 1500  # 单条工具输出超此 token → 立即蒸馏
    ARTIFACT_TTL: int = 3600                  # artifact 完整输出 TTL（秒，对齐 1h）
    CHECKPOINT_TTL: int = 604800              # LangGraph checkpoint TTL（7 天 = 604800s，对齐 task26 防过载）

    # ============================================================
    # 【task96 新增段 · R4 context editing 与上下文使用率监控】※ 本段为 task96 专属，
    #   并行任务（task93 skills / task95 MCP）请勿在此段内插入配置，避免 merge 冲突。
    #   对齐 Claude Code《Manage Claude's context window》：context editing = 最轻量上下文管理
    #   （精确删历史消息、不重写前缀 → prompt cache 前缀仍命中）；compaction 为重量兜底。
    # ============================================================
    CONTEXT_WINDOW_TOKENS: int = 32000        # 上下文窗口预算（使用率分母；按实际模型窗口调整）
    CONTEXT_USAGE_WARN_RATIO: float = 0.6     # 使用率告警水位，≥此比例记 warn 快照并打日志
    CONTEXT_EDIT_ENABLED: bool = True         # 灰度开关；False → 跳过轻量编辑直接走 compaction
    CONTEXT_EDIT_KEEP_RECENT_ROUNDS: int = 0  # 保护最近 N 轮工具对不被删（0=删除全部已完成对）
    CONTEXT_EDIT_DROP_REDUNDANT_REASONING: bool = True  # 顺带删除紧邻被删工具对的填充式中间推理
    CONTEXT_STRATEGY_ORDER: str = "context_edit,compaction"  # 阈值策略顺序（轻量优先，重量兜底）
    CONTEXT_USAGE_MONITOR_MAX: int = 50       # 使用率快照环形缓冲条数上限
    # ============================================================
    # 【task96 新增段结束】
    # ============================================================

    # ============================================================
    # 【task-C1 新增段 · 上下文动态压缩（token 预算分配器 + 锚定闸门）】※ 本段为 task-C1 专属，
    #   对齐 Codex token 预算分配器 / Claude 锚定策略（production-upgrade-plan.md P4）。
    #   - COMPACTION_BUDGET_RATIOS：压缩时按内容类型分配 token 预算（Σ=1.0）。
    #   - ANCHOR_ROUND：锚定闸门轮数；闸门前（System + 核心决策轮 + 工具前缀）永不改，保护前缀缓存。
    #   - COMPACTION_LLM_SELECT：LLM 动态选片段总开关；实际生效需调用方注入 llm 调用（窗口内），
    #     未注入时自动回退规则选片段（向后兼容，零回归）。
    # ============================================================
    COMPACTION_BUDGET_RATIOS: dict = {
        "system": 0.10,       # 系统/可缓存前缀
        "user_query": 0.20,   # 用户问题
        "tool_result": 0.30,  # 工具结果
        "history": 0.40,      # 历史上下文
    }
    ANCHOR_ROUND: int = 3                    # 锚定闸门轮数（闸门前字节零改动）
    COMPACTION_LLM_SELECT: bool = True       # LLM 动态选片段总开关（未注入 llm 时回退规则）
    # ============================================================
    # 【task-C1 新增段结束】
    # ============================================================

    # ============================================================
    # AI HITL 退款审批（task28：LangGraph interrupt + Command resume）
    #   对齐 tech-source-audit §二 HITL（LangGraph 原生 human checkpoint，无需自研审批状态机）
    # ============================================================
    HITL_REFUND_ENABLED: bool = True            # True=走 HITL 审批图；False=退回 task19 stub
    HITL_ESCALATION_HOURS: int = 72             # 审批无动作超时（小时）→ 升级 high 工单并通知(GWT③)
    HITL_ESCALATION_INTERVAL: int = 1800        # 后台超时扫描间隔（秒）
    HITL_ESCALATION_AUTO: bool = True           # 服务启动时是否自动拉起超时扫描后台任务

    # ============================================================
    # Redis 防过载（task26：全局 LLM 并发闸 + 会话并发 + 队列削峰 + 大 key 治理）
    # ============================================================
    LLM_GLOBAL_CONCURRENCY: int = 8           # 全局 LLM 并发闸上限（信号量 + Redis 分布式计数）
    USER_MAX_CONCURRENT: int = 2              # 单用户最大并发请求，第 3 个被拒
    QUEUE_POP_TIMEOUT: float = 10.0           # chat:queue BLPOP 阻塞上限，>此秒返回友好提示
    QUEUE_KEY: str = "chat:queue"             # LLM 请求排队 Redis list key
    CONCURRENT_KEY_PREFIX: str = "chat:concurrent"  # 单用户并发计数 key 前缀（INCR/DECR）
    GLOBAL_CONCURRENT_KEY: str = "ai:llm:concurrent"  # 全局并发计数 key（原子 Lua INCR/DECR）
    ZSET_SHARD_SIZE: int = 50                 # ZSET 单分片条目上限，超限按 member 哈希分片
    BIGKEY_THRESHOLD_BYTES: int = 1048576     # bigkey 扫描告警阈值（1MB = 1024*1024）

    # ============================================================
    # token 级并发预算 + 用户分级队列（task-G1，production-upgrade-plan P5）
    #   并发闸从「请求数」升级为「预估 token 速率预算」（第一道）+ 保留请求数并发闸（第二道）；
    #   L1~L3 优先级队列（L3 大请求优先于 L1 闲聊）；智能重试退避按错误类型动态（见 app/core/retry.py）。
    #   对齐 DeepSeek-V3 用户分级队列 / 通用云 LLM token 速率限制 + 配额 + 预估排队（P5 实证）。
    # ============================================================
    LLM_TOKEN_RATE_LIMIT_PER_MIN: int = 600000     # 全局 LLM 预估 token 速率上限（/分钟），超限进队列不拒绝
    USER_TOKEN_QUOTA_PER_MIN: int = 30000          # 单用户单分钟 token 配额，超配额返回 user_token_quota_exceeded
    ESTIMATE_DEFAULT_TOKENS: int = 2000            # request_meta 缺失时的兜底预估 token
    QUEUE_POP_TIMEOUT_L3: float = 30.0             # L3 大请求排队超时（秒），容忍更长排队
    QUEUE_PRIORITY_ORDER: list = ["L3", "L2", "L1"]  # 消费者轮询优先级顺序（L3 先出队）
    TOKEN_RATE_KEY: str = "ai:llm:token_rate"      # 全局 token 速率计数 key（INCRBY + EXPIRE 60s 窗口）
    USER_TOKEN_KEY_PREFIX: str = "chat:user_token"  # 单用户 token 配额计数 key 前缀（INCRBY + EXPIRE 60s）
    # token 窗口治理升级：固定 60s 窗口 → 令牌桶平滑（G1-②）。
    # 默认关闭以保持既有生产窗口行为不变；开启后全局速率改用令牌桶，消除窗口边界 2× 突发。
    TOKEN_BUCKET_ENABLED: bool = False              # True=全局速率走令牌桶平滑；False=保持固定 60s 窗口
    TOKEN_BUCKET_BURST_RATIO: float = 1.0          # 令牌桶容量 / 速率（=1.0 表示突发上限 = 1 分钟速率）
    TOKEN_BUCKET_REFILL_WINDOW_SEC: float = 60.0   # 令牌桶重填窗口（秒），与速率/分钟对齐

    # ============================================================
    # 观测性基座（task-O1，production-upgrade-plan P8）
    #   trace_id 贯穿 + 5 维指标 + OTel 导出（JSONL 落盘 / OTLP HTTP 双通道）。
    #   对齐 Codex OTel log export / Claude 缓存命中率当 uptime（P8 实证）。
    #   OTEL_EXPORT_ENDPOINT 空 → 结构化 JSONL 落盘 logs/otel/；配置后走 OTLP HTTP。
    # ============================================================
    OTEL_EXPORT_ENDPOINT: str = ""          # 空=本地 JSONL 落盘；配置后走 OTLP HTTP（可选依赖缺失自动降级 JSONL）
    OTEL_JSONL_DIR: str = "logs/otel"      # JSONL 落盘目录（OTEL_EXPORT_ENDPOINT 空时生效）
    OTEL_SAMPLE_RATE: float = 1.0          # 埋点采样率（0~1，1=全量）
    TRACE_SESSION_LEVEL: bool = True       # 会话级 trace_id：同一会话多次请求复用同一 trace_id（span_id 各异）

    # ============================================================
    # AI 助手三层记忆 + 遗忘机制（task25 R7）
    #   Working=LangGraph state｜Short-term=Redis session history+chat_message
    #   Long-term=MySQL user_memory + Milvus/in-memory 向量（用户分区）
    #   遗忘：score = importance×exp(-0.01·Δt) + recency_bonus（Ebbinghaus 指数衰减）
    # ============================================================
    MEMORY_CAPACITY_PER_USER: int = 500            # 默认档（normal）每用户记忆容量上限，超限触发遗忘淘汰
    # 按用户活跃度分档的容量上限（配置化，取代单值硬编码）：部署时可按活跃度/高价值精调
    MEMORY_CAPACITY_TIERS: dict = {
        "inactive": 200,   # 长期不活跃：收紧容量，省存储
        "normal": 500,     # 普通活跃（默认档）
        "active": 1000,    # 高频活跃：放宽
        "power": 2000,     # 重度用户/高价值：最大档
    }
    MEMORY_CAPACITY_DEFAULT_TIER: str = "normal"   # 未指定档时的默认档
    # 指定用户的容量覆盖（user_id -> 容量），用于高价值/灰度用户按活跃度精调
    MEMORY_CAPACITY_USER_OVERRIDE: dict = {}
    MEMORY_SOFT_DELETE_SCORE: float = 0.1          # 综合分 < 此值 → 软删遗忘（时间衰减非误删）
    MEMORY_DECAY_LAMBDA: float = 0.01              # 遗忘曲线衰减系数（Δt 单位天）：exp(-λ·Δt)
    MEMORY_RECENCY_WEIGHT: float = 2.0             # recency_bonus = W/(1+0.1·days_since_access)
    MEMORY_RECENCY_SLOPE: float = 0.1              # recency_bonus 分母斜率
    MEMORY_IMPORTANCE_THRESHOLD: int = 4           # 会话结束落库的重要性下限（≥4 才写长时记忆）
    MEMORY_TOP_K: int = 3                          # 向量召回 top-k 进 lead plan prompt
    MEMORY_QUEUE_KEY: str = "edu:mem_queue"        # 异步写队列 Redis list key
    MEMORY_QUEUE_MAX_RETRY: int = 3                # 单条写失败最大重试次数（异步隔离）
    MEMORY_VECTOR_DIM: int = 512                   # 内存向量降级维度（Milvus 时用 EMBEDDING_DIM=1024）
    MILVUS_MEMORY_COLLECTION: str = "user_memory"  # 记忆向量 collection（用户分区/过滤）

    # ============================================================
    # 记忆事件溯源 + Dream 巩固（task-M1，对齐 production-upgrade-plan P1/P3）
    #   user_memory_event 为记忆唯一事实源（append-only）；user_memory 降级为兼容视图
    # ============================================================
    MEMORY_EVENT_ENABLED: bool = True          # 事件溯源总开关（True=写路径走 user_memory_event）
    MEMORY_EVENT_TTL_DAYS: int = 180          # 容量压缩器保留近期高保真天数（TIME_COMPRESS）
    DREAM_SESSION_INTERVAL: int = 5           # 每 N 会话触发一次 Dream 巩固
    DREAM_MIN_AGE_HOURS: int = 24             # Dream 最小间隔（小时），防抖动频繁巩固
    DREAM_LOCK_TTL_S: int = 600               # Dream 分布式锁 TTL（秒），SET NX EX 窗口锁
    DREAM_MAX_ENTITIES_PER_RUN: int = 200     # 单次 Dream 最多处理实体数（防长尾阻塞）
    DREAM_MODEL: str = "fast"                 # Dream 巩固子代理模型（cost 友好；生产可切 opus）

    # ============================================================
    # 缓存前缀达标（task-C2，对齐 production-upgrade-plan P7）
    #   对齐 Claude prompt caching：最小可缓存前缀 1024 token；低于门槛静默不缓存（DEV 实证）；
    #   工具延迟展开（defer_loading）保前缀稳定；命中率当 uptime 监控（Glean：低即 SEV）。
    # ============================================================
    PROMPT_CACHE_MIN_TOKENS: int = 1024        # 可缓存前缀最小 token（跨过 DeepSeek/Claude 缓存门槛）
    CACHE_FILLER_VERSION: str = "v3"           # 静态填充注释版本号（逐字节稳定，随版本升级）
    TOOL_DEFERRED_MODE: bool = True            # True=决策前缀只放 tool_name+summary，schema 被选中才展开
    CACHE_HIT_RATE_SEV: float = 0.5            # 缓存命中率 < 此值记 SEV（对齐 Claude 把命中率当 uptime）

    # ============================================================
    # Embedding API（独立配置，可与聊天 LLM 不同源）
    #   留空时自动复用 LLM 的 base_url/key；若聊天走 DeepSeek/a6api
    #   （无 embeddings 端点），必须显式配置硅基流动 SiliconFlow。
    # ============================================================
    EMBEDDING_API_URL: str = ""           # 空 → 复用 LLM_BASE_URL
    EMBEDDING_API_KEY: str = ""           # 空 → 复用 LLM_API_KEY
    EMBEDDING_MODEL: str = "BAAI/bge-m3"  # 硅基流动默认；DashScope 用 text-embedding-v3
    # 云端优先（2026-08-22 用户裁定）：EMBED_BACKEND="cloud" → 先调云端 API，
    # 失败再回退本地 CUDA；"cuda" → 本地优先（旧行为）。
    EMBED_BACKEND: str = "cloud"
    # 云端 rerank（硅基流动等 OpenAI 兼容 rerank 端点）
    RERANK_API_URL: str = ""             # 空 → 复用 EMBEDDING_API_URL
    RERANK_API_KEY: str = ""             # 空 → 复用 EMBEDDING_API_KEY
    RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"  # 硅基流动 rerank 模型
    RERANK_BACKEND: str = "cloud"        # "cloud" → 优先云端 API；"cuda" → 本地优先

    # ============================================================
    # P8 MCP 工具调用开关
    # ============================================================
    USE_MCP_TOOL_CALLING: bool = True     # 总开关：False 时聊天流程跳过 MCP 工具调用
    MCP_TOOL_MAX_TRIES: int = 1           # 单轮最多触发几次工具（避免反复调用）

    # ============================================================
    # 【task-T1 新增段 · 工具调用闭环（换参→换工具→熔断→人工指南）】※ 本段为 task-T1 专属，
    #   对齐 Codex orchestrator.rs / auto-review（3 连续拒绝熔断）/ retry telemetry（production-upgrade-plan P6）。
    #   - TOOL_FALLBACK_MAP：原工具失败后尝试的备用工具（按列表顺序取第一个可用）；
    #   - MAX_TOOL_ATTEMPTS：闭环总步数（1 正常→2 换参→3 换工具→4 人工指南）；
    #   - TOOL_CONSECUTIVE_REJECTIONS：同一会话内连续被拒次数上限，达到即中断该回合工具循环；
    #   - TOOL_REJECT_TTL_S：拒绝计数在 Redis 的存活窗口（跨请求持久，防反复打同一失败工具）。
    # ============================================================
    TOOL_FALLBACK_MAP: dict = {
        "web_search": ["calculator", "search_knowledge"],
        "code_runner": ["search_knowledge"],
        "calculator": ["search_knowledge"],
    }
    MAX_TOOL_ATTEMPTS: int = 4                 # 闭环步数：第 4 步 = 结构化人工操作指南并停止
    TOOL_CONSECUTIVE_REJECTIONS: int = 3       # 同会话连续被拒 3 次 → 第 4 次中断回合工具循环
    TOOL_REJECT_TTL_S: int = 300               # 拒绝计数 Redis TTL（秒）
    TOOL_RETRY_LLM_REWRITE: bool = True        # 第 2 步是否尝试 LLM 改写 args（关闭则走规则跳级兜底）
    # ============================================================
    # 【task-T1 新增段结束】
    # ============================================================

    # ============================================================
    # 【task-S1 新增段 · 全流程 HITL 护栏（非单点审批）】※ 本段为 task-S1 专属，
    #   对齐 Claude 解释→提议→同意→行动 透明护栏 + Codex auto-review（3 连续拒绝熔断）。
    #   - HITL_ENABLED：全局总开关；默认 False=关闭（零行为变化，保护 task28 退款 HITL 回归 AC5）。
    #   - HITL_RISK_THRESHOLD：仅风险等级 >= 此值的动作过 Gate（L3 强制全过）。
    #   - HITL_PENDING_TTL_S：pending 超时自动拒绝窗口（AC3）。
    #   - HITL_AI_REVIEW：是否启用 AI 审查子代理（task92 fork）；True 时高风险动作先过 reviewer（AC4）。
    #   - HITL_REJECT_BREAKER：同动作类型连续被拒上限，达到即熔断升级（AC4，对齐 Codex 3 连拒）。
    # ============================================================
    HITL_ENABLED: bool = False                 # 全局总开关；默认关闭，接入 executor 前由运维显式开启
    HITL_RISK_THRESHOLD: str = "L2"            # 仅风险等级 >= 此值的动作过 Gate
    HITL_PENDING_TTL_S: int = 600             # pending 超时自动拒绝窗口（秒）
    HITL_AI_REVIEW: bool = False              # 是否启用 AI 审查子代理（仅测试窗口内开）
    HITL_REJECT_BREAKER: int = 3              # 同动作类型连续被拒达此数 → 第 N+1 次熔断升级（需管理员）
    HITL_OPERATOR: str = ""                   # 默认操作者标识（executor 接入时由 user_id 覆盖）
    # ============================================================
    # 【task-S1 新增段结束】
    # ============================================================

    # ============================================================
    # 【task-R1 新增段 · Rerank sidecar 独立服务 + 连续批处理】
    #   P9：Rerank 同进程阻塞事件循环 → 拆 sidecar 进程 + 跨请求连续批处理。
    #   默认 RERANK_SIDECAR_ENABLED=True：主链路经 HTTP 调 sidecar（GPU 计算在独立进程，
    #   不阻塞主事件循环）；sidecar 不可达自动回退进程内直连（task31 现状），再失败走规则兜底。
    RERANK_SERVICE_PORT: int = 8601           # sidecar 监听端口
    RERANK_SERVICE_URL: str = "http://127.0.0.1:8601"   # 主链路调用地址
    RERANK_BATCH_WINDOW_MS: int = 20          # 攒批窗口：窗口内到达的请求合并成一批
    RERANK_MAX_BATCH_PAIRS: int = 64          # 单批最大 (query,content) 对数，超则拆下一批
    RERANK_MAX_WAIT_MS: int = 50              # 单请求排队延迟上限（到时强制 flush）
    RERANK_QUEUE_MAX: int = 200               # 内存队列上限，超则调用方走降级（返回 503/None）
    RERANK_HTTP_TIMEOUT: float = 2.0          # 主链路调 sidecar 超时（秒）
    RERANK_SIDECAR_ENABLED: bool = True       # False → 主链路直接进程内 rerank（平滑切换/降级调试）
    RERANK_QUEUE_REDIS: bool = False          # 可选：Redis list 缓冲峰值（默认直连 batcher）
    # ============================================================
    # 【task-R1 新增段结束】
    # ============================================================

    # ============================================================
    # 【task-A1 新增段 · 可插拔 Harness 抽象（替代硬编码 6 节点图）】
    #   - HARNESS_IMPL：选择 harness 实现（节点级可替换，图结构不变）。
    #   - 默认 sixnode = 现有 6 节点 DAG（route/plan/fan_out/merge/reflect/answer）
    #     + skill/compact/context_edit 支持节点；对齐 task29 R8 keep_sixnode 裁定，
    #     默认行为零变化（AC2 / AC4）。
    #   - 注册自定义实现见 app/ai/harness/registry.register_harness。
    # ============================================================
    HARNESS_IMPL: str = "sixnode"            # 可插拔实现选择；"sixnode" 为默认（重构前行为零差异）

    # ============================================================
    # task-M2：Redis 共享向量降级链（多实例一致性）
    #   降级链 milvus → redis → memory；任一不可达自动落下一档，不 500。
    #   Redis 结构：HSET memory:vec:{user_id} -> {memory_id: json(vector)}
    #               ZSET memory:vec:idx:{user_id} -> {memory_id: score}（枚举/排序索引）
    #               HSET memory:vec:owner -> {memory_id: user_id}（删除反向映射）
    #   跨实例一致：写入/读取走同一 Redis key，多实例召回结果一致（AC1/AC4）。
    # ============================================================
    MEMORY_VECTOR_BACKEND_ORDER: list[str] = ["milvus", "redis", "memory"]
    MEMORY_REDIS_VEC_KEY_PREFIX: str = "memory:vec"
    MEMORY_REDIS_SCAN_LIMIT: int = 2000      # 单用户向量枚举上限，防大 key

    # ============================================================
    # task30 RAG Contextual Retrieval（chunk 上下文前缀 + 降级）
    #   对齐 tech-source-audit §三：contextual embeddings 降 35% 失败率；
    #   仅知识型内容（题库/代码跳过），并发 ≤8 不击穿 LLM 预算。
    #   默认 False=关闭（避免量产无感知烧 LLM 额度，R-独立审查 P2）；真正启用由
    #   运维在 .env 设 CONTEXTUALIZE_ENABLED=True 并确认模型/额度预算。
    # ============================================================
    CONTEXTUALIZE_ENABLED: bool = False             # 总开关；False 跳过前缀（保留原 chunk 原文）
    CONTEXTUALIZE_MODEL: str = "fast"               # 生成前缀用便宜快速模型（省 DeepSeek 额度）
    CONTEXTUALIZE_MAX_CONCURRENCY: int = 8          # 前缀生成最大并发（GWT③ 并发 ≤8）
    CONTEXT_PREFIX_TOKEN_BUDGET_MIN: int = 50       # 前缀 token 下限（CONTEXT_PROMPT 约束）
    CONTEXT_PREFIX_TOKEN_BUDGET_MAX: int = 100      # 前缀 token 上限

    # ============================================================
    # 日志配置
    # ============================================================
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    LOG_DIR: str = "./logs"
    LOG_ROTATION: str = "100 MB"          # 单文件最大大小
    LOG_RETENTION: str = "7 days"         # 保留时长

    # ============================================================
    # 鉴权配置 —— 密码哈希 + JWT 双 Token
    # ============================================================
    # JWT 签名密钥（生产环境必须替换成强随机 32 字节 hex，生成：python -c "import secrets;print(secrets.token_hex(32))"）
    JWT_SECRET: str = "dev-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"

    # access_token：用于日常接口调用，过期要拿 refresh_token 换新
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24   # 24 小时（默认）
    # refresh_token：用于换新 access_token，实现「7 天滑动过期」
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7            # 7 天（默认）
    # 兼容老字段（其他模块还在用 JWT_EXPIRE_MINUTES）
    JWT_EXPIRE_MINUTES: int = 60 * 24

    # bcrypt 哈希轮次（12 轮 ≈ 250ms，防暴力破解；服务器 CPU 强可升 13/14）
    PASSWORD_HASH_ROUNDS: int = 12

    # 管理端 API 占位 Token（部分后台内部脚本调用时使用）
    API_TOKEN: str = "edu-agent-dev-token"

    # ============================================================
    # 检索参数（P2 调优时改这里，不用改代码）
    # ============================================================
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    TOP_K_RECALL: int = 20
    TOP_K_RERANK: int = 5
    CLIFF_MIN_KEEP: int = 3
    CLIFF_MAX_KEEP: int = 8
    CLIFF_RATIO: float = 0.4

    # ============================================================
    # task31 RAG reranker 接入（top-150 → rerank top-20 → 断崖 → 5）
    #   tech-source-audit §三：bge-reranker-v2-m3 本地化零 API 成本。
    #   RERANKER_* 懒加载默认值见模型配置段（PATH/DEVICE/BATCH_SIZE=16）。
    # ============================================================
    RETRIEVER_RECALL_TOPK: int = 150           # RRF 融合后召回候选（GWT② 12→150）
    RETRIEVER_RERANK_TOPK: int = 20            # rerank 后保留 top-n 再断崖
    # course_public 保留分区：课程知识隔离用户上传（GWT③），检索期排除下列 content_type 防促销/班次混入
    COURSE_PUBLIC_PARTITION: str = "course_public"
    RETRIEVER_EXCLUDE_CONTENT_TYPES: tuple[str, ...] = (
        "promotion", "schedule", "announcement", "marketing",
    )

    # ============================================================
    # P7 管理端 RAG：rebuild 状态机（task04 #3/#8）
    # ============================================================
    RAG_REBUILD_TIMEOUT_SECONDS: int = 120   # rebuilding 超过此时长（秒）未完成 → list_collections 自动回置 error

    # ============================================================
    # SQL 安全（P4）
    # ============================================================
    SQL_MAX_ROWS: int = 1000
    SQL_TIMEOUT: int = 30
    SQL_MAX_REPAIR: int = 2

    # ============================================================
    # task-E1 评估体系：影子模式 / 金丝雀 / 4 维 Judge
    #   - SHADOW_MODE_ENABLED：开启后主链路答案不变，影子对比 fire-and-forget 落库不阻塞
    #   - CANARY_RATIO：金丝雀分流比例（默认 1%）；CANARY_DAYS：观察窗口天数
    #   - JUDGE_DIMENSIONS：4 维 Judge 维度（替代单一 0-1）
    # ============================================================
    SHADOW_MODE_ENABLED: bool = False
    SHADOW_MODE_RATIO: float = 1.0
    CANARY_RATIO: float = 0.01
    CANARY_DAYS: int = 3
    JUDGE_DIMENSIONS: list[str] = ["fact_correctness", "completeness", "harmlessness", "coherence"]

    # ============================================================
    # 路径配置
    # ============================================================
    DATA_DIR: str = "./data"
    KNOWLEDGE_SOURCE_DIR: str = "C:/Users/Administrator/Desktop/edu"

    # ============================================================
    # pydantic-settings 配置
    # ============================================================
    @model_validator(mode="after")
    def _security_guard(self):
        """生产环境安全护栏（fail-fast）：防公开默认值/裸奔配置上线。

        - DEBUG=False（生产）时：JWT_SECRET 用公开默认值、API_TOKEN 用默认值 → 直接拒绝启动
        - DEBUG=True 时：仅打告警（本地开发便利，不阻断）
        """
        import logging

        _log = logging.getLogger("eduguard")
        public_jwt = {"", "dev-secret-key-change-in-production"}
        public_token = {"", "edu-agent-dev-token"}

        if not self.DEBUG:
            if self.JWT_SECRET in public_jwt:
                raise ValueError(
                    "生产环境禁止使用默认 JWT_SECRET。请设置强随机密钥："
                    "python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            if self.API_TOKEN in public_token:
                raise ValueError(
                    "生产环境禁止使用默认 API_TOKEN。请设置随机值。"
                )
        else:
            if self.JWT_SECRET in public_jwt:
                _log.warning("[安全] DEBUG 模式使用公开 JWT_SECRET，仅限本地开发，禁止上线")
            if self.API_TOKEN in public_token:
                _log.warning("[安全] DEBUG 模式使用默认 API_TOKEN，仅限本地开发，禁止上线")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",                  # 从 .env 文件读取
        env_file_encoding="utf-8",
        case_sensitive=False,             # 环境变量不区分大小写
        extra="ignore",                   # 忽略未定义的环境变量
    )


# 全局单例
settings = Settings()


def memory_capacity_for(user_id: int, *, tier: str | None = None) -> int:
    """按用户活跃度分档解析记忆容量上限（配置化，非硬编码）。

    - user_id 命中 MEMORY_CAPACITY_USER_OVERRIDE → 直接用覆盖值（按活跃度/高价值精调）；
    - 否则按 tier（默认 MEMORY_CAPACITY_DEFAULT_TIER）从 MEMORY_CAPACITY_TIERS 取值；
    - 兜底回退到 MEMORY_CAPACITY_PER_USER（normal 档）。
    """
    override = settings.MEMORY_CAPACITY_USER_OVERRIDE.get(int(user_id))
    if override is not None:
        return int(override)
    t = tier or settings.MEMORY_CAPACITY_DEFAULT_TIER
    return int(settings.MEMORY_CAPACITY_TIERS.get(t, settings.MEMORY_CAPACITY_PER_USER))
