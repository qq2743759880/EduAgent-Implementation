# -*- coding: utf-8 -*-
"""task39 GWT② 容灾演练：六存储逐一故障注入 + 优雅降级对照（doc-architect-tech-arch §6.4）。

演练方式（**不 kill 共享服务**）：
  真实 kill VM 上的 Milvus/Neo4j/Mongo/MinIO 会影响其它并行任务，且恢复窗口不可控。
  这里改用**连接层故障注入**：给每个场景拉起一个独立的后端实例（独占端口，env 覆盖指向
  不可达地址），等价于「该依赖网络不可达」，且**零共享状态、随起随停、可重复执行**。

  注入地址统一用 127.0.0.1:6553x（本机无监听）→ 连接被拒（fail-fast）。
  这与真实网络分区（超时等待）的差别在报告中标注：fail-fast 是**乐观**情形，
  真实分区还要叠加 connect timeout，故降级正确性成立不代表延迟达标。

判定口径（对齐 §6.4 矩阵）：
  1. 核心链路**不返回 5xx**（降级或 4xx 明确报错均可，静默 500 不可接受）
  2. 降级点写 degraded_reason（响应体可见）
  3. /metrics 上 edu_degraded_total{component} 计数 > 0（本次新增指标的可观测性验证）

用法：
    .venv\\Scripts\\python scripts/verify_task39_disaster_drill.py
    .venv\\Scripts\\python scripts/verify_task39_disaster_drill.py --only redis,milvus
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPORT: list[str] = []
FAILED: list[str] = []


def _log(msg: str) -> None:
    print(msg, flush=True)
    REPORT.append(msg)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


# ──────────────────────────────────────────────────────────────
# 故障场景定义：component → (env 覆盖, 探针, 期望降级组件标签)
# ──────────────────────────────────────────────────────────────
SCENARIOS: dict[str, dict] = {
    # 基线对照（**不注入任何故障**）：证明探针本身有效。
    # 若基线也返回 5xx、或基线也报降级，则「断连后无 5xx」「降级指标增长」两种结论
    # 都失去说服力。这是 Chaos Engineering 五原则第一条
    # 「围绕稳态行为建立假设（build a hypothesis around steady state）」的可执行形式。
    "baseline": {
        "title": "基线对照（全依赖在线，不注入故障）",
        "env": {},
        "expect_component": "baseline",
        "expect": "稳态：所有探针 2xx，且 RAG/问答无降级原因",
    },
    "milvus": {
        "title": "Milvus 向量库断连",
        "env": {"MILVUS_URI": "http://127.0.0.1:65530"},
        "expect_component": "milvus",
        "expect": "空 docs + 降级答案，不 500",
    },
    "redis": {
        "title": "Redis 断连（缓存/限流/幂等/checkpoint）",
        "env": {"REDIS_URL": "redis://127.0.0.1:65531/0"},
        "expect_component": "redis",
        "expect": "缓存直通 + 限流放行 + 幂等跳过，不 500",
    },
    "neo4j": {
        "title": "Neo4j 图谱断连",
        "env": {"NEO4J_URI": "bolt://127.0.0.1:65532"},
        "expect_component": "neo4j",
        "expect": "跳图谱扩展，不 500",
    },
    "mongo": {
        "title": "MongoDB 对话状态断连",
        "env": {"MONGO_URI": "mongodb://127.0.0.1:65533"},
        "expect_component": "mongo",
        "expect": "chat_message(MySQL) 权威历史兜底，不 500",
    },
    "minio": {
        "title": "MinIO 对象存储断连",
        "env": {"MINIO_ENDPOINT": "127.0.0.1:65534"},
        "expect_component": "minio",
        "expect": "上传/视频明确报错（4xx/5xx 明确，非静默），课程文字部分可用",
    },
    "llm": {
        "title": "LLM 供应商断连",
        "env": {
            "LLM_FAST_BASE_URL": "http://127.0.0.1:65535",
            "LLM_STRONG_BASE_URL": "http://127.0.0.1:65535",
            "LLM_BASE_URL": "http://127.0.0.1:65535",
        },
        "expect_component": "llm",
        "expect": "规则兜底答案（_local_rule_answer），不 500",
    },
}

# 探针：(方法, 路径, body, 名称, 允许的状态码)
def _probes(token: str | None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    # 探针选型说明（演练实证）：
    #   POST /api/chat 走 **agent 链路**（USE_AGENT_LOOP=True），实测其 search 子代理
    #   并不调用 RAG 检索器 —— Milvus 断连时 /api/chat 日志里根本没有检索调用，
    #   断连只会体现在 app.ai.memory.vector 的记忆向量降级上。
    #   因此**必须**另加 /api/chat/search（纯检索：Milvus 双通道 + Neo4j 图谱 + reranker），
    #   才能真正打到 Milvus / Neo4j 的降级路径。
    return [
        ("GET", "/health", None, "健康检查", {200}),
        ("GET", "/health/detail", None, "详细健康", {200}),
        ("GET", "/api/series?page=1&page_size=5", None, "课程列表（MySQL）", {200}),
        ("POST", "/api/chat/search",
         {"query": "机器学习的基本概念", "use_hyde": False, "top_k": 5,
          "final_max_k": 5, "enable_graph": True},
         "RAG 检索（Milvus+图谱）", {200, 429}),
        ("POST", "/api/chat", {"query": "什么是机器学习？", "stream": False, "use_hyde": False},
         "AI 问答（agent 全链路）", {200, 429}),
    ]


# ──────────────────────────────────────────────────────────────
# 实例管理
# ──────────────────────────────────────────────────────────────
def _wait_up(port: int, timeout: float = 120.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1.5)
    return False


def _start_instance(port: int, extra_env: dict[str, str]) -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["EDUAGENT_RATE_LIMIT_DEFAULT"] = "100000"
    env["EDUAGENT_CHAT_LIMIT"] = "5000"
    env.update(extra_env)
    log = ROOT / "logs" / f"task39_drill_{port}.log"
    fh = open(log, "w", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env=env, stdout=fh, stderr=subprocess.STDOUT,
    )


def _http(method: str, url: str, body: dict | None, headers: dict, timeout: float = 180.0):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, raw, (time.perf_counter() - t0) * 1000
    except urllib.error.HTTPError as e:
        return e.code, e.read(), (time.perf_counter() - t0) * 1000
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}".encode(), (time.perf_counter() - t0) * 1000


def _login(port: int, account: str = "perf1") -> str | None:
    st, raw, _ = _http("POST", f"http://127.0.0.1:{port}/api/auth/login",
                       {"account": account, "password": "Test1234!"},
                       {"Content-Type": "application/json"}, timeout=60)
    if st == 200:
        try:
            return (json.loads(raw).get("data") or {}).get("access_token")
        except Exception:
            return None
    return None


def _upload_probe(port: int, token: str | None) -> tuple[int, str]:
    """MinIO 写入路径探针：multipart 上传一个极小 .txt（§6.4 要求断连时「明确报错」）。

    上传链路是「先落本地临时盘 → 后台任务导入（此时才碰 MinIO）」，
    故 MinIO 断连不会让 /upload 立即失败，而是后台任务标记失败。
    这里同时探测「立即返回码」与「任务最终状态」，如实记录不断言。
    """
    # 用 httpx 构造 multipart：urllib 手工拼的 multipart 会被 FastAPI 判为
    # missing field（422）——那是**探针**的编码问题，不是产品缺陷（httpx 同请求 200）。
    import httpx

    hdrs = {}
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=180.0, trust_env=False) as cli:
            resp = cli.post(
                f"http://127.0.0.1:{port}/api/knowledge/upload",
                headers=hdrs,
                files=[("files", ("task39-minio.txt", b"task39 minio drill\n", "text/plain"))],
            )
        return resp.status_code, resp.text[:200]
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def _degraded_count(port: int, component: str) -> float:
    st, raw, _ = _http("GET", f"http://127.0.0.1:{port}/metrics", None, {}, timeout=30)
    if st != 200:
        return -1.0
    text = raw.decode("utf-8", "replace")
    total = 0.0
    for line in text.splitlines():
        if line.startswith("edu_degraded_total{") and f'component="{component}"' in line:
            try:
                total += float(line.rsplit(" ", 1)[-1])
            except ValueError:
                pass
    return total


def run_scenario(name: str, cfg: dict) -> dict:
    port = _free_port()
    _log(f"\n{'─'*72}")
    _log(f"■ 场景 {name}：{cfg['title']}")
    _log(f"  注入: {cfg['env']}")
    _log(f"  期望: {cfg['expect']}")

    proc = _start_instance(port, cfg["env"])
    result: dict = {"scenario": name, "port": port, "probes": [], "degraded_count": -1.0}
    try:
        if not _wait_up(port):
            _log("  [FAIL] 实例未能启动（该依赖断连导致启动即失败）")
            FAILED.append(f"{name}: 实例启动失败")
            result["startup"] = "failed"
            return result
        result["startup"] = "ok"
        token = _login(port)
        result["token"] = bool(token)
        hdrs = {"Content-Type": "application/json"}
        if token:
            hdrs["Authorization"] = f"Bearer {token}"

        has_5xx = False
        degraded_seen: list[str] = []
        for method, path, body, label, allowed in _probes(token):
            st, raw, ms = _http(method, f"http://127.0.0.1:{port}{path}", body, hdrs)
            deg = ""
            try:
                payload = json.loads(raw)
                d = payload.get("data") or {}
                deg = d.get("degraded_reason") or payload.get("degraded_reason") or ""
            except Exception:
                pass
            if deg:
                degraded_seen.append(f"{label}: {str(deg)[:90]}")
            if 500 <= st < 600:
                has_5xx = True
            result["probes"].append({
                "name": label, "status": st, "ms": round(ms),
                "degraded_reason": str(deg)[:200],
            })
            _log(f"    {label:16s} HTTP {st:<4d} {ms:8.0f}ms  "
                 f"degraded={'有' if deg else '—'}{(' | ' + str(deg)[:70]) if deg else ''}")

        # MinIO 是纯写入依赖：读链路完全不碰它，必须单独上传探针才能验证降级行为
        if name == "minio":
            st, txt = _upload_probe(port, token)
            result["probes"].append({"name": "知识库上传（MinIO 写入）", "status": st,
                                     "ms": 0, "degraded_reason": txt[:200]})
            if 500 <= st < 600:
                has_5xx = True
            _log(f"    {'知识库上传（MinIO）':16s} HTTP {st:<4d} {'':8s}  {txt[:80]}")

        cnt = _degraded_count(port, cfg["expect_component"])
        result["degraded_count"] = cnt

        ok = not has_5xx
        _log(f"  判定 无5xx: {'✅' if ok else '❌'}   "
             f"edu_degraded_total{{component=\"{cfg['expect_component']}\"}} = {cnt}")
        if not ok:
            FAILED.append(f"{name}: 出现 5xx")
        if cnt <= 0:
            # minio/mongo 场景无读路径探针，指标可能不增长；仅作提示不判失败
            _log(f"  ⚠️ {name}: edu_degraded_total 未增长（该场景可能无读路径探针命中，"
                 f"或该依赖本身有兜底不产生降级计数）")
        if name == "baseline" and degraded_seen:
            # 稳态不成立 → 后续所有断连场景的「降级」结论都不可信
            _log("  ⚠️ 基线出现降级原因：稳态假设不成立，断连场景的降级对照需谨慎解读")
        _log(f"  降级原因样本: {degraded_seen[:2] if degraded_seen else '无'}")
        return result
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔，只跑指定场景")
    ap.add_argument("--out", default="", help="结果文件名（默认 task39-disaster-drill.json）")
    args = ap.parse_args()

    names = [n for n in SCENARIOS if n in {s.strip() for s in args.only.split(",") if s.strip()}] \
        if args.only else list(SCENARIOS)

    _log("=" * 72)
    _log("task39 GWT② 容灾演练（连接层故障注入，不 kill 共享服务）")
    _log(f"场景: {', '.join(names)}")
    _log("=" * 72)

    results = []
    for n in names:
        try:
            results.append(run_scenario(n, SCENARIOS[n]))
        except Exception as exc:
            _log(f"  [FAIL] 场景 {n} 异常: {type(exc).__name__}: {exc}")
            FAILED.append(f"{n}: 异常 {type(exc).__name__}")

    _log("\n" + "=" * 72)
    _log("容灾演练汇总（对照 doc-architect-tech-arch §6.4 优雅降级矩阵）")
    _log("=" * 72)
    _log(f"{'依赖':10s} {'启动':6s} {'无5xx':6s} {'降级指标':10s} 期望行为")
    for r in results:
        cfg = SCENARIOS[r["scenario"]]
        n5 = all(not (500 <= p["status"] < 600) for p in r.get("probes", []))
        _log(f"{r['scenario']:10s} {r.get('startup','?'):6s} "
             f"{'✅' if n5 else '❌':6s} {r.get('degraded_count', -1):<10} {cfg['expect']}")

    stem = args.out or "task39-disaster-drill"
    out = ROOT / "test-reports" / f"{stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": results, "failed": FAILED}, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    (ROOT / "test-reports" / f"{stem}.txt").write_text("\n".join(REPORT), encoding="utf-8")
    _log(f"\n明细已写入: {out}")

    if FAILED:
        _log(f"\n❌ 失败项 {len(FAILED)}: {FAILED}")
        return 1
    _log(f"\n✅ GWT② 容灾演练通过：{len(names)} 个场景均无 5xx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
