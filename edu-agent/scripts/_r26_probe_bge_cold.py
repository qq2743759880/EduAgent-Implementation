# -*- coding: utf-8 -*-
"""R26-T10: BGE-M3 冷启动分段计时探针（只读诊断，不改业务代码；下划线前缀=临时脚本）。

用法:
    python scripts/_r26_probe_bge_cold.py            # cuda 全分段（默认，读 .env EMBED_DEVICE）
    python scripts/_r26_probe_bge_cold.py cpu        # 强制 cpu 对照（排除 CUDA 因素）
    python scripts/_r26_probe_bge_cold.py read       # 仅磁盘读速（不 import torch，读 2.27GB safetensors）

分段口径（对齐编排者要求的三段）:
    import_libs      : import torch + FlagEmbedding（含 torch DLL/扩展装载）
    cuda_init        : torch.cuda 初始化（context 创建 + 首个 kernel 同步）
    model_load       : BGEM3FlagModel(...) 权重加载到 device（= 业务 embedder._get_bge_model 同参）
    first_embed      : 首条 encode（含 CUDA kernel JIT 预热）
    raw_file_read    : model.safetensors 2.27GB 顺序读（放最后，避免预热页缓存污染冷加载计时）

输出末行 JSON: [R26T10] {...}
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

EDU_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EDU_ROOT))

from dotenv import load_dotenv  # noqa: E402

_ENV = EDU_ROOT / ".env"
if _ENV.is_file():
    load_dotenv(_ENV, override=False)

MODE = sys.argv[1] if len(sys.argv) > 1 else "cuda"
if MODE in ("cuda", "cpu"):
    DEVICE = MODE
else:
    DEVICE = str(os.getenv("EMBED_DEVICE", "cuda")).lower()

MODEL_PATH = Path(os.getenv("BGE_M3_PATH", "E:/stu/ai-models/bge-m3"))
SEG: dict[str, float] = {}

# ---- 磁盘读速单独模式（不碰 torch） ---------------------------------------
if MODE == "read":
    st = MODEL_PATH / "model.safetensors"
    size = st.stat().st_size
    t0 = time.perf_counter()
    total = 0
    with open(st, "rb") as h:
        while True:
            chunk = h.read(16 * 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
    dt = time.perf_counter() - t0
    out = {
        "mode": "read",
        "file_GB": round(size / 1e9, 2),
        "read_s": round(dt, 3),
        "read_GBs": round(total / dt / 1e9, 2),
    }
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(0)

# ---- 全分段模式 ------------------------------------------------------------
t0 = time.perf_counter()
import torch  # noqa: E402

t1 = time.perf_counter()
SEG["import_torch"] = t1 - t0

from FlagEmbedding import BGEM3FlagModel  # noqa: E402

t2 = time.perf_counter()
SEG["import_flagembedding"] = t2 - t1

if DEVICE == "cuda":
    ok = torch.cuda.is_available()
    if not ok:
        print(json.dumps({"error": "torch.cuda.is_available()=False", "device": DEVICE}, ensure_ascii=False))
        sys.exit(2)
    torch.zeros(1, device="cuda")
    torch.cuda.synchronize()
t3 = time.perf_counter()
SEG["cuda_init"] = t3 - t2

# 模型文件存在性 + 大小（与业务 embedder 同路径）
if not MODEL_PATH.exists():
    print(json.dumps({"error": f"model path missing: {MODEL_PATH}"}, ensure_ascii=False))
    sys.exit(2)

tm = time.perf_counter()
model = BGEM3FlagModel(
    str(MODEL_PATH),
    use_fp16=(DEVICE == "cuda"),   # 与 app/knowledge/importer/embedder.py _get_bge_model 同参
    device=DEVICE,
)
t5 = time.perf_counter()
SEG["model_load"] = t5 - tm

te = time.perf_counter()
out = model.encode(["R26 冷启动探针：一条普通中文句子。"], batch_size=8, max_length=8192)
t6 = time.perf_counter()
SEG["first_embed"] = t6 - te

# 磁盘读速放最后（此时文件大概率已在页缓存——给出的是"热读"上限参考）
st = MODEL_PATH / "model.safetensors"
tr = time.perf_counter()
total = 0
with open(st, "rb") as h:
    while True:
        chunk = h.read(16 * 1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
trd = time.perf_counter() - tr
SEG["raw_file_read_hot"] = trd

dim = 0
try:
    dim = len(out["dense_vecs"][0])
except Exception:  # noqa: BLE001 — 探针容错
    pass

result = {
    "mode": "load",
    "device": DEVICE,
    "use_fp16": DEVICE == "cuda",
    "segments_s": {k: round(v, 3) for k, v in SEG.items()},
    "model_load_plus_import_s": round(t6 - t0, 3),
    "dense_dim": dim,
    "read_GBs_hot": round(total / trd / 1e9, 2) if trd > 0 else None,
}
print(json.dumps(result, ensure_ascii=False))
