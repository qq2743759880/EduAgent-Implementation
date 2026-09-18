# -*- coding: utf-8 -*-
"""R-M1 学习事件流测试（M-1 + M-3，contracts/reshape-r-analytics.json draft）。

覆盖（对齐派单验收 GWT）：
- ① mongo skipif 隔离：真实 mongo 不可达时集成用例整体 skip（单元/故障注入用例照跑）
- ② 旁路写不阻断主链：开关关闭/队列满/写失败/emit 内部异常 全部不向调用方抛错（WARN+计数）
- ③ 故障注入：写失败重试→超限丢弃；连续失败熔断 OPEN → 换正常依赖后半开探针自愈 CLOSED
- ④ 聚合正确性：按 type count/最近活跃/时间窗过滤/total/first_ts+last_ts
- ⑤ 权限：student 查他人 403(40320)、非法 range 400(40030)、mongo 不可达 503(50301)、
  stream-stats student 403（require_role 范式）
- ⑥ 索引契约：uid_ts/type_ts 复合 + ts TTL（TTL 变更 collMod 热更）

mongo 集成用例使用独立测试库 edu_agent_rm1_test（settings.MONGO_DB monkeypatch），
不污染生产库 edu_agent；用例前后 drop 自清理。
"""
from __future__ import annotations

import asyncio
import contextlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.config import settings
from app.domains.analytics import event_stream
from app.domains.analytics.event_stream import (
    COLLECTION, LearningEventWorker, emit_learning_event, reset_event_worker_for_test,
)

# ── 步骤0：mongo 连通性探针（192.168.85.101:27017）──
def _mongo_up() -> bool:
    try:
        import pymongo

        c = pymongo.MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
        c.admin.command("ping")
        c.close()
        return True
    except Exception:
        return False


MONGO_UP = _mongo_up()
mongo_needed = pytest.mark.skipif(not MONGO_UP, reason=f"MongoDB {settings.MONGO_URI} 不可达（skipif 隔离）")

TEST_DB = "edu_agent_rm1_test"


# ══════════════════════════════════════════════════════════════
# ①② 单元：旁路挂点绝不抛错/开关/入队字段
# ══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _fresh_worker():
    reset_event_worker_for_test()
    yield
    reset_event_worker_for_test()


def test_emit_disabled_returns_false(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "MONGO_EVENT_ENABLED", False)
    assert emit_learning_event("quiz_submit", user_id=1) is False


def test_emit_never_raises_on_internal_error(monkeypatch: pytest.MonkeyPatch):
    def _boom():
        raise RuntimeError("worker 构造爆炸（故障注入）")

    monkeypatch.setattr(event_stream, "_get_worker", _boom)
    # 主链语义：返回 False（可观测降级），绝不 raise
    assert emit_learning_event("quiz_submit", user_id=1) is False


def test_emit_queues_doc_with_schema_fields():
    ok = emit_learning_event("video_heartbeat", user_id=7, session_id=99,
                             payload={"rows_inserted": 2, "study_seconds_delta": 60})
    assert ok is True
    w = event_stream._get_worker()
    doc = w._queue.get_nowait()
    assert doc["user_id"] == 7 and doc["type"] == "video_heartbeat" and doc["session_id"] == 99
    assert doc["payload"]["rows_inserted"] == 2
    assert isinstance(doc["ts"], datetime)


def test_emit_queue_full_drops_without_raise(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "MONGO_EVENT_QUEUE_MAXSIZE", 2)
    reset_event_worker_for_test()
    assert emit_learning_event("quiz_submit", user_id=1) is True
    assert emit_learning_event("quiz_submit", user_id=1) is True
    assert emit_learning_event("quiz_submit", user_id=1) is False  # 队列满 → 丢弃计数，主链无感
    w = event_stream._get_worker()
    assert w.stats["dropped_queue_full"] == 1


