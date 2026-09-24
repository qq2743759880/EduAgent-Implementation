# -*- coding: utf-8 -*-
"""TA7 D3 确定性探针（在 edu-agent/ 下运行：`./.venv/Scripts/python.exe <本文件>`）。

证明三件事：
  A) 「NaN 向量 → Milvus 拒收」这一环是确定的（复现日志里的 65535 报错行）；
  B) 修复后 MemoryVectorStore 在**同样产出 NaN 的 embedder** 下仍能写进 Milvus 且搜得到；
  C) 修复后「Milvus 写入失败 → 落 in-memory」的记忆**读得出来**（修复前 search 恒先问
     Milvus 且空结果直接 return [] → 永久召回空洞）。
"""
from __future__ import annotations

import asyncio
import math
import os
import sys

os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
sys.path.insert(0, os.getcwd())  # 须在 edu-agent/ 下运行，把仓库 app/ 加入 import 路径

from app.ai.memory.vector import DeterministicEmbedder, MemoryVectorStore  # noqa: E402
from app.config import settings  # noqa: E402


class NaNEmbedder:
    """模拟 fp16/CUDA 数值抖动：产出全 NaN 向量 + degraded_reason 标注。"""

    def __init__(self, dim: int) -> None:
        self.dim = dim
        self.degraded_reason = None

    def embed_batch(self, texts):
        self.degraded_reason = "真实 embedding 含 NaN/±Inf（模拟 fp16/CUDA 抖动）"
        return [[float("nan")] * self.dim for _ in texts]

    def embed(self, text):
        return self.embed_batch([text])[0]


def finite(v):
    return all(math.isfinite(float(x)) for x in v)


async def main() -> None:
    dim = settings.EMBEDDING_DIM
    store = MemoryVectorStore()
    print(f"[env] backend={store.backend} collection={store._collection} dim={dim} "
          f"milvus={'ok' if store._milvus is not None else 'None'} "
          f"redis_client={'set' if store._redis is not None else 'None'}")

    # ---------- A) 直接送 NaN → Milvus 必须拒收（复现根因那一环） ----------
    nan_vec = [float("nan")] * dim
    print("\n[A] 直接把 NaN 向量交 Milvus（修复前的实况）")
    if store._milvus is not None:
        try:
            store._milvus.upsert(collection_name=store._collection, data=[{
                "id": 990000001, "user_id": 990001, "content": "NaN 探针", "vector": nan_vec,
            }])
            print("    UNEXPECTED: Milvus 居然接受了 NaN")
        except Exception as exc:
            print(f"    OK 被拒收: {type(exc).__name__}: {str(exc)[:110]}")
    else:
        print("    (Milvus 不可达，跳过 A；B/C 走 in-memory 档)")

    # ---------- B) 修复后：NaN embedder 也能写进 Milvus 并召回 ----------
    print("\n[B] 修复后：embedder 产出 NaN → 清洗 → 入库 → 召回")
    nan_store = MemoryVectorStore(embedder=NaNEmbedder(dim))
    uid = 990002
    txt = "用户名字：TA7探针"
    await nan_store.upsert(memory_id=990000002, user_id=uid, content=txt)
    # 注：Milvus 存在「写后读可见窗口」（实测：立即 search 可能为空，约 3s 后可见，
    # flush 亦可见）——与本缺陷无关，故此处等窗口再断言，避免把一致性时序当成本次结论。
    await asyncio.sleep(3.5)
    hits = await nan_store.search(user_id=uid, query="我叫什么名字", top_k=3)
    print(f"    degraded_reason={nan_store.degraded_reason!r}")
    print(f"    upsert 后 search 命中={hits}")
    print(f"    => {'PASS' if any(int(h['memory_id']) == 990000002 for h in hits) else 'FAIL'}")

    # ---------- C) 修复后：Milvus 写失败落 in-memory 的记忆读得出来 ----------
    print("\n[C] 修复后：Milvus 写失败 → in-memory 档仍可召回（修复前恒空）")
    good = MemoryVectorStore(embedder=DeterministicEmbedder(dim))
    uid2 = 990003
    mem_id = 990000003
    if good._milvus is not None:
        good._milvus.upsert = lambda **kw: (_ for _ in ()).throw(  # 模拟 Milvus 拒收
            RuntimeError("value 'NaN' is not a number or infinity"))
    await good.upsert(memory_id=mem_id, user_id=uid2, content="用户名字：落内存档探针")
    print(f"    _mem 档条数={len(good._mem)}")
    hits2 = await good.search(user_id=uid2, query="我叫什么名字", top_k=3)
    print(f"    search 命中={hits2}")
    print(f"    => {'PASS' if any(int(h['memory_id']) == mem_id for h in hits2) else 'FAIL'}")

    # ---------- 清理探针数据 ----------
    for uid_ in (990001, uid, uid2):
        try:
            await store.clear_user(uid_)
        except Exception:
            pass
    print("\n[cleanup] 探针向量已清理")


if __name__ == "__main__":
    asyncio.run(main())
