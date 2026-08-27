# -*- coding: utf-8 -*-
"""task-R1 Rerank sidecar 独立服务包。

- batcher.py：跨请求连续批处理（对齐 vLLM continuous batching），纯逻辑可注入 fake 测试；
- main.py：FastAPI 独立进程，POST /rerank 调 batcher，GET /health 探活；
- queue_adapter.py：可选 Redis list 削峰（默认直连 batcher）。
"""
