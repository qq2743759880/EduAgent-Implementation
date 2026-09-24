# -*- coding: utf-8 -*-
"""TA7 自验②：真实课程的**成功收藏**路径（零 ID 用户旅程：用户只说课名，ID 由模型从候选里取）。

背景（TA7 实测数据属性）：`series` 在售 2627 行 / 438 个不同课名 → 每个课名平均重名 6 行，
**不存在任何「整串 LIKE 唯一命中」的课名**（SQL: HAVING COUNT(*)=1 → 0 行）。
故按名解析必然落到 40930「匹配到多门，需用户确认」（不猜＝正确行为），
用户旅程 = ①按名请求 → ②服务端给候选(含 series_id) → ③模型取 ID 再收藏 → SUCCESS 真实落库。
"""
from __future__ import annotations

import json
import sys

import _ta7_lib as L

STUDENT = "user000002"
OUT = "ta7_accept_result.json"


def fav_count(user_id: int, series_id: int) -> int:
    r = L.q("SELECT COUNT(*) c FROM series_favorite WHERE user_id=%s AND series_id=%s",
            (user_id, series_id))
    return int(r[0]["c"])


def main() -> None:
    token = L.login(STUDENT)
    uid = int(L.q("SELECT id FROM sys_user WHERE account=%s", (STUDENT,))[0]["id"])

    # ---- 第 1 轮：按名请求（必然 need_clarify，给候选）----
    q1 = "帮我把《Python 入门》这门课加入我的收藏"
    _e1, ans1, done1, _ = L.chat_stream(q1, token)
    inner1 = done1.get("data") if isinstance(done1.get("data"), dict) else done1
    sid_session = inner1.get("session_id")
    rows1 = L.q("SELECT status, error_message FROM mcp_tool_call_log WHERE tool_name='favorite_add'"
                " ORDER BY id DESC LIMIT 1")
    print(f"[轮1] {q1!r}\n  SSE={[c.get('status') for c in (inner1.get('mcp_tool_calls') or [])]}"
          f"  DB={rows1}")
    print(f"[轮1 answer]\n{ans1}\n")
    # 服务端真实候选（取 fuzzy 命中的前 3 个，供报告对账）
    cand = L.q("SELECT id, series_name FROM series WHERE sale_status='on_sale'"
               " AND series_name LIKE '%入门%' ORDER BY CHAR_LENGTH(series_name) ASC, id ASC LIMIT 3")
    print(f"[候选对账] LIKE '%入门%' 前 3 = {L.jj(cand)}")
    target = cand[0]

    # ---- 第 2 轮：用户口头确认（不报 ID，让模型用候选里的 ID）----
    q2 = f"就收藏你刚才列出的第一门课吧（《{target['series_name']}》）。"
    before = fav_count(uid, int(target["id"]))
    _e2, ans2, done2, _ = L.chat_stream(q2, token, session_id=sid_session)
    inner2 = done2.get("data") if isinstance(done2.get("data"), dict) else done2
    after = fav_count(uid, int(target["id"]))
    rows2 = L.q("SELECT id, status, error_message, LEFT(args_json,160) args FROM mcp_tool_call_log"
                " WHERE tool_name='favorite_add' ORDER BY id DESC LIMIT 1")
    print(f"[轮2] {q2!r}\n  SSE={[c.get('status') for c in (inner2.get('mcp_tool_calls') or [])]}"
          f"  receipt_unverified={inner2.get('tool_receipt_unverified')}")
    print(f"  DB 行={L.jj(rows2)}")
    print(f"  series_favorite(user={uid}, series={target['id']}) before={before} after={after}")
    print(f"[轮2 answer]\n{ans2}")

    # 兜底探针：若第 2 轮模型没用上 ID，则直接以 series_id 直传验证成功路径（如实标注）
    fallback = None
    if after <= before:
        print("\n[兜底] 轮 2 未成功 → 直接以 series_id 直传验证成功路径（证明成功路径如实）")
        q3 = f"请直接调用 favorite_add，参数 series_id={target['id']}，把课程加入我的收藏。"
        _e3, ans3, done3, _ = L.chat_stream(q3, token)
        inner3 = done3.get("data") if isinstance(done3.get("data"), dict) else done3
        after2 = fav_count(uid, int(target["id"]))
        rows3 = L.q("SELECT id, status, error_message, LEFT(args_json,160) args FROM mcp_tool_call_log"
                    " WHERE tool_name='favorite_add' ORDER BY id DESC LIMIT 1")
        print(f"[兜底] SSE={[c.get('status') for c in (inner3.get('mcp_tool_calls') or [])]}"
              f" receipt_unverified={inner3.get('tool_receipt_unverified')}")
        print(f"[兜底] DB 行={L.jj(rows3)}  fav {before}->{after2}")
        print(f"[兜底 answer]\n{ans3}")
        fallback = {"query": q3, "answer": ans3,
                    "sse_tool_calls": [{"tool_name": c.get("tool_name"), "status": c.get("status")}
                                       for c in (inner3.get("mcp_tool_calls") or [])],
                    "receipt_unverified": inner3.get("tool_receipt_unverified"),
                    "db_row": rows3[0] if rows3 else None, "fav_after": after2}
        after = after2

    # ---- 还原：经应用接口取消收藏 ----
    try:
        resp = L.delete_json(f"/api/favorites/{int(target['id'])}", token=token)
        print(f"[还原] DELETE /api/favorites/{target['id']} → {L.jj(resp)[:150]}")
    except Exception as exc:
        print(f"[还原] 接口失败 {type(exc).__name__}: {exc} → SQL 删除")
        L.x("DELETE FROM series_favorite WHERE user_id=%s AND series_id=%s", (uid, int(target["id"])))
    print(f"[还原] 复查 count={fav_count(uid, int(target['id']))}（应回到 {before}）")

    try:
        with open(OUT, encoding="utf-8") as f:
            acc = json.load(f)
    except Exception:
        acc = {}
    acc["d1_success_case"] = {
        "note": "本库 438 个在售课名全部重名（无「整串 LIKE 唯一命中」的课名）→ 按名成功路径"
                "在数据层不可达（40930 need_clarify = 正确的不猜行为）；成功路径以 series_id 收敛。",
        "round1_query": q1, "round1_answer": ans1, "round1_db": rows1,
        "target": {"series_id": int(target["id"]), "series_name": target["series_name"]},
        "round2_query": q2, "round2_answer": ans2,
        "round2_sse": [{"tool_name": c.get("tool_name"), "status": c.get("status")}
                       for c in (inner2.get("mcp_tool_calls") or [])],
        "round2_db": rows2, "fav_before": before, "fav_after_all": after,
        "fallback_series_id_path": fallback,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(acc, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[证据] 已并入 {OUT}")


if __name__ == "__main__":
    main()
