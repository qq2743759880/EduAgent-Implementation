# -*- coding: utf-8 -*-
"""R01 契约测试：记忆 worker 通电 + 对话窗抽取 + 防幻觉序号映射（audit P0 收口）。

全离线、零外部依赖（不连 MySQL/Milvus/Redis/LLM）：
- broker：monkeypatch ``app.database.get_redis`` 直接抛错 → MemoryWriteQueue 强制走
  进程内 asyncio.Queue / degraded 进程内列表（生产降级路径同款）；
- 存储：MemEventMemoryPersistence（user_memory_event 内存事实表）+ in-memory 向量
  + DeterministicEmbedder（字符 n-gram，不加载 BGE-M3）；
- LLM：以假件注入 extract_candidates_llm（或经其 llm= 注入点走真实解析链路）。

覆盖（对应交接单剩余工作 a-d）：
a) normalize_window：messages 形态 / text+reply 形态 / limit 截断 / 非法角色过滤；
b) turn 载荷 pump_once：规则候选（用户目标）+ LLM 候选（助手陈述事实）→ 候选回灌
   → 再 pump 落库，user_memory 同时覆盖两侧来源（R01-b GWT）；
c) LLM 抛异常/乱码/空输出 → degraded_count 增且规则候选仍落库（非静默丢弃）；
   合法 "[]" → 不增 degraded；
d) format_memories_for_prompt：序号连续、真实 id 不入文本、ref_map 正确、空列表
   返回 ("", {})；recall_topk / recall_topk_mapped 返回体无 "id" 键。

运行：
    cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_task_r01.py -q
"""
from __future__ import annotations

import pytest

from app.ai.memory.event_persistence import MemEventMemoryPersistence
from app.ai.memory.ingest import normalize_window
from app.ai.memory.queue import MemoryWriteQueue
from app.ai.memory.service import format_memories_for_prompt
from app.ai.memory.store import MemoryStore
from app.ai.memory.vector import DeterministicEmbedder, MemoryVectorStore
from app.ai.memory.schemas import MemoryCandidate


# ============================================================
# 离线夹具 / 组件构造
# ============================================================
@pytest.fixture
def offline_broker(monkeypatch: pytest.MonkeyPatch):
    """禁用 Redis：队列入队/取单/degraded 全部强制进程内路径，向量库强制 in-memory。"""
    import app.database as _database

    def _redis_unavailable(*_args, **_kwargs):
        raise RuntimeError("R01 契约测试：Redis 已禁用（离线）")

    monkeypatch.setattr(_database, "get_redis", _redis_unavailable)


def _make_components(*, capacity: int = 500):
    """构造（内存事实表 + 内存向量 + 真实 MemoryWriteQueue）三件套。

    注意：调用方需先挂 offline_broker（get_redis 抛错），否则 MemoryVectorStore
    会尝试拿真实 Redis 客户端切到 redis backend。
    """
    persistence = MemEventMemoryPersistence()
    vector_store = MemoryVectorStore(
        milvus_uri="", dim=64, embedder=DeterministicEmbedder(dim=64)
    )
    store = MemoryStore(persistence, vector_store, capacity=capacity)
    queue = MemoryWriteQueue(store)
    return persistence, store, queue


async def _drain(queue: MemoryWriteQueue) -> int:
    """反复 pump_once 直到队列空，返回成功消费的载荷数。"""
    processed = 0
    while await queue.pump_once():
        processed += 1
    return processed


def _patch_extract_with_llm(monkeypatch: pytest.MonkeyPatch, fake_llm):
    """让 queue 调到的 extract_candidates_llm 走真实解析链路、但 LLM 调用用假件。

    queue 内是延迟 ``from app.ai.memory.extract_llm import extract_candidates_llm``，
    patch 模块属性即可生效；真实函数的 llm= 注入点保证零网络且覆盖真实 JSON 解析/
    空数组判定/异常包装逻辑（不经 subagents.runner，避免重依赖导入）。
    """
    from app.ai.memory import extract_llm as _extract_module

    real_extract = _extract_module.extract_candidates_llm

    async def _wrapped(messages, **kwargs):
        kwargs.pop("llm", None)
        return await real_extract(messages, llm=fake_llm, **kwargs)

    monkeypatch.setattr(_extract_module, "extract_candidates_llm", _wrapped)


