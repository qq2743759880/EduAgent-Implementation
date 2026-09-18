# -*- coding: utf-8 -*-
"""H-2 加固契约测试：checkpoint pickle 快照 HMAC 签名（Mimosa 审计登记② HIGH）。

背景：PlainRedisSaver 把线程快照 pickle 后直写 Redis、读时 pickle.loads 直反序列化
——Redis 被写入即等于 RCE。加固（签名最小方案）：
  写：pickle payload → HMAC-SHA256 信封 {"v":1,"hmac":hex,"payload":b64}；
      key = CHECKPOINT_HMAC_KEY（缺省回退 JWT_SECRET 并 WARN）。
  读：先恒定时间校验 hmac（hmac.compare_digest），不过 → 丢弃该快照 + WARN +
      走重建路径（不抛 500）。
  兼容：旧无签名裸 pickle 快照按「无签名=不可信」丢弃走重建。
  回滚开关：CHECKPOINT_SIGN=False → 旧裸 pickle 行为。

用例（全部真 Redis 127.0.0.1:6379）：
  T1 写入→读出 roundtrip（新 saver 实例 = 模拟进程重启后恢复）
  T2 篡改 payload → 校验拒 → 丢弃走重建（aget_tuple=None，不抛 500）
  T3 篡改 hmac → 同上
  T4 旧无签名格式 → 拒收走重建（一次性影响实证）
  T5 签名密钥回退 JWT_SECRET（CHECKPOINT_HMAC_KEY 缺省）+ WARN 触发
  T6 回滚开关 CHECKPOINT_SIGN=False → 旧裸 pickle 行为
  T7 HMAC 算法自证（独立复算比对，不依赖实现内部）
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import pickle
import uuid

import pytest
from loguru import logger as loguru_logger

import redis as _redis

from app.ai.checkpoint_redis import PlainRedisSaver
from app.config import settings


def _redis_ok() -> bool:
    try:
        r = _redis.Redis(host="127.0.0.1", port=6379, socket_connect_timeout=2)
        return r.ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_ok(), reason="Redis 不可用")

REDIS_URL = "redis://127.0.0.1:6379/0"
_TEST_HMAC_KEY = "hard2-hmac-test-key-" + uuid.uuid4().hex[:16]


def _mk_checkpoint(cp_id: str) -> dict:
    return {
        "v": 1, "id": cp_id, "ts": "2026-09-12T00:00:00+00:00",
        "channel_values": {"__root__": "val-" + cp_id},
        "channel_versions": {"__root__": 1}, "versions_seen": {},
    }


def _cfg(tid: str) -> dict:
    return {"configurable": {"thread_id": tid, "checkpoint_ns": "", "checkpoint_id": None}}


def _make_saver(monkeypatch, prefix: str, *, sign: bool = True, hmac_key: str | None = _TEST_HMAC_KEY) -> PlainRedisSaver:
    monkeypatch.setattr(settings, "CHECKPOINT_SIGN", sign)
    monkeypatch.setattr(settings, "CHECKPOINT_HMAC_KEY", hmac_key if hmac_key is not None else "")
    return PlainRedisSaver(REDIS_URL, prefix=prefix, ttl=600)


async def _put(saver: PlainRedisSaver, tid: str, cp_id: str):
    return await saver.aput(_cfg(tid), _mk_checkpoint(cp_id), {"source": "input", "step": 1}, {"__root__": 1})


async def _get(saver: PlainRedisSaver, tid: str):
    return await saver.aget_tuple(_cfg(tid))


# ============================================================
# T1 写入 → 读出 roundtrip（跨实例恢复）
# ============================================================
def test_h2_roundtrip_sign_envelope(monkeypatch):
    prefix = f"edu:ckpt-h2t1-{uuid.uuid4().hex[:8]}"
    tid = "tid-" + uuid.uuid4().hex[:8]
    w = _make_saver(monkeypatch, prefix)

    async def _main():
        await _put(w, tid, "cp-1")
        # 落盘值必须是签名信封 JSON（非裸 pickle）
        cli = await w._client()
        raw = await cli.get(f"{prefix}:{tid}")
        env = json.loads(raw)
        assert env["v"] == 1 and isinstance(env["hmac"], str) and env["payload"]
        # 模拟进程重启：全新实例同 prefix/thread
        r = _make_saver(monkeypatch, prefix)
        t = await _get(r, tid)
        assert t is not None
        assert t.checkpoint["id"] == "cp-1"
        assert t.checkpoint["channel_values"]["__root__"] == "val-cp-1"

    try:
        asyncio.run(_main())
    finally:
        asyncio.run(w.aclose())


# ============================================================
# T2/T3 篡改 → 拒收走重建
# ============================================================
@pytest.mark.parametrize("tamper", ["payload", "hmac"])
def test_h2_tamper_rejected_rebuild(monkeypatch, tamper):
    prefix = f"edu:ckpt-h2t2-{uuid.uuid4().hex[:8]}"
    tid = "tid-" + uuid.uuid4().hex[:8]
    w = _make_saver(monkeypatch, prefix)

    async def _main():
        await _put(w, tid, "cp-1")
        cli = await w._client()
        key = f"{prefix}:{tid}"
        env = json.loads(await cli.get(key))
        if tamper == "payload":
            payload = bytearray(base64.b64decode(env["payload"]))
            payload[0] ^= 0xFF  # 翻转 payload 首字节（模拟恶意 pickle 注入/位翻转）
            env["payload"] = base64.b64encode(bytes(payload)).decode("ascii")
        else:
            mac = bytearray.fromhex(env["hmac"])
            mac[0] ^= 0xFF
            env["hmac"] = mac.hex()
        await cli.set(key, json.dumps(env, separators=(",", ":")).encode("ascii"))
        # 新实例读取：校验不过 → 丢弃 → 重建路径（不抛 500，aget_tuple 返回 None）
        r = _make_saver(monkeypatch, prefix)
        t = await _get(r, tid)
        assert t is None, "被篡改快照必须拒收走重建（内存从空开始）"

    try:
        asyncio.run(_main())
    finally:
        asyncio.run(w.aclose())


# ============================================================
# T4 旧无签名裸 pickle 快照 → 拒收走重建（一次性影响）
# ============================================================
def test_h2_legacy_unsigned_pickle_rejected(monkeypatch):
    prefix = f"edu:ckpt-h2t4-{uuid.uuid4().hex[:8]}"
    tid = "tid-" + uuid.uuid4().hex[:8]
    w = _make_saver(monkeypatch, prefix)

    async def _main():
        cli = await w._client()
        key = f"{prefix}:{tid}"
        # 直接伪造旧格式：裸 pickle（升级前写入的存量快照形态）
        legacy = pickle.dumps({"storage": {"legacy": "not-trusted"}, "writes": {}, "blobs": {}})
        await cli.set(key, legacy)
        records: list = []
        hid = loguru_logger.add(records.append, level="WARNING")
        try:
            t = await _get(w, tid)
        finally:
            loguru_logger.remove(hid)
        assert t is None, "旧无签名快照按不可信丢弃，必须走重建"
        msgs = [(getattr(r, "message", None) or str(r)) for r in records]
        assert any("签名校验失败或为旧无签名格式" in m for m in msgs), f"拒收旧快照必须打 WARN，实际日志: {msgs}"

    try:
        asyncio.run(_main())
    finally:
        asyncio.run(w.aclose())


# ============================================================
# T5 密钥回退 JWT_SECRET + WARN
# ============================================================
def test_h2_hmac_key_fallback_jwt_secret_warn(monkeypatch):
    prefix = f"edu:ckpt-h2t5-{uuid.uuid4().hex[:8]}"
    tid = "tid-" + uuid.uuid4().hex[:8]
    # CHECKPOINT_HMAC_KEY 留空 → 回退 JWT_SECRET（conftest 已覆盖为测试密钥）
    w = _make_saver(monkeypatch, prefix, hmac_key=None)

    async def _main():
        assert w._hmac_fallback_warned is False
        await _put(w, tid, "cp-1")
        assert w._hmac_fallback_warned is True, "回退 JWT_SECRET 必须触发一次 WARN"
        # 回退密钥下 roundtrip 仍正确
        r = _make_saver(monkeypatch, prefix, hmac_key=None)
        t = await _get(r, tid)
        assert t is not None and t.checkpoint["id"] == "cp-1"
        # 独立密钥实例不能解 JWT_SECRET 签的快照（密钥隔离实证）
        other = _make_saver(monkeypatch, prefix, hmac_key="independent-key-" + uuid.uuid4().hex[:8])
        t2 = await _get(other, tid)
        assert t2 is None, "不同 HMAC 密钥的实例必须拒收他人签名的快照"

    try:
        asyncio.run(_main())
    finally:
        asyncio.run(w.aclose())


# ============================================================
# T6 回滚开关 CHECKPOINT_SIGN=False → 旧裸 pickle 行为
# ============================================================
def test_h2_sign_off_rollback(monkeypatch):
    prefix = f"edu:ckpt-h2t6-{uuid.uuid4().hex[:8]}"
    tid = "tid-" + uuid.uuid4().hex[:8]
    w = _make_saver(monkeypatch, prefix, sign=False, hmac_key=None)

    async def _main():
        await _put(w, tid, "cp-1")
        cli = await w._client()
        raw = await cli.get(f"{prefix}:{tid}")
        # 落盘是裸 pickle（旧格式），非 JSON 信封
        with pytest.raises(Exception):
            json.loads(raw)
        data = pickle.loads(raw)
        assert "storage" in data and "writes" in data and "blobs" in data
        r = _make_saver(monkeypatch, prefix, sign=False, hmac_key=None)
        t = await _get(r, tid)
        assert t is not None and t.checkpoint["id"] == "cp-1"

    try:
        asyncio.run(_main())
    finally:
        asyncio.run(w.aclose())


# ============================================================
# 补充：HMAC 算法自证（独立复算比对，不依赖实现内部）
# ============================================================
def test_h2_hmac_algorithm_selfcheck(monkeypatch):
    prefix = f"edu:ckpt-h2t7-{uuid.uuid4().hex[:8]}"
    tid = "tid-" + uuid.uuid4().hex[:8]
    w = _make_saver(monkeypatch, prefix)

    async def _main():
        await _put(w, tid, "cp-1")
        cli = await w._client()
        env = json.loads(await cli.get(f"{prefix}:{tid}"))
        payload = base64.b64decode(env["payload"])
        expect = hmac.new(_TEST_HMAC_KEY.encode(), payload, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(env["hmac"], expect), "信封 hmac 必须等于独立复算的 HMAC-SHA256"

    try:
        asyncio.run(_main())
    finally:
        asyncio.run(w.aclose())
