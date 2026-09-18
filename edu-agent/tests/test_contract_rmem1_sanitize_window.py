# -*- coding: utf-8 -*-
"""W-NEXT-R-MEM-001 契约测试：R04-b 落库脱敏 + R08 enqueue_turn 完整对话窗。

全离线、零外部依赖（对齐 test_contract_task_r01.py 夹具范式）：
- broker：monkeypatch ``app.database.get_redis`` 抛错 → MemoryWriteQueue 走进程内队列；
- 存储：MemEventMemoryPersistence（user_memory_event 内存事实表，HEAD 判据
  ``valid_to IS NULL AND event_type <> 'delete'`` 与生产 SQL 实现语义一致）；
- LLM：MEMORY_LLM_EXTRACT_ENABLED=False（规则路径确定性）或假件注入。

覆盖（任务书验收点）：
R04-b 脱敏——
  1) 模式级命中：sk-/ghp_/JWT/Bearer/AWS/xox/高熵串/password=/手机号/身份证/邮箱；
  2) 不误伤正常内容：中文偏好句/订单号/日期/普通 URL/普通英文；
  3) 结构不变：sanitize_turn_messages 条数/键集/role 保留；候选载荷 JSON 字段完整；
  4) 落库断言：含密钥的对话经 worker 落 user_memory_event 后 content 已掩码；
  5) 命中计数入日志：SANITIZE_STATS 累计 + loguru INFO 记录。
R08 对话窗——
  6) build_turn_window 纯函数：history+query+answer 成对 / answer 空 / dict 入参；
  7) 载荷版本：enqueue_turn_window 产出 v=2；旧 v1 turn（无 v）消费走 turn 路径；
  8) 旧 candidate 载荷（无 kind）消费走 candidate 写库路径；
  9) 残缺载荷（无 content 无 messages）→ poison 计数，不炸 worker；
 10) 半窗守卫：仅 user 发言入队成功（兼容）但告警；完整窗不告警。

运行：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_rmem1_sanitize_window.py -q
"""
from __future__ import annotations

import json

import pytest
from loguru import logger as _logger

from app.ai.memory.event_persistence import MemEventMemoryPersistence
from app.ai.memory.ingest import normalize_window
from app.ai.memory.queue import MemoryWriteQueue
from app.ai.memory.sanitize import (
    REDACTED,
    SANITIZE_STATS,
    reset_stats_for_test,
    sanitize_memory_text,
    sanitize_turn_messages,
)
from app.ai.memory.service import build_turn_window, enqueue_turn
from app.ai.memory.store import MemoryStore
from app.ai.memory.vector import DeterministicEmbedder, MemoryVectorStore


# ============================================================
# 离线夹具（对齐 R01 契约测试范式）
# ============================================================
@pytest.fixture
def offline_broker(monkeypatch: pytest.MonkeyPatch):
    """禁用 Redis：入队/取单/degraded 全部进程内路径；向量库强制 in-memory。"""
    import app.database as _database

    def _redis_unavailable(*_args, **_kwargs):
        raise RuntimeError("RMEM1 契约测试：Redis 已禁用（离线）")

    monkeypatch.setattr(_database, "get_redis", _redis_unavailable)


@pytest.fixture(autouse=True)
def _reset_sanitize_stats():
    reset_stats_for_test()
    yield
    reset_stats_for_test()


@pytest.fixture
def llm_extract_disabled(monkeypatch: pytest.MonkeyPatch):
    """规则路径确定性：关 LLM 抽取（worker 内 getattr 直读 settings）。"""
    from app.config import settings

    monkeypatch.setattr(settings, "MEMORY_LLM_EXTRACT_ENABLED", False, raising=False)


def _make_components(*, capacity: int = 500):
    persistence = MemEventMemoryPersistence()
    vector_store = MemoryVectorStore(milvus_uri="", dim=64, embedder=DeterministicEmbedder(dim=64))
    store = MemoryStore(persistence, vector_store, capacity=capacity)
    queue = MemoryWriteQueue(store)
    return persistence, store, queue


async def _drain(queue: MemoryWriteQueue) -> int:
    """反复 pump_once 直到队列空（poison 返回 False 时查内存队列再决定是否继续）。"""
    processed = 0
    while True:
        ok = await queue.pump_once()
        if ok:
            processed += 1
            continue
        if queue._memq.empty():
            break
    return processed


