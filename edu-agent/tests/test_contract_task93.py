# -*- coding: utf-8 -*-
"""task93 契约测试：R2 skill 机制（self-critique 维度4 结构性缺失补全）。

执行方式：in-process + fake LLM/tool（不连真实 LLM/MCP），遵守测试窗口纪律（无真实 LLM 调用）。

GWT：
① Given AI-Hub skills（计划 56，实际全部），When registry 启动，Then 全部索引
② Given 触发匹配，When 决策，Then body 按需注入（不进前缀）
③ Given allowed-tools，When 执行，Then 该轮工具免授权（context:fork 走 task92 runner）

竞品对标：agentskills.io 标准 + Claude Code skills 文档（code.claude.com/docs/en/skills，
self-critique §〇 已抓取全文）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ai.skills import SkillRegistry, loader, trigger, fork_exec
from app.ai.skills.runtime import Skill, SKILL_DESCRIPTION_MAX, parse_skill_md

AI_HUB_SKILLS = r"D:\.ai-hub\skills"
PROJECT_SKILLS = r"E:\stu\project\stu\EduAgent实施手册\.claude\skills"


def _write_skill(tmp: Path, name: str, body: str, **fm) -> Path:
    d = tmp / name
    d.mkdir(parents=True, exist_ok=True)
    fm_lines = ["---"]
    fm_lines.append(f"name: {name}")
    if "description" in fm:
        fm_lines.append(f"description: {fm['description']}")
    for k in ("paths", "context", "allowed_tools", "disable_model_invocation", "agent"):
        if k in fm and fm[k] is not None:
            if k == "paths":
                items = fm[k]
                fm_lines.append("paths:")
                for it in items:
                    fm_lines.append(f"  - \"{it}\"")  # 加引号避免 YAML 将 **/*.py 解析为 alias
            elif k == "allowed_tools":
                fm_lines.append(f"allowed-tools: {' '.join(fm[k])}")
            elif k == "disable_model_invocation":
                fm_lines.append(f"disable-model-invocation: {str(fm[k]).lower()}")
            else:
                fm_lines.append(f"{k}: {fm[k]}")
    fm_lines.append("---")
    (d / "SKILL.md").write_text("\n".join(fm_lines) + "\n" + body, encoding="utf-8")
    return d


# ═══════════════════════════════════════════════════════════
# GWT① 全索引
# ═══════════════════════════════════════════════════════════
class TestIndexing:
    def test_temp_dir_all_indexed(self, tmp_path: Path):
        """临时目录 N 个 skill 全部被索引。"""
        for i in range(7):
            _write_skill(tmp_path, f"skill{i}", f"body{i}", description=f"desc{i}")
        reg = SkillRegistry.from_roots([tmp_path])
        assert reg.count() == 7
        assert set(reg.names()) == {f"skill{i}" for i in range(7)}
        for i in range(7):
            assert reg.get(f"skill{i}") is not None
            assert reg.get(f"skill{i}").body == f"body{i}"

    def test_real_aihub_all_indexed(self):
        """真实 AI-Hub corpus：索引数 == 独立枚举到的 SKILL.md 文件数（全部索引）。"""
        root = Path(AI_HUB_SKILLS)
        if not root.exists():
            pytest.skip("AI-Hub 不存在（非本机环境）")
        reg = SkillRegistry.from_roots([root])
        expected = len(list(root.rglob("SKILL.md")))
        assert reg.count() == expected
        assert reg.count() > 0
        # 每个 skill 均可按目录索引取回
        for s in reg.all():
            assert s.name
            assert reg.get_by_dir(s.source_dir) is not None

    def test_project_skills_absent_ok(self, tmp_path: Path):
        """项目 .claude/skills 不存在时不报错（缺省 root 容错）。"""
        _write_skill(tmp_path, "p1", "b1", description="d1")
        reg = SkillRegistry.from_roots([tmp_path, PROJECT_SKILLS])
        # 项目 skills 目录不存在 → 仅 tmp 的 1 个被索引
        assert reg.count() == 1

    def test_parse_error_still_indexed(self, tmp_path: Path):
        """frontmatter 损坏的 SKILL.md 仍计入索引（不丢索引）。"""
        bad = tmp_path / "broken"
        bad.mkdir()
        (bad / "SKILL.md").write_text("---not valid yaml: [unclosed\nbody text", encoding="utf-8")
        reg = SkillRegistry.from_roots([tmp_path])
        assert reg.count() == 1
        s = reg.get("broken")
        assert s is not None
        assert s.parse_error is not None  # 记录告警但不丢


# ═══════════════════════════════════════════════════════════
# GWT② body 不进前缀 / 按需注入 + 1536 截断
# ═══════════════════════════════════════════════════════════
class TestProgressiveDisclosure:
    def test_body_not_in_listing(self, tmp_path: Path):
        marker = "UNIQUE_BODY_MARKER_ZZZ_9f3a"
        _write_skill(
            tmp_path, "viz", f"short desc for viz",
            description="short desc for viz",
        )
        # 给 body 注入唯一标记
        d = tmp_path / "viz"
        (d / "SKILL.md").write_text(
            "---\nname: viz\ndescription: short desc for viz\n---\n"
            f"Here is the body with {marker} inside.",
            encoding="utf-8",
        )
        reg = SkillRegistry.from_roots([tmp_path])
        s = reg.get("viz")
        listing = loader.build_description_listing(reg.all())
        # 不变量：常驻清单不含 body 标记
        assert marker not in listing
        assert "short desc for viz" in listing
        # 按需加载才拿到 body
        assert marker in loader.load_body(s)
        assert loader.contains_body(listing, s) is False

    def test_description_truncated_at_1536(self):
        long_desc = "x" * 2000
        s = Skill(name="big", description=long_desc)
        trunc = loader.truncate_description(s.description)
        assert len(trunc) == SKILL_DESCRIPTION_MAX + 1  # 1536 + "…"
        assert trunc.endswith("…")
        # 不超过 1536 的主体
        assert trunc[:-1] == "x" * SKILL_DESCRIPTION_MAX

    def test_listing_includes_all_skills(self, tmp_path: Path):
        for i in range(5):
            _write_skill(tmp_path, f"s{i}", f"b{i}", description=f"desc number {i}")
        reg = SkillRegistry.from_roots([tmp_path])
        listing = loader.build_description_listing(reg.all())
        for i in range(5):
            assert f"s{i}: desc number {i}" in listing


# ═══════════════════════════════════════════════════════════
# GWT③ allowed-tools 该轮免授权 + context:fork
# ═══════════════════════════════════════════════════════════
class TestAllowedToolsAndFork:
    def test_is_preauthorized(self):
        s = Skill(name="mermaid", description="d", allowed_tools=("Read", "Write", "Edit"))
        assert fork_exec.is_preauthorized(s, "Read") is True
        assert fork_exec.is_preauthorized(s, "Write") is True
        assert fork_exec.is_preauthorized(s, "Bash") is False

    def test_permission_gate_cycle(self):
        s = Skill(name="mermaid", description="d", allowed_tools=("Read", "Write"))
        gate = fork_exec.PermissionGate()
        gate.activate(s, turn=1)
        assert gate.is_authorized(s, "Read") is True
        assert gate.is_authorized(s, "Bash") is False
        # 未激活的 skill 不授权
        other = Skill(name="other", description="d", allowed_tools=())
        assert gate.is_authorized(other, "Read") is False
        gate.deactivate(s)
        assert gate.is_authorized(s, "Read") is False

    async def test_fork_executes_via_runner(self, tmp_path: Path):
        """context:fork 的 skill 走 task92 run_subagent（独立子代理上下文）。"""
        _write_skill(
            tmp_path, "super", "fork body instructions",
            description="run pipeline", context="fork", allowed_tools=("Read",),
        )
        reg = SkillRegistry.from_roots([tmp_path])
        s = reg.get("super")
        assert s.is_fork

        calls = {"n": 0}

        async def fake_llm(messages, model):
            calls["n"] += 1
            if calls["n"] == 1:
                return json.dumps({"tool": "Read", "args": {"file": "x"}})
            return json.dumps({"tool": None, "final": "FORK_DONE_SUMMARY"})

        async def read_tool(args=None):
            return {"content": "file body"}

        res = await fork_exec.exec_skill(
            s, objective="do the task", llm=fake_llm,
            tool_services={"Read": read_tool},
        )
        assert res.mode == "fork"
        assert res.ok
        assert "FORK_DONE_SUMMARY" in res.summary
        # 预授权信息透出
        assert "Read" in res.preauthorized

    async def test_inline_injects_body(self, tmp_path: Path):
        """非 fork skill 走 inline：body 注入当前轮（body_injected=True）。"""
        _write_skill(tmp_path, "lookup", "inline body content here", description="lookup lib")
        reg = SkillRegistry.from_roots([tmp_path])
        s = reg.get("lookup")
        assert not s.is_fork
        res = await fork_exec.exec_skill(s, objective="q")
        assert res.mode == "inline"
        assert res.body_injected is True


# ═══════════════════════════════════════════════════════════
# 触发：description / paths / /skill + disable-model-invocation
# ═══════════════════════════════════════════════════════════
class TestTrigger:
    def _registry(self, tmp_path: Path) -> SkillRegistry:
        _write_skill(
            tmp_path, "mermaid",
            "body", description="Generate Mermaid diagrams from user requirements for flows and sequences",
        )
        _write_skill(
            tmp_path, "py-linter", "body",
            description="Lint and fix Python code style issues",
            paths=["**/*.py", "src/**"],
        )
        _write_skill(
            tmp_path, "pick-ui", "body",
            description="Pick the right frontend UI library for a task",
            disable_model_invocation=True,
        )
        return SkillRegistry.from_roots([tmp_path])

    def test_description_match(self, tmp_path: Path):
        reg = self._registry(tmp_path)
        hits = trigger.match_by_description(reg.all(), "please generate a mermaid diagram for the login flow")
        names = [s.name for s in hits]
        assert "mermaid" in names
        assert "pick-ui" not in names  # disable-model-invocation 不参加自动匹配

    def test_paths_trigger(self, tmp_path: Path):
        reg = self._registry(tmp_path)
        hits = trigger.match_by_paths(reg.all(), ["src/app/main.py", "README.md"])
        names = [s.name for s in hits]
        assert "py-linter" in names
        assert "mermaid" not in names

    def test_slash_manual_trigger(self, tmp_path: Path):
        reg = self._registry(tmp_path)
        # disable-model-invocation 的 skill 仅手动可触发
        hits = trigger.match_by_slash(reg.all(), "use /pick-ui to choose a chart lib")
        assert [s.name for s in hits] == ["pick-ui"]

    def test_decide_dedup(self, tmp_path: Path):
        reg = self._registry(tmp_path)
        hits = trigger.decide(
            reg.all(),
            "generate a mermaid diagram",
            active_paths=["src/x.py"],
        )
        names = [s.name for s in hits]
        assert "mermaid" in names
        assert "py-linter" in names
        assert len(names) == len(set(names))  # 去重