# ============================================================
# a) normalize_window：对话窗归一（纯函数，零 I/O）
# ============================================================
class TestNormalizeWindow:
    def test_messages_form_role_canonical_and_filter(self):
        """messages 形态：human/ai/bot 别名归一，system/tool/空内容/非 dict 全过滤。"""
        messages = [
            {"role": "human", "content": "  你好 "},      # → user，strip
            {"role": "user", "content": "   "},           # 空白内容丢弃
            {"role": "system", "content": "系统指令"},      # 非法角色丢弃
            {"role": "ai", "content": "在的"},             # → assistant
            "not-a-dict",                                  # 非 dict 丢弃
            {"role": "bot", "content": ""},                # 空内容丢弃
            {"role": "tool", "content": "工具输出"},         # 非法角色丢弃
        ]
        window = normalize_window(messages)
        assert window == [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "在的"},
        ]

    def test_text_reply_form_and_empty(self):
        """text(+assistant_reply) 合成最小窗口；空输入返回 []；messages 优先于 text。"""
        assert normalize_window(text="我想考雅思", assistant_reply="已收到") == [
            {"role": "user", "content": "我想考雅思"},
            {"role": "assistant", "content": "已收到"},
        ]
        assert normalize_window(text="我想考雅思") == [
            {"role": "user", "content": "我想考雅思"}
        ]
        assert normalize_window() == []
        assert normalize_window(text="   ") == []
        # 同时给 messages 与 text：messages 形态优先
        assert normalize_window(
            [{"role": "user", "content": "窗口消息"}], text="被忽略"
        ) == [{"role": "user", "content": "窗口消息"}]

    def test_limit_keeps_last_and_truncates_content(self):
        """limit 保留最近 N 条；单条内容超 2000 字截断。"""
        messages = [{"role": "user", "content": f"m{i}"} for i in range(12)]
        window = normalize_window(messages, limit=10)
        assert len(window) == 10
        assert window[0]["content"] == "m2"          # 最早保留的是第 3 条
        assert window[-1]["content"] == "m11"        # 最新一条在末尾
        window_3 = normalize_window(messages, limit=3)
        assert [item["content"] for item in window_3] == ["m9", "m10", "m11"]

        long_window = normalize_window(text="雅" * 2500, limit=10)
        assert len(long_window[0]["content"]) == 2000


# ============================================================
# b) R01-b GWT：turn 对话窗 pump → 规则+LLM 双源候选回灌 → 落库
# ============================================================
class TestTurnWindowPump:
    async def test_turn_pump_persists_user_goal_and_assistant_fact(
        self, offline_broker, monkeypatch: pytest.MonkeyPatch
    ):
        """用户「我想考雅思」（规则）+ 助手陈述的课程进度事实（LLM）最终都落库。"""
        # 假 LLM：从助手回复中抽出一条用户事实（规则路径不扫助手文本，只能靠 LLM）
        async def _fake_extract(messages, **_kwargs):
            return [MemoryCandidate(
                content="用户已完成 Python 入门课程前三章学习",
                memory_type="fact", topic="general",
                importance=4, source="llm_window",
            )], None

        from app.ai.memory import extract_llm as _extract_module
        monkeypatch.setattr(_extract_module, "extract_candidates_llm", _fake_extract)

        persistence, _store, queue = _make_components()
        user_id = 9001001
        messages = [
            {"role": "user", "content": "我想考雅思，目标是 6.5 分"},
            {"role": "assistant", "content": "好的。根据你的学习记录，你已经完成 Python 入门前三章。"},
        ]

        # 入队毫秒级快返（载荷此时尚未落库）
        assert await queue.enqueue_turn_window(user_id, messages) is True
        assert await persistence.count_effective(user_id) == 0

        # 第一次 pump：消费 turn → 双源候选回灌同队列（candidate 载荷）
        assert await queue.pump_once() is True
        assert queue.stats["turn"] == 1
        assert await persistence.count_effective(user_id) == 0, "回灌阶段不应已落库"

        # 再 pump：候选逐条写库
        processed = await _drain(queue)
        assert processed == 2, f"规则+LLM 各一条候选，实际消费 {processed} 条"
        assert queue.stats["candidate"] == 2

        rows = await persistence.list_effective(user_id)
        contents = "\n".join(row.content for row in rows)
        assert "雅思" in contents, "用户目标（规则候选）必须落库"
        assert "Python" in contents, "助手陈述事实（LLM 候选）必须落库"

    async def test_service_enqueue_turn_composes_window(
        self, offline_broker
    ):
        """门面 enqueue_turn(text, assistant_reply=) 合成 user/assistant 成对窗口。"""
        from app.ai.memory import service as memory_service

        _persistence, _store, queue = _make_components()
        saved_store, saved_queue = memory_service._store, memory_service._queue
        memory_service._store, memory_service._queue = _store, queue
        try:
            flag = await memory_service.enqueue_turn(
                8802001, "我想考雅思", assistant_reply="已为你记录目标"
            )
            assert flag == 1
            payload = queue._memq.get_nowait()  # 离线 broker：载荷必在进程内队列
            assert payload["kind"] == "turn"
            assert [m["role"] for m in payload["messages"]] == ["user", "assistant"]

            # 空窗（text/messages 均空）→ 返回 0，不入队
            assert await memory_service.enqueue_turn(8802001, None) == 0
        finally:
            memory_service._store, memory_service._queue = saved_store, saved_queue


