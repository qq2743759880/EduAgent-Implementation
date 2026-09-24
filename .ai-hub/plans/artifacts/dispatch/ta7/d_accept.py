# -*- coding: utf-8 -*-
"""TA7 自验 ①②③（真实 HTTP + DB 对照），单次登录避免触发登录限流。

① 收藏不存在的课 → 调用日志 status=非 SUCCESS、SSE 如实、tool_receipt_unverified=true、
   AI 话术含「未找到」+ 模糊候选（D2）
② 收藏真实存在的课（SQL 现挑一门**名字唯一**的在售课）→ SUCCESS + series_favorite 真实 +1，
   验完经应用接口取消收藏还原
③ 跨会话记忆：会话 A 记名字 → 新会话问名字 → 正确答出

用法：python d_accept.py [all|1|2|3]
"""
from __future__ import annotations

import json
import sys
import time
import uuid

import _ta7_lib as L

STUDENT = "user000002"
OUT = "ta7_accept_result.json"
result: dict = {}


def pick_real_course() -> dict:
    """挑一门「名字在售课里唯一」的在售课（重名课会走 40930 need_clarify——那是正确行为，
    不是本次要验的成功路径，故排除）。"""
    rows = L.q(
        "SELECT s.id, s.series_name FROM series s"
        " JOIN (SELECT series_name FROM series WHERE sale_status='on_sale'"
        "       GROUP BY series_name HAVING COUNT(*)=1) u ON u.series_name = s.series_name"
        " WHERE s.sale_status='on_sale' AND s.series_name IS NOT NULL AND s.series_name <> ''"
        " AND NOT EXISTS (SELECT 1 FROM series_favorite f WHERE f.series_id=s.id AND f.user_id=2)"
        " ORDER BY CHAR_LENGTH(s.series_name) ASC, s.id ASC LIMIT 5")
    return rows[0]


def fav_count(user_id: int, series_id: int) -> int:
    r = L.q("SELECT COUNT(*) c FROM series_favorite WHERE user_id=%s AND series_id=%s",
            (user_id, series_id))
    return int(r[0]["c"])


def case1(token: str) -> None:
    print("\n" + "=" * 72 + "\n① 收藏《Python 入门》（库内不存在）\n" + "=" * 72)
    q1 = "帮我把《Python 入门》这门课加入我的收藏，并说明你调用了哪个工具、结果如何。"
    _ev, ans1, done1, _ = L.chat_stream(q1, token)
    inner1 = done1.get("data") if isinstance(done1.get("data"), dict) else done1
    calls1 = inner1.get("mcp_tool_calls") or []
    print(f"[SSE] mcp_tool_calls = "
          f"{[{k: c.get(k) for k in ('tool_name', 'status')} for c in calls1]}")
    print(f"[SSE] tool_receipt_unverified = {inner1.get('tool_receipt_unverified')}")
    print(f"[answer]\n{ans1}")
    rows1 = L.q("SELECT id, status, error_message, LEFT(result_json,400) rj FROM mcp_tool_call_log"
                " WHERE tool_name='favorite_add' ORDER BY id DESC LIMIT 1")
    print(f"[DB] 最新 favorite_add 行 = {L.jj(rows1)}")
    result["d1_fail_case"] = {
        "query": q1,
        "sse_tool_calls": [{"tool_name": c.get("tool_name"), "status": c.get("status")}
                           for c in calls1],
        "tool_receipt_unverified": inner1.get("tool_receipt_unverified"),
        "answer": ans1,
        "db_row": rows1[0] if rows1 else None,
    }