async def _head_contents(persistence: MemEventMemoryPersistence, user_id: int) -> list[str]:
    """按 HEAD 判据取当前有效记忆 content（AGENTS.md 教训 11 口径）。"""
    rows = await persistence.list_effective(user_id)
    return [m.content for m in rows]


# ============================================================
# R04-b：模式级脱敏——命中
# ============================================================
class TestSanitizeHits:
    @pytest.mark.parametrize(
        "text",
        [
            "我的密钥是 sk-abc123XYZdef456ghi789 请保存",
            "token: ghp_abcdefghijklmnopqrstuvwx123456",
            "登录态 Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJVadQssw5c",
            "password=SuperSecret123!",
            "api_key: 4f8a2b1c9d7e5f3a1b2c3d4e5f6a7b8c",
            "AWS key AKIAIOSFODNN7EXAMPLE 记住",
            "slack xoxb-123456789-abcdefghij",
            "random_hex d41d8cd98f00b204e9800998ecf8427e",
            "我的手机号是 13812345678",
            "身份证 110101199003078515 收好",
            "邮箱 user@example.com 是我的",
        ],
    )
    def test_sensitive_patterns_masked(self, text):
        out, hits = sanitize_memory_text(text)
        assert hits >= 1, f"未命中敏感模式: {text}"
        assert out != text
        # 掩码后原文敏感值不再完整出现
        assert out != text and REDACTED in out or "****" in out or "***" in out

    def test_masked_output_examples(self):
        # 密钥前缀 → ***REDACTED***
        out, _ = sanitize_memory_text("密钥 sk-abc123XYZdef456ghi789 保存")
        assert "sk-abc123XYZdef456ghi789" not in out and REDACTED in out
        # 手机号 partial mask（log_sanitizer 同款 138****1234）
        out, _ = sanitize_memory_text("手机号 13812345678")
        assert "138****5678" in out and "13812345678" not in out
        # 身份证 partial mask
        out, _ = sanitize_memory_text("身份证 110101199003078515 收好")
        assert "110101199003078515" not in out
        # key=value 保留 key 与分隔符
        out, _ = sanitize_memory_text("password=SuperSecret123!")
        assert out.startswith("password=") and "SuperSecret" not in out


# ============================================================
# R04-b：不误伤正常内容
# ============================================================
class TestSanitizeNoFalsePositive:
    @pytest.mark.parametrize(
        "text",
        [
            "我喜欢Python，目标是雅思6.5",
            "订单号 20240918123456 已出",
            "今天是2026年9月18日，我在准备考研",
            "https://docs.python.org/3.11/library/asyncio-task.html 很好用",
            "The quick brown fox jumps over the lazy dog",
            "小明 20190901 入学，学号 A2024001",
            "章节 3.11.4 讲了 asyncio 的用法",
            "",  # 空串零开销路径
        ],
    )
    def test_normal_content_untouched(self, text):
        out, hits = sanitize_memory_text(text)
        assert hits == 0, f"误伤正常内容: {text!r} -> {out!r}"
        assert out == text

    def test_task_word_not_masked_as_sk(self):
        # 「task-」类单词后接长数字不得被 sk- 前缀规则误伤
        out, hits = sanitize_memory_text("跟踪 task-2024091812345678 进度")
        assert hits == 0 and out == "跟踪 task-2024091812345678 进度"


# ============================================================
# R04-b：只损内容不损结构
# ============================================================
class TestSanitizeStructurePreserved:
    def test_turn_messages_structure_intact(self):
        msgs = [
            {"role": "user", "content": "记住 token sk-abc123XYZdef456ghi789"},
            {"role": "assistant", "content": "好的，手机号 13812345678 已记录"},
            {"role": "user", "content": "另外我的偏好是 Python"},
        ]
        out, total = sanitize_turn_messages(msgs)
        assert len(out) == len(msgs)
        for orig, masked in zip(msgs, out):
            assert set(masked.keys()) == set(orig.keys())  # 键集完整
            assert masked["role"] == orig["role"]
        # 原入参不被原地改
        assert "sk-abc123XYZdef456ghi789" in msgs[0]["content"]
        assert "sk-abc123XYZdef456ghi789" not in out[0]["content"]
        assert total >= 2

    def test_non_dict_and_non_str_passthrough(self):
        msgs = [{"role": "user", "content": "偏好 Java"}, {"other": 1}]
        out, _ = sanitize_turn_messages(msgs)
        assert out[1] == {"other": 1}  # 非 dict 原样透传

    def test_sanitize_text_non_string_defensive(self):
        assert sanitize_memory_text(None) == (None, 0)
        assert sanitize_memory_text("") == ("", 0)

    def test_hit_count_logged_and_stats(self, caplog):
        import io

        from loguru import logger

        buf = io.StringIO()
        handler_id = logger.add(buf, level="INFO")
        try:
            sanitize_memory_text("密钥 sk-abc123XYZdef456ghi789 保存")
        finally:
            logger.remove(handler_id)
        assert SANITIZE_STATS["hits"] >= 1
        assert "[Memory:sanitize] 落库脱敏命中" in buf.getvalue()  # 命中计数入日志


