# -*- coding: utf-8 -*-
"""ARKBAT Stage A: thinking compat + perf baseline + concurrency probe (model-level, direct API).

SSRF guard: https-only + host allowlist (ark.cn-beijing.volces.com) + resolved-IP must be
public (no loopback/private/link-local/metadata) — checked before every request.
"""
from __future__ import annotations
import io, json, os, socket, sys, time, statistics, concurrent.futures as cf
import urllib.request, urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ALLOWED_HOST = "ark.cn-beijing.volces.com"


def guard_url(url: str) -> str:
    from urllib.parse import urlparse
    p = urlparse(url)
    if p.scheme != "https" or p.hostname != ALLOWED_HOST:
        raise ValueError("blocked: host not in allowlist")
    infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    for info in infos:
        ip = info[4][0]
        if ip.startswith(("127.", "10.", "192.168.", "169.254.", "0.")) or ip == "::1" or ip.startswith("fc") or ip.startswith("fd"):
            raise ValueError("blocked: resolved private/loopback ip " + ip)
        if ip.startswith("172.") and 16 <= int(ip.split(".")[1]) <= 31:
            raise ValueError("blocked: resolved private ip " + ip)
    return url


BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env = {}
for line in io.open(os.path.join(BASE, "edu-agent", ".env"), encoding="utf-8", errors="ignore"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

URL = guard_url((env.get("LLM_FAST_BASE_URL") or "").rstrip("/") + "/chat/completions")
KEY = env.get("LLM_FAST_API_KEY") or ""
MODEL = env.get("LLM_MODEL_FAST") or "ark-code-latest"
OUT_DIR = os.path.join(BASE, "edu-agent", "data", "ark_battery")
os.makedirs(OUT_DIR, exist_ok=True)


def call(content, max_tokens=64, stream=False, timeout=60, thinking_off=False, temperature=0.0):
    body = {"model": MODEL, "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens, "temperature": temperature, "stream": stream}
    if thinking_off:
        body["thinking"] = {"type": "disabled"}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(URL, data=data, headers={
        "Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        if stream:
            first = None
            n_chunks = 0
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "ignore").strip()
                    if line.startswith("data:") and "[DONE]" not in line:
                        n_chunks += 1
                        if first is None:
                            first = time.perf_counter() - t0
            return {"ok": True, "ttft": first, "total": time.perf_counter() - t0, "chunks": n_chunks}
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read().decode("utf-8", "ignore"))
        m = (d.get("choices") or [{}])[0].get("message", {})
        u = d.get("usage", {})
        return {"ok": True, "total": time.perf_counter() - t0,
                "reasoning": bool(m.get("reasoning_content")),
                "completion": u.get("completion_tokens")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "err": e.read().decode("utf-8", "ignore")[:120]}
    except Exception as e:
        return {"ok": False, "err": str(e)[:120]}


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(int(p * len(xs)), len(xs) - 1)] if xs else None


def err_codes(cres):
    from collections import Counter
    return dict(Counter(str(r.get("status")) for r in cres if not r["ok"]))


res = {"model": MODEL, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

a_on = [call("hi", max_tokens=32) for _ in range(3)]
a_off = [call("hi", max_tokens=32, thinking_off=True) for _ in range(3)]
res["thinking_on"] = [{"ok": r["ok"], "reasoning": r.get("reasoning"), "t": round(r.get("total", 0), 2)} for r in a_on]
res["thinking_off"] = [{"ok": r["ok"], "reasoning": r.get("reasoning"), "t": round(r.get("total", 0), 2)} for r in a_off]
res["thinking_disable_supported"] = all(r["ok"] and not r.get("reasoning") for r in a_off)

use_off = res["thinking_disable_supported"]
lat, fails = [], 0
for i in range(30):
    r = call("Use one short sentence to explain recursion.", max_tokens=120, thinking_off=use_off)
    if r["ok"]:
        lat.append(r["total"])
    else:
        fails += 1
res["nonstream30"] = {"n": len(lat), "fails": fails,
                      "p50": round(pct(lat, .5), 3) if lat else None,
                      "p95": round(pct(lat, .95), 3) if lat else None,
                      "mean": round(statistics.mean(lat), 3) if lat else None}

tt, sf = [], 0
for i in range(10):
    r = call("Count from 1 to 20.", max_tokens=120, stream=True, thinking_off=use_off)
    if r.get("ok") and r.get("ttft"):
        tt.append(r["ttft"])
    elif not r.get("ok"):
        sf += 1
res["stream10"] = {"n": len(tt), "fails": sf,
                   "ttft_p50": round(pct(tt, .5), 3) if tt else None,
                   "ttft_p95": round(pct(tt, .95), 3) if tt else None}

t0 = time.perf_counter()
with cf.ThreadPoolExecutor(20) as ex:
    cres = list(ex.map(lambda _: call("ping", max_tokens=8, thinking_off=True), range(20)))
res["concurrent20"] = {"ok": sum(1 for r in cres if r["ok"]),
                       "fail": sum(1 for r in cres if not r["ok"]),
                       "wall": round(time.perf_counter() - t0, 2),
                       "err_codes": err_codes(cres)}

path = os.path.join(OUT_DIR, "arkbat_stage_a.json")
with io.open(path, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print(json.dumps({k: res[k] for k in ["thinking_disable_supported", "nonstream30", "stream10", "concurrent20"]},
                 ensure_ascii=False, indent=2))
print("artifact:", path)