def test_emit_accepts_none_fields_payload():
    """P0 回归护栏（前任 WIP live 实测炸主链）：mock 题库题 question_id=None 时，
    quiz 挂点实参 `int(q.question_id)` 在主链帧求值 → TypeError → quiz submit 500。
    修复：挂点 payload 必须就地 None 护栏（app/interactive/quiz/service.py）；
    本用例锁「emit 容忍含 None 字段的 payload」语义，防回归。"""
    assert emit_learning_event("quiz_submit", user_id=1,
                               payload={"question_id": None, "score": 0.0}) is True
    doc = event_stream._get_worker()._queue.get_nowait()
    assert doc["payload"]["question_id"] is None and doc["payload"]["score"] == 0.0


# ══════════════════════════════════════════════════════════════
# ②③ 故障注入：写失败重试→丢弃 / 熔断 OPEN→自愈（不依赖真 mongo）
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def broken_collection(monkeypatch: pytest.MonkeyPatch):
    class _BrokenColl:
        def insert_one(self, *_a, **_k):
            raise ConnectionError("mongo 断连（故障注入）")

    monkeypatch.setattr(event_stream, "_get_collection", lambda: _BrokenColl())


async def _run_worker_for(w: LearningEventWorker, seconds: float) -> asyncio.Task:
    t = asyncio.create_task(w.run())
    await asyncio.sleep(seconds)
    return t


async def test_write_failure_retries_then_drops(broken_collection, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "MONGO_EVENT_MAX_RETRY", 2)
    monkeypatch.setattr(settings, "MONGO_EVENT_BREAKER_FAILURES", 99)  # 本用例不触发熔断
    w = event_stream._get_worker()
    assert emit_learning_event("quiz_submit", user_id=1) is True
    t = await _run_worker_for(w, 1.2)
    t.cancel()
    assert w.stats["dropped_over_retry"] == 1      # 超限丢弃
    assert w.stats["written"] == 0
    assert w.stats["retries"] >= 2                  # 重试计数
    assert w.stats["loop_error"] == 0               # worker 自愈存活，未炸循环


async def test_breaker_opens_then_self_heals(broken_collection, monkeypatch: pytest.MonkeyPatch):
    """故障注入③：连续失败 2 次 → OPEN（快速失败期事件保留队列）；依赖恢复后
    半开探针成功 → CLOSED 且积压补写。恢复依赖用内存 fake（确定性，不依赖真 mongo——
    e2e 写路径已由 test_worker_e2e_writes_and_indexes 覆盖）。

    前任 skip 根因已修：_OkColl.insert_one 必须是 async（event_stream._insert 里
    `await coll.insert_one(...)`，sync fake 返回值被 await → TypeError → 永远记失败）。
    """
    from types import SimpleNamespace

    monkeypatch.setattr(settings, "MONGO_EVENT_BREAKER_FAILURES", 2)
    monkeypatch.setattr(settings, "MONGO_EVENT_BREAKER_OPEN_S", 0.3)
    monkeypatch.setattr(settings, "MONGO_EVENT_MAX_RETRY", 50)  # 熔断期事件保留队列不超限丢弃
    w = event_stream._get_worker()

    assert emit_learning_event("quiz_submit", user_id=1) is True
    assert emit_learning_event("quiz_submit", user_id=2) is True
    t = await _run_worker_for(w, 0.8)
    # OPEN 证据：熔断快速失败路径被命中（CircuitOpenError → 事件回队保留）；written 恒 0
    assert w.stats["breaker_open_requeue"] > 0
    assert w.stats["written"] == 0
    written_before = w.stats["written"]

    # 依赖恢复（内存 fake，async insert_one 才能被 await）
    stored: list[dict] = []

    class _OkColl:
        async def insert_one(self, doc):
            stored.append(doc)
            return SimpleNamespace(inserted_id="x")

    monkeypatch.setattr(event_stream, "_get_collection", lambda: _OkColl())

    # > open_duration → check() 转 half_open 放探针 → 成功 → CLOSED → 积压补写
    await asyncio.sleep(1.2)
    t.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await t
    assert w._breaker._state.value == "closed"      # 自愈回 CLOSED
    assert w.stats["written"] > written_before      # 积压事件补写成功
    assert len(stored) == 2                          # 两条事件均落库（零丢失）