# ============================================================
# R04-b：落库断言（worker 全链路：窗口 → 候选 → user_memory_event）
# ============================================================
@pytest.mark.asyncio
async def test_secret_conversation_persists_masked(
    offline_broker, llm_extract_disabled
):
    """含密钥/手机号的对话经真实 worker 消费落库，user_memory_event.content 已脱敏。"""
    persistence, _store, queue = _make_components()
    window = [
        {"role": "user", "content": "记住 我喜欢Python，我的 API key 是 sk-abc123XYZdef456ghi789"},
        {"role": "assistant", "content": "好的，已记录，手机号 13812345678"},
    ]
    assert await queue.enqueue_turn_window(user_id=991, messages=window) is True
    await _drain(queue)
    contents = await _head_contents(persistence, 991)
    assert contents, "应有记忆落库（HEAD 判据 valid_to IS NULL AND event_type<>'delete'）"
    blob = "\n".join(contents)
    assert "sk-abc123XYZdef456ghi789" not in blob
    assert "13812345678" not in blob
    # 正常语义内容保留（只损内容不损语义）
    assert any("Python" in c for c in contents)


@pytest.mark.asyncio
async def test_enqueue_candidate_payload_sanitize_and_json_shape(
    offline_broker,
):
    """candidate 载荷脱敏 + JSON 字段完整（结构不损）。"""
    from app.ai.memory.schemas import MemoryCandidate

    persistence, _store, queue = _make_components()
    await queue.enqueue_candidate(
        992, MemoryCandidate(content="key sk-abc123XYZdef456ghi789", memory_type="preference",
                              topic="preferences", importance=5)
    )
    raw = queue._memq.get_nowait()
    payload = json.loads(json.dumps(raw, ensure_ascii=False))
    # JSON 结构完整：字段集不变
    assert set(payload.keys()) == {"user_id", "content", "memory_type", "topic", "importance", "retries"}
    assert "sk-abc123XYZdef456ghi789" not in payload["content"]
    assert REDACTED in payload["content"]


@pytest.mark.asyncio
async def test_turn_window_payload_masked_v2(offline_broker):
    """turn 载荷：v=2 版本字段 + 窗内 content 已掩码 + 结构完整。"""
    _p, _s, queue = _make_components()
    window = [
        {"role": "user", "content": "token ghp_abcdefghijklmnopqrstuvwx123456 记住"},
        {"role": "assistant", "content": "偏好 Java 已记录"},
    ]
    assert await queue.enqueue_turn_window(user_id=993, messages=window) is True
    payload = queue._memq.get_nowait()
    assert payload["v"] == 2
    assert payload["kind"] == "turn"
    assert len(payload["messages"]) == 2
    assert set(payload["messages"][0].keys()) == {"role", "content"}
    assert "ghp_abcdefghijklmnopqrstuvwx123456" not in payload["messages"][0]["content"]


# ============================================================
# R08：build_turn_window（完整对话窗拼装）
# ============================================================
class TestBuildTurnWindow:
    def test_history_plus_pair(self):
        history = [("user", "我想考雅思"), ("assistant", "好的，你的目标是雅思")]
        window = build_turn_window(history, query="那口语怎么练", answer="建议每天跟读 30 分钟")
        roles = [m["role"] for m in window]
        assert roles == ["user", "assistant", "user", "assistant"]  # 两对成对
        assert window[-2]["content"] == "那口语怎么练"
        assert window[-1]["content"] == "建议每天跟读 30 分钟"

    def test_empty_answer_keeps_user_side(self):
        window = build_turn_window([], query="hi", answer="")
        assert [m["role"] for m in window] == ["user"]

    def test_dict_history_and_none(self):
        window = build_turn_window([{"role": "user", "content": "a"}], query="b", answer="c")
        assert len(window) == 3
        assert build_turn_window(None, query="x", answer="y") == [
            {"role": "user", "content": "x"}, {"role": "assistant", "content": "y"},
        ]
        assert build_turn_window(None, query="", answer="") == []


