# -*- coding: utf-8 -*-
"""task39 GWT① Locust 压测脚本（P95 ≤800ms / LLM P95 ≤8s / 流式首包 ≤3s）。

与旧 ``locustfile.py`` 的关系：
  旧脚本路由已失效（``/api/curriculum/series`` 在课程域重构后改为 ``/api/series``），
  且没有 L1~L3 分档、没有 TTFT 度量、没有缓存命中/未命中分组。本脚本按 task39 GWT①
  重写并保留旧脚本的可读性风格；旧文件不动（交由 task37 死代码清理统一处置）。

三类 User（用 --class-picker 或 tags 选择）：
  1. CachedBrowseUser  课程浏览（命中 Redis 缓存）  → GWT① P95 ≤800ms
  2. ChatUser          L1/L2 非流式问答             → GWT① P95 ≤8s
  3. StreamChatUser    L1/L2 流式问答（度量 TTFT）  → GWT① 首包 ≤3s

自定义指标：
  - TTFT（流式首包）：以独立 request 事件上报，name = "TTFT /api/chat/stream"
  - Redis 命中率：test_start / test_stop 时读 Redis INFO keyspace_hits/misses 差值
  - effort 分布：按查询类型分 name（knowledge=L1 / tool=L2 / learning=L2）

用法（无 UI）：
  .venv\\Scripts\\python -m locust -f tests/performance/locustfile_task39.py \\
      --host=http://127.0.0.1:8000 --headless \\
      --users 50 --spawn-rate 5 --run-time 3m \\
      --html test-reports/task39-locust.html --csv test-reports/task39-locust

  只压缓存链路（不烧 LLM，无需等窗口）：
      --tags cached
  只压 LLM（**必须在 12:00-14:00 / 18:00-09:00 窗口内执行**）：
      --tags chat stream
"""
from __future__ import annotations

import json
import os
import random
import time
import urllib.request

from locust import HttpUser, between, events, tag, task

# ──────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────
_USERS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "_task39_users.json")

# 压测账号（优先读 scripts/_task39_users.json，缺失时回退账号前缀 + 密码）
ACCOUNTS: list[tuple[str, str]] = []
try:
    with open(_USERS_FILE, encoding="utf-8") as _f:
        for _acc, _tok, _uid in json.load(_f):
            ACCOUNTS.append((_acc, "Test1234!"))
except Exception:
    ACCOUNTS = []

if not ACCOUNTS:
    ACCOUNTS = [(f"perf{i}", "Test1234!") for i in range(1, 6)]

# 真实存在的 series_id / cohort_id（启动前从数据库采样，见 on_locust_init）
SERIES_IDS: list[int] = []
COHORT_IDS: list[int] = []

# 预取 token 池：/api/auth/login 限流 10 次/60s（按 IP 维度），而所有 Locust 虚拟用户
# 都从 127.0.0.1 出发 → 用户数 >10 时必然 429，且登录会把 ~4s 的 bcrypt 延迟灌进统计。
# 登录不是本次压测目标，故在 test_start 用独立 HTTP 客户端预取少量 token 共享。
TOKEN_POOL: list[str] = []

# User 类选择：--tags 只过滤 task，不会让「无匹配 task」的 User 类变抽象，
# Locust 仍会实例化并直接报错退出。这里用环境变量显式选择要跑的类。
_SELECTED = {
    s.strip().lower()
    for s in os.environ.get("TASK39_CLASSES", "cached,chat,stream").split(",")
    if s.strip()
}

# L1/L2 分档语料（intent 由 /route 节点 LLM 判定，这里按语义给三类）
_Q_KNOWLEDGE = [          # intent=knowledge → effort L1
    "什么是机器学习？",
    "Python 的装饰器怎么用？",
    "英语现在完成时和过去时的区别是什么？",
    "解释一下什么是向量数据库",
]
_Q_TOOL = [               # intent=tool → effort L2
    "帮我算一下 12345 乘以 6789 等于多少",
    "计算 (158 + 273) * 46 的结果",
    "把 3.14159 保留两位小数是多少",
]
_Q_LEARNING = [           # intent=learning → effort L2
    "给我制定一个 4 周的 Python 学习计划",
    "我想从零学数据分析，应该怎么安排学习路径？",
    "备考信息学竞赛，帮我规划一下学习节奏",
]

