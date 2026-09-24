# -*- coding: utf-8 -*-
"""TA7 D3 复现：跨会话记忆召回失效（Milvus upsert NaN 降级）。

① 会话 A 说名字 → 看 done.memorized + user_memory_event HEAD
② 新会话 B 问名字 → 看 AI 答不答得出
③ 直接探 embedded 向量是否含 NaN（根因定位）
"""
from __future__ import annotations

import math
import sys

import _ta7_lib as L

STUDENT = sys.argv[1] if len(sys.argv) > 1 else "user000002"


def probe_embedder(texts: list[str]) -> None:
    print("\n--- ③ embedder 向量有限性探针（SemanticEmbedder 真实路径）---")
    from app.ai.memory.vector import SemanticEmbedder

    emb = SemanticEmbedder()
    vecs = emb.embed_batch(texts)
    for t, v in zip(texts, vecs):
        bad = [i for i, x in enumerate(v) if not math.isfinite(x)]
        print(f"   text={t[:40]!r:46} dim={len(v)} non_finite={len(bad)}"
              f" degraded_reason={emb.degraded_reason!r}")
        if bad:
            print(f"      !! NaN/Inf 命中索引前 5 个：{bad[:5]}")


def main() -> None:
    print("=" * 70)
    print(f"[D3] account={STUDENT}")
    token = L.login(STUDENT)
    uid = L.q("SELECT id, account FROM sys_user WHERE account=%s", (STUDENT,))
    print("user row:", uid)
    uid = int(uid[0]["id"])

    print("\n--- 写入前 user_memory_event HEAD ---")
    for r in L.q("SELECT entity_id, event_type, valid_to, LEFT(content,60) content FROM user_memory_event"
                 " WHERE user_id=%s ORDER BY id DESC LIMIT 5", (uid,)):
        print("  ", r)

    # ① 会话 A：写入名字
    msg_a = "你好，我叫王小明，请记住我的名字"
    ev_a, ans_a, done_a, _ = L.chat_stream(msg_a, token)
    inner_a = done_a.get("data") if isinstance(done_a.get("data"), dict) else done_a
    print(f"\n--- ① 会话 A: {msg_a!r} ---")
    print("  memorized =", L.jj(inner_a.get("memorized")))
    print("  答案尾部:", (ans_a or "")[-160:].replace("\n", " "))

    print("\n--- ①' 写入后 user_memory_event HEAD（valid_to IS NULL AND event_type<>'delete'）---")
    for r in L.q("SELECT entity_id, event_type, valid_to, LEFT(content,80) content FROM user_memory_event"
                 " WHERE user_id=%s AND valid_to IS NULL AND event_type<>'delete'"
                 " ORDER BY id DESC LIMIT 5", (uid,)):
        print("  ", r)

    # ② 新会话 B：问名字
    msg_b = "我叫什么名字？"
    ev_b, ans_b, done_b, _ = L.chat_stream(msg_b, token)
    inner_b = done_b.get("data") if isinstance(done_b.get("data"), dict) else done_b
    print(f"\n--- ② 新会话 B: {msg_b!r} ---")
    print("  memo/recall 字段 keys:", sorted(inner_b.keys()))
    print("  答案全文:\n", ans_b or "(空)")

    probe_embedder([
        msg_a,
        "用户名字：王小明",
        "我叫什么名字？",
        "用户名字：王小明；用户偏好：喜欢 Python",
    ])


if __name__ == "__main__":
    main()
