"""
配置管理 —— 读取环境变量并提供默认值。

设计原则：
1. 所有配置项集中在一个类
2. 用 pydantic-settings 自动从环境变量读取
3. 提供合理的默认值（本地开发可直接跑）
4. 敏感信息（密码/API Key）必须通过环境变量提供
"""
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    APP_VERSION: str = "0.2.0"
    DEBUG: bool = False

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
    # Milvus 配置（向量数据库，部署在虚拟机 Docker 上）
    # ============================================================
    MILVUS_URI: str = "http://192.168.85.101:19530"
    MILVUS_TOKEN: str = ""                # 无认证时留空
    MILVUS_DB: str = "default"
    MILVUS_COLLECTION: str = "edu_knowledge"

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

    # ============================================================
    # Embedding API（独立配置，可与聊天 LLM 不同源）
    #   留空时自动复用 LLM 的 base_url/key；若聊天走 DeepSeek/a6api
    #   （无 embeddings 端点），必须显式配置硅基流动 SiliconFlow。
    # ============================================================
    EMBEDDING_API_URL: str = ""           # 空 → 复用 LLM_BASE_URL
    EMBEDDING_API_KEY: str = ""           # 空 → 复用 LLM_API_KEY
    EMBEDDING_MODEL: str = "BAAI/bge-m3"  # 硅基流动默认；DashScope 用 text-embedding-v3

    # ============================================================
    # P8 MCP 工具调用开关
    # ============================================================
    USE_MCP_TOOL_CALLING: bool = True     # 总开关：False 时聊天流程跳过 MCP 工具调用
    MCP_TOOL_MAX_TRIES: int = 1           # 单轮最多触发几次工具（避免反复调用）

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
    # JWT 签名密钥（生产环境必须替换成强随机 32 字节 hex）
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
    # 路径配置
    # ============================================================
    DATA_DIR: str = "./data"
    KNOWLEDGE_SOURCE_DIR: str = "C:/Users/Administrator/Desktop/edu"

    # ============================================================
    # pydantic-settings 配置
    # ============================================================
    model_config = SettingsConfigDict(
        env_file=".env",                  # 从 .env 文件读取
        env_file_encoding="utf-8",
        case_sensitive=False,             # 环境变量不区分大小写
        extra="ignore",                   # 忽略未定义的环境变量
    )


# 全局单例
settings = Settings()