# ============================================================
# c) LLM 失败显式 degraded（不伪装空列表、不静默丢弃规则候选）
# ============================================================
@pytest.mark.parametrize(
    "behavior,reason_prefix",
    [
        ("raise", "llm_call_failed"),       # LLM 调用抛异常
        ("garbled", "llm_unparseable_output"),  # 返回散文乱码（无 JSON 数组）
        ("empty", "llm_empty_output"),      # 空输出
    ],
)
async def test_llm_failure_marks_degraded_but_rule_candidate_persists(
    offline_broker, monkeypatch: pytest.MonkeyPatch, behavior, reason_prefix
):
    """LLM 链路失败三态：degraded 留存 +1，规则候选照常落库，turn 正常消费。"""

    async def _raise_llm(_messages, model=None):
        raise RuntimeError("llm upstream 503")

    async def _garbled_llm(_messages, model=None):
        return "抱歉，@@@无法解析的散文，没有数组"

    async def _empty_llm(_messages, model=None):
        return "   "

    fake_llm = {"raise": _raise_llm, "garbled": _garbled_llm, "empty": _empty_llm}[behavior]
    _patch_extract_with_llm(monkeypatch, fake_llm)

    persistence, _store, queue = _make_components()
    user_id = {"raise": 9003001, "garbled": 9003002, "empty": 9003003}[behavior]
    messages = [
        {"role": "user", "content": "我想考雅思"},
        {"role": "assistant", "content": "闲聊式回复，不含可抽事实"},
    ]
    assert await queue.enqueue_turn_window(user_id, messages) is True

    # 第一次 pump 消费 turn：LLM 失败落 degraded，规则候选仍回灌
    assert await queue.pump_once() is True
    assert queue.stats["turn"] == 1
    assert queue.stats["degraded"] == 1
    assert await queue.degraded_count() == 1, "Redis 关闭时 degraded_count 读进程内留存"
    record = queue._degraded_mem[0]
    assert record["reason"].startswith(reason_prefix), record["reason"]
    assert record["user_id"] == user_id
    assert record["window_preview"], "degraded 记录必须留窗口预览，可回放定位"

    # 规则候选不丢：再 pump 后用户目标照常落库
    assert await _drain(queue) == 1
    rows = await persistence.list_effective(user_id)
    assert len(rows) == 1 and "雅思" in rows[0].content


async def test_llm_legal_empty_array_not_degraded(offline_broker, monkeypatch):
    """合法空结果 [ ] = 本轮确无记忆：不增 degraded；规则候选仍落库。"""

    async def _empty_array_llm(_messages, model=None):
        return "[]"

    _patch_extract_with_llm(monkeypatch, _empty_array_llm)

    persistence, _store, queue = _make_components()
    user_id = 9004001
    await queue.enqueue_turn_window(user_id, [
        {"role": "user", "content": "我想考雅思"},
        {"role": "assistant", "content": "好的"},
    ])
    assert await queue.pump_once() is True
    assert queue.stats["degraded"] == 0
    assert await queue.degraded_count() == 0
    assert await _drain(queue) == 1
    assert await persistence.count_effective(user_id) == 1