# ══════════════════════════════════════════════════════════════
# ①④⑥ mongo 集成：端到端写 + 索引契约 + 聚合正确性（独立测试库）
# ══════════════════════════════════════════════════════════════

@pytest.fixture
async def mongo_test_db(monkeypatch: pytest.MonkeyPatch):
    if not MONGO_UP:
        pytest.skip(f"MongoDB {settings.MONGO_URI} 不可达")
    from app.database import close_mongo, get_mongo_db, init_mongo

    monkeypatch.setattr(settings, "MONGO_DB", TEST_DB)
    await init_mongo()
    db = get_mongo_db()
    await db[COLLECTION].delete_many({})
    yield db
    await db[COLLECTION].delete_many({})
    reset_event_worker_for_test()
    await close_mongo()


async def test_worker_e2e_writes_and_indexes(mongo_test_db, monkeypatch: pytest.MonkeyPatch):
    idx = await event_stream.ensure_indexes(mongo_test_db)
    assert set(idx["indexes"]) >= {"_id_", "uid_ts", "type_ts", "ts_1"}
    info = await mongo_test_db[COLLECTION].index_information()
    assert info["ts_1"].get("expireAfterSeconds") == int(settings.MONGO_EVENT_TTL_DAYS) * 86400
    keys = {name: [k for k, _ in v["key"]] for name, v in info.items()}
    assert keys["uid_ts"] == ["user_id", "ts"] and keys["type_ts"] == ["type", "ts"]

    await event_stream.start_event_worker()
    assert emit_learning_event("video_heartbeat", user_id=1, session_id=5, payload={"rows_inserted": 1})
    assert emit_learning_event("quiz_submit", user_id=1)
    assert emit_learning_event("session_complete", user_id=2, session_id=5, payload={"completed": True})
    for _ in range(50):  # ≤5s 轮询消费完成
        if event_stream._get_worker().stats["written"] >= 3:
            break
        await asyncio.sleep(0.1)
    assert event_stream._get_worker().stats["written"] == 3
    assert await mongo_test_db[COLLECTION].count_documents({}) == 3
    await event_stream.stop_event_worker()


async def test_ttl_collmod_hot_update(mongo_test_db, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "MONGO_EVENT_TTL_DAYS", 1)
    await event_stream.ensure_indexes(mongo_test_db)
    info = await mongo_test_db[COLLECTION].index_information()
    assert info["ts_1"]["expireAfterSeconds"] == 86400  # collMod 热更生效
    monkeypatch.setattr(settings, "MONGO_EVENT_TTL_DAYS", 90)
    await event_stream.ensure_indexes(mongo_test_db)  # 还原 90d（不污染后续用例/真库索引）