_REDIS_URL = os.environ.get("TASK39_REDIS_URL", "redis://127.0.0.1:6379/0")


def _redis_stats() -> tuple[int, int]:
    """读 Redis keyspace_hits / keyspace_misses（失败返回 (-1,-1)）。"""
    try:
        import redis as _redis

        r = _redis.Redis.from_url(_REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        info = r.info("stats")
        return int(info.get("keyspace_hits", 0)), int(info.get("keyspace_misses", 0))
    except Exception:
        return -1, -1


# ──────────────────────────────────────────────────────────────
# Locust 生命周期钩子
# ──────────────────────────────────────────────────────────────
@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    """启动时：探测后端、采样真实 series/cohort id、断言预热已完成。"""
    host = environment.host or "http://127.0.0.1:8000"
    print(f"\n{'='*72}")
    print("  task39 GWT① 性能压测")
    print(f"  目标: {host}")
    print("  场景: 课程浏览(缓存命中) / L1~L2 非流式 / L1~L2 流式(TTFT)")
    print(f"  账号: {len(ACCOUNTS)} 个")
    print(f"{'='*72}")

    def _get(path: str, timeout: int = 20):
        with urllib.request.urlopen(host.rstrip("/") + path, timeout=timeout) as resp:
            return json.load(resp)

    # 1) 预热断言：模型未就绪时首请求会把加载时间算进 P95，压测数据失真
    try:
        w = _get("/health/warmup?wait=60", timeout=70)
        print(f"  预热状态: {w.get('status')}  elapsed={w.get('elapsed_ms')}ms  failed={w.get('failed')}")
        if w.get("status") not in ("ready",):
            print("  ⚠️ 预热未就绪，首请求延迟会计入 P95，数据偏高")
    except Exception as exc:
        print(f"  ⚠️ 预热状态不可读: {exc}")

    # 2) 采样真实 ID（避免全部打在同一个 key 上，也避免 404 污染统计）
    global SERIES_IDS, COHORT_IDS
    try:
        data = _get("/api/series?page=1&page_size=20")
        SERIES_IDS = [int(x["id"]) for x in (data.get("data") or {}).get("items", [])][:20]
    except Exception as exc:
        print(f"  ⚠️ series 采样失败: {exc}")
    for sid in SERIES_IDS[:5]:
        try:
            d = _get(f"/api/series/{sid}/cohorts")
            # R2 分页壳：data.items；兼容旧裸数组形态
            _payload = (d.get("data") or {})
            _items = _payload.get("items") if isinstance(_payload, dict) else _payload
            COHORT_IDS.extend(int(c["id"]) for c in (_items or []))
        except Exception as exc:
            print(f"  ⚠️ cohort 采样失败 series/{sid}: {exc}")
        if len(COHORT_IDS) >= 10:
            break
    COHORT_IDS = COHORT_IDS[:10]
    print(f"  采样: series={SERIES_IDS[:5]}{'...' if len(SERIES_IDS) > 5 else ''} "
          f"cohort={COHORT_IDS[:5]}{'...' if len(COHORT_IDS) > 5 else ''}\n")


@events.test_start.add_listener
def on_test_start(environment, **_kwargs):
    """预取 token 池 + 记录 Redis 基线。"""
    environment.task39_redis_start = _redis_stats()  # type: ignore[attr-defined]

    host = (environment.host or "http://127.0.0.1:8000").rstrip("/")
    for account, password in ACCOUNTS[:8]:  # 不超过登录限流 10/60s
        try:
            req = urllib.request.Request(
                host + "/api/auth/login",
                data=json.dumps({"account": account, "password": password}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                tok = ((json.load(resp) or {}).get("data") or {}).get("access_token", "")
            if tok:
                TOKEN_POOL.append(tok)
        except Exception as exc:
            print(f"  ⚠️ 预取 token 失败 {account}: {exc}")
    print(f"  token 池: {len(TOKEN_POOL)} 个（登录请求不计入压测统计）")
    if not TOKEN_POOL:
        print("  ❌ 无可用 token，压测结果会全是 401/403")


@events.test_stop.add_listener
def on_test_stop(environment, **_kwargs):
    h0, m0 = getattr(environment, "task39_redis_start", (-1, -1))
    h1, m1 = _redis_stats()
    if h0 >= 0 and h1 >= 0:
        dh, dm = h1 - h0, m1 - m0
        total = dh + dm
        rate = (dh / total * 100) if total else 0.0
        print(f"\n  Redis 命中率（压测窗口内）: {rate:.2f}%  "
              f"hits+{dh} / misses+{dm}")
    else:
        print("\n  Redis 命中率: 不可读（未连上 Redis）")


# ──────────────────────────────────────────────────────────────
# 基类：登录 + 通用响应校验
# ──────────────────────────────────────────────────────────────
class _AuthedUser(HttpUser):
    abstract = True
    network_timeout = 60.0
    connection_timeout = 10.0

    def on_start(self):
        # 复用 test_start 预取的 token（登录不是压测目标，避免 429 与 bcrypt 延迟污染统计）
        self.token = random.choice(TOKEN_POOL) if TOKEN_POOL else ""
        self.auth_headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def _ok(self, resp, expect=(200,), label=""):
        if resp.status_code in expect:
            resp.success()
            return True
        if resp.status_code == 429:
            resp.success()  # 被限流属预期行为，不计入失败
            return False
        resp.failure(f"{label} HTTP {resp.status_code}: {resp.text[:200]}")
        return False


# ──────────────────────────────────────────────────────────────
# 1) 课程浏览（缓存命中）—— GWT① P95 ≤800ms
# ──────────────────────────────────────────────────────────────
class CachedBrowseUser(_AuthedUser):
    """课程浏览链路。

    分组依据（实测路由与缓存点）：
      · GET /api/series            → **未缓存**（直连 MySQL，灰度未开）
      · GET /api/series/{id}       → 命中 course:series:detail:{id}（TTL 300）
      · GET /api/cohorts/{id}      → 命中 course:cohort:detail:{id}（TTL 300）
    P95 目标 ≤800ms 针对**命中缓存**的两个详情接口；列表接口单独计名以便对照。
    """

    abstract = "cached" not in _SELECTED
    weight = 3
    wait_time = between(0.5, 2.0)

    @tag("cached", "browse")
    @task(5)
    def series_detail_cached(self):
        """课程详情（命中缓存）— GWT① 主考核项。"""
        if not SERIES_IDS:
            return
        sid = random.choice(SERIES_IDS)
        with self.client.get(
            f"/api/series/{sid}",
            headers=self.auth_headers,
            name="GET /api/series/{id} [cached]",
            catch_response=True,
        ) as resp:
            self._ok(resp, label="series detail")

    @tag("cached", "browse")
    @task(3)
    def cohort_detail_cached(self):
        """班次详情（命中缓存）。"""
        if not COHORT_IDS:
            return
        cid = random.choice(COHORT_IDS)
        with self.client.get(
            f"/api/cohorts/{cid}",
            headers=self.auth_headers,
            name="GET /api/cohorts/{id} [cached]",
            catch_response=True,
        ) as resp:
            self._ok(resp, label="cohort detail")

    @tag("browse")
    @task(2)
    def series_list_uncached(self):
        """课程列表（**未缓存**，对照组：用来量化缓存收益）。"""
        with self.client.get(
            "/api/series?page=1&page_size=10",
            headers=self.auth_headers,
            name="GET /api/series [uncached]",
            catch_response=True,
        ) as resp:
            self._ok(resp, label="series list")


# ──────────────────────────────────────────────────────────────
# 2) 非流式 LLM 问答 —— GWT① P95 ≤8s
# ──────────────────────────────────────────────────────────────
class ChatUser(_AuthedUser):
    """L1/L2 非流式问答。P95 目标 ≤8s（task29 批判② 治理指标）。

    ⚠️ 本类会真实调用 LLM 产生费用，**只在 12:00-14:00 / 18:00-09:00 窗口内执行**。
    """

    abstract = "chat" not in _SELECTED
    weight = 1
    wait_time = between(3, 8)  # LLM 重，放慢节奏避免把压测变成自我 DoS

    @tag("chat", "llm")
    @task(5)
    def chat_knowledge_l1(self):
        """knowledge 意图 → effort L1（2 子代理）。"""
        self._chat(_Q_KNOWLEDGE, "L1-knowledge")

    @tag("chat", "llm")
    @task(3)
    def chat_tool_l2(self):
        """tool 意图 → effort L2（3 子代理）。"""
        self._chat(_Q_TOOL, "L2-tool")

    @tag("chat", "llm")
    @task(2)
    def chat_learning_l2(self):
        """learning 意图 → effort L2（3 子代理，learning 走 strong 模型）。"""
        self._chat(_Q_LEARNING, "L2-learning")

    def _chat(self, pool: list[str], label: str):
        if not self.token:
            return
        with self.client.post(
            "/api/chat",
            json={"query": random.choice(pool), "stream": False, "use_hyde": False},
            headers=self.auth_headers,
            name=f"POST /api/chat [{label}]",
            timeout=60.0,
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json() or {}
                payload = data.get("data") or {}
                deg = payload.get("degraded_reason") or data.get("degraded_reason")
                if deg:
                    # 降级不算失败（容灾目标就是不 500），但计入独立统计便于对照
                    self.environment.events.request.fire(
                        request_type="DEGRADED",
                        name=f"degraded:{label}",
                        response_time=resp.request_meta["response_time"],
                        response_length=0,
                        exception=None,
                        context={},
                    )
                resp.success()
            elif resp.status_code == 429:
                resp.success()
            else:
                resp.failure(f"{label} HTTP {resp.status_code}: {resp.text[:200]}")


# ──────────────────────────────────────────────────────────────
# 3) 流式 LLM 问答 —— GWT① 首包 ≤3s
# ──────────────────────────────────────────────────────────────
class StreamChatUser(_AuthedUser):
    """流式问答：除端到端耗时外，单独度量 TTFT（首包）。

    TTFT 定义：发起请求 → 收到第一个 SSE token 事件的时间。
    用 stream=True 逐块读，遇到首个含 content 的 data 行即停表。
    ⚠️ 同样只在 LLM 窗口内执行。
    """

    abstract = "stream" not in _SELECTED
    weight = 1
    wait_time = between(5, 12)

    @tag("stream", "llm")
    @task(3)
    def stream_knowledge_l1(self):
        self._stream(random.choice(_Q_KNOWLEDGE), "L1-knowledge")

    @tag("stream", "llm")
    @task(2)
    def stream_learning_l2(self):
        self._stream(random.choice(_Q_LEARNING), "L2-learning")

    def _stream(self, query: str, label: str):
        if not self.token:
            return
        t0 = time.perf_counter()
        ttft: float | None = None
        status = 0
        total = 0.0
        try:
            with self.client.post(
                "/api/chat/stream",
                json={"query": query, "stream": True, "use_hyde": False},
                headers=self.auth_headers,
                name=f"POST /api/chat/stream [{label}]",
                timeout=60.0,
                catch_response=True,
                stream=True,
            ) as resp:
                status = resp.status_code
                if status != 200:
                    resp.failure(f"{label} HTTP {status}: {resp.text[:200]}")
                    return
                for chunk in resp.iter_content(chunk_size=256):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if ttft is None and b"token" in chunk:
                        ttft = (time.perf_counter() - t0) * 1000
                resp.success()
        except Exception as exc:  # noqa: BLE001
            self.environment.events.request.fire(
                request_type="POST",
                name=f"POST /api/chat/stream [{label}]",
                response_time=(time.perf_counter() - t0) * 1000,
                response_length=0,
                exception=exc,
                context={},
            )
            return
        finally:
            if ttft is not None:
                # 首包作为独立指标上报（name 以 TTFT 前缀，便于在报告中单独看 P95）
                self.environment.events.request.fire(
                    request_type="TTFT",
                    name=f"TTFT /api/chat/stream [{label}]",
                    response_time=ttft,
                    response_length=int(total),
                    exception=None,
                    context={},
                )
