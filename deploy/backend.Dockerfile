# ============================================================
# EduAgent 后端镜像 —— 生产部署
# 多阶段构建：
#   1) deps   : 只装 Python 依赖（利用 Docker 层缓存，代码变更不重装）
#   2) runtime: 精简运行镜像（仅 python + 依赖 + 源码）
# ============================================================
FROM python:3.11-slim AS deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先拷贝依赖清单 → 装依赖（层缓存：改代码不会触发重装）
COPY edu-agent/pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install \
        "fastapi>=0.110,<0.142" \
        "uvicorn[standard]>=0.29,<0.53" \
        "sse-starlette>=2.0,<3.5" \
        "langgraph>=1.2,<1.3" \
        "langchain-core>=1.5,<2.0" \
        "langchain-openai>=1.4,<2.0" \
        "pydantic>=2.7,<3.0" \
        "pydantic-settings>=2.3,<3.0" \
        "email-validator>=2.1,<3.0" \
        "pymilvus>=3.0,<3.1" \
        "motor>=3.4,<4.0" \
        "sqlalchemy>=2.0,<3.0" \
        "asyncmy>=0.2.9,<0.3" \
        "pymysql>=1.1,<2.0" \
        "minio>=7.2,<8.0" \
        "neo4j>=5.0,<6.0" \
        "redis[hiredis]>=5.0,<6.0" \
        "httpx>=0.27,<0.29" \
        "jinja2>=3.1,<4.0" \
        "pyyaml>=6.0,<7.0" \
        "python-docx>=1.1,<1.3" \
        "loguru>=0.7,<0.8" \
        "prometheus-client>=0.19,<0.22" \
        "sqlglot>=23.0,<24.0" \
        "sqlparse>=0.5,<1.0" \
        "alembic>=1.13,<2.0" \
        "jieba>=0.42,<1.0" \
        "rank-bm25>=0.1,<1.0" \
        "bcrypt>=4.1,<6.0" \
        "pyjwt>=2.8,<3.0"

# ---------------- 运行镜像 ----------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 从 deps 阶段拷贝已安装的 site-packages
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# 拷贝应用源码
COPY edu-agent/app /app/app

# 非 root 运行（安全基线）
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# 健康检查（compose 用 /health 做 liveness，/health/detail 做 readiness）
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else 1)"

# 生产用 gunicorn+uvicorn workers（多进程）；DEBUG 环境由 compose 覆盖
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
