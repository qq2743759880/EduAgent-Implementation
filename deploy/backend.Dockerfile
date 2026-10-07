# CPU is the portable default. The native CUDA environment is not changed.
FROM python:3.11-slim AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/
WORKDIR /app
ENV UV_CONCURRENT_DOWNLOADS=4 UV_CONCURRENT_INSTALLS=2
COPY bili-study-agent/pyproject.toml bili-study-agent/uv.lock ./
RUN uv sync --frozen --no-dev --extra cpu --no-install-project
ARG INSTALL_MINERU=true
RUN mkdir -p /opt/mineru && if [ "$INSTALL_MINERU" = "true" ]; then \
      uv venv /opt/mineru && uv pip install --python /opt/mineru/bin/python 'mineru==4.0.10'; \
    fi

FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH=/app/.venv/bin:$PATH PYTHONPATH=/app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data /app/logs /opt/mineru /home/appuser/.cache \
    && chown -R appuser:appuser /app/data /app/logs /home/appuser/.cache
COPY --from=dependencies /app/.venv /app/.venv
COPY --from=dependencies /opt/mineru /opt/mineru
COPY bili-study-agent/app /app/app
COPY bili-study-agent/alembic /app/alembic
COPY bili-study-agent/scripts/run_parser_worker.py bili-study-agent/scripts/run_ingest_worker.py bili-study-agent/scripts/run_reconciler.py /app/scripts/
COPY deploy/bootstrap.py deploy/portable.py deploy/schema.sql deploy/schema-manifest.json /app/deploy/
USER appuser
EXPOSE 9988
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=30 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9988/health/ready', timeout=3)"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9988", "--workers", "1"]
