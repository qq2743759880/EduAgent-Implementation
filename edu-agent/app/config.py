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
    # 环境名（H1b P1-8）：local=本机开发（DEBUG 虚拟管理员允许）；非 local（如
    # dev/staging/prod/production 等）为显式声明的生产类环境。仅作为 DEBUG
    # 启动硬门禁（_debug_env_gate）的判据使用，别处请勿当部署参数消费。
    ENV_NAME: str = "local"

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
    # task39 GWT① 实证：Windows 上 `localhost` 经 getaddrinfo 优先解析为 IPv6 `::1`，
    # 而本机 Redis（Windows 构建）只监听 IPv4 → 每次新建连接都要先撞一次 IPv6 建连超时
    # 再回落 IPv4。实测 20 并发首次连接：localhost 6058ms vs 127.0.0.1 4ms（1500×）。
    # 该延迟落在 chat 热路径（checkpoint/限流/缓存每次冷连接都要付），是 P95 吹高的隐形项。
    # 这里在配置层把 `localhost` 归一为 `127.0.0.1`（语义等价，见 _normalize_loopback）。
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 20          # 连接池上限
    REDIS_SOCKET_TIMEOUT: float = 5.0        # 单次操作超时（秒）
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 3.0 # 建连超时（秒）
    REDIS_RETRY_ON_TIMEOUT: bool = True      # 超时自动重试一次

    # Schema 注册表（C2-③：跨实例 Redis 共享，task-M2 协同）
    SCHEMA_REGISTRY_REDIS_ENABLED: bool = True        # False → 纯本地（向后兼容/无 Redis 环境）
    SCHEMA_REGISTRY_CACHE_TTL: float = 30.0          # 本地缓存 TTL（秒），吸收 Redis 读延迟
    SCHEMA_REGISTRY_NAMESPACE: str = "default"       # 同 namespace 多实例共享同一 schema 集合
    SCHEMA_REGISTRY_KEY_PREFIX: str = "edu:schema"   # Redis key 前缀

    # ============================================================
    # Milvus 配置（向量数据库，部署在虚拟机 Docker 上）
    # ============================================================
    MILVUS_URI: str = "http://192.168.85.101:19530"
    MILVUS_TOKEN: str = ""                # 无认证时留空
    MILVUS_DB: str = "default"
    MILVUS_COLLECTION: str = "edu_knowledge"
    MILVUS_SEARCH_TIMEOUT: float = 8.0    # Milvus 混合检索超时（秒），超时降级不拖死链路（P1-4）
    # VEC-LOCK dim9：dense ANN 检索 nprobe（IVF_FLAT nlist=128 时 nprobe=32 与 FLAT 全等，
    # 实测 nprobe=10 有 4/20 查询 top-10 重合度 <0.98 → 默认抬到 32，消除 ANN 召回缺口）
    RAG_DENSE_NPROBE: int = 32

    # W-NEXT-INT-001B：classify_internal 内容语义判定可配置项（治本重写）。
    #   INTERNAL_FILENAME_PATTERNS：来源文件名兜底正则；缺省由 internal_classifier 提供。
    #   INTERNAL_KEYWORDS：5 桶关键词字典 {bucket: [(label, pattern, weight)]}；
    #     留空用 DEFAULT_KEYWORD_BUCKETS（治本内建）。
    #   INTERNAL_SCORE_THRESHOLD：内容打分阈值（>= 即标 internal=True）。
    #   行为同 INTERNAL_KEYWORDS=[]：走默认桶；settings 注入空 dict = 禁用所有内容打分（仅文件名兜底）。
    INTERNAL_FILENAME_PATTERNS: list = []         # list[str]；空 = 用 default
    INTERNAL_KEYWORDS: dict = {}                 # dict[bucket_name, list[(label, pattern, weight)]]；空 = 用 default
    INTERNAL_SCORE_THRESHOLD: float = 0.6

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
    # R1-① fp32 批处理：默认 fp16（省显存，历史行为零回归）；置 "fp32" 启用高精度路径
    # （跳过 .half()，分数噪声 < 1e-4，跨请求批处理排序更稳定，对排序敏感场景更稳）。
    RERANKER_PRECISION: Literal["fp16", "fp32"] = "fp16"

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
    # task-P1L LLM 延迟治理：规则路由 / 直连快路径（0-LLM 决策）
    #   对齐 Anthropic Building Effective Agents：高频确定性意图用 workflow（规则）分流，
    #   LLM 仅兜底开放场景。三开关默认开启，压测/异常时可整体或分级关闭回退旧链路。
    # ============================================================
    RULE_ROUTING_ENABLED: bool = True                # route/decide_agent_plan 规则分类先行（命中 0 LLM；未命中默认 knowledge）
    KNOWLEDGE_DIRECT_RETRIEVAL_ENABLED: bool = True  # L1 knowledge：fan_out 直连检索，跳过子代理 LLM 循环
    SUBAGENT_DIRECT_TOOL_ENABLED: bool = True        # 单工具子代理：turn-1 预执行唯一工具，LLM 仅总结轮

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
    # R02 流式主路径进 LangGraph（dev-plan-reshape-r W2）
    # ============================================================
    # 流式主路径执行体开关：True → POST /api/chat/stream 经 graph.astream（六节点图）执行；
    # False → 一键回旧路径 run_agent_turn（flows/agent.py 普通函数）。SSE 契约冻结（contracts/reshape-a.json）。
    STREAM_VIA_GRAPH: bool = True
    # 图内检索参数对齐旧路径（R02 检索参数对齐；基线=RagQueryRequest 生产默认 + R20-b PROD_DEFAULTS）。
    # 六节点直连检索（sixnode.fan_out knowledge 快路径）与子代理 search_knowledge 服务共用。
    SIXNODE_USE_HYDE: bool = True            # 对齐旧路径 use_hyde=True（R20-b 根因：图内硬编码 False 致 Jaccard 0.641）
    SIXNODE_TOP_K: int = 12                  # 对齐旧路径 top_k=12（图内硬编码 8）
    SIXNODE_FINAL_MAX_K: int = 5             # 对齐旧路径 final_max_k=5
    SIXNODE_CUTOFF_DROP_RATIO: float = 0.40  # 对齐旧路径断崖阈值 0.40（图内硬编码 0.2）
    # 图内 answer 节点流式吐 token 的上层开关（适配层经 configurable.stream_tokens 逐请求门控；
    # 本开关为全局熔断，False 时图内一律阻塞生成，流式路径退化为整段一次性 token）
    GRAPH_ANSWER_STREAMING: bool = True

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
    # 【H 加固批 · Mimosa 审计登记项 ①② 修复开关】※ 独立安全加固配置段
    # ============================================================
    # ① coding 判题 exec 子进程隔离（H-1）：True → 用户代码在独立 python 子进程
    #   （-I isolated mode）中执行，timeout 硬杀；False → 回退旧进程内 exec 路径
    #   （回滚开关，默认开）。
    CODING_EXEC_SUBPROCESS: bool = True
    # ② checkpoint 快照 HMAC 签名（H-2）：True → pickle 快照包 HMAC-SHA256 信封写入，
    #   读时恒定时间校验，不过即丢弃走重建（Redis 被写不再等于 RCE）；False → 回退旧
    #   无签名裸 pickle 行为（回滚开关，默认开）。
    CHECKPOINT_SIGN: bool = True
    # HMAC 独立密钥：留空 → 回退 JWT_SECRET（启动 WARN 提示隔离性缺失）。
    CHECKPOINT_HMAC_KEY: str = ""

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
    FREEZE_ZONE_MAX_RATIO: float = 0.5       # C1-③ 冻结区 token 占比阈值；占比>此值触发告警+建议降 ANCHOR_ROUND
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
    GUARD_SLOT_TTL: int = 600                # 并发槽 TTL 自愈（R20-b 缺陷：进程崩溃残留槽永不释放 → 用户被永久拒；TTL 须 > 最长请求时长）
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
    # W-NEXT-OTLP-001：标准 OTLP HTTP 导出器探针（生产连 OTel Collector 用）。
    #   与 app/otel/exporter.py 的 OTEL_EXPORT_ENDPOINT（JSONL 兜底）并存：本字段为空时
    #   init_otlp() 走 SKIP，仅打 INFO；非空时 init_otlp() 启动期做 SSRF 白名单守门 + 探活，
    #   任何失败仅 WARN 不阻断（与现有 6 存储 init 同语义）。默认 disabled 防首次启动报错。
    #   字段命名遵循 OpenTelemetry 标准环境变量（OTEL_EXPORTER_OTLP_ENDPOINT）。
    # ============================================================
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""       # 空=disabled（不探活、不导出）；非空=OTel Collector HTTP 端点
    OTEL_EXPORTER_OTLP_HEADERS: str = ""        # 可选：`k1=v1,k2=v2`；header 仅从环境配置读取（密钥零入库）
    OTEL_SERVICE_NAME: str = "edu-agent"        # resource 属性 service.name（OTel 标准）
    OTEL_EXPORTER_OTLP_TIMEOUT_S: float = 2.0   # 单次 HTTP POST 超时（秒），防 collector 慢拖累主链路
    OTEL_EXPORTER_OTLP_PROBE_ON_START: bool = True  # 启动期是否做一次 SSRF 白名单+探活（False=跳过启动探活）

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
    # R01-b：mem0 式对话窗抽取（用户 query + assistant 回复成对，抽取在 worker 内完成）
    MEMORY_INGEST_WINDOW: int = 10                 # 每轮入队的最近对话条数（用户/助手发言）
    MEMORY_LLM_EXTRACT_ENABLED: bool = True        # worker 内 LLM 事实抽取开关（False=仅规则抽取）
    MEMORY_EXTRACT_MODEL: str = "fast"             # 抽取 LLM 通道（与 Dream 巩固同档，cost 友好）
    MEMORY_EXTRACT_MAX_TOKENS: int = 600           # 抽取输出上限（JSON 数组，防 token 膨胀）
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
    #   对齐 Claude prompt caching：最小可缓存前缀 2048 token（火山 ark 实测 2048 分块）；
    #   工具延迟展开（defer_loading）保前缀稳定；命中率当 uptime 监控（Glean：低即 SEV）。
    # ============================================================
    PROMPT_CACHE_MIN_TOKENS: int = 2048        # 可缓存前缀最小 token（火山 ark 实测缓存按 2048-token 分块，1024 永远命中 0 块）
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
    # VEC-LOCK（模型一致性锁定）：sha256 伪向量默认禁入库——宁可任务失败标记重试，
    # 不静默混写假向量污染索引（audit-rag #10）。置 True 仅用于对账/一次性重建场景。
    EMBED_ALLOW_FAKE_VECTOR: bool = False
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
    # B1（reshape-b）：stdio 单台健康检查复用 sessions 池长连会话（池内仅发一条 ping）。
    # False = 回滚开关：退回一次性 spawn 全握手旧路径（行为与 B1 前完全一致）。
    MCP_HC_USE_POOL: bool = True
    MCP_HC_SESSION_TTL_S: int = 600       # hc 专用会话空闲 TTL（秒），session_create 内钳制 30~1800

    # ============================================================
    # WNEXT10 F5-b / WNEXT11：平台自有 skill 根目录（生产必核对）
    # ------------------------------------------------------------
    # 平台默认 skill 注册表（app.ai.skills.registry.default()）只扫描本变量指向的平台
    # **自有** skill 根目录（os.pathsep 分隔多个根），用于把平台自身维护的 skill 注入
    # 平台 agent 的 skill_context。
    #
    # 安全缺省：默认空串 = 不消费任何平台 skill 根 → skill_node 只注入
    # platform_capability_block()（源自 permission_gate.TOOL_CLASS_MAP 实物清单），
    # 不注入任何开发机 skill body（list_directory/read_file 等 dev-host 工具绝不泄漏）。
    #
    # 生产部署形态：
    #   - 不配置（保持空）→ skill_node 仅注入 platform 实物能力清单，无平台自有 skill；
    #   - 配置为平台自有 skill 根目录 → 这些 skill 的 body 会进 skill_context。
    # 该字段与开发机 AI-Hub（registry.dev_default）完全隔离，二者互不影响。
    # ============================================================
    EDUAGENT_PLATFORM_SKILL_ROOTS: str = ""

    # ============================================================
    # R12：图内 LLM 工具决策接管（dev-plan-reshape-r W3）
    #   默认 rule = 现行为（tool_calling._parse_heuristic 启发式正则），不改生产；
    #   llm = LLM 决策器（tool_decision.decide_tool_plan）：query+真实 registry 工具清单
    #   → 结构化 tool_plan；超时/异常 → 规则路由 fallback，降级计数入日志。
    # ============================================================
    TOOL_DECISION_MODE: str = "rule"      # "rule"=启发式正则（现行为，默认） | "llm"=LLM 决策器
    TOOL_DECISION_TIMEOUT: float = 5.0    # llm 模式决策超时预算（秒）；超时→规则路由 fallback（防 TTFT 劣化）

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
    # HITL_ENABLED_REQUIRED：上线守卫期望值。生产环境(ENV_NAME in prod/production)必须为 True，
    # 否则主链路写类工具经 chat 流式触发后**静默失败**（SURFACED-1：executor 拒收缺 tool_name +
    # HITL 关闭时写类工具直接 fail 而非挂起确认），等于 HITL 第四道防线与生产断开。
    # 与 HITL_ENABLED 默认值区分：HITL_ENABLED 默认 False 保护 task28 退款回归 AC5（零行为变化），
    # 但生产部署必须显式 True，否则 _hitl_prod_guard 启动硬拒（fail-fast）。
    HITL_ENABLED_REQUIRED: bool = True         # 生产环境 HITL_ENABLED 应取值（启动守卫对照）
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
    RERANK_HTTP_TIMEOUT: float = 10.0         # 主链路调 sidecar 超时（秒）：2.0 在 6 并发×20docs 批处理+GPU 竞争下过紧，易误触发进程内回退→事件循环阻塞→雪崩链（2026-08-29 周末复测实测 44 次 ConnectTimeout/ReadTimeout）
    RERANK_SIDECAR_ENABLED: bool = True       # False → 主链路直接进程内 rerank（平滑切换/降级调试）
    RERANK_QUEUE_REDIS: bool = False          # 可选：Redis list 缓冲峰值（默认直连 batcher）
    # R02-tail（TTFT 检索段优化，profile 实测驱动）：
    #   实测 sidecar 不可达时每次请求的连接尝试固定烧 ~2.05s（8010 profile 4 轮全部 2051~2092ms），
    #   占 start→retrieval 的 ~55%。两项不改检索语义的修复：
    #   - RERANK_CONNECT_TIMEOUT：连接相位独立短超时（连接失败快速暴露，不再吃满总超时/连接耗尽）；
    #   - RERANK_SIDECAR_COOLDOWN_S：连接失败后 sidecar 熔断冷却窗（窗内直接进程内直连，分数与
    #     sidecar 同模型同批式等价——rerank_pairs AC1；冷却到期自动重试，自愈不丧失 sidecar 优先级）。
    RERANK_CONNECT_TIMEOUT: float = 1.0       # sidecar 连接相位超时（秒）；0 = 沿用 RERANK_HTTP_TIMEOUT
    RERANK_SIDECAR_COOLDOWN_S: float = 60.0   # sidecar 连接失败熔断冷却窗（秒）；0 = 关闭熔断（逐请求重试）
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

    # refresh_token 轮换 allowlist（C5-K4）：默认开。登录/刷新签发的 refresh_token
    # 带 jti，Redis 存 rt:{user_id}:{jti}（TTL=refresh 有效期）；刷新成功原子消费
    # 旧 jti、登记新 jti（轮换后旧 refresh 被拒，防重放）。Redis 降级 fail-open
    # （跳过校验维持旧行为）；false=回退轮换前行为（存量会话不失效）。
    JWT_REFRESH_ROTATION_ENABLED: bool = True
    # 兼容老字段（其他模块还在用 JWT_EXPIRE_MINUTES）
    JWT_EXPIRE_MINUTES: int = 60 * 24

    # bcrypt 哈希轮次（12 轮 ≈ 250ms，防暴力破解；服务器 CPU 强可升 13/14）
    PASSWORD_HASH_ROUNDS: int = 12

    # 管理端 API 占位 Token（部分后台内部脚本调用时使用）
    API_TOKEN: str = "edu-agent-dev-token"

    # /metrics 抓取门禁（C5-K1）：可选。留空 → /metrics 维持公开（向后兼容，
    # 监控抓取不被破坏，启动打 WARN）；设置后 /metrics 要求
    # Authorization: Bearer <METRICS_TOKEN>，否则 401（Prometheus
    # bearer_token/bearer_token_file 配置同一值即可）。
    METRICS_TOKEN: str = ""

    # JWT 轮换窗口期旧密钥（C5-K2）：可选。轮换 JWT_SECRET 时把旧密钥填到这里，
    # 验签先试当前密钥、失败再试旧密钥（旧 token 在窗口期内仍有效）；签发永远
    # 只用 JWT_SECRET。窗口期结束后清空本字段即可彻底作废旧密钥签发的 token。
    JWT_SECRET_PREVIOUS: str = ""

    # 500 错误上报 Webhook（C5-K3）：可选。非 DEBUG 且设置时，全局兜底异常处理
    # 对 500 级异常 POST 精简载荷（trace_id/时间/异常类型/堆栈首 2000 字符）到该
    # URL；发送失败静默不影响错误响应，DEBUG 模式一律不发。响应契约零变更。
    ERROR_WEBHOOK_URL: str = ""

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
    def _normalize_loopback(self):
        """把 REDIS_URL 里的 `localhost` 归一为 `127.0.0.1`（task39 GWT① 实证修复）。

        为什么必须在配置层做：
          仅改 .env 不解决他人/其它环境复现；而 Redis 客户端每次新建连接都会重新解析主机名，
          只要 URL 里还是 localhost，冷连接就要再付一次 IPv6 超时。归一后 IPv4/IPv6 双栈
          与纯 IPv4 部署均等价可用（127.0.0.1 在两种环境下都能连上）。
        只改写 host 恰为 `localhost` 的情形，显式 `::1` / 域名 / IP 一律不动。
        """
        from urllib.parse import urlsplit, urlunsplit

        url = (self.REDIS_URL or "").strip()
        if not url:
            return self
        try:
            parts = urlsplit(url)
            if parts.hostname and parts.hostname.lower() == "localhost":
                netloc = parts.netloc
                # 保留 userinfo/port，只替换 host 段
                host_start = netloc.rfind("@") + 1
                host_end = netloc.find(":", host_start)
                host_end = len(netloc) if host_end == -1 else host_end
                netloc = netloc[:host_start] + "127.0.0.1" + netloc[host_end:]
                self.REDIS_URL = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
        except Exception:  # noqa: BLE001 — 解析失败保持原值，不改行为
            return self
        return self

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

    @model_validator(mode="after")
    def _debug_env_gate(self):
        """DEBUG 虚拟管理员启动硬门禁（H1b / P1-8，fail-fast）。

        背景：DEBUG=true 时未携带 Authorization 的请求会被注入虚拟管理员
        user_id=1（app/auth/dependencies.py 规则②），生产误开 DEBUG 等于
        匿名可读全量用户数据（P1-8 批判）。原状仅有 _security_guard 的告警，
        本门禁升级为硬约束：

        - DEBUG=True 且 ENV_NAME 显式为非 local（如 prod/production/staging/
          dev/qa 等，大小写不敏感）→ 抛 ValueError 拒绝启动（对标 Django
          DEBUG 生产拒启）；
        - DEBUG=True 且 ENV_NAME 为 local（默认）→ 放行（本机开发体验不变，
          Windows 本机现有 .env DEBUG=true 照常能启动）；
        - DEBUG=False → 与 DEBUG 无关，门禁不生效（生产启动不受影响）。
        """
        env = (self.ENV_NAME or "").strip().lower()
        if self.DEBUG and env not in ("", "local"):
            raise ValueError(
                f"启动拒绝：DEBUG=true 且 ENV_NAME='{self.ENV_NAME}' 为非本机环境。"
                "DEBUG 模式存在虚拟管理员后门（未登录可读用户数据），禁止在非 local "
                "环境开启。请改用 DEBUG=false 并配置正式鉴权，或 ENV_NAME=local 仅限本机开发。"
            )
        return self

    @model_validator(mode="after")
    def _hitl_prod_guard(self):
        """HITL 上线守卫（SURFACED-1 防假闭环复发，fail-fast）。

        HITL_ENABLED 默认 False 是为保护 task28 退款回归 AC5（零行为变化），但生产环境
        若 HITL_ENABLED 仍为 False，则：
          - chat 流式触发的写类工具（knowledge_import 等内置）直接 `_mcp_executor.call_tool`
            而不挂起确认，叠加 SURFACED-1 的 tool_name 缺口 → executor 拒收 → 工具静默失败；
          - 等于 HITL 第四道防线与生产实际断开（W-NEXT-2 P0-2）。
        故生产环境(ENV_NAME in prod/production)且 HITL_ENABLED=False → 启动硬拒，强制运维
        在 .env 显式 `HITL_ENABLED=True`。本机 local/debug 不受影响。
        """
        env = (self.ENV_NAME or "").strip().lower()
        import logging
        _log = logging.getLogger("eduguard")
        if env in ("prod", "production") and not self.HITL_ENABLED:
            raise RuntimeError(
                "启动拒绝：生产环境(ENV_NAME='%s') 必须启用 HITL_ENABLED=True。"
                "当前 HITL_ENABLED=False，chat 流式写类工具将静默失败（HITL 第四道防线断开）。"
                "请在 .env 显式设置 HITL_ENABLED=True 后重启；本机开发用 ENV_NAME=local 不受影响。"
                % self.ENV_NAME
            )
        # W-NEXT-2 写类知识库导入：生产虽显式开了 HITL_ENABLED 仍给一条告警，提示确认门已生效
        if env in ("prod", "production") and self.HITL_ENABLED and not self.HITL_AI_REVIEW:
            _log.warning(
                "[HITL] 生产环境 HITL_ENABLED=True（写类工具需人工确认）；AI 审查(HITL_AI_REVIEW)"
                "当前未开启，高风险写操作仅过人工 confirm 门。"
            )
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