async def test_aggregation_correctness(mongo_test_db):
    from app.domains.analytics import service

    coll = mongo_test_db[COLLECTION]
    now = datetime.now()
    docs = [
        {"user_id": 11, "type": "quiz_submit", "payload": {}, "ts": now, "session_id": None},
        {"user_id": 11, "type": "quiz_submit", "payload": {}, "ts": now - timedelta(hours=1), "session_id": None},
        {"user_id": 11, "type": "video_heartbeat", "payload": {"rows_inserted": 3}, "ts": now - timedelta(hours=2), "session_id": 9},
        {"user_id": 11, "type": "quiz_submit", "payload": {}, "ts": now - timedelta(days=40), "session_id": None},  # 7d 窗外
        {"user_id": 22, "type": "quiz_submit", "payload": {}, "ts": now, "session_id": None},  # 他人
    ]
    await coll.insert_many([dict(d) for d in docs])

    r7 = await service.summarize_learning_events(11, "7d")
    assert r7["user_id"] == 11 and r7["range"] == "7d" and r7["total"] == 3
    types = {i["type"]: i for i in r7["by_type"]}
    assert types["quiz_submit"]["count"] == 2
    assert types["video_heartbeat"]["count"] == 1
    assert types["quiz_submit"]["last_active_at"] is not None
    counts = [i["count"] for i in r7["by_type"]]
    assert counts == sorted(counts, reverse=True)   # count 降序（$sort 契约）
    assert r7["last_ts"] is not None and r7["first_ts"] is not None

    r90 = await service.summarize_learning_events(11, "90d")
    assert r90["total"] == 4 and {i["type"]: i["count"] for i in r90["by_type"]}["quiz_submit"] == 3

    empty = await service.summarize_learning_events(99, "1d")
    assert empty["total"] == 0 and empty["by_type"] == [] and empty["first_ts"] is None


# ══════════════════════════════════════════════════════════════
# ⑤ 端点契约（离线 TestClient + 鉴权桩，对齐 test_contract_50301_dependency 范式）
# ══════════════════════════════════════════════════════════════

from fastapi.testclient import TestClient  # noqa: E402

from app.auth import dependencies as auth_deps  # noqa: E402
from app.auth import service as auth_service  # noqa: E402
from app.auth.schemas import UserInfo, UserRole  # noqa: E402
from app.main import app  # noqa: E402


def _headers_for(monkeypatch: pytest.MonkeyPatch, role: UserRole, uid: int) -> dict:
    """离线认证桩（对齐 test_contract_50301_dependency 范式）：真 JWT + 内存用户桩，不触 DB。"""
    token, _ = auth_service.create_access_token(user_id=uid, role=role)

    async def _fake(user_id: int) -> UserInfo:
        return UserInfo(user_id=uid, nickname=f"T{role.value}", real_name="R-M1 测试用户",
                        mobile=None, email=None, gender=None, avatar_url=None, role=role)

    # monkeypatch 管理生命周期（勿直接赋值：会跨用例泄漏全局命名空间）
    monkeypatch.setattr(auth_service, "get_user_info_by_id", _fake)   # service 命名空间
    monkeypatch.setattr(auth_deps, "get_user_info_by_id", _fake)      # dependencies 命名空间（路由依赖用）
    return {"Authorization": f"Bearer {token}"}


class _FakeAgg:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    async def to_list(self, length: int):
        # service 里 `await coll.aggregate(p).to_list(...)`：motor cursor 的 to_list 是协程，
        # fake 必须同为 awaitable（前任 skip 根因：sync to_list 被 await → TypeError）
        return list(self._rows)


class _FakeColl:
    """按 pipeline 第二段 $group._id 区分 by_type / overall 两路聚合。"""

    def __init__(self, by_type_rows: list[dict], overall_rows: list[dict]):
        self._by = by_type_rows
        self._all = overall_rows

    def aggregate(self, pipeline: list[dict]):
        group = next((s for s in pipeline if "$group" in s), {})
        return _FakeAgg(self._all if group["$group"].get("_id") is None else self._by)


@pytest.fixture()
def client():
    return TestClient(app)


