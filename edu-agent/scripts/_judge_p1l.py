# -*- coding: utf-8 -*-
"""task-P1L 回答质量抽查（LLM-as-judge）。

对三个意图（knowledge / tool / learning）各发 1 次非流式请求，收集回答，
用 LLM 按 4 维度打分（1-5）：相关性 / 完整性 / 准确性 / 可读性，输出汇总。

用法：python scripts/_judge_p1l.py
"""
from __future__ import annotations

import json
import time
import urllib.request

from app.chat.generator import _ChatClient
from app.config import settings

_QUERIES = [
    ("L1-knowledge", "现在完成时和过去时的区别是什么？请举例说明。"),
    ("L2-tool", "帮我查一下我最近的考试成绩并分析一下进步情况。"),
    ("L2-learning", "我最近学英语总是记不住单词，有什么科学的学习方法？"),
]

_CRITERIA = """你是严谨的教育质量评审。请对下面的 AI 教学回答打分（1-5 分，5 为最优），
从四个维度：相关性（是否切题）、完整性（是否覆盖要点）、准确性（是否有事实/逻辑错误）、
可读性（结构是否清晰、是否易懂）。
输出严格 JSON：{"relevance": 分, "completeness": 分, "accuracy": 分, "readability": 分, "comment": "一句话"}"""


def _chat(query: str) -> dict:
    token = json.load(open("scripts/_task39_users.json", encoding="utf-8"))[0][1]
    body = json.dumps({"query": query, "stream": False, "use_hyde": False}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/chat",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode("utf-8"))
    payload = data.get("data") or {}
    return {
        "latency": time.perf_counter() - t0,
        "degraded": payload.get("degraded_reason"),
        "answer": payload.get("answer") or "",
    }


def _judge(answer: str) -> dict:
    client = _ChatClient.get()
    try:
        raw = client.call_chat(
            messages=[
                {"role": "system", "content": _CRITERIA},
                {"role": "user", "content": f"回答内容（{len(answer)} 字）：\n{answer[:3000]}"},
            ],
            model=settings.LLM_MODEL_STRONG,
            temperature=0.0,
            max_tokens=200,
        )
        return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "comment": "judge 失败"}


def main() -> None:
    results = []
    for label, query in _QUERIES:
        print(f"[{label}] 请求中...")
        r = _chat(query)
        print(f"  latency={r['latency']:.1f}s degraded={r['degraded']} answer={len(r['answer'])}字")
        j = _judge(r["answer"])
        j["label"] = label
        j["latency"] = round(r["latency"], 1)
        j["degraded"] = r["degraded"]
        j["answer_len"] = len(r["answer"])
        results.append(j)
        print(f"  judge: {j}")
    print("\n=== 汇总 ===")
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
