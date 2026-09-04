# -*- coding: utf-8 -*-
"""task29 批判③ 独立复核：缓存命中率与成本落地的可复算校验（离线，不烧 LLM）。"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # 项目根
from app.ai.prompt_cache import evaluate_hit_rate, evaluate_cache_sev  # noqa: E402

d = json.load(open(os.path.join(os.path.dirname(__file__), "task29_results.json"), encoding="utf-8"))
c = d["cache"]; cost = d["cost"]

hits = sum(r["cache_hit_tokens"] for r in c["rounds"])
miss = sum(r["cache_miss_tokens"] for r in c["rounds"])
tot = hits + miss
rate = round(hits / tot, 4)
out = {
    "independent_recalc": {"hit": hits, "miss": miss, "total": tot, "hit_rate": rate,
                            "matches_persisted": abs(rate - c["hit_rate"]) < 1e-6},
    "persisted": {"hit_rate": c["hit_rate"], "rounds": len(c["rounds"])},
    "evaluate_hit_rate_official": evaluate_hit_rate(
        [{"prompt_cache_hit_tokens": r["cache_hit_tokens"],
          "prompt_cache_miss_tokens": r["cache_miss_tokens"]} for r in c["rounds"]], model="fast"),
    "evaluate_cache_sev": evaluate_cache_sev(rate),
    "min_prefix_tokens": c["min_prefix_tokens"], "provider": c.get("provider"),
    "cache_gap_note": "真实短请求前缀约300token<DeepSeek缓存门槛1024；96%命中仅对>1600token大前缀成立（生产规模场景），落地到短对话前缀收益有限",
}
tot_cost = 0
rows = []
for r in cost["rows"]:
    pr = r["prompt_tok"] / 1e6 * cost["price_assumption"]["in_per_M"]
    co = r["completion_tok"] / 1e6 * cost["price_assumption"]["out_per_M"]
    per = pr + co; line = per * r["monthly_req"]; tot_cost += line
    rows.append({"tier": r["tier"], "per_req_recalc": round(per, 4),
                 "per_req_persisted": r["per_req_cost_yuan"],
                 "monthly_recalc": round(line, 2), "monthly_persisted": r["monthly_cost_yuan"],
                 "consist": abs(per - r["per_req_cost_yuan"]) < 0.002})
out["cost_recalc"] = {"rows": rows,
    "monthly_total_recalc": round(tot_cost, 2),
    "monthly_total_persisted": cost["monthly_total_yuan"],
    "budget_yuan": cost["budget_yuan"],
    "over_budget": tot_cost > cost["budget_yuan"],
    "over_budget_x": round(tot_cost / cost["budget_yuan"], 2),
    "price_assumption": cost["price_assumption"], "daily_query_assumption": cost["daily_query_assumption"]}
print(json.dumps(out, ensure_ascii=False, indent=2))