async def test_summary_admin_any_user_ok(client, monkeypatch: pytest.MonkeyPatch):
    fake = _FakeColl(
        [{"_id": "quiz_submit", "count": 2, "last_active_at": datetime(2026, 9, 18, 10, 0, 0)}],
        [{"_id": None, "count": 2, "first_ts": datetime(2026, 9, 18, 9, 0, 0),
          "last_ts": datetime(2026, 9, 18, 10, 0, 0)}],
    )
    monkeypatch.setattr("app.domains.analytics.service._get_collection", lambda: fake)
    h = _headers_for(monkeypatch, UserRole.ADMIN, 1)
    resp = client.get("/api/analytics/learning-events/summary?user_id=42&range=30d", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0 and body["message"] == "ok"
    assert body["data"]["user_id"] == 42 and body["data"]["range_days"] == 30
    assert body["data"]["total"] == 2
    assert body["data"]["by_type"][0]["type"] == "quiz_submit"
    assert body["data"]["by_type"][0]["last_active_at"] == "2026-09-18T10:00:00"


def test_summary_student_self_ok_and_other_403(client, monkeypatch: pytest.MonkeyPatch):
    fake = _FakeColl([], [])
    monkeypatch.setattr("app.domains.analytics.service._get_collection", lambda: fake)
    h = _headers_for(monkeypatch, UserRole.STUDENT, 7)
    resp = client.get("/api/analytics/learning-events/summary", headers=h)  # 缺省=本人
    assert resp.status_code == 200 and resp.json()["data"]["user_id"] == 7

    resp = client.get("/api/analytics/learning-events/summary?user_id=999", headers=h)
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "40320"  # ANALYTICS_FORBIDDEN


def test_summary_manager_any_user_ok(client, monkeypatch: pytest.MonkeyPatch):
    fake = _FakeColl([], [])
    monkeypatch.setattr("app.domains.analytics.service._get_collection", lambda: fake)
    h = _headers_for(monkeypatch, UserRole.MANAGER, 3)
    resp = client.get("/api/analytics/learning-events/summary?user_id=55", headers=h)
    assert resp.status_code == 200 and resp.json()["data"]["user_id"] == 55


def test_summary_invalid_range_400(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.domains.analytics.service._get_collection", lambda: _FakeColl([], []))
    h = _headers_for(monkeypatch, UserRole.ADMIN, 1)
    resp = client.get("/api/analytics/learning-events/summary?range=3h", headers=h)
    assert resp.status_code == 400
    assert resp.json()["code"] == "40030"  # ANALYTICS_RANGE_INVALID


def test_summary_mongo_down_50301(client, monkeypatch: pytest.MonkeyPatch):
    def _down():
        raise RuntimeError("mongo 断连（故障注入）")

    monkeypatch.setattr("app.domains.analytics.service._get_collection", _down)
    h = _headers_for(monkeypatch, UserRole.ADMIN, 1)
    resp = client.get("/api/analytics/learning-events/summary", headers=h)
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "50301"            # DEPENDENCY_UNAVAILABLE（脱敏）
    assert body["data"] is None               # data 恒 null
    assert "RuntimeError" not in body["message"]  # 不泄内部细节


def test_stream_stats_admin_ok_student_403(client, monkeypatch: pytest.MonkeyPatch):
    ha = _headers_for(monkeypatch, UserRole.ADMIN, 1)
    resp = client.get("/api/analytics/learning-events/stream-stats", headers=ha)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["collection"] == COLLECTION
    assert {"enabled", "worker_running", "queue_size", "breaker_state", "counters"} <= set(data)

    hs = _headers_for(monkeypatch, UserRole.STUDENT, 8)
    resp = client.get("/api/analytics/learning-events/stream-stats", headers=hs)
    assert resp.status_code == 403            # require_role 范式


def test_summary_anonymous_401_when_debug_off(client, monkeypatch: pytest.MonkeyPatch):
    """匿名 401 契约：仅 DEBUG=False 生效（DEBUG=true 走平台级虚拟管理员后门，
    AGENTS.md 教训6 已登记；live 8000 实例 DEBUG=true 故匿名 200 属已知门禁语义）。
    本用例关 DEBUG 锁生产门禁。"""
    monkeypatch.setattr(settings, "DEBUG", False)
    resp = client.get("/api/analytics/learning-events/summary")
    assert resp.status_code == 401
    assert resp.json()["data"] is None
