# -*- coding: utf-8 -*-
"""taskR20b · 新旧路径双跑探针（W0，R02 灰度收敛基准）。

对同一批 100 条样本（①task32_eval_set 前 32 切片 + ②chat_message 真采 50 + ③边界 18），
分别走旧路径 run_agent_turn（app/chat/flows/agent.py:218，SSE 流式正产编排）与新路径
run_agent（app/ai/graph.py:775，六节点 LangGraph 图），采集中间层信号：
intent / need_search / docs chunk_ids / 检索计数 / TTFT 代理（start→首检索完成）。

确定性（详档 v1.2 终审 A1）：
- RULE_ROUTING_ENABLED / LLM_TEMPERATURE 为生产默认已是确定性配置（app/config.py:166,187），
  探针启动时断言；不 monkeypatch 温度、不改正产代码。
- 每样本先做「同 query 双轮 intent 稳定预验」（旧=decide_agent_plan，新=route_node 单节点）；
  不稳定项列表化并处置（补 1 轮 → 仍不稳则冻结首轮值为该路径基线，入 unstable 列表）。
- 门槛指标只取 intent 分歧率 / docs Jaccard 两项；答案语义抽 30%（seed 固定）仅入报告不入门槛。
- TTFT 代理：旧=决策完成→检索完成（打点经 flows 绑定的计时 spy，仅本进程）；新=t0→hook 首检索完成。

零正产文件改动；新路径 docs 观测经 scripts/eval/r20b_hook.py（monkeypatch spy，见其模块注释）。

用法（edu-agent/ 下）：
  .venv/Scripts/python.exe scripts/eval/r20b_dualrun_probe.py            # 全量 100 样本
  .venv/Scripts/python.exe scripts/eval/r20b_dualrun_probe.py --limit 5  # 冒烟

产物（详档 §5）：
  scripts/eval/dualrun_samples.json      样本清单（source 三类，chat 采样 SQL/seed 逐字）
  scripts/eval/dualrun_results.json      逐样本双跑明细（机验 GWT①）
  scripts/eval/dualrun-summary.json      汇总指标 + 五条件门槛对照当前值
  ../test-reports/dualrun-baseline.md    人读报告
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from _safeio import safe_w  # Mimosa 路径穿越防护:写出统一收容校验

EDU_ROOT = Path(__file__).resolve().parents[2]          # edu-agent/（本文件在 scripts/eval/ 下）
REPO_ROOT = EDU_ROOT.parent                              # EduAgent实施手册/
sys.path.insert(0, str(EDU_ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

OUT_SAMPLES = EDU_ROOT / "scripts/eval/dualrun_samples.json"
OUT_RESULTS = EDU_ROOT / "scripts/eval/dualrun_results.json"
OUT_SUMMARY = EDU_ROOT / "scripts/eval/dualrun-summary.json"
OUT_REPORT = REPO_ROOT / "test-reports/dualrun-baseline.md"

SEED = 20260914
CHAT_SAMPLE_N = 50
CHAT_SQL_PRELIMIT = 120
CHAT_PER_SESSION_CAP = 3
EVAL_SLICE_N = 32
SEM_RATIO = 0.30
JUDGE_MAX_TOKENS = 800
NEW_PATH_TIMEOUT_S = 90.0  # 单样本新路径硬超时（minimax/deepseek 偶发挂起不拖垮全量）

# 生产请求默认值（RagQueryRequest/_BaseRagRequest，app/chat/schemas.py:98-130）
PROD_DEFAULTS = {"use_hyde": True, "top_k": 12, "final_max_k": 5, "cutoff_drop_ratio": 0.40, "enable_graph": True}
PROBE_USER_ID = 1  # 测试 admin（sys_user.id=1）；检索租户范围按学员（role=STUDENT）对齐生产非 admin

# ---- 边界样本③：18 条（6 chitchat / 6 tool / 6 knowledge），逐字入报告 ----
EDGE_CASES: list[tuple[str, str]] = [
    ("chitchat", "你好呀，你叫什么名字？"),
    ("chitchat", "今天天气真不错，适合出去走走。"),
    ("chitchat", "讲个笑话听听吧。"),
    ("chitchat", "你都能做些什么？"),
    ("chitchat", "晚安，明天见。"),
    ("chitchat", "我有点无聊，陪我聊聊天。"),
    ("tool", "帮我算一下 128 乘以 46 等于多少。"),
    ("tool", "请把 hello 用 python echo 输出一遍。"),
    ("tool", "计算 (15+27)*3 的结果。"),
    ("tool", "帮我执行一段代码：print(sum(range(10)))。"),
    ("tool", "查一下 2 的 20 次方是多少。"),
    ("tool", "用工具算出 2024 年有多少天。"),
    ("knowledge", "线性代数中特征值和特征向量的几何意义是什么？"),
    ("knowledge", "雅思听力Section 4的常见陷阱有哪些？"),
    ("knowledge", "解释一下光合作用的光反应和暗反应区别。"),
    ("knowledge", "权责发生制和收付实现制在会计确认上的核心差异？"),
    ("knowledge", "考研英语阅读的精读方法应该怎么做？"),
    ("knowledge", "Python装饰器的底层实现机制是什么？"),
]


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _pct(vals: list[float], q: float) -> float | None:
    if not vals:
        return None
    xs = sorted(vals)
    k = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return round(xs[k], 4)


def log(msg: str) -> None:
    print(f"[r20b {datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _git_rev() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=str(EDU_ROOT), text=True).strip()
    except Exception:
        return "unknown"


# ============================================================
# 样本构建（确定性；SQL/seed 逐字入 samples 文件）
# ============================================================
async def build_samples() -> list[dict]:
    import app.database as db

    # ① eval_set32 全量 32（R20-min 冻结产物 rag_eval_set32.json，v1.1 A2：以冻结 32 条为准，
    #    不复用历史 task32_eval_set.json[:32] 切片）
    ev_path = EDU_ROOT / "scripts/eval/data/rag_eval_set32.json"
    with open(ev_path, encoding="utf-8") as f:
        ev = json.load(f)
    n_total = len(ev["cases"])
    slice_n = min(EVAL_SLICE_N, n_total)
    out = [
        {"source": "eval_set32", "query": c["query"],
         "golden_chunk_id": (c.get("golden") or {}).get("chunk_id")}
        for c in ev["cases"][:slice_n]
    ]
    log(f"样本① eval_set32 全量 {slice_n}/{n_total}（R20-min 冻结 rag_eval_set32.json）")

    # ② chat_message 真采（确定性：SQL 相对序 + 种子内洗牌 + 会话配额≤3）
    count_sql = (
        "SELECT COUNT(*) AS n FROM chat_message m "
        "JOIN chat_session s ON s.session_id = m.session_id "
        "WHERE m.role = 'user' AND CHAR_LENGTH(m.content) >= 10 AND s.yn = 1"
    )
    row = await db.fetch_one(count_sql)
    eligible = int(row["n"]) if row else 0
    sql = (
        "SELECT m.session_id AS session_id, m.user_id AS user_id, m.content AS content, "
        "m.created_at AS created_at FROM chat_message m "
        "JOIN chat_session s ON s.session_id = m.session_id "
        "WHERE m.role = 'user' AND CHAR_LENGTH(m.content) >= 10 AND s.yn = 1 "
        "ORDER BY m.created_at DESC LIMIT %s"
    )
    rows = await db.fetch_all(sql, (CHAT_SQL_PRELIMIT,))
    rng = random.Random(SEED)
    by_sess: dict[str, list[dict]] = {}
    for r in rows:
        by_sess.setdefault(str(r["session_id"]), []).append(dict(r))
    picked: list[dict] = []
    for sess, items in by_sess.items():
        order = list(items)
        rng.shuffle(order)
        picked.extend(order[:CHAT_PER_SESSION_CAP])
    rng.shuffle(picked)
    chat_rows = picked[:CHAT_SAMPLE_N]
    chat_meta = {
        "sql": sql,
        "params": {"limit": CHAT_SQL_PRELIMIT},
        "seed": SEED,
        "per_session_cap": CHAT_PER_SESSION_CAP,
        "eligible_total": eligible,
        "prelimit_rows": len(rows),
        "session_count": len(by_sess),
        "order_note": (f"SQL 相对序=created_at 倒序 LIMIT {CHAT_SQL_PRELIMIT}；确定性=python 种子内洗牌"
                       "（新插入数据不改已选集，仅 eligible_total 漂移），会话配额≤3 防单会话偏置"),
    }
    for r in chat_rows:
        out.append({"source": "chat_history", "query": str(r["content"]).strip(), "session_id": str(r["session_id"])})
    log(f"样本② chat_message 真采 {len(chat_rows)} 条（eligible={eligible}, sessions={len(by_sess)}）")

    # ③ 边界构造
    for typ, text in EDGE_CASES:
        out.append({"source": "edge_" + typ, "query": text})
    log(f"样本③ 边界构造 {len(EDGE_CASES)} 条")

    for i, s in enumerate(out):
        s["sample_id"] = i + 1
    meta = {
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "seed": SEED,
        "n_total": len(out),
        "counts": {"eval_set32": slice_n, "chat_history": len(chat_rows),
                   "edge_chitchat": 6, "edge_tool": 6, "edge_knowledge": 6},
        "chat_sampling": chat_meta,
        "note_eval_set32": (f"rag_eval_set32.json（R20-min 冻结，builder={ev['meta'].get('builder')}, "
                            f"built_at={ev['meta'].get('built_at')}, seed={ev['meta'].get('seed')}, "
                            f"n_cases={ev['meta'].get('n_cases')}, recall_topk={ev['meta'].get('recall_topk')}）；"
                            f"本探针全量取 {slice_n} 条 query。"),
    }
    with open(safe_w(OUT_SAMPLES), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "samples": out}, f, ensure_ascii=False, indent=2)
    return out


# ============================================================
# 被测路径探针
# ============================================================
# kickoff 配额护栏：主跑只到 intent+docs 层。answer 节点短路为 no-op（不再调 answer LLM，
# 规避 strong 402 后 fast 偶发挂起；route/fan_out 检索/子代理仍真实执行，hook 照采 docs）。
_OrigAnswerMethod = None


def install_answer_noop() -> None:
    global _OrigAnswerMethod
    from app.ai.harness.sixnode import SixNodeHarness

    _OrigAnswerMethod = SixNodeHarness.answer

    async def _noop_answer(self, state):
        from app.ai.graph import _record
        return {"final_answer": "", "degraded_reason": "probe_answer_skipped"} | _record(state, "answer")

    SixNodeHarness.answer = _noop_answer


def restore_answer() -> None:
    global _OrigAnswerMethod
    if _OrigAnswerMethod is not None:
        from app.ai.harness.sixnode import SixNodeHarness
        SixNodeHarness.answer = _OrigAnswerMethod


async def probe_old(query: str, flows_timing: dict) -> dict:
    """旧路径（流式正产编排）：run_agent_turn。TTFT=决策完成→检索完成（flows 绑定计时 spy）。"""
    import app.chat.flows.agent as flows
    from app.auth.schemas import UserRole

    flows_timing["t_end"] = None
    t0 = time.perf_counter()
    res = await flows.run_agent_turn(
        query,
        user_id=PROBE_USER_ID,
        role=UserRole.STUDENT,
        use_hyde=PROD_DEFAULTS["use_hyde"],
        enable_graph=PROD_DEFAULTS["enable_graph"],
        top_k=PROD_DEFAULTS["top_k"],
        final_max_k=PROD_DEFAULTS["final_max_k"],
        cutoff_drop_ratio=PROD_DEFAULTS["cutoff_drop_ratio"],
        session_id=None,
    )
    plan, bundle = res["plan"], res["bundle"]
    ttft = (flows_timing["t_end"] - t0) if flows_timing["t_end"] else None
    return {
        "t_total_s": round(time.perf_counter() - t0, 3),
        "need_search": bool(plan.need_search),
        "query_rewrite": plan.query_rewrite or None,
        "tool_plan_n": len(plan.tool_plan),
        "decision_error": plan.decision_error,
        "retrieved_count": int(bundle.raw_retrieved_count or 0),
        "final_count": len(bundle.docs or []),
        "doc_ids": [d.doc_id for d in (bundle.docs or [])],
        "doc_scores": [round(float(d.score), 6) for d in (bundle.docs or [])],
        "degraded": bundle.degraded_reason,
        "ttft_proxy_s": round(ttft, 3) if ttft is not None else None,
    }


async def probe_new(query: str) -> dict:
    """新路径（六节点图）：run_agent。docs 经 r20b_hook 捕获（P1-5：API 返回体恒空）。

    kickoff 配额护栏：主跑只取 intent+docs 层——answer 节点已由 install_answer_noop() 短路
    （不再调 answer LLM）；整体加硬超时，单样本挂起不拖垮全量。"""
    import app.ai.graph as graph
    import r20b_hook

    r20b_hook.reset()
    session_id = f"r20b-{int(time.time() * 1000)}-{random.randrange(1 << 30):08x}"
    t0 = time.perf_counter()
    try:
        res = await asyncio.wait_for(
            graph.run_agent(query, user_id=PROBE_USER_ID, session_id=session_id),
            timeout=NEW_PATH_TIMEOUT_S,
        )
        timeout_hit = False
    except asyncio.TimeoutError:
        res = {"answer": "", "intent": "", "degraded_reason": "new_path_timeout"}
        timeout_hit = True
    cap = r20b_hook.CAPTURE
    ttft = (cap["t_last"] - t0) if cap["calls"] and cap["t_last"] else None
    out = {
        "t_total_s": round(time.perf_counter() - t0, 3),
        "final_answer": str(res.get("answer") or ""),
        "intent": res.get("intent", ""),
        "effort": res.get("effort", ""),
        "retrieval_calls": cap["calls"],
        "retrieved_count": int(cap["raw_retrieved_count"] or 0),
        "final_count": len(cap["docs"]),
        "doc_ids": [d["chunk_id"] for d in cap["docs"]],
        "doc_scores": [d["score"] for d in cap["docs"]],
        "retrieval_queries": cap["queries"],
        "degraded": cap["degraded"] or res.get("degraded_reason"),
        "nodes_executed": list(res.get("nodes_executed") or []),
        "subagent_n": len(res.get("subagents") or []),
        "ttft_proxy_s": round(ttft, 3) if ttft is not None else None,
        "timeout": timeout_hit,
        "session_id": session_id,
    }
    return out


async def stability_probe(query: str) -> dict:
    """同 query 双轮 intent 预验：旧=decide_agent_plan，新=route_node 单节点（不进子代理）。"""
    import app.chat.flows.agent as flows
    import app.ai.graph as graph

    from app.ai.rule_router import classify_intent

    old_pairs: list[tuple[str, bool]] = []
    old_errors: list = []
    new_intents: list[str] = []
    for _ in range(2):
        p = await flows.decide_agent_plan(query, tool_metas=None)
        old_pairs.append((classify_intent(query) or "knowledge", bool(p.need_search)))
        if p.decision_error:
            old_errors.append(p.decision_error)
        state = graph._empty_state(query, user_id=PROBE_USER_ID, session_id="r20b-stab")
        out = await graph.route_node(state)
        new_intents.append(str(out.get("intent", "")))

    return {
        "old_pairs": [[a, b] for a, b in old_pairs],
        "old_errors": old_errors,
        "new_intents": new_intents,
        "old_stable": len(set(old_pairs)) == 1,
        "new_stable": len(set(new_intents)) == 1,
    }


async def semantic_pair(query: str, old_bundle_full: dict, plan_need_search: bool, new_final_answer: str) -> dict:
    """答案语义 30% 抽检：旧=generate_answer 真实生成；新=新路径 final_answer；LLM-judge 判等。"""
    import app.chat.generator as gen
    from app.chat.generator import _ChatClient
    from app.chat.schemas import RetrievedDoc

    docs = [RetrievedDoc(**d) for d in old_bundle_full["docs_full"]]
    old_answer, old_deg = await gen.generate_answer(
        query=query,
        docs=docs,
        graph_entities=[],
        history_turns=[],
        model="fast",
        degraded_reason=old_bundle_full.get("degraded"),
        mcp_context="",
        strict_rag=plan_need_search,
    )
    judge_prompt = (
        "判断以下两个针对同一问题的回答语义是否等价（要点一致即可，措辞不同不算分歧）。\n"
        f"问题：{query}\n\n回答A：{old_answer[:1200]}\n\n回答B：{str(new_final_answer)[:1200]}\n\n"
        '只输出 JSON：{"equivalent": true|false}'
    )
    loop = asyncio.get_running_loop()
    try:
        raw = await loop.run_in_executor(
            None,
            lambda: _ChatClient.get().call_chat(
                messages=[{"role": "user", "content": judge_prompt}],
                model="fast", temperature=0.0, max_tokens=JUDGE_MAX_TOKENS, timeout=90.0,
            ),
        )
        import re as _re
        m = _re.search(r'"equivalent"\s*:\s*(true|false)', raw)
        equivalent = (m.group(1) == "true") if m else None
        judge_raw = raw[:200]
    except Exception as exc:  # LLM 抖动不阻塞主指标
        equivalent, judge_raw = None, f"{type(exc).__name__}: {str(exc)[:150]}"
    return {
        "old_answer_head": old_answer[:200], "new_answer_head": str(new_final_answer)[:200],
        "old_answer_degraded": old_deg, "equivalent": equivalent, "judge_raw": judge_raw,
    }


# ============================================================
# 主流程
# ============================================================
async def run_probe(limit: int | None) -> int:
    import r20b_hook

    # ---- 0) 环境自证 + 确定性配置断言（生产默认即确定性配置，详档 v1.2 A1）----
    import app.database as db
    from app.config import settings

    assert getattr(settings, "RULE_ROUTING_ENABLED", None) is True, "RULE_ROUTING_ENABLED 必须为生产默认 True"
    assert float(getattr(settings, "LLM_TEMPERATURE", 1.0)) == 0.0, "LLM_TEMPERATURE 必须为生产默认 0.0（确定性）"
    assert bool(getattr(settings, "USE_AGENT_LOOP", False)) is True, "USE_AGENT_LOOP 必须为 True"

    # kickoff v1.1 确定性注入（commit ①，可 revert）：钉死 temp=0 兜底
    import r20b_temp0
    r20b_temp0.install()
    await db.init_mysql()
    try:
        await db.init_redis()
        # 清崩溃残留的防过载并发槽（先前 run 被 kill 未 release → 单用户槽卡死拒绝全部新路径）
        try:
            _r = db.get_redis()
            await _r.delete(f"{settings.CONCURRENT_KEY_PREFIX}:{PROBE_USER_ID}")
            await _r.set(settings.GLOBAL_CONCURRENT_KEY, 0)
        except Exception as _ge:
            log(f"WARN guard 槽复位跳过: {_ge}")
    except Exception as exc:
        log(f"WARN Redis init 异常（guard/checkpoint 将 fail-open，继续）: {type(exc).__name__}: {exc}")
    db.init_milvus()
    for _init in ("init_mongo", "init_neo4j", "init_minio"):
        try:
            await getattr(db, _init)() if _init == "init_mongo" else getattr(db, _init)()
        except Exception as exc:
            log(f"WARN {_init} 异常（对应通道自动降级，继续）: {type(exc).__name__}: {exc}")
    colls = db.get_milvus_client().list_collections()
    assert "edu_knowledge" in list(colls), f"Milvus 缺 edu_knowledge collection: {colls}"
    log(f"环境自证 OK（mysql/redis/milvus.edu_knowledge）probe_user={PROBE_USER_ID}（检索租户按学员）")

    # ---- 1) 样本（文件缺失则构建；存在则复用——保证同一样本集可跨次续跑）----
    if OUT_SAMPLES.exists():
        with open(OUT_SAMPLES, encoding="utf-8") as f:
            payload = json.load(f)
        samples_meta = payload["meta"]
        samples = payload["samples"]
        log(f"样本复用 {len(samples)} 条（built_at={samples_meta['built_at']}）")
    else:
        samples = await build_samples()
        with open(OUT_SAMPLES, encoding="utf-8") as f:
            samples_meta = json.load(f)["meta"]
    if limit:
        samples = samples[:limit]
    log(f"本轮执行 {len(samples)} 条")

    # ---- 2) hook 安装（import 顺序契约：先 service/flows 绑定原函数，再 install retriever spy）----
    import app.chat.service  # noqa: F401  绑定原 retrieve_three_channel（旧路径行为不变）
    import app.chat.flows.agent as flows
    import app.ai.graph  # noqa: F401

    r20b_hook.install()
    iso = r20b_hook.assert_isolation()
    assert iso["flows_binding_is_orig"], f"hook 隔离破坏：{iso}"
    install_answer_noop()  # 配额护栏：主跑 intent+docs 层，answer 不调 LLM

    # 旧路径 TTFT 计时 spy：替换 flows 模块绑定的 retrieve_three_channel（仅旧路径使用该绑定；
    # 新路径经 retriever 模块属性 = r20b_hook spy，二者互不可见）
    flows_timing: dict = {"t_end": None}
    _orig_flows_ret = flows.retrieve_three_channel

    async def _flows_timing_spy(query, **kwargs):
        bundle = await _orig_flows_ret(query, **kwargs)
        flows_timing["t_end"] = time.perf_counter()
        return bundle

    flows.retrieve_three_channel = _flows_timing_spy
    log(f"hook 就绪：retriever spy（新路径 docs）+ flows 计时 spy（旧路径 TTFT）隔离={iso}")

    # ---- 3) 语义抽检 30%（seed 固定）----
    rng = random.Random(SEED + 1)
    sem_ids = set(rng.sample(range(len(samples)), max(1, int(len(samples) * SEM_RATIO))))
    log(f"语义抽检 {len(sem_ids)}/{len(samples)} 条")

    # ---- 4) 逐样本双跑 ----
    results: list[dict] = []
    unstable: list[dict] = []
    t_start = time.perf_counter()
    for n, s in enumerate(samples):
        q = s["query"]
        rec: dict = {"sample_id": s["sample_id"], "source": s["source"], "query": q}
        try:
            # 4a) intent 稳定预验（双轮；不稳定→补 1 轮→仍不稳冻结首轮）
            stab = await stability_probe(q)
            if not (stab["old_stable"] and stab["new_stable"]):
                more = await stability_probe(q)
                stab["old_pairs"] += more["old_pairs"][:1]
                stab["new_intents"] += more["new_intents"][:1]
                stab["old_stable"] = len({tuple(p) for p in stab["old_pairs"]}) == 1
                stab["new_stable"] = len(set(stab["new_intents"])) == 1
            rec["stability"] = {
                "old_stable": stab["old_stable"], "new_stable": stab["new_stable"],
                "old_pairs": stab["old_pairs"], "new_intents": stab["new_intents"],
                "old_errors": stab["old_errors"],
            }
            if not (stab["old_stable"] and stab["new_stable"]):
                unstable.append({"sample_id": s["sample_id"], "source": s["source"],
                                 "old_pairs": stab["old_pairs"], "new_intents": stab["new_intents"]})

            # 4b) 旧路径 baseline（intent/need 冻结预验首轮值）
            old = await probe_old(q, flows_timing)
            old_intent, old_need = stab["old_pairs"][0]

            # 4c) 新路径 baseline
            new = await probe_new(q)
            new_intent = stab["new_intents"][0]

            # 4d) 对比
            jac = _jaccard(old["doc_ids"], new["doc_ids"])
            rec["compare"] = {
                "old_intent": old_intent, "new_intent": new_intent,
                "intent_match": old_intent == new_intent,
                "old_need_search": old_need, "new_retrieval_calls": new["retrieval_calls"],
                "need_search_match": old_need == (new["retrieval_calls"] > 0),
                "docs_jaccard": round(jac, 4),
                "old_final_n": old["final_count"], "new_final_n": new["final_count"],
                "old_retrieved_n": old["retrieved_count"], "new_retrieved_n": new["retrieved_count"],
                "old_doc_ids": old["doc_ids"], "new_doc_ids": new["doc_ids"],
                "old_ttft_s": old["ttft_proxy_s"], "new_ttft_s": new["ttft_proxy_s"],
                "old_degraded": old["degraded"], "new_degraded": new["degraded"],
                "new_nodes": new["nodes_executed"], "new_subagent_n": new["subagent_n"],
                "new_retrieval_queries": new["retrieval_queries"],
                "old_query_rewrite": old["query_rewrite"],
                "old_total_s": old["t_total_s"], "new_total_s": new["t_total_s"],
            }
        except Exception as exc:
            rec["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            rec["trace_head"] = traceback.format_exc()[-600:]
            log(f"  ✗ sample {s['sample_id']} 异常：{rec['error']}")
        results.append(rec)
        if (n + 1) % 10 == 0 or n + 1 == len(samples):
            log(f"进度 {n + 1}/{len(samples)}（累计 {time.perf_counter() - t_start:.0f}s, unstable={len(unstable)}）")
            _dump_results(results, unstable, [], partial=True)

    # ---- 5) 答案语义 30% 抽检（仅入报告；旧路径真实生成 vs 新路径 final_answer）----
    restore_answer()  # 语义抽检需要真实 answer（主跑已 intent+docs 收口）
    sem_records: list[dict] = []
    for rec in results:
        if rec["sample_id"] - 1 not in sem_ids or "compare" not in rec:
            continue
        s = samples[rec["sample_id"] - 1]
        try:
            # 旧路径完整 docs（含 content）供生成：单次 run_agent_turn 直调（=probe_old 同参数）
            from app.chat.flows.agent import run_agent_turn
            from app.auth.schemas import UserRole
            full = await run_agent_turn(
                s["query"], user_id=PROBE_USER_ID, role=UserRole.STUDENT,
                use_hyde=PROD_DEFAULTS["use_hyde"], enable_graph=PROD_DEFAULTS["enable_graph"],
                top_k=PROD_DEFAULTS["top_k"], final_max_k=PROD_DEFAULTS["final_max_k"],
                cutoff_drop_ratio=PROD_DEFAULTS["cutoff_drop_ratio"], session_id=None)
            docs_full = [d.model_dump() for d in (full["bundle"].docs or [])]
            new_res = await probe_new(s["query"])
            sem = await semantic_pair(s["query"], {"docs_full": docs_full, "degraded": full["bundle"].degraded_reason},
                                      bool(full["plan"].need_search), new_res.get("final_answer") or "")
            sem_records.append({"sample_id": rec["sample_id"], "source": s["source"], **sem})
        except Exception as exc:
            sem_records.append({"sample_id": rec["sample_id"], "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
        if len(sem_records) % 5 == 0:
            log(f"语义抽检 {len(sem_records)} 条完成")

    # ---- 6) 汇总 ----
    valid = [r for r in results if "compare" in r]
    n_valid = len(valid)
    intent_dis = [r["compare"] for r in valid if not r["compare"]["intent_match"]]
    need_dis = [r["compare"] for r in valid if not r["compare"]["need_search_match"]]
    jacs = [r["compare"]["docs_jaccard"] for r in valid]
    old_ttfts = [r["compare"]["old_ttft_s"] for r in valid if r["compare"]["old_ttft_s"] is not None]
    new_ttfts = [r["compare"]["new_ttft_s"] for r in valid if r["compare"]["new_ttft_s"] is not None]
    sem_eq = [x["equivalent"] for x in sem_records if x.get("equivalent") is not None]

    def dist(vals: list[float]) -> dict:
        vals = sorted(vals)
        return {"n": len(vals),
                "mean": round(sum(vals) / len(vals), 4) if vals else None,
                "p50": _pct(vals, 0.5), "p95": _pct(vals, 0.95),
                "min": round(vals[0], 4) if vals else None,
                "max": round(vals[-1], 4) if vals else None,
                "eq1_count": sum(1 for v in vals if v >= 0.9999),
                "lt0.5_count": sum(1 for v in vals if v < 0.5),
                "eq0_count": sum(1 for v in vals if v <= 0.0001)}

    summary = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "seed": SEED,
        "git_rev": _git_rev(),
        "probe_user": {"user_id": PROBE_USER_ID, "role_sent": "UserRole.STUDENT（对齐生产非 admin 租户范围）"},
        "prod_defaults": PROD_DEFAULTS,
        "hooks": iso,
        "n_samples": len(samples), "n_valid": n_valid, "n_error": len(results) - n_valid,
        "unstable_n": len(unstable),
        "intent_divergence": {"count": len(intent_dis),
                              "rate": round(len(intent_dis) / n_valid, 4) if n_valid else None,
                              "by_source": _by_source(results, "intent_match")},
        "need_search_divergence": {"count": len(need_dis),
                                   "rate": round(len(need_dis) / n_valid, 4) if n_valid else None,
                                   "by_source": _by_source(results, "need_search_match")},
        "docs_jaccard": dist(jacs),
        "ttft_proxy": {"old": dist(old_ttfts), "new": dist(new_ttfts),
                       "note": ("旧=决策完成→检索完成；新=start→hook 首检索完成；无检索路径（chitchat 直连/降级）"
                                "为 None 不计入——两路径事件源不同，近似口径，供 R02 TTFT 预算立项参考")},
        "semantic_30pct": {"n_planned": len(sem_ids & set(range(1, len(samples) + 1))), "n_done": len(sem_records),
                           "equivalent": sum(1 for e in sem_eq if e),
                           "not_equivalent": sum(1 for e in sem_eq if not e),
                           "judge_failed": sum(1 for x in sem_records if x.get("equivalent") is None),
                           "gate_note": "答案语义仅入报告，不作灰度门槛（详档 v1.2 终审 A1）"},
        "five_conditions_current": {
            "千条样本": {"当前值": f"{len(samples)} 条/批（W0 初值；千条由 R02-b 灰度期累积）"},
            "连续3天": {"当前值": "单日 1 轮（连续性由 R02-b 灰度期考核）"},
            "intent分歧<5%": {"当前值": f"{round(len(intent_dis) / n_valid * 100, 2)}%" if n_valid else None},
            "docsJaccard>0.9": {"当前值": round(sum(jacs) / len(jacs), 4) if jacs else None},
            "P95TTFT容差": {"旧P95_s": _pct(old_ttfts, 0.95), "新P95_s": _pct(new_ttfts, 0.95),
                          "阈值说明": "旧路径实测 P95 + 10%；阈值裁定属用户/编排者，本探针只报数"},
        },
    }
    _dump_results(results, unstable, sem_records, partial=False)
    with open(safe_w(OUT_SUMMARY), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    write_report(summary, samples_meta, sem_records)
    log(f"完成：valid={n_valid} intent分歧={len(intent_dis)} jaccard均值={summary['docs_jaccard']['mean']} "
        f"报告={OUT_REPORT}")
    return 0


def _dump_results(results, unstable, sem_records, *, partial: bool) -> None:
    # M-2 收口: dualrun 全量 results（249KB 级大 JSON, 曾被迫 force-add 进 git 的教训）
    # 真身入 GridFS 制品库, 本地留同字节工作副本; mongo 不可达自动降级
    # test-reports/artifacts_local/, 归档层自身失败回退直接落盘——均不阻断探针主流程。
    payload = {"ran_at": datetime.now().isoformat(timespec="seconds"), "results": results,
               "unstable": unstable, "semantic": sem_records, "partial": partial}
    try:
        from app.common.artifact_store import save_artifact
        _arch = save_artifact("eval/r20b/dualrun_results.json", payload,
                              metadata={"kind": "r20b_dualrun_results", "partial": partial,
                                        "n_results": len(results)},
                              local_copy=str(safe_w(OUT_RESULTS)))
        print(f"[artifact] backend={_arch['backend']} aid={_arch['aid']} "
              f"sha256={_arch['sha256'][:16]} size={_arch['size']}")
    except Exception as _e:  # noqa: BLE001
        print(f"[artifact] 归档失败(忽略, 回退直接落盘): {type(_e).__name__}: {_e}")
        with open(safe_w(OUT_RESULTS), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)


def _by_source(results: list[dict], key: str) -> dict:
    agg: dict[str, list[int]] = {}
    for r in results:
        c = r.get("compare")
        if not c:
            continue
        agg.setdefault(r["source"], [0, 0])
        agg[r["source"]][0] += 1
        if not c[key]:
            agg[r["source"]][1] += 1
    return {k: {"n": v[0], "diverge": v[1]} for k, v in sorted(agg.items())}


def write_report(s: dict, meta: dict, sem_records: list[dict]) -> None:
    j = s["docs_jaccard"]
    fc = s["five_conditions_current"]
    lines = [
        "# taskR20b 双跑基线报告（W0 · R02 灰度收敛基准）",
        "",
        f"- ran_at: {s['ran_at']}  |  git_rev: `{s['git_rev']}`  |  seed: {s['seed']}",
        f"- 样本 {s['n_samples']}/{meta['n_total']}（eval_set32 切片 {meta['counts']['eval_set32']} + chat 真采 "
        f"{meta['counts']['chat_history']} + 边界 18）｜valid {s['n_valid']}｜error {s['n_error']}｜"
        f"unstable {s['unstable_n']}",
        f"- 探针身份: user_id={s['probe_user']['user_id']}（检索租户按 {s['probe_user']['role_sent']}）",
        f"- 生产默认参数: use_hyde={s['prod_defaults']['use_hyde']}, top_k={s['prod_defaults']['top_k']}, "
        f"final_max_k={s['prod_defaults']['final_max_k']}, cutoff={s['prod_defaults']['cutoff_drop_ratio']}, "
        f"enable_graph={s['prod_defaults']['enable_graph']}",
        f"- hook 隔离校验: {json.dumps(s['hooks'], ensure_ascii=False)}",
        "",
        "## 门槛指标（仅此两项入灰度门槛，详档 v1.2 终审 A1）",
        "",
        f"- **intent 分歧率**: {s['intent_divergence']['count']}/{s['n_valid']} = "
        f"**{round((s['intent_divergence']['rate'] or 0) * 100, 2)}%**（五条件参考 <5%）",
        f"  - 分源: {json.dumps(s['intent_divergence']['by_source'], ensure_ascii=False)}",
        f"- **docs Jaccard**: mean={j['mean']}, p50={j['p50']}, p95={j['p95']}, min={j['min']}, max={j['max']}"
        f"（五条件参考 mean>0.9；=1 共 {j['eq1_count']} 条，<0.5 共 {j['lt0.5_count']} 条，=0 共 {j['eq0_count']} 条）",
        f"- need_search 分歧率（报告项，非门槛）: {s['need_search_divergence']['count']}/{s['n_valid']} = "
        f"{round((s['need_search_divergence']['rate'] or 0) * 100, 2)}%"
        f"｜分源: {json.dumps(s['need_search_divergence']['by_source'], ensure_ascii=False)}",
        "",
        "## TTFT 代理（start→首检索完成，P2-17 承接）",
        "",
        "| 路径 | n | P50(s) | P95(s) | min | max |",
        "|---|---|---|---|---|---|",
    ]
    for label, d in (("旧 run_agent_turn", s["ttft_proxy"]["old"]), ("新 run_agent(图)", s["ttft_proxy"]["new"])):
        lines.append(f"| {label} | {d['n']} | {d['p50']} | {d['p95']} | {d['min']} | {d['max']} |")
    lines += [
        "",
        f"- P95 容差对照（五条件参考：新 ≤ 旧 P95 × 1.1）: 旧 {fc['P95TTFT容差']['旧P95_s']}s vs 新 "
        f"{fc['P95TTFT容差']['新P95_s']}s",
        "",
        "## 确定性设计（详档 v1.2 A1 承接）",
        "",
        "- RULE_ROUTING_ENABLED=True / LLM_TEMPERATURE=0.0 / USE_AGENT_LOOP=True 启动断言通过"
        "（路由 0-LLM 纯正则；temp0 注入强制所有 LLM 收口含旧路径 HyDE 改写 temperature=0.0）。",
        f"- 每样本同 query 双轮 intent 预验（旧=decide_agent_plan；新=route_node 单节点）；不稳定样本 "
        f"{s['unstable_n']} 条" + ("，已冻结首轮值并列清单（results.unstable）。" if s["unstable_n"] else "。"),
        f"- 答案语义 30% 抽检（仅入报告）：n_done={s['semantic_30pct']['n_done']}, "
        f"equivalent={s['semantic_30pct']['equivalent']}, not_equivalent={s['semantic_30pct']['not_equivalent']}, "
        f"judge_failed={s['semantic_30pct']['judge_failed']}",
        "",
        "## 样本构成（可复现）",
        "",
        f"- eval_set32: {meta['note_eval_set32']}",
        f"- chat 采样 SQL: `{meta['chat_sampling']['sql']}`（params={meta['chat_sampling']['params']}, "
        f"seed={meta['chat_sampling']['seed']}, eligible={meta['chat_sampling']['eligible_total']}, "
        f"会话数={meta['chat_sampling']['session_count']}）",
        f"- {meta['chat_sampling']['order_note']}",
        "- 边界 18 条逐字:",
    ]
    for typ, text in EDGE_CASES:
        lines.append(f"  - ({typ}) {text}")
    lines += [
        "",
        "## 五条件门槛对照（只报数，阈值裁定属用户/编排者）",
        "",
        "| 条件 | 当前值 |",
        "|---|---|",
    ]
    for k, v in fc.items():
        lines.append(f"| {k} | {json.dumps(v, ensure_ascii=False)} |")
    lines += [
        "",
        "## 已知口径与偏差（批判性审查输入）",
        "",
        "1. eval_set32 来源=R20-min 冻结产物 rag_eval_set32.json（n_cases=32, seed=20260914, recall_topk=150, "
        "built_at=2026-09-14T11:17），本探针全量取其 32 条 query（未用历史 task32_eval_set.json 切片）。",
        "2. chat 采样确定性=「SQL 相对序（created_at DESC LIMIT 120）+ 种子内洗牌 + 会话配额」——新插入数据不改"
        "已选集，仅 eligible_total 漂移；SQL/参数/seed 逐字存 dualrun_samples.json。",
        "3. 新路径 docs 由 r20b_hook 进程内 spy 捕获（run_agent 返回体 docs 恒空，P1-5）；旧路径绑定原函数不受"
        "影响（隔离断言写入 summary.hooks）。",
        "4. 新路径 tool/learning 意图走子代理编排（KNOWLEDGE_DIRECT_RETRIEVAL 仅覆盖 knowledge），检索参数与旧"
        "路径「统一 top_k=12」结构性不同——该差异属 P2-23 分歧面，如实计入指标，不做归一化。",
        "5. 新路径检索硬编码 use_hyde=False（sixnode.fan_out），旧路径按生产默认 True——查询改写差异计入 docs "
        "分歧；逐样本检索 query 见 results 的 new_retrieval_queries / old_query_rewrite。",
        "6. TTFT 代理口径：两路径事件源不同（旧=决策完成→检索完成；新=start→hook 首检索完成），近似对比；"
        "chitchat 直连样本双方均无检索（None 不计入）。",
        "7. 答案语义对比中，旧路径答案=generate_answer 真实生成（fast，temp=0），新路径答案=同轮 run_agent 的 "
        "final_answer；两者 prompt 结构/上下文天然不同，judge 结果仅供人读。",
        "",
        "## 复跑命令",
        "",
        "```bash",
        "cd edu-agent",
        ".venv/Scripts/python.exe scripts/eval/r20b_dualrun_probe.py            # 全量 100",
        ".venv/Scripts/python.exe scripts/eval/r20b_dualrun_probe.py --limit 5  # 冒烟",
        "```",
        "",
        "产物: scripts/eval/dualrun_samples.json / dualrun_results.json / dualrun-summary.json / 本报告",
    ]
    # Mimosa safe_w 仅允许 eval 目录树内写出 → 先落 eval/，运行后由执行 agent 拷到
    # kickoff 指定的 ../test-reports/dualrun-baseline.md
    local_report = EDU_ROOT / "scripts" / "eval" / "dualrun-baseline.md"
    with open(safe_w(str(local_report)), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log(f"报告已写 eval 内: {local_report}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 条样本（冒烟）")
    args = ap.parse_args()
    sys.exit(asyncio.run(run_probe(args.limit)))