async def test_extract_llm_success_empty_and_empty_window(offline_broker):
    """抽取器单元级：合法 JSON 数组解析为候选；合法 [] 无 error；空窗判失败。"""
    from app.ai.memory.extract_llm import extract_candidates_llm

    async def _valid_llm(_messages, model=None):
        return (
            '[{"content": "用户偏好深色主题", "memory_type": "preference", '
            '"topic": "preferences", "importance": 4}]'
        )

    candidates, error = await extract_candidates_llm(
        [{"role": "user", "content": "我喜欢深色主题"}], llm=_valid_llm
    )
    assert error is None
    assert len(candidates) == 1
    assert candidates[0].content == "用户偏好深色主题"
    assert candidates[0].source == "llm_window"

    async def _empty_array_llm(_messages, model=None):
        return "[]"

    candidates_empty, error_empty = await extract_candidates_llm(
        [{"role": "user", "content": "今天天气不错"}], llm=_empty_array_llm
    )
    assert candidates_empty == [] and error_empty is None

    # 空窗（无任何 user/assistant 发言）属链路失败而非合法空结果
    candidates_blank, error_blank = await extract_candidates_llm(
        [{"role": "system", "content": "x"}], llm=_empty_array_llm
    )
    assert candidates_blank == [] and error_blank == "empty_window"


# ============================================================
# c2) 截断容错 salvage（T9-C1：前几条合法事实不因尾部截断连坐落 degraded）
# ============================================================
def test_salvage_json_array_boundaries():
    """salvage 纯函数边界：只收已闭合元素；字符串内花括号/转义引号不误判。"""
    from app.ai.memory.extract_llm import _salvage_json_array

    truncated = '[{"content":"a"}, {"content":"b"}, {"content":"c'
    assert [e["content"] for e in _salvage_json_array(truncated)] == ["a", "b"]
    # 字符串内的 }{ 与 \" 不参与括号计数
    tricky = '[{"content":"含 }{ 与 \\" 引号"}, {"content":"截'
    assert [e["content"] for e in _salvage_json_array(tricky)] == ['含 }{ 与 " 引号']

    assert _salvage_json_array("抱歉，@@@无法解析的散文，没有数组") == []
    assert _salvage_json_array('[{"content": "截') == [], "无一条完整元素→空"


async def test_truncated_output_salvages_leading_entries_not_degraded():
    """截断输出（前 2 条完整 + 第 3 条截断）→ 前 2 条为候选、error=None。"""
    from app.ai.memory.extract_llm import extract_candidates_llm

    async def _truncated_llm(_messages, model=None):
        return (
            '[{"content": "用户目标雅思 6.5", "memory_type": "goal", "topic": "learning-goals", "importance": 5}, '
            '{"content": "用户零基础", "memory_type": "profile", "topic": "profile", "importance": 4}, '
            '{"content": "用户想学'
        )

    candidates, error = await extract_candidates_llm(
        [{"role": "user", "content": "我想考雅思 6.5，零基础"}], llm=_truncated_llm
    )
    assert error is None, "尾部截断不得整批判 llm_unparseable_output"
    assert [c.content for c in candidates] == ["用户目标雅思 6.5", "用户零基础"]
    assert {c.source for c in candidates} == {"llm_window"}


