# -*- coding: utf-8 -*-
"""
VEC-LOCK embed 一致性健康探针（check-demo.mjs ⑩ 调用；VEC-G5 健康门子断言）

机验：edu_knowledge 全部行 embedding_model = 锁定 BGE-M3 revision、无 embed_fallback、
无空文本 chunk、embed_normalized 全 1。全过 exit 0，否则 exit 1 并输出原因。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# W-NEXT-CHECKDEMO-004 修:.env 加载兜底 ——
# 现象:check-demo.mjs ⑪ 守卫 spawn 子进程时 cwd=仓库根,不是 edu-agent/。
#       pydantic-settings 的 env_file='.env' 是相对 cwd 的相对路径,cwd=仓库根时
#       找不到 edu-agent/.env → 启动期 ValidationError: LLM_API_KEY Field required,
#       子进程 exit=1。和 W-NEXT-CHECKDEMO-003 (⑲ veclock_verify) 同型根因。
# 修复:入口处显式 load_dotenv(EDU_ROOT/.env),让进程环境变量在 import app.config 之前
#       已经被填好,绕过 pydantic-settings 的 cwd-相对 env_file 寻址陷阱。
#       不依赖 cwd,不依赖父进程的 env 注入,不依赖 shell .env-source 习惯。
from dotenv import load_dotenv  # noqa: E402

EDU_ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = EDU_ROOT / ".env"
if _ENV_PATH.is_file():
    load_dotenv(_ENV_PATH, override=False)  # 已有环境变量优先,避免覆盖 CI 注入
else:
    print(f"[veclock_health_probe] WARN .env not found at {_ENV_PATH} — pydantic Field required 风险", file=sys.stderr)

sys.path.insert(0, str(EDU_ROOT))

from app.knowledge.importer.embedder import _bge_revision_fingerprint, is_blank_text  # noqa: E402
from app.knowledge.importer.loader import get_milvus_client  # noqa: E402

rev = _bge_revision_fingerprint()
client = get_milvus_client()
rows: list[dict] = []
offset = 0
page = 4000
while True:
    part = client.query(
        "edu_knowledge", filter="",
        output_fields=["embedding_model", "embed_precision", "embed_normalized", "embed_fallback", "content"],
        limit=page, offset=offset,
    )
    if not part:
        break
    rows.extend(part)
    offset += len(part)
    if len(part) < page:
        break
bad_model = {r.get("embedding_model") for r in rows} - {rev}
bad_fallback = {r.get("embed_fallback") for r in rows if r.get("embed_fallback")}
bad_norm = sum(1 for r in rows if r.get("embed_normalized") != 1)
bad_blank = sum(1 for r in rows if is_blank_text(str(r.get("content") or "")))
ok = not bad_model and not bad_fallback and bad_norm == 0 and bad_blank == 0
print(
    f"edu_knowledge {len(rows)} 行 embed 一致性：model={rev} 混写={bad_model or '无'} "
    f"fallback={bad_fallback or '无'} 未归一化={bad_norm} 空文本={bad_blank} => {'PASS' if ok else 'FAIL'}"
)
sys.exit(0 if ok else 1)
