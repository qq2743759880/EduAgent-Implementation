# -*- coding: utf-8 -*-
"""taskR20b GWT③ 复验：跨进程重跑稳定性探针，验证 intent 可复现（分歧非采样噪声）。

做法：从 dualrun_results.json（主跑 A）抽 10 个样本（均匀跨全量），每样本重跑
stability_probe（旧=decide_agent_plan ×2 轮；新=route_node ×2 轮），对照主跑 A 记录的
intent/need——跨「进程 × 时间」两次执行一致 ⇒ 确定性成立（GWT③）。

用法（edu-agent/ 下，主跑完成后执行）：
  .venv/Scripts/python.exe scripts/eval/r20b_gwt_verify.py

产物：scripts/eval/r20b-gwt3-verify.json + 控制台结论。
"""
from __future__ import annotations

import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from _safeio import safe_w  # Mimosa 路径穿越防护:写出统一收容校验

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # scripts/（r20b_hook 同级导入）
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

RESULTS = Path(__file__).resolve().parent / "dualrun_results.json"
OUT = Path(__file__).resolve().parent / "r20b-gwt3-verify.json"
N_VERIFY = 10


async def main() -> int:
    from app.config import settings
    import app.database as db
    from r20b_dualrun_probe import PROBE_USER_ID, stability_probe

    assert getattr(settings, "RULE_ROUTING_ENABLED", None) is True
    assert float(getattr(settings, "LLM_TEMPERATURE", 1.0)) == 0.0
    await db.init_mysql()
    db.init_milvus()
    try:
        await db.init_redis()
    except Exception:
        pass

    data = json.load(open(RESULTS, encoding="utf-8"))
    if data.get("partial"):
        print("主跑 results 为 partial（未完成），先等主跑结束")
        return 2
    recs = [r for r in data["results"] if "compare" in r]
    rng = random.Random(20260915)
    picks = sorted(rng.sample(recs, min(N_VERIFY, len(recs))), key=lambda r: r["sample_id"])
    print(f"[gwt3] 复验 {len(picks)} 样本（跨进程 vs 主跑 {data['ran_at']}）")

    out_rows = []
    mismatches = []
    for r in picks:
        q = r["query"]
        stab = await stability_probe(q)
        old_intent_now = stab["old_pairs"][0][0]
        old_need_now = stab["old_pairs"][0][1]
        new_intent_now = stab["new_intents"][0]
        row = {
            "sample_id": r["sample_id"], "source": r["source"],
            "runA": {"old_intent": r["compare"]["old_intent"], "old_need_search": r["compare"]["old_need_search"],
                     "new_intent": r["compare"]["new_intent"]},
            "rerun": {"old_intent": old_intent_now, "old_need_search": old_need_now, "new_intent": new_intent_now,
                      "old_stable": stab["old_stable"], "new_stable": stab["new_stable"]},
        }
        same = (old_intent_now == r["compare"]["old_intent"]
                and old_need_now == r["compare"]["old_need_search"]
                and new_intent_now == r["compare"]["new_intent"])
        row["reproducible"] = same
        if not same:
            mismatches.append(row)
        out_rows.append(row)
        print(f"  #{row['sample_id']} ({r['source']}): {'OK' if same else 'MISMATCH'} "
              f"old={old_intent_now}/{old_need_now} new={new_intent_now}")

    verdict = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "n_verified": len(out_rows),
        "mismatch_n": len(mismatches),
        "gwt3_pass": len(mismatches) == 0,
        "rows": out_rows,
        "note": "稳定性预验本身每样本已含同进程双轮；本脚本补跨进程×时间维度。任何 MISMATCH 列表化"
                "交编排者处置（固化手段：seed/prompt 缓存/规则覆盖），不得静默忽略。",
    }
    with open(safe_w(OUT), "w", encoding="utf-8") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=2)
    print(f"[gwt3] 结论：{'PASS' if verdict['gwt3_pass'] else 'FAIL'}"
          f"（mismatch={len(mismatches)}）→ {OUT}")
    return 0 if verdict["gwt3_pass"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
