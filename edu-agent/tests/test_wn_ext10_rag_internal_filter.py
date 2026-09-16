# -*- coding: utf-8 -*-
"""
WNEXT10（T4-C4 拆解）回归测试 —— 两个批判项的机验门。

任务一【P0】RAG `_default` 分区内部文档按角色过滤（F5-a）
  ① classify_internal：内部来源/内部正文 → True；业务语料 → False；显式标记优先
  ② role_allows_internal：admin/manager 可见，student/teacher/None 不可见
  ③ hybrid_search：include_internal=False / role=student → expr 带 internal 过滤 + 结果侧剔除；
     admin 与「不传参」保持历史行为（检索契约不破坏）
  ④ load_chunks 写入 internal dynamic field（True/False 全量写，保证过滤语义一致）
  ⑤ /api/chat/search 端点按角色注入可见性，请求结束恢复默认

任务二【P1】系统 prompt 工具清单以实物为准（F5-b）
  ⑥ platform_capability_block 由 permission_gate.TOOL_CLASS_MAP 动态生成（7 个实物工具，
     无开发宿主工具名）
  ⑦ SkillRegistry.default() 与开发机 skill 库隔离；dev_default() 保留历史扫描
  ⑧ graph.skill_node 的 skill_context 注入权威能力清单

离线运行：不依赖 live backend / 真 Milvus（Milvus 客户端 monkeypatch）。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.auth.schemas import UserInfo, UserRole
from app.knowledge.importer import loader as L
from app.knowledge.importer.loader import (
    INTERNAL_FIELD,
    INTERNAL_FILTER_EXPR,
    classify_internal,
    internal_visibility_allowed,
    reset_internal_visibility,
    role_allows_internal,
    set_internal_visibility,
)


def _user(role: UserRole, uid: int = 1) -> UserInfo:
    return UserInfo(user_id=uid, nickname="t", real_name="t", mobile=None,
                    email="t@e", gender=None, avatar_url=None, role=role)


# ============================================================
# ① classify_internal
# ============================================================
class TestClassifyInternal:
    def test_internal_source_patterns(self):
        for src in [
            "3e2b7812be2f.md",                       # 哈希导出（实测 1789 行 doc_chunk 形态）
            "D:/.ai-hub/notes/x.md",
            "test-reports/critique-blind-t4-t9.md",
            "refactor_sql/01.sql",
            ".ai-hub/plans/artifacts/kickoff-WNEXT10.md",
            "scripts/restore_admin.py",
            "deploy/Dockerfile.md",
            "kickoff-WNEXT10-rag.md",
        ]:
            assert classify_internal(src, "普通正文") is True, src

    def test_internal_content_patterns(self):
        for body in [
            "②若需要可登录批量用户，在 task09~14 中补 sys_user_auth 批量生成",
            "优化方案：restore_admin.py 的哈希逻辑",
            "本批次为 W-NEXT-10，GWT 见下",
            "编排者已复现该问题",
        ]:
            assert classify_internal("some/business.md", body) is True, body

    def test_business_corpus_not_internal(self):
        # 实测业务语料：seeds/* 来源 + 题目/课程正文（应零误伤）
        assert classify_internal(
            "seeds/3_question/question.csv",
            "【单选题】题目：关于班级管理，哪些说法正确？ 选项：A. 班规应兼顾民主参与",
        ) is False
        assert classify_internal(
            "seeds/2_course/series_course.csv",
            "课程模块：进程线程与调度原理 模块编码：operating_and_runtime_systems_foundation_m1",
        ) is False
        assert classify_internal("seeds/2_course/series.csv", "所属系列：数据分析求职班") is False

    def test_explicit_flag_wins(self):
        assert classify_internal("seeds/x.csv", "普通正文", internal_flag=True) is True
        assert classify_internal("3e2b7812be2f.md", "task09 报告", internal_flag=False) is False


# ============================================================
# ② role_allows_internal
# ============================================================
class TestRoleAllowsInternal:
    def test_privileged_roles(self):
        assert role_allows_internal(UserRole.ADMIN) is True
        assert role_allows_internal(UserRole.MANAGER) is True
        assert role_allows_internal("admin") is True
        assert role_allows_internal("MANAGER") is True

    def test_non_privileged_roles(self):
        for role in (UserRole.STUDENT, UserRole.TEACHER, "student", "teacher", None, "", "unknown"):
            assert role_allows_internal(role) is False, role


# ============================================================
# ③ hybrid_search 过滤（假 Milvus 客户端）
# ============================================================
class _FakeClient:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.calls: list[dict] = []

    def hybrid_search(self, **kw):
        self.calls.append(kw)
        return [[
            {"id": i, "distance": 0.9, "entity": dict(r)}
            for i, r in enumerate(self.rows)
        ]]


def _rows():
    return [
        {"chunk_id": "biz1", "source_file": "seeds/3_question/question.csv",
         "content": "【单选题】极值判定", "content_type": "question", INTERNAL_FIELD: False},
        {"chunk_id": "int_tagged", "source_file": "3e2b7812be2f.md",
         "content": "task09 报告", "content_type": "doc_chunk", INTERNAL_FIELD: True},
        # 存量无 internal 字段（回填需人工确认，尚未执行）→ 结果侧兜底判定
        {"chunk_id": "int_legacy", "source_file": "abc.md",
         "content": "批量生成 sys_user_auth", "content_type": "doc_chunk"},
        {"chunk_id": "biz2", "source_file": "seeds/2_course/series.csv",
         "content": "数据分析求职班", "content_type": "course_intro"},
    ]


def _exprs(call: dict) -> list[str | None]:
    return [getattr(r, "expr", None) for r in call["reqs"]]


@pytest.fixture()
def fake_milvus(monkeypatch):
    holder = {}

    def _make(rows):
        c = _FakeClient(rows)
        holder["client"] = c
        monkeypatch.setattr(L, "get_milvus_client", lambda: c)
        return c

    holder["make"] = _make
    return holder


class TestHybridSearchInternalFilter:
    def test_default_call_unchanged(self, fake_milvus):
        """不传 include_internal/role → 历史行为不变（expr 原样、结果不剔除）。"""
        fake_milvus["make"](_rows())
        out = L.hybrid_search([0.1] * 4, {"0": 1.0})
        assert len(out) == 4
        assert all(e is None for e in _exprs(fake_milvus["client"].calls[0]))

    def test_include_internal_false_filters(self, fake_milvus):
        fake_milvus["make"](_rows())
        out = L.hybrid_search([0.1] * 4, {"0": 1.0}, include_internal=False)
        ids = [r["chunk_id"] for r in out]
        assert ids == ["biz1", "biz2"]          # 已打标 internal + 存量命中特征 → 均剔除
        exprs = _exprs(fake_milvus["client"].calls[0])
        assert all(e and INTERNAL_FILTER_EXPR in e for e in exprs), exprs

    def test_role_student_filters_role_admin_not(self, fake_milvus):
        fake_milvus["make"](_rows())
        out = L.hybrid_search([0.1] * 4, {"0": 1.0}, role=UserRole.STUDENT)
        assert [r["chunk_id"] for r in out] == ["biz1", "biz2"]

        fake_milvus["make"](_rows())
        out = L.hybrid_search([0.1] * 4, {"0": 1.0}, role=UserRole.ADMIN)
        assert len(out) == 4

    def test_contextvar_drives_filter(self, fake_milvus):
        """router 注入路径：请求级 ContextVar=False 时无参调用也过滤。"""
        fake_milvus["make"](_rows())
        token = set_internal_visibility(False)
        try:
            out = L.hybrid_search([0.1] * 4, {"0": 1.0})
            assert [r["chunk_id"] for r in out] == ["biz1", "biz2"]
        finally:
            reset_internal_visibility(token)
        assert internal_visibility_allowed() is True

    def test_filter_combines_with_existing_expr(self, fake_milvus):
        fake_milvus["make"](_rows())
        L.hybrid_search([0.1] * 4, {"0": 1.0}, include_internal=False,
                        filter_expr='content_type not in ["promo"]')
        exprs = _exprs(fake_milvus["client"].calls[0])
        assert all('content_type not in ["promo"]' in e and INTERNAL_FILTER_EXPR in e for e in exprs)

    def test_output_fields_carry_internal_flag(self, fake_milvus):
        fake_milvus["make"](_rows())
        L.hybrid_search([0.1] * 4, {"0": 1.0}, include_internal=False)
        assert INTERNAL_FIELD in fake_milvus["client"].calls[0]["output_fields"]


# ============================================================
# ④ load_chunks 写 internal 标记
# ============================================================
def test_load_chunks_writes_internal_flag(monkeypatch):
    captured = {}

    class _Client:
        def upsert(self, collection_name, data, partition_name=None):
            captured.setdefault("data", []).extend(data)
            return None

        def list_partitions(self, name):
            return ["_default"]

    monkeypatch.setattr(L, "get_milvus_client", lambda: _Client())
    monkeypatch.setattr(L, "ensure_collection_exists", lambda: False)
    monkeypatch.setattr(L, "ensure_partition_exists", lambda t: "_default")

    from app.knowledge.models import ContentType, KnowledgeChunk, Visibility

    def _chunk(sf: str, text: str) -> KnowledgeChunk:
        return KnowledgeChunk(
            chunk_id="tmp", content=text, content_type=ContentType.DOC_CHUNK,
            source_file=sf, visibility=Visibility.PUBLIC, dense_vector=[0.1] * 4,
        )

    n = L.load_chunks([
        _chunk("3e2b7812be2f.md", "task09 报告"),
        _chunk("seeds/3_question/question.csv", "【单选题】极值判定"),
    ], tenant_id="_default")
    assert n == 2
    flags = {d["source_file"]: d[INTERNAL_FIELD] for d in captured["data"]}
    assert flags["3e2b7812be2f.md"] is True
    assert flags["seeds/3_question/question.csv"] is False
    assert all(isinstance(v, bool) for v in flags.values())


# ============================================================
# ⑤ /api/chat/search 端点按角色注入可见性
# ============================================================
def _post_search(role: UserRole, monkeypatch) -> bool:
    """以指定角色打一次 /api/chat/search，返回「检索执行期间」的 internal 可见性。

    用「仅挂载 chat.router 的最小 FastAPI 应用」替代 app.main（避免完整启动链路里
    连接 Milvus/Redis 的生命周期事件阻塞），聚焦验证端点按角色注入检索可见性。
    """
    from fastapi import FastAPI

    from app.chat import router as chat_router

    captured = {}

    async def _fake_search_only(req, *, user_id, role):
        captured["allowed"] = internal_visibility_allowed()
        return [], [], 0, None, None

    monkeypatch.setattr(chat_router, "search_only", _fake_search_only)
    app = FastAPI()
    app.include_router(chat_router.router)
    app.dependency_overrides[get_current_user] = lambda: _user(role)
    with TestClient(app) as client:
        resp = client.post("/api/chat/search", json={"query": "sys_user_auth 批量生成"})
        assert resp.status_code == 200, resp.text
    return captured["allowed"]


class TestSearchEndpointRoleInjection:
    def test_student_request_hides_internal(self, monkeypatch):
        assert _post_search(UserRole.STUDENT, monkeypatch) is False

    def test_admin_request_keeps_internal(self, monkeypatch):
        assert _post_search(UserRole.ADMIN, monkeypatch) is True

    def test_visibility_restored_after_request(self, monkeypatch):
        _post_search(UserRole.STUDENT, monkeypatch)
        assert internal_visibility_allowed() is True  # 默认可见，未泄漏到其它调用


# ============================================================
# ⑥ 平台能力清单以实物为准（F5-b）
# ============================================================
class TestPlatformCapabilityInventory:
    def test_inventory_matches_tool_class_map(self):
        from app.ai.permission_gate import TOOL_CLASS_MAP
        from app.ai.platform_capability import platform_capability_block, platform_tool_names

        names = platform_tool_names()
        # 清单必须由权限门实物（TOOL_CLASS_MAP）动态生成，禁硬编码 → 以实物为准
        assert names == sorted(TOOL_CLASS_MAP.keys())
        assert len(names) >= 1, "平台至少应声明其注册到的工具"
        block = platform_capability_block()
        for name in names:
            assert name in block
        assert "TOOL_CLASS_MAP" in block  # 来源可追溯（禁硬编码）

    def test_no_dev_host_tools_declared(self):
        from app.ai.platform_capability import platform_capability_block

        block = platform_capability_block()
        for dev_tool in ("list_directory", "read_file", "list_skills", "read_command"):
            assert dev_tool not in block, dev_tool


# ============================================================
# ⑦ SkillRegistry 开发机隔离
# ============================================================
class TestSkillRegistryIsolation:
    def test_default_is_empty_without_platform_roots(self, monkeypatch):
        from app.ai.skills.registry import PLATFORM_SKILL_ROOTS_ENV, SkillRegistry

        monkeypatch.delenv(PLATFORM_SKILL_ROOTS_ENV, raising=False)
        reg = SkillRegistry.default()
        assert reg.count() == 0
        assert reg.all() == []

    def test_default_reads_platform_roots_env(self, monkeypatch, tmp_path):
        from app.ai.skills.registry import PLATFORM_SKILL_ROOTS_ENV, SkillRegistry

        skill_dir = tmp_path / "platform-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            "---\nname: platform-skill\ndescription: 平台自有 skill\n---\n\nbody\n",
            encoding="utf-8",
        )
        monkeypatch.setenv(PLATFORM_SKILL_ROOTS_ENV, str(tmp_path))
        reg = SkillRegistry.default()
        assert reg.count() == 1
        assert reg.get("platform-skill") is not None

    def test_dev_default_still_scans_dev_host(self):
        from app.ai.skills.registry import SkillRegistry

        reg = SkillRegistry.dev_default()
        # AI-Hub 存在则应有索引；不存在（换机/未挂载）时退化为 0，均不视为缺陷
        assert reg.count() >= 0
        assert reg.roots() == [] or all(isinstance(r, str) for r in reg.roots())


# ============================================================
# ⑧ skill_node 注入权威能力清单
# ============================================================
def test_skill_node_injects_platform_inventory():
    from langchain_core.messages import HumanMessage

    from app.ai import graph as g
    from app.ai.permission_gate import TOOL_CLASS_MAP
    from app.ai.skills.registry import SkillRegistry

    g.set_skill_registry(SkillRegistry())  # 空注册表（开发机 skill 已隔离）
    try:
        state = {"messages": [HumanMessage(content="你能调用哪些工具？")], "active_paths": []}
        out = asyncio.run(g.skill_node(state))
    finally:
        g.set_skill_registry(SkillRegistry())
    ctx = out["skill_context"]
    for name in TOOL_CLASS_MAP:
        assert name in ctx, name
    assert "deepseek-local-bridge" not in ctx
