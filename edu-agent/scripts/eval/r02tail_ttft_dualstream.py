# -*- coding: utf-8 -*-
"""R02-tail C-01 · TTFT 双路径真实流式复测探针（W-NEXT-R02TAIL-001）。

背景（tracker R02 验收登记尾巴 / critique C-b）：
  R02 流式进图后编排者活体实测热态 TTFT 5.27~5.32s > 冻结预算 4.51s（=R20-b W0 冻结
  旧路径 P95 4.103s × 1.10，contracts/reshape-r-eval-draft.json dualrun_gate_R02b 第③条），
  旧路径保留、R05（删旧路径）冻结至达标。此后两项变量落地：①LLMSWITCH（答案生成主模型
  deepseek-flash；注意：thinking=disabled 仅注入**非流式**，流式按设计不注入，单测
  test_stream_path_never_injects_thinking 钉死）；②R12 exact-pin 对齐（双跑 Jaccard 1.0）。
  本探针在两变量落地后的 HEAD 上，对**真实 SSE 流式**（POST /api/chat/stream）做新旧
  双路径各 ≥50 轮 TTFT 复测（temp=0 确定性），并对同一批 query 顺带产出跨路径 docs
  Jaccard 独立旁证（C-01 逐断言独立实证）。

测法（照抄既有仪器，不新造口径）：
  - SSE 逐帧计时方法 = test-reports/r02tail-ttft-probe.py（start→retrieval / start→首 token）
  - 产物格式 = scripts/eval/data/rn2_runs/rn2-dualrun-{summary,results}.json 同款
  - 百分位算法 = r20b_dualrun_probe._pct（线性序取整索引）

双路径实现：STREAM_VIA_GRAPH 为进程级配置（config.py:226，默认 True），无法按请求切换
→ 由编排脚本对 8011 一次性实例分别以 true/false 启动两轮测量（本脚本只管打流）。
两路径同 LLM：新图路径 answer 固定 model="strong"（sixnode.py:432）；旧路径按请求体
model 字段（schemas.py RagQueryRequest.model，默认 fast）→ 本探针显式传 model="strong"
使两路径答案生成同为 deepseek-flash。

确定性：LLM_TEMPERATURE=0（实例 env 显式钉死）、RULE_ROUTING_ENABLED=True（0-LLM 规则
路由）、query 计划无 RNG（固定轮转）。EMBED_BACKEND=cpu 进程级（GPU 被 8000 生产实例
占用 4.6/8.2GB，R12 已登记争用段错误前科；两路径同用，口径不变）。

用法（edu-agent/ 下，8011 一次性实例已就绪后）：
  .venv/Scripts/python.exe scripts/eval/r02tail_ttft_dualstream.py --label graph  --rounds 55
  .venv/Scripts/python.exe scripts/eval/r02tail_ttft_dualstream.py --label legacy --rounds 55
  .venv/Scripts/python.exe scripts/eval/r02tail_ttft_dualstream.py --summarize     # 汇总双路径

产物（rn2 同款，data/r02tail_runs/）：
  r02tail-ttft-graph-results.json / r02tail-ttft-legacy-results.json   逐轮明细
  r02tail-ttft-dualrun-summary.json                                    汇总+门槛对照
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parents[2]  # edu-agent/
OUT_DIR = BASE_DIR / "scripts" / "eval" / "data" / "r02tail_runs"
EVAL_SET = BASE_DIR / "scripts" / "eval" / "data" / "rag_eval_set32.json"

DEFAULT_BASE = "http://127.0.0.1:8011"
ACCOUNT, PASSWORD = "user000001", "Test@123456"  # AGENTS.md 测试账号（学员）
FROZEN_BUDGET_S = 4.513   # R20-b W0 冻结旧路径 P95 4.103s × 1.10（contracts/reshape-r-eval-draft.json）
FROZEN_OLD_P95_S = 4.103  # W0 冻结基线（dualrun-baseline.md @57491e5）
WARMUP_N = 3
ROUND_GAP_S = 1.0
REQ_TIMEOUT = (15, 180)

# 边界样本（r20b_dualrun_probe.EDGE_CASES 逐字子集，确定性）
CHITCHAT = [
    "你好呀，你叫什么名字？",
    "今天天气真不错，适合出去走走。",
    "讲个笑话听听吧。",
]
TOOL = [
    "帮我算一下 128 乘以 46 等于多少。",
    "计算 (15+27)*3 的结果。",
    "查一下 2 的 20 次方是多少。",
]


def log(msg: str) -> None:
    print(f"[r02tail {datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _git_rev() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(BASE_DIR), text=True
        ).strip()
    except Exception:
        return "unknown"


def _pct(vals: list[float], q: float) -> float | None:
    """与 r20b_dualrun_probe._pct 同算法。"""
    if not vals:
        return None
    xs = sorted(vals)
    k = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return round(xs[k], 4)


def build_plan(n_rounds: int) -> list[dict]:
    """确定性轮转：每轮 = 8 knowledge + 2 chitchat + 1 tool（镜像 W0 样本构成比例 82/6/12 的方向）。

    5 轮循环 = 55 轮（K40/C10/T5）。无 RNG；同计划跨路径逐位一致 → 支持按轮配对 Jaccard。
    """
    if EVAL_SET.exists():
        with open(EVAL_SET, encoding="utf-8") as f:
            cases = json.load(f)["cases"]
        K = [c["query"] for c in cases[:8]]
    else:  # 冻结评估集缺失时的逐字兜底（正常路径不走）
        K = [
            "化学方程式总是写错时，最该加强的是？",
            "在多学科并行时，最能提升效率的是？",
            "线性代数中特征值和特征向量的几何意义是什么？",
            "雅思听力Section 4的常见陷阱有哪些？",
            "解释一下光合作用的光反应和暗反应区别。",
            "权责发生制和收付实现制在会计确认上的核心差异？",
            "考研英语阅读的精读方法应该怎么做？",
            "Python装饰器的底层实现机制是什么？",
        ]
    plan: list[dict] = []
    c = 0
    while len(plan) < n_rounds:
        for q in K:
            if len(plan) >= n_rounds:
                break
            plan.append({"kind": "knowledge", "query": q})
        for _ in range(2):
            if len(plan) >= n_rounds:
                break
            plan.append({"kind": "chitchat", "query": CHITCHAT[c % 3]})
        if len(plan) < n_rounds:
            plan.append({"kind": "tool", "query": TOOL[c % 3]})
        c += 1
    for i, p in enumerate(plan):
        p["round"] = i + 1
    return plan


def login(base: str) -> str:
    import requests

    last = None
    for attempt in range(4):
        r = requests.post(base + "/api/auth/login",
                          json={"account": ACCOUNT, "password": PASSWORD}, timeout=15)
        try:
            d = r.json()
        except Exception:
            d = {}
        if r.status_code == 200 and d.get("code") == 0:
            return d["data"]["access_token"]
        last = f"HTTP {r.status_code} body={r.text[:150]}"
        log(f"login 第 {attempt + 1} 次失败：{last}（429 限流预算 awareness，退避重试）")
        time.sleep(6)
    raise RuntimeError(f"login 4 连败：{last}")


def sse_round(base: str, token: str, query: str, model: str = "strong") -> dict:
    """单轮真实流式：逐帧计时 + 契约采集（测法照抄 r02tail-ttft-probe.sse_query，扩展 docs 捕获）。"""
    import requests

    H = {"Authorization": f"Bearer {token}"}
    body = {"query": query, "session_id": None, "stream": True, "model": model}
    t0 = time.perf_counter()
    r = requests.post(base + "/api/chat/stream", headers=H, json=body,
                      stream=True, timeout=REQ_TIMEOUT)
    t_conn = time.perf_counter() - t0
    if r.status_code != 200:
        return {"ok": False, "http_status": r.status_code, "body_head": r.text[:200],
                "t_conn_s": round(t_conn, 4)}
    names: list[str] = []
    cur_event, cur_data = None, None
    t_start = t_ret = t_tok = t_done = None
    ret_payload: dict | None = None
    done_payload: dict | None = None
    errors: list[dict] = []
    n_tokens = 0
    try:
        for raw in r.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            if raw.startswith("event: "):
                cur_event = raw[7:].strip()
            elif raw.startswith("data: ") and cur_event:
                try:
                    cur_data = json.loads(raw[6:])
                except Exception:
                    cur_data = {"_raw": str(raw[6:])[:200]}
            elif raw == "" and cur_event:
                now = time.perf_counter() - t0
                names.append(cur_event)
                if cur_event == "start" and t_start is None:
                    t_start = now
                elif cur_event == "retrieval" and t_ret is None:
                    t_ret = now
                    ret_payload = cur_data if isinstance(cur_data, dict) else None
                elif cur_event == "token":
                    if t_tok is None:
                        t_tok = now
                    n_tokens += 1
                elif cur_event == "done":
                    t_done = now
                    done_payload = cur_data if isinstance(cur_data, dict) else None
                elif cur_event == "error":
                    errors.append(cur_data if isinstance(cur_data, dict) else {"_raw": str(cur_data)[:200]})
                cur_event, cur_data = None, None
    finally:
        r.close()
    total = time.perf_counter() - t0
    ok = bool(names and names[0] == "start" and "retrieval" in names
              and "token" in names and names[-1] == "done" and not errors)
    done_code = None
    if isinstance(done_payload, dict):
        done_code = done_payload.get("code")
        ok = ok and done_code == 0
    docs = []
    if isinstance(ret_payload, dict):
        for d in (ret_payload.get("docs") or [])[:12]:
            docs.append({
                "doc_id": (d or {}).get("doc_id"),
                "score": (d or {}).get("score"),
            })
    return {
        "ok": ok,
        "frames": names,
        "t_conn_s": round(t_conn, 4),
        "t_start_s": round(t_start, 4) if t_start is not None else None,
        "ttft_retrieval_s": round(t_ret, 4) if t_ret is not None else None,
        "ttft_first_token_s": round(t_tok, 4) if t_tok is not None else None,
        "t_done_s": round(t_done, 4) if t_done is not None else None,
        "total_s": round(total, 4),
        "n_tokens": n_tokens,
        "done_code": done_code,
        "done_data": (done_payload or {}).get("data") if isinstance(done_payload, dict) else None,
        "retrieved_count": (ret_payload or {}).get("retrieved_count") if isinstance(ret_payload, dict) else None,
        "final_count": (ret_payload or {}).get("final_count") if isinstance(ret_payload, dict) else None,
        "rewrite_query": (ret_payload or {}).get("rewrite_query") if isinstance(ret_payload, dict) else None,
        "degraded_reason": (ret_payload or {}).get("degraded_reason") if isinstance(ret_payload, dict) else None,
        "doc_ids_head": [d["doc_id"] for d in docs],
        "doc_scores_head": [d["score"] for d in docs],
        "errors": errors,
    }


def run_label(label: str, base: str, n_rounds: int) -> int:
    plan = build_plan(n_rounds)
    token = login(base)
    log(f"[{label}] login ok；计划 {n_rounds} 测量轮 + {WARMUP_N} 预热轮（预热不入统计）")
    rows: list[dict] = []
    for w in range(WARMUP_N):
        p = plan[w]
        t0 = time.perf_counter()
        row = sse_round(base, token, p["query"])
        row.update({"phase": "warmup", "round": -(w + 1), "kind": p["kind"], "query": p["query"]})
        rows.append(row)
        log(f"[{label}] warmup {w + 1}/{WARMUP_N} kind={p['kind']} ok={row.get('ok')} "
            f"ret={row.get('ttft_retrieval_s')} tok={row.get('ttft_first_token_s')} "
            f"({time.perf_counter() - t0:.1f}s)")
        time.sleep(ROUND_GAP_S)
    for p in plan:
        row = sse_round(base, token, p["query"])
        row.update({"phase": "measured", "round": p["round"], "kind": p["kind"], "query": p["query"]})
        rows.append(row)
        log(f"[{label}] round {p['round']}/{len(plan)} kind={p['kind']} ok={row.get('ok')} "
            f"ret={row.get('ttft_retrieval_s')} tok={row.get('ttft_first_token_s')} "
            f"tokens={row.get('n_tokens')} deg={row.get('degraded_reason')}")
        time.sleep(ROUND_GAP_S)
    out = OUT_DIR / f"r02tail-ttft-{label}-results.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {
            "label": label,
            "base": base,
            "stream_via_graph_claim": label == "graph",
            "model_sent": "strong（两路径同 LLM：deepseek-flash；流式不注入 thinking-disabled，as-built）",
            "embed_backend_claim": "cpu（进程级，两路径同用；GPU 4.6/8.2GB 被 8000 生产实例占用）",
            "llm_temperature_claim": "0（实例 env 显式）",
            "n_warmup": WARMUP_N,
            "n_measured": n_rounds,
            "plan_note": "确定性轮转 8K+2C+1T×5，无 RNG；query 逐字见逐轮 rows",
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "git_rev": _git_rev(),
        },
        "rows": rows,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    ok_n = sum(1 for r in rows if r.get("phase") == "measured" and r.get("ok"))
    log(f"[{label}] 完成：measured ok {ok_n}/{n_rounds} → {out}")
    return 0


# ============================================================
# 汇总（--summarize）：rn2 同款 summary + 门槛对照
# ============================================================
def _dist(vals: list[float]) -> dict:
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "mean": round(sum(vals) / len(vals), 4),
            "p50": _pct(vals, 0.5), "p95": _pct(vals, 0.95),
            "min": round(min(vals), 4), "max": round(max(vals), 4)}


def _jaccard(a: list, b: list) -> float:
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def summarize() -> int:
    def load(label: str) -> list[dict]:
        p = OUT_DIR / f"r02tail-ttft-{label}-results.json"
        if not p.exists():
            raise SystemExit(f"缺少 {p}，先跑 --label {label}")
        with open(p, encoding="utf-8") as f:
            return json.load(f)["rows"]

    g_rows = [r for r in load("graph") if r.get("phase") == "measured"]
    l_rows = [r for r in load("legacy") if r.get("phase") == "measured"]
    n = min(len(g_rows), len(l_rows))

    def subset(rows: list[dict], kinds: tuple[str, ...] | None) -> list[dict]:
        return [r for r in rows if r.get("ok") and (kinds is None or r.get("kind") in kinds)]

    def pack(ok_rows: list[dict], all_rows: list[dict]) -> dict:
        return {"ttft_retrieval": _dist([r.get("ttft_retrieval_s") for r in ok_rows]),
                "ttft_first_token": _dist([r.get("ttft_first_token_s") for r in ok_rows]),
                "n_ok": len(ok_rows), "n_measured": len(all_rows),
                "n_fail": len(all_rows) - len(ok_rows)}

    g_all, l_all = subset(g_rows, None), subset(l_rows, None)
    g_k, l_k = subset(g_rows, ("knowledge",)), subset(l_rows, ("knowledge",))
    g_pack, l_pack = pack(g_all, g_rows), pack(l_all, l_rows)
    gk_pack, lk_pack = pack(g_k, [r for r in g_rows if r.get("kind") == "knowledge"]), \
        pack(l_k, [r for r in l_rows if r.get("kind") == "knowledge"])

    # 跨路径逐轮配对（同计划同序）→ Jaccard 独立旁证 + 同轮 TTFT 配对
    pairs = []
    for i in range(n):
        gr, lr = g_rows[i], l_rows[i]
        pairs.append({
            "round": i + 1,
            "kind": gr.get("kind"),
            "query_head": str(gr.get("query"))[:40],
            "query_match": gr.get("query") == lr.get("query"),
            "jaccard": round(_jaccard(gr.get("doc_ids_head"), lr.get("doc_ids_head")), 4),
            "g_ok": gr.get("ok"), "l_ok": lr.get("ok"),
            "g_ret": gr.get("ttft_retrieval_s"), "l_ret": lr.get("ttft_retrieval_s"),
            "g_tok": gr.get("ttft_first_token_s"), "l_tok": lr.get("ttft_first_token_s"),
            "g_final_n": gr.get("final_count"), "l_final_n": lr.get("final_count"),
            "g_deg": gr.get("degraded_reason"), "l_deg": lr.get("degraded_reason"),
        })
    jacs = [p["jaccard"] for p in pairs if p["g_ok"] and p["l_ok"]]
    q_mismatch = sum(1 for p in pairs if not p["query_match"])

    g_tok_p95 = (g_pack["ttft_first_token"] or {}).get("p95")
    l_tok_p95 = (l_pack["ttft_first_token"] or {}).get("p95")
    g_ret_p95 = (g_pack["ttft_retrieval"] or {}).get("p95")
    l_ret_p95 = (l_pack["ttft_retrieval"] or {}).get("p95")
    gk_tok_p95 = (gk_pack["ttft_first_token"] or {}).get("p95")

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "git_rev": _git_rev(),
        "frozen_budget": {
            "threshold_s": FROZEN_BUDGET_S,
            "source": ("R20-b W0 冻结旧路径 P95 4.103s × 1.10（contracts/reshape-r-eval-draft.json "
                       "dualrun_gate_R02b 第③条 + tracker R02 验收登记）；活体超标原值 5.27~5.32s"),
        },
        "paths": {
            "graph": {"desc": "新图路径 STREAM_VIA_GRAPH=true（graph.astream 适配层）", **g_pack},
            "legacy": {"desc": "旧路径 STREAM_VIA_GRAPH=false（service_chat_stream）", **l_pack},
        },
        "knowledge_only": {
            "graph": gk_pack, "legacy": lk_pack,
            "note": "六节点直连快路径（R02 §1.2 指定预算口径的子集）",
        },
        "gate_first_token": {
            "graph_p95_s": g_tok_p95, "legacy_p95_s": l_tok_p95,
            "graph_vs_frozen_budget": round(g_tok_p95 - FROZEN_BUDGET_S, 4) if g_tok_p95 else None,
            "graph_pass_frozen_budget": (g_tok_p95 is not None and g_tok_p95 <= FROZEN_BUDGET_S),
            "graph_vs_legacy_x1p1": round(l_tok_p95 * 1.10, 4) if l_tok_p95 else None,
            "graph_pass_legacy_x1p1": (g_tok_p95 is not None and l_tok_p95 is not None
                                       and g_tok_p95 <= l_tok_p95 * 1.10),
        },
        "gate_retrieval_segment": {
            "graph_p95_s": g_ret_p95, "legacy_p95_s": l_ret_p95,
            "graph_pass_frozen_budget": (g_ret_p95 is not None and g_ret_p95 <= FROZEN_BUDGET_S),
            "note": "R02-tail 优化段（start→retrieval）；冻结预算同值引用",
        },
        "knowledge_gate_first_token": {
            "graph_knowledge_p95_s": gk_tok_p95,
            "pass_frozen_budget": (gk_tok_p95 is not None and gk_tok_p95 <= FROZEN_BUDGET_S),
        },
        "cross_path_docs_jaccard": {
            "n_pairs": len([p for p in pairs if p["g_ok"] and p["l_ok"]]),
            "mean": round(sum(jacs) / len(jacs), 4) if jacs else None,
            "p50": _pct(jacs, 0.5), "p95": _pct(jacs, 0.95),
            "min": round(min(jacs), 4) if jacs else None,
            "eq1_count": sum(1 for j in jacs if j >= 0.9999),
            "query_order_mismatch": q_mismatch,
            "note": "SSE retrieval 帧 doc_ids 逐轮配对（同计划同序）；knowledge 空检索对=1.0 计入",
        },
        "pairs": pairs,
        "conditions_note": ("本探针为单日单批测量；五条件中「连续3天」「累计>=1000」仍需灰度期窗口，"
                           "详见报告记分卡"),
    }
    out = OUT_DIR / "r02tail-ttft-dualrun-summary.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    gt = summary["gate_first_token"]
    log(f"汇总 → {out}")
    log(f"首 token P95: graph={gt['graph_p95_s']}s legacy={gt['legacy_p95_s']}s | "
        f"冻结预算 {FROZEN_BUDGET_S}s 判定 graph_pass={gt['graph_pass_frozen_budget']} | "
        f"legacy×1.1={gt['graph_vs_legacy_x1p1']}s 判定 pass={gt['graph_pass_legacy_x1p1']}")
    log(f"retrieval 段 P95: graph={g_ret_p95}s legacy={l_ret_p95}s")
    log(f"跨路径 Jaccard: mean={summary['cross_path_docs_jaccard']['mean']} "
        f"(=1 共 {summary['cross_path_docs_jaccard']['eq1_count']})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", choices=["graph", "legacy"], default=None)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--rounds", type=int, default=55)
    ap.add_argument("--summarize", action="store_true")
    args = ap.parse_args()
    if args.summarize:
        return summarize()
    if not args.label:
        raise SystemExit("需要 --label graph|legacy（或 --summarize）")
    return run_label(args.label, args.base, args.rounds)


if __name__ == "__main__":
    sys.exit(main())