def case2(token: str, uid: int) -> None:
    real = pick_real_course()
    sid = int(real["id"])
    print("\n" + "=" * 72 + f"\n② 收藏真实课程《{real['series_name']}》(id={sid})\n" + "=" * 72)
    before = fav_count(uid, sid)
    q2 = f"请帮我把《{real['series_name']}》这门课加入收藏"
    _ev, ans2, done2, _ = L.chat_stream(q2, token)
    inner2 = done2.get("data") if isinstance(done2.get("data"), dict) else done2
    calls2 = inner2.get("mcp_tool_calls") or []
    after = fav_count(uid, sid)
    print(f"[SSE] mcp_tool_calls = "
          f"{[{k: c.get(k) for k in ('tool_name', 'status')} for c in calls2]}")
    print(f"[SSE] tool_receipt_unverified = {inner2.get('tool_receipt_unverified')}")
    print(f"[DB]  series_favorite(user={uid}, series={sid})  before={before} after={after}")
    print(f"[answer]\n{ans2}")
    rows2 = L.q("SELECT id, status, error_message, LEFT(args_json,160) args FROM mcp_tool_call_log"
                " WHERE tool_name='favorite_add' ORDER BY id DESC LIMIT 1")
    print(f"[DB] 最新 favorite_add 行 = {L.jj(rows2)}")
    result["d1_success_case"] = {
        "query": q2, "series_id": sid, "series_name": real["series_name"],
        "fav_before": before, "fav_after": after,
        "sse_tool_calls": [{"tool_name": c.get("tool_name"), "status": c.get("status")}
                           for c in calls2],
        "tool_receipt_unverified": inner2.get("tool_receipt_unverified"),
        "answer": ans2, "db_row": rows2[0] if rows2 else None,
    }

    # 还原：经应用接口取消收藏（不用裸 SQL）
    try:
        del_resp = L.delete_json(f"/api/favorites/{sid}", token=token)
        print(f"[还原] DELETE /api/favorites/{sid} → {L.jj(del_resp)[:160]}")
        result["cleanup_delete_resp"] = del_resp
    except Exception as exc:
        print(f"[还原] 应用接口删除失败({type(exc).__name__}: {exc}) → 回退 SQL 删除")
        L.x("DELETE FROM series_favorite WHERE user_id=%s AND series_id=%s", (uid, sid))
    print(f"[还原] 复查 count = {fav_count(uid, sid)}（应为 {before}）")


def case3(token: str, uid: int) -> None:
    print("\n" + "=" * 72 + "\n③ 跨会话记忆（新会话问名字）\n" + "=" * 72)
    name = f"TATOU{uuid.uuid4().hex[:4]}"
    msg_a = f"你好，我叫{name}，请记住我的名字"
    _e, ans_a, done_a, _ = L.chat_stream(msg_a, token)
    inner_a = done_a.get("data") if isinstance(done_a.get("data"), dict) else done_a
    print(f"[会话A] {msg_a!r}\n  memorized = {L.jj(inner_a.get('memorized'))}")
    heads = L.q("SELECT entity_id, LEFT(content,60) c FROM user_memory_event"
                " WHERE user_id=%s AND valid_to IS NULL AND event_type<>'delete'"
                " ORDER BY id DESC LIMIT 5", (uid,))
    print(f"[DB] HEAD 记忆 = {L.jj(heads)}")
    time.sleep(4)  # Milvus 写后读可见窗口（实测约 3s）
    msg_b = "我叫什么名字？"
    _e2, ans_b, _done_b, _ = L.chat_stream(msg_b, token)
    hit = name in (ans_b or "")
    print(f"[会话B] {msg_b!r}\n[answer]\n{ans_b}\n[判定] 答出名字({name}) = {hit}")
    result["d3_cross_session"] = {
        "name": name, "session_a_query": msg_a,
        "memorized": inner_a.get("memorized"), "heads": heads,
        "session_b_query": msg_b, "answer_b": ans_b, "recalled": hit,
    }


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    # 累积式证据文件：多次分步跑（all/1/2/3）合并进同一份 JSON，不互相覆盖
    global result
    try:
        with open(OUT, encoding="utf-8") as f:
            result = json.load(f)
    except Exception:
        result = {}
    token = L.login(STUDENT)
    with open("ta7_token.txt", "w", encoding="utf-8") as f:
        f.write(token)
    uid = int(L.q("SELECT id FROM sys_user WHERE account=%s", (STUDENT,))[0]["id"])
    print(f"[env] user={STUDENT} uid={uid} mode={only}")
    if only in ("all", "1"):
        case1(token)
    if only in ("all", "2"):
        case2(token, uid)
    if only in ("all", "3"):
        case3(token, uid)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[证据] 已写入 {OUT}")


if __name__ == "__main__":
    main()