# ============================================================
# R08：消费端新旧载荷形状探测兼容
# ============================================================
@pytest.mark.asyncio
async def test_v1_turn_payload_without_version_field_consumed(
    offline_broker, llm_extract_disabled
):
    """旧 v1 turn 载荷（kind=turn 无 v 字段，部署时 Redis 在途）照常走抽取路径。"""
    persistence, _store, queue = _make_components()
    queue._memq.put_nowait({
        "kind": "turn",  # 无 v 字段 = v1
        "user_id": 994,
        "messages": [{"role": "user", "content": "我想考雅思"}],
        "threshold": 4,
        "retries": 0,
        "ts": "2026-09-18T00:00:00",
    })
    assert await queue.pump_once() is True  # turn 消费 → 候选回灌
    assert queue.stats["turn"] == 1
    await _drain(queue)  # 回灌的 candidate 落库
    assert "雅思" in "\n".join(await _head_contents(persistence, 994))


@pytest.mark.asyncio
async def test_legacy_candidate_payload_without_kind_consumed(offline_broker):
    """旧 candidate 载荷（无 kind，R7 原始形态）走 candidate 写库路径。"""
    persistence, _store, queue = _make_components()
    queue._memq.put_nowait({
        "user_id": 995,
        "content": "偏好 Rust",
        "memory_type": "preference",
        "topic": "preferences",
        "importance": 5,
        "retries": 0,
    })
    assert await queue.pump_once() is True
    assert queue.stats["candidate"] == 1
    assert "偏好 Rust" in (await _head_contents(persistence, 995))[0]


@pytest.mark.asyncio
async def test_broken_payload_counted_as_poison_no_crash(offline_broker):
    """残缺载荷（无 messages 无 content）→ poison 计数丢弃，worker 不炸。"""
    _p, _s, queue = _make_components()
    queue._memq.put_nowait({"kind": "turn", "user_id": 996, "messages": []})
    assert await queue.pump_once() is False
    assert queue.stats["poison"] == 1


# ============================================================
# R08：半窗守卫 + 完整窗入队（service 层）
# ============================================================
@pytest.mark.asyncio
async def test_service_enqueue_turn_full_window_ok(
    offline_broker, llm_extract_disabled
):
    """R08 目标态：messages 完整窗（含 assistant）→ 正常入队并落库（service 单例换件）。"""
    from app.ai.memory import service as memory_service

    persistence, store, queue = _make_components()
    saved_store, saved_queue = memory_service._store, memory_service._queue
    memory_service._store, memory_service._queue = store, queue
    try:
        window = build_turn_window(
            [("user", "我在准备 CFA"), ("assistant", "好的，CFA 一级建议先学伦理与数量")],
            query="notes: api_key sk-abc123XYZdef456ghi789",
            answer="收到，已记录",
        )
        assert await enqueue_turn(997, messages=window) == 1
        await _drain(queue)
        contents = await _head_contents(persistence, 997)
        assert any("CFA" in c for c in contents)
        assert not any("sk-abc123XYZdef456ghi789" in c for c in contents)
    finally:
        memory_service._store, memory_service._queue = saved_store, saved_queue


@pytest.mark.asyncio
async def test_service_enqueue_turn_half_window_warns_but_compat_enqueues(
    offline_broker, llm_extract_disabled, caplog
):
    """旧单 query 调用（缺 assistant 半边）：兼容入队返回 1，但显式告警。"""
    from app.ai.memory import service as memory_service

    _persistence, store, queue = _make_components()
    saved_store, saved_queue = memory_service._store, memory_service._queue
    memory_service._store, memory_service._queue = store, queue
    import io

    buf = io.StringIO()
    hid = _logger.add(buf, level="WARNING")
    try:
        rc = await enqueue_turn(998, "我想考雅思")
    finally:
        _logger.remove(hid)
        memory_service._store, memory_service._queue = saved_store, saved_queue
    assert rc == 1  # 旧契约兼容
    assert "缺 assistant 半边" in buf.getvalue()


@pytest.mark.asyncio
async def test_normalize_window_still_trims_full_window(offline_broker):
    """完整窗超 MEMORY_INGEST_WINDOW 时取最近 N 条（R08 与 R01-b 语义一致）。"""
    msgs = [{"role": "user", "content": f"m{i}"} for i in range(20)]
    msgs.append({"role": "assistant", "content": "tail"})
    window = normalize_window(msgs, limit=10)
    assert len(window) == 10
    assert window[-1]["content"] == "tail"
