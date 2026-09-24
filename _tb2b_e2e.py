# -*- coding: utf-8 -*-
"""TB2b 端到端实证探针：student 真实提问 → Jaeger 查分层瀑布 → 截图。

用法：edu-agent/.venv/Scripts/python.exe _tb2b_e2e.py
输出：trace_id、Jaeger 瀑布树、截图路径、证据 JSON。
"""
import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, "edu-agent")

import os

BASE = os.environ.get("TB2B_BASE", "http://127.0.0.1:9988")
JAEGER = os.environ.get("TB2B_JAEGER", "http://127.0.0.1:16686")
_STUDENT = "user000001"
_PWD = "Test@123456"


def _op():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post_json(url, body, headers=None, timeout=180):
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with _op().open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]


def get_json(url, timeout=30):
    try:
        with _op().open(url, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def login(account, password):
    st, body = post_json(f"{BASE}/api/auth/login", {"account": account, "password": password})
    if st != 200:
        raise RuntimeError(f"login failed {st}: {body}")
    return body["data"]["access_token"]


def chat_stream(token, query, session_id=None, timeout=240):
    """发一次真实 SSE 流式提问，返回 (frames, done_data, first_token_ms, total_ms)。"""
    payload = {"query": query, "session_id": session_id, "stream": True}
    req = urllib.request.Request(
        f"{BASE}/api/chat/stream",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    t0 = time.perf_counter()
    events = []
    done_data = None
    first_tok = None
    with _op().open(req, timeout=timeout) as resp:
        cur_event = None
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("event:"):
                cur_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_txt = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(data_txt)
                except Exception:
                    data = data_txt
                events.append(cur_event)
                if cur_event == "token" and first_tok is None:
                    first_tok = int((time.perf_counter() - t0) * 1000)
                if cur_event == "done" and isinstance(data, dict):
                    done_data = data.get("data")
    return events, done_data, first_tok, int((time.perf_counter() - t0) * 1000)


def find_trace(trace_id, retries=8, gap=1.5):
    for _ in range(retries):
        st, body = get_json(f"{JAEGER}/api/traces?service=edu-agent&limit=200&lookback=1h")
        if st == 200:
            for tr in body.get("data", []):
                if tr["traceID"] == trace_id:
                    return tr
        time.sleep(gap)
    return None


def parent_of(s):
    """取父 spanId。

    ⚠️ 实测踩坑（TB2b）：**Jaeger 的 /api/traces 响应里没有 `parentSpanID` 字段**，
    父关系存在 `references[]` 中（`refType=CHILD_OF` 的 `spanID`）。
    早期版本探针读 `s.get("parentSpanID")` 恒为 None → 误判「父子链断裂」，
    实际 Jaeger 存储一直是正确的。两处都读，兼容不同版本。
    """
    for ref in s.get("references") or []:
        if str(ref.get("refType", "")).upper() == "CHILD_OF" and ref.get("spanID"):
            return str(ref["spanID"])
    return s.get("parentSpanID") or ""


def render_tree(tr):
    spans = tr["spans"]
    by = {s["spanID"]: s for s in spans}

    def tags(s):
        return {t["key"]: t["value"] for t in s.get("tags", [])}

    children = {}
    for s in spans:
        pid = parent_of(s)
        if pid and pid in by:
            children.setdefault(pid, []).append(s)

    lines = []

    def walk(s, depth):
        t = tags(s)
        dur = s.get("duration", 0) / 1000.0
        st_code = t.get("otel.status_code", "-")
        lines.append(
            f"{'  ' * depth}- {s['operationName']:22} "
            f"kind={t.get('span.kind', '-'):8} status={st_code:6} dur={dur:8.1f}ms"
            f"  sid={s['spanID'][:8]}"
        )
        for k in ("model", "answer_chars", "retrieved_count", "final_count",
                  "nodes", "tool_count", "degraded_reason"):
            if k in t:
                lines.append(f"{'  ' * depth}    · {k}={str(t[k])[:90]}")
        for c in sorted(children.get(s["spanID"], []), key=lambda x: x["startTime"]):
            walk(c, depth + 1)

    # 多个 root（父不在本 trace 内）时全部渲染，避免静默丢层
    roots = [s for s in spans if not (parent_of(s) in by)]
    roots.sort(key=lambda x: x["startTime"])
    for r in roots:
        walk(r, 0)
    linked = sum(1 for s in spans if parent_of(s) in by)
    lines.append(f"[linkage] spans={len(spans)} linked_children={linked} roots={len(roots)}")
    return lines


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "ok"
    out = {"mode": mode}
    print("== login student ==")
    tok = login(_STUDENT, _PWD)
    print("token len", len(tok))

    if mode == "ok":
        q = "Python 入门课程有哪些核心内容？请简要概括。"
    else:
        # 失败路径：故意指向不可达的上游，制造 llm_call error span
        q = "请简要介绍一下数据结构中的栈。"
    out["query"] = q

    events, done_data, first_tok, total = chat_stream(tok, q)
    print("events:", " ".join(dict.fromkeys(events)))
    print("first_token_ms:", first_tok, "total_ms:", total)
    print("done_data keys:", sorted(done_data.keys()) if isinstance(done_data, dict) else done_data)
    out.update(first_token_ms=first_tok, total_ms=total,
               event_kinds=list(dict.fromkeys(events)))
    out["done_data"] = done_data

    tid = None
    if isinstance(done_data, dict):
        tid = done_data.get("trace_id")
    if not tid:
        # done 帧不带 trace_id → 用会话 id 反查（Jaeger 里 chat.request 的 session_id attr）
        tid = (done_data or {}).get("session_id")
    print("trace/session hint:", tid)
    time.sleep(2)

    # 用时间窗内最新一条含 chat.request 的 trace 作为本次实证对象
    st, body = get_json(f"{JAEGER}/api/traces?service=edu-agent&limit=50&lookback=1h")
    target = None
    newest = 0
    for tr in (body.get("data") or []):
        names = [s["operationName"] for s in tr["spans"]]
        if "chat.request" in names:
            mx = max(s.get("startTime", 0) for s in tr["spans"])
            if mx > newest:
                newest, target = mx, tr
    if target is None:
        print("!! 未在 Jaeger 找到 chat.request trace")
        sys.exit(2)
    print("== Jaeger trace", target["traceID"], f"spans={len(target['spans'])} ==")
    tree = render_tree(target)
    print("\n".join(tree))
    out["trace_id"] = target["traceID"]
    out["span_count"] = len(target["spans"])
    out["tree"] = tree

    with open(f"test-reports/tb2b/e2e_{mode}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("saved -> test-reports/tb2b/e2e_%s.json" % mode)