async def test_truncated_output_salvage_persists_without_degraded(offline_broker, monkeypatch):
    """队列级：截断 salvage 的候选照常落库，degraded 不增。"""
    async def _truncated_llm(_messages, model=None):
        return (
            '[{"content": "用户已完成 Python 入门前三章", "memory_type": "fact", '
            '"topic": "general", "importance": 4}, '
            '{"content": "用户每晚学习一小时'
        )

    _patch_extract_with_llm(monkeypatch, _truncated_llm)
    persistence, _store, queue = _make_components()
    user_id = 9005001
    assert await queue.enqueue_turn_window(user_id, [
        {"role": "user", "content": "随便聊聊"},
        {"role": "assistant", "content": "好的，根据记录你已完成 Python 入门前三章。"},
    ]) is True

    assert await queue.pump_once() is True
    assert queue.stats["degraded"] == 0, "截断但可 salvage → 不落 degraded"
    assert await queue.degraded_count() == 0
    assert await _drain(queue) >= 1
    contents = [r.content for r in await persistence.list_effective(user_id)]
    assert "用户已完成 Python 入门前三章" in contents, contents


async def test_no_complete_element_still_degraded(offline_broker, monkeypatch):
    """连一条完整元素都 salvage 不出 → 仍判 llm_unparseable_output 落 degraded。"""
    async def _cut_mid_element_llm(_messages, model=None):
        return '[{"content": "用户想学雅思，但这条被截断在字符串里'

    _patch_extract_with_llm(monkeypatch, _cut_mid_element_llm)
    persistence, _store, queue = _make_components()
    user_id = 9005002
    await queue.enqueue_turn_window(user_id, [
        {"role": "user", "content": "我想考雅思"},
        {"role": "assistant", "content": "好的"},
    ])
    assert await queue.pump_once() is True
    assert queue.stats["degraded"] == 1
    assert queue._degraded_mem[0]["reason"].startswith("llm_unparseable_output")


# ============================================================
# d) 防幻觉：ID→序号映射 + 召回返回体剥离 id
# ============================================================
class TestPromptIdMapping:
    def test_serial_continuous_and_raw_id_hidden(self):
        """注入文本序号连续 [M1]/[M2]，真实 id 只在 ref_map，不进 prompt 文本。"""
        rows = [
            {"id": 101, "content": "喜欢用番茄工作法"},
            {"id": 202, "content": "目标是雅思七分"},
        ]
        text, ref_map = format_memories_for_prompt(rows)
        assert "[M1]" in text and "[M2]" in text and "[M3]" not in text
        assert "101" not in text and "202" not in text, "真实 memory_id 禁止入 prompt"
        assert "番茄工作法" in text and "雅思" in text
        assert ref_map == {"[M1]": 101, "[M2]": 202}
        assert "序号" in text, "须随附「只能引用列出序号」的防臆造指令"

    def test_empty_and_malformed_rows(self):
        """空列表 → ("", {})；非 dict 跳过；id 缺失映射 None，序号仍连续。"""
        assert format_memories_for_prompt([]) == ("", {})
        assert format_memories_for_prompt(None) == ("", {})

        text, ref_map = format_memories_for_prompt([
            "garbage-row",                              # 非 dict 跳过
            {"id": None, "content": "无 id 的记忆"},      # id 缺失 → None
            {"content": "   "},                          # 空内容跳过
        ])
        assert ref_map == {"[M1]": None}
        assert "[M1]" in text and "[M2]" not in text

    async def test_recall_topk_strips_internal_id(self, offline_broker):
        """recall_topk / recall_topk_mapped 返回体一律不含内部 id（store 行带 id）。"""
        from app.ai.memory import service as memory_service

        _persistence, store, queue = _make_components()
        saved_store, saved_queue = memory_service._store, memory_service._queue
        memory_service._store, memory_service._queue = store, queue
        try:
            await store.write(
                user_id=8805001, content="目标考试是雅思总分七分",
                memory_type="goal", topic="learning-goals", importance=5,
            )
            rows = await memory_service.recall_topk(8805001, "雅思考试", top_k=3)
            assert rows, "字符 n-gram 重叠应召回写入的记忆"
            assert all("id" not in row for row in rows), "召回返回体必须剥离内部 id"

            text, ref_map, safe_rows = await memory_service.recall_topk_mapped(
                8805001, "雅思考试", top_k=3
            )
            assert text and ref_map, "映射入口应返回序号化文本与映射表"
            assert all(isinstance(memory_id, int) for memory_id in ref_map.values())
            assert all("id" not in row for row in safe_rows)
            assert "8805001" not in text  # user_id 同样不应泄入 prompt
        finally:
            memory_service._store, memory_service._queue = saved_store, saved_queue
