# -*- coding: utf-8 -*-
"""B1 契约测试：MCP health-scan 异步化 + 单台健康检查复用 sessions 池。

冻结契约：contracts/reshape-b.json（hash b6772f8d，用户签字①幂等 / 签字②40450）
变更单：.ai-hub/plans/contract-change-reshape-b-health-scan.md（C18 承接）

GWT：
① 异步语义：POST /api/mcp/health-scan-async → 202 {job_id,...}；
   GET /api/mcp/health-scan/{job_id} → {status: running|done, result}，
   done 时 result 与同步端点 MCPHealthScanResp 同构（scanned/ok_count/error_count/items/elapsed_ms）
② 幂等（用户签字①）：同参重复 POST → 同一 job_id（single-flight，running 期收敛）
③ 40450（用户签字②）：未知/过期 job → HTTP 404 + 壳 code="40450"
④ 并发：扫描期间 50 并发 GET 轮询无 500/无排队；同 server 并发健康检查互不干扰
   （池化锁：hc_busy GC 豁免 + 单 stdio pipe 交换串行化）

结构：
- TestJobPolicy / TestHcPoolPolicy：进程内纯逻辑（job 表幂等/GC/TTL、池化锁语义），
  monkeypatch 扫描引擎与池通道，零外部依赖（无后端/无 DB 亦可跑）；
- TestLiveHealthAsync：直连真实后端（TEST_BASE，默认 127.0.0.1:8000，可用 8001 覆盖），
  后端不可达时由 conftest 自动 skip（task37 GWT③ 机制）。

运行：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_mcp_health_async.py -q
    TEST_BASE=http://127.0.0.1:8001 ... （B1 验收打临时实例）
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import time
import types
import urllib.error
import urllib.request

import pytest

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

from app import database as app_database
from app.mcp import executor

BASE = os.environ.get("TEST_BASE", "http://127.0.0.1:8000")

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

ADMIN_ACCOUNT = "adm02test"
PASSWORD = "Test@123456"

_ADMIN_TOKEN: str | None = None


# ============================================================
# 通用 helper（对齐 test_contract_task15.py 口径）
# ============================================================
def api(method: str, path: str, body=None, token=None, timeout: int = 30):
    """发请求并返回 (status, body_json)。"""
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def api_with_headers(method: str, path: str, token=None, timeout: int = 30):
    """返回 (status, headers_dict, body_json)——验 Deprecated 头用。"""
    req = urllib.request.Request(f"{BASE}{path}", data=b"{}", method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers), json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), {}


def login_token() -> str | None:
    global _ADMIN_TOKEN
    if _ADMIN_TOKEN:
        return _ADMIN_TOKEN
    s, j = api("POST", "/api/auth/login", {"account": ADMIN_ACCOUNT, "password": PASSWORD})
    if s != 200:
        return None
    _ADMIN_TOKEN = (j.get("data") or {}).get("access_token")
    return _ADMIN_TOKEN


def assert_ok_shell(j, name: str = ""):
    assert isinstance(j, dict), f"{name}: 非 dict 响应 {j!r}"
    assert j.get("code") == 0, f"{name}: code != 0 → {json.dumps(j, ensure_ascii=False)[:200]}"
    assert "message" in j and "data" in j


# ============================================================
# 进程内纯逻辑：job 表策略（幂等 single-flight / TTL GC / 未知 job）
# ============================================================
@pytest.fixture
def _clean_job_table():
    executor._HC_SCAN_JOBS.clear()
    yield
    executor._HC_SCAN_JOBS.clear()


class TestJobPolicy:
    def test_unknown_job_returns_none(self, _clean_job_table):
        """GWT③（进程内侧）：未知 job → status 函数返回 None（router 层转 404/40450）。"""
        assert asyncio.run(executor.health_scan_job_status("hs-000000000000")) is None

    def test_singleflight_same_job_id(self, _clean_job_table, monkeypatch):
        """GWT②（进程内侧）：running 期并发 POST → 同一 job_id，且只起一个后台任务（用户签字①）。"""

        async def scenario():
            scan_calls = {"n": 0}

            async def fake_scan(progress_cb=None):
                scan_calls["n"] += 1
                await asyncio.sleep(0.4)
                return {"scanned": 3, "ok_count": 2, "error_count": 1,
                        "items": [], "elapsed_ms": 400}

            async def fake_fetch_one(*a, **k):
                return {"c": 3}

            monkeypatch.setattr(executor, "scan_all_servers_health", fake_scan)
            monkeypatch.setattr(app_database, "fetch_one", fake_fetch_one)

            r1, r2 = await asyncio.gather(
                executor.health_scan_async_start(),
                executor.health_scan_async_start(),
            )
            assert r1["job_id"] == r2["job_id"], (
                f"幂等破坏：两次 POST 得到不同 job_id {r1['job_id']} vs {r2['job_id']}")
            assert r1["status"] == "running" and r2["status"] == "running"
            already = [r for r in (r1, r2) if r.get("already_running")]
            assert len(already) >= 1, "并发 POST 应收敛为 1 次创建 + N 次幂等复用"

            # 轮询到 done：result 与扫描引擎返回同构
            snap = None
            for _ in range(120):
                snap = await executor.health_scan_job_status(r1["job_id"])
                assert snap is not None, "running 期 job 不允许被 GC 摘除"
                if snap["status"] == "done":
                    break
                await asyncio.sleep(0.05)
            assert snap is not None and snap["status"] == "done"
            assert snap["result"]["scanned"] == 3 and snap["result"]["elapsed_ms"] > 0
            assert scan_calls["n"] == 1, f"single-flight 破坏：扫描引擎被起了 {scan_calls['n']} 次"
            assert snap["progress"]["total"] == 3   # scanned_total 透传进度分母

            # done 后再 POST → 允许新扫描（幂等窗=running 期），job_id 必然不同
            r3 = await executor.health_scan_async_start()
            assert r3["job_id"] != r1["job_id"]
            assert r3.get("already_running") in (False, None)

        try:
            asyncio.run(scenario())
        finally:
            for j in executor._HC_SCAN_JOBS.values():   # 防 runner 任务泄漏告警
                t = j.get("task")
                if t is not None and not t.done():
                    t.cancel()

    def test_done_job_ttl_expiry_then_gone(self, _clean_job_table):
        """GWT③（进程内侧）：done job 超 10 分钟 TTL → GC 摘除 → 查询返回 None（→40450）。"""
        jid = "hs-ttldeadbeef"
        now_ms = int(time.time() * 1000)
        executor._HC_SCAN_JOBS[jid] = {
            "job_id": jid, "status": "done", "created_ms": now_ms - 11 * 60 * 1000,
            "finished_ms": now_ms - 10 * 60 * 1000 - 1,   # 刚过期
            "scanned_total": 1, "scanned_done": 1, "result": {"scanned": 1},
        }
        snap = asyncio.run(executor.health_scan_job_status(jid))
        assert snap is None, "过期 done job 必须被 GC 摘除（结果不可得 → 40450）"
        assert jid not in executor._HC_SCAN_JOBS

        # 未过期的 done job 必须存活
        jid2 = "hs-ttlalive000"
        executor._HC_SCAN_JOBS[jid2] = {
            "job_id": jid2, "status": "done", "created_ms": now_ms,
            "finished_ms": now_ms - 1000, "scanned_total": 1, "scanned_done": 1,
            "result": {"scanned": 1},
        }
        snap2 = asyncio.run(executor.health_scan_job_status(jid2))
        assert snap2 is not None and snap2["status"] == "done"

    def test_done_job_never_poisons_idempotency(self, _clean_job_table, monkeypatch):
        """runner 异常兜底：扫描引擎抛错也必须落 done 终态，不留永挂 running 的毒 job。"""

        async def scenario():
            async def fake_scan(progress_cb=None):
                raise RuntimeError("boom")

            async def fake_fetch_one(*a, **k):
                return {"c": 0}

            monkeypatch.setattr(executor, "scan_all_servers_health", fake_scan)
            monkeypatch.setattr(app_database, "fetch_one", fake_fetch_one)
            r = await executor.health_scan_async_start()
            for _ in range(100):
                snap = await executor.health_scan_job_status(r["job_id"])
                if snap and snap["status"] == "done":
                    break
                await asyncio.sleep(0.05)
            assert snap is not None and snap["status"] == "done", "异常必须收敛为 done（防幂等被毒化）"

        try:
            asyncio.run(scenario())
        finally:
            for j in executor._HC_SCAN_JOBS.values():
                t = j.get("task")
                if t is not None and not t.done():
                    t.cancel()


# ============================================================
# 进程内纯逻辑：hc 池化会话（GC 豁免 / 同 server 串行交换）
# ============================================================
def _make_fake_pool_session(sid: str, server_id: int = 1, *, hc_busy: bool = False,
                            last_used_ms: int | None = None) -> dict:
    entry = {
        "server": {"id": server_id, "server_code": "fake", "transport": "stdio"},
        "proc": types.SimpleNamespace(returncode=None),   # 活进程替身
        "created_ms": int(time.time() * 1000),
        "last_used_ms": last_used_ms if last_used_ms is not None else int(time.time() * 1000),
        "ttl_s": 600, "call_count": 0, "id_counter": 100,
        "last_error": None, "hc": True, "hc_busy": hc_busy,
    }
    executor._SESSION_POOL[sid] = entry
    return entry


@pytest.fixture
def _clean_hc_pool():
    saved_pool = dict(executor._SESSION_POOL)
    saved_reg = dict(executor._HC_SESSION_BY_SERVER)
    executor._SESSION_POOL.clear()
    executor._HC_SESSION_BY_SERVER.clear()
    yield
    executor._SESSION_POOL.clear()
    executor._SESSION_POOL.update(saved_pool)
    executor._HC_SESSION_BY_SERVER.clear()
    executor._HC_SESSION_BY_SERVER.update(saved_reg)


class TestHcPoolPolicy:
    def test_gc_spares_busy_hc_session(self, _clean_hc_pool):
        """GWT④（池化锁口径）：交换中（hc_busy）的 hc 会话对 GC 豁免；空闲后照常回收。"""
        sid = "ms-hcbusyfake"
        old_ms = int(time.time() * 1000) - 3600 * 1000   # 远超 TTL，本应被回收
        _make_fake_pool_session(sid, hc_busy=True, last_used_ms=old_ms)

        removed = asyncio.run(executor.session_pool_gc(force_all=False))
        assert sid in executor._SESSION_POOL, "在检（hc_busy）会话必须被 GC 豁免（防竞争误杀）"

        executor._SESSION_POOL[sid]["hc_busy"] = False   # 交换结束
        asyncio.run(executor.session_pool_gc(force_all=False))
        assert sid not in executor._SESSION_POOL, "空闲 hc 会话应照常被 TTL 回收"

    def test_concurrent_ping_on_same_server_serialized(self, _clean_hc_pool, monkeypatch):
        """GWT④（互不干扰）：同 server 并发健康检查 → 单条 stdio pipe 交换串行（max 并发=1），结论互不污染。"""
        active = {"n": 0, "max": 0}

        async def fake_exchange(session_id, requests, timeout_s):
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
            await asyncio.sleep(0.03)
            active["n"] -= 1
            return [{"jsonrpc": "2.0", "id": 101, "result": {}}]

        monkeypatch.setattr(executor, "_stdio_exchange_via_session", fake_exchange)

        async def scenario():
            server = {"id": 1, "server_code": "fake", "transport": "stdio",
                      "connect_timeout_ms": 5000, "call_timeout_ms": 30000}
            _make_fake_pool_session("ms-fakehc01", server_id=1)
            executor._HC_SESSION_BY_SERVER[1] = "ms-fakehc01"
            # 同 server 8 路并发健康检查
            outs = await asyncio.gather(*[
                executor._stdio_health_via_pool(server, 5.0) for _ in range(8)
            ])
            return outs

        outs = asyncio.run(scenario())
        assert active["max"] == 1, f"同 server 交换必须串行，实测最大并发={active['max']}"
        for ok, reason, concluded in outs:
            assert concluded is True and ok is True, f"并发检查互不干扰破坏：{ok} {reason}"

    def test_pool_failure_falls_back_not_false_negative(self, _clean_hc_pool, monkeypatch):
        """池通道故障（会话僵死）→ 弃会话并回退一次性路径（concluded=False），绝不误报不健康。"""

        async def dead_exchange(session_id, requests, timeout_s):
            raise RuntimeError("session_id=ms-x 子进程已退出")

        monkeypatch.setattr(executor, "_stdio_exchange_via_session", dead_exchange)

        async def scenario():
            server = {"id": 2, "server_code": "fake2", "transport": "stdio",
                      "connect_timeout_ms": 5000, "call_timeout_ms": 30000}
            _make_fake_pool_session("ms-fakehc02", server_id=2)
            executor._HC_SESSION_BY_SERVER[2] = "ms-fakehc02"
            return await executor._stdio_health_via_pool(server, 5.0)

        ok, reason, concluded = asyncio.run(scenario())
        assert concluded is False, "池故障应回退一次性路径（concluded=False），不是不健康结论"
        assert 2 not in executor._HC_SESSION_BY_SERVER, "坏会话必须摘注册表，下次重建"


# ============================================================
# Live 契约（真实后端；不可达时 conftest 自动 skip）
# ============================================================
@pytest.mark.live_backend
class TestLiveHealthAsync:
    def test_01_post_202_shell_job_id(self):
        """GWT①：POST /health-scan-async → HTTP 202 + 壳 {code:0,data:{job_id: hs-*}}。"""
        tok = login_token()
        assert tok, "admin 登录失败"
        s, j = api("POST", "/api/mcp/health-scan-async", token=tok)
        assert s == 202, f"应为 202 Accepted，实测 {s}"
        assert_ok_shell(j, "health-scan-async")
        data = j["data"]
        assert isinstance(data.get("job_id"), str) and data["job_id"].startswith("hs-")
        assert data.get("status") == "running"
        assert isinstance(data.get("created_ms"), int)
        assert isinstance(data.get("scanned_total"), int) and data["scanned_total"] >= 0

    def test_02_idempotent_same_job_id(self):
        """GWT②（live）：并发重复 POST → 同一 job_id（用户签字①）。"""
        tok = login_token()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            f1 = ex.submit(api, "POST", "/api/mcp/health-scan-async", None, tok)
            f2 = ex.submit(api, "POST", "/api/mcp/health-scan-async", None, tok)
            s1, j1 = f1.result()
            s2, j2 = f2.result()
        assert s1 == 202 and s2 == 202
        id1, id2 = j1["data"]["job_id"], j2["data"]["job_id"]
        assert id1 == id2, f"幂等破坏：并发 POST 得到不同 job_id（{id1} vs {id2}）"
        # 收敛性：至少一路是 already_running（或两路都复用既有 running job）
        msgs = {j1.get("message"), j2.get("message")}
        assert msgs <= {"accepted", "already_running"}, f"message 异常：{msgs}"

    def test_03_poll_to_done_result_schema(self):
        """GWT①（live）：running → done；done.result 与同步端点 MCPHealthScanResp 同构。"""
        tok = login_token()
        s, j = api("POST", "/api/mcp/health-scan-async", token=tok)
        assert s == 202
        job_id = j["data"]["job_id"]
        scanned_total = j["data"]["scanned_total"]
        snap = None
        deadline = time.time() + 180
        first = True
        while time.time() < deadline:
            s2, j2 = api("GET", f"/api/mcp/health-scan/{job_id}", token=tok)
            assert s2 == 200, f"轮询期不允许非 200：{s2} {j2}"
            assert_ok_shell(j2, "poll")
            snap = j2["data"]
            assert snap["status"] in ("running", "done")
            if snap["status"] == "running":
                assert snap["result"] is None, "running 期 result 必须为 null"
                if first:
                    assert snap["job_id"] == job_id and "progress" in snap
                    first = False
            else:
                break
            time.sleep(0.5)
        assert snap is not None and snap["status"] == "done", "180s 内未到 done"
        result = snap["result"]
        assert result is not None
        for key in ("scanned", "ok_count", "error_count", "items", "elapsed_ms"):
            assert key in result, f"result 缺字段 {key}（须与 MCPHealthScanResp 同构）"
        assert result["ok_count"] + result["error_count"] == result["scanned"]
        assert len(result["items"]) == result["scanned"]
        assert result["elapsed_ms"] > 0
        if scanned_total > 0:
            assert result["scanned"] == scanned_total, "扫描数应与提交时分母一致（yn=1 全量）"
        item = result["items"][0]
        for key in ("server_id", "server_code", "display_name", "ok", "latency_ms"):
            assert key in item, f"item 缺字段 {key}"

    def test_04_unknown_job_40450(self):
        """GWT③（live）：未知 job → HTTP 404 + 壳 code="40450"（用户签字②）。"""
        tok = login_token()
        s, j = api("GET", "/api/mcp/health-scan/hs-000000000000", token=tok)
        assert s == 404, f"未知 job 应 404，实测 {s}"
        assert j.get("code") == "40450", f'code 应为字符串 "40450"，实测 {j.get("code")!r}'
        assert j.get("data") is None

    def test_05_50_concurrent_polls_no_500_no_queue(self):
        """GWT④（live）：扫描期间 50 并发 GET 轮询 → 全 200/壳 code=0/无排队（max<2s）。"""
        tok = login_token()
        s, j = api("POST", "/api/mcp/health-scan-async", token=tok)
        assert s == 202
        job_id = j["data"]["job_id"]

        def poll(_):
            t0 = time.perf_counter()
            st, body = api("GET", f"/api/mcp/health-scan/{job_id}", token=tok, timeout=15)
            return st, body, (time.perf_counter() - t0) * 1000

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
            futures = [ex.submit(poll, i) for i in range(50)]
            results = [f.result() for f in futures]
        lat = sorted(r[2] for r in results)
        bad = [r for r in results if r[0] != 200 or r[1].get("code") != 0]
        assert not bad, f"50 并发轮询出现异常响应：{bad[:3]}"
        p95 = lat[int(len(lat) * 0.95) - 1]
        assert lat[-1] < 2000, f"轮询 P100={lat[-1]:.0f}ms 超 2s（疑似排队）"
        statuses = {r[1]["data"]["status"] for r in results}
        assert statuses <= {"running", "done"}
        print(f"\n[50-concurrent-polls] min={lat[0]:.0f}ms p50={lat[25]:.0f}ms "
              f"p95={p95:.0f}ms max={lat[-1]:.0f}ms statuses={statuses}")

    def test_06_concurrent_single_health_no_interference(self):
        """GWT④（live）：同 server 并发单台健康检查互不干扰——全 200/ok 恒真/server_id 无串扰。"""
        tok = login_token()
        # 前置：stdio-echodemo(id=1) 必须 ok:true（派单前置实证同款断言）
        s0, j0 = api("POST", "/api/mcp/servers/1/health", token=tok)
        assert s0 == 200 and j0["data"]["ok"] is True, f"前置失败：id=1 不健康 {j0}"

        def health(sid):
            t0 = time.perf_counter()
            st, body = api("POST", f"/api/mcp/servers/{sid}/health", token=tok, timeout=30)
            return st, body, (time.perf_counter() - t0) * 1000

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
            futs = [ex.submit(health, 1) for _ in range(10)]
            futs.append(ex.submit(health, 6))   # 混入另一台（sse），验证结果按 server 隔离
            futs.append(ex.submit(health, 6))
            outs = [f.result() for f in futs]
        id1_outs = outs[:10]
        for st, body, wall_ms in id1_outs:
            assert st == 200, f"id=1 并发检查出现 HTTP {st}"
            assert body["code"] == 0, f"id=1 并发检查壳异常：{body}"
            assert body["data"]["server_id"] == 1, "server_id 串扰！"
            assert body["data"]["ok"] is True, (
                f"健康 server 在并发检查下被误报不健康：{body['data']}")
        for st, body, _ in outs[10:]:
            assert st == 200 and body["data"]["server_id"] == 6, "混入检查结果串扰"
        print("\n[10x-concurrent-health id=1] walls=" +
              ",".join(f"{w:.0f}ms" for _, _, w in id1_outs))

        # 池复用证据：/sessions 出现 server_id=1 的 hc 专用会话
        s3, j3 = api("GET", "/api/mcp/sessions", token=tok)
        assert s3 == 200 and j3["code"] == 0
        items = j3["data"]["items"]
        hc_items = [x for x in items if x.get("hc") and x.get("server_id") == 1]
        assert hc_items, f"未发现 server 1 的 hc 专用池会话（池复用未生效）：{items}"

    def test_07_legacy_sync_scan_compat_window(self):
        """兼容窗（contracts/reshape-b.json）：旧同步端点保留且行为不变 + Deprecated 头。"""
        tok = login_token()
        s, headers, j = api_with_headers("POST", "/api/mcp/health-scan", token=tok, timeout=180)
        assert s == 200, f"旧同步端点应保留 200，实测 {s}"
        assert_ok_shell(j, "legacy health-scan")
        for key in ("scanned", "ok_count", "error_count", "items", "elapsed_ms"):
            assert key in j["data"], f"旧端点响应缺字段 {key}"
        assert str(headers.get("Deprecation", headers.get("deprecation", ""))).lower() == "true", \
            f"应带 Deprecation 头，实测 {headers!r}"
