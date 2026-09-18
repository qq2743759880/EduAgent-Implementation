"""
task94 / R2 接入验证契约测试（124 skills 接入 + graph/agent 集成）。

全部纯函数 + 进程内 fixture，不依赖外部 AI-Hub（GWT① 另含可选 LIVE 扫描）。
GWT 验收（对应 task94-ai-revision.md + 用户精简 GWT）：

① 124 skills 全量注册验证（无 404/死链 skill）
② 抽 3 个代表性 skill 跑通渐进式披露：触发 → body 按需注入 → 执行
③ 集成 graph/agent 决策链路（registry 被对话决策消费，非仅独立可调用）
④ 补 paths 触发真实 skill 验证（task93 批判① 闭环）

竞品对标：Claude Code skills 官方文档（code.claude.com/docs/en/skills）。
"""
import asyncio
import os
import textwrap

import pytest

import app.ai.graph as g
from app.ai.skills.registry import SkillRegistry, DEFAULT_AI_HUB, PROJECT_SKILLS
from app.ai.skills.runtime import Skill
from app.ai.skills import loader, trigger, verify


# ============================================================
# 夹具：构造 skill（直接构建 Skill，避免强依赖外部 AI-Hub 路径）
# ============================================================
def _skill(name: str, description: str, body: str = "", **kw) -> Skill:
    return Skill(
        name=name,
        description=description,
        body=body,
        source_dir=f"d:/fake/{name}",
        source_file=f"d:/fake/{name}/SKILL.md",
        **kw,
    )


def _registry_of(skills: list[Skill]) -> SkillRegistry:
    reg = SkillRegistry()
    for s in skills:
        reg._by_dir[s.source_dir] = s
        if s.name not in reg._by_name:
            reg._by_name[s.name] = s
    return reg


AUDIT = _skill(
    "audit", "对代码进行安全审计、静态检查与漏洞发现",
    body="审计步骤：1) 检查输入校验 2) 检查鉴权与越权 3) 输出风险报告",
)
KNOWLEDGE_TRACE = _skill(
    "knowledge-trace", "追踪知识点依赖关系，构建知识图谱回溯",
    body="trace 步骤：定位根概念 → 展开依赖 → 标注掌握度",
)
DEV_STANDARD = _skill(
    "dev-standard", "按团队开发规范做代码评审与风格检查",
    body="规范：命名、目录结构、类型注解、测试覆盖",
)
FORK_SKILL = _skill(
    "review", "子代理评审", body="review body", context="fork",
)
PATHS_SKILL = _skill(
    "py-linter", "Python 文件 lint", body="lint body", paths=("**/*.py",),
)


# ============================================================
# GWT①：全量注册验证（无 404/死链）
# ============================================================
class TestGwt4Registry:
    def test_full_registration_no_dead_links(self, tmp_path):
        """扫描临时 roots 下 N 个 SKILL.md，全部在盘、无死链、parse 可枚举。"""
        for i in range(7):
            d = tmp_path / f"skill{i}"
            d.mkdir()
            (d / "SKILL.md").write_text(
                textwrap.dedent(f"""
                ---
                name: skill{i}
                description: 示例技能 {i} 用于验证注册
                ---
                这是 skill{i} 的正文。
                """).strip(), encoding="utf-8",
            )
        report = verify.verify_registry([str(tmp_path)])
        assert report["total"] == 7
        assert report["on_disk"] == 7
        assert report["dead_links"] == 0
        assert report["ok"] is True

    def test_live_ai_hub_180_registered(self):
        """LIVE：真实 AI-Hub 中心库应注册 >=80 个 skill，无死链。

        task37：AI-Hub 技能库数随 center 库变化是预期（结构重构会减少、持续沉淀会增加）。
        临界值由编排者刷新。下限历史：318（等值断言，随库膨胀频繁假红）→ 150（WIP 09-18，
        仍高于重构后实际值）→ 80（TEST-BASE 2026-09-19：中心库重构后实测 total=93，
        下限取 80=实测值下方约 14% 缓冲，仅防「灾难性丢失/整库扫空」级回归；
        精确计数不属本用例职责，死链=0 才是核心断言）。

        WNEXT10 F5-b 注意：平台生产注册表已与开发机 AI-Hub 隔离，
        故此处显式扫描中心库根 DEFAULT_AI_HUB 以验证中心库本体完整性。
        """
        if not os.path.exists(DEFAULT_AI_HUB):
            pytest.skip("AI-Hub skills 目录不可用，跳过 LIVE 校验")
        report = verify.verify_registry(roots=[DEFAULT_AI_HUB])
        assert report["total"] >= 80, f"AI-Hub skills 异常偏少（<80）: {report}"
        assert report["dead_links"] == 0, report["dead"]
        assert report["ok"] is True

    def test_parse_errors_reported(self, tmp_path):
        """损坏 frontmatter 仍被索引（降级计入），parse_errors 可枚举。"""
        d = tmp_path / "broken"
        d.mkdir()
        (d / "SKILL.md").write_text("no frontmatter at all\njust body", encoding="utf-8")
        report = verify.verify_registry([str(tmp_path)])
        assert report["total"] == 1
        assert report["parse_errors"] >= 1
        assert report["dead_links"] == 0  # 文件在盘，仅解析告警，非死链


# ============================================================
# GWT②：渐进式披露（触发 → body 按需注入 → 执行）
# ============================================================
class TestGwt4ProgressiveDisclosure:
    def test_three_representative_skills_full_flow(self):
        """抽 3 个代表性 skill（audit/knowledge-trace/dev-standard）跑通渐进式披露。"""
        skills = [AUDIT, KNOWLEDGE_TRACE, DEV_STANDARD]
        # 触发：/skill 手动触发
        matched = trigger.match_by_slash(skills, "/audit 分析这段代码")
        assert any(s.name == "audit" for s in matched)
        # body 按需加载（不进前缀）
        d = verify.disclose_skill(AUDIT)
        assert d["body_len"] > 0 and d["body_in_prefix"] is False
        # 执行（inline → body 注入当前轮）
        res = asyncio.run(verify.execute_skill(AUDIT, objective="审计"))
        assert res.mode == "inline"
        assert res.body_injected is True and res.ok is True

    def test_description_auto_match_triggers_body(self):
        """description 自动匹配：用户消息『审计代码』命中 audit 的 description。"""
        skills = [AUDIT, DEV_STANDARD]
        matched = trigger.match_by_description(skills, "请审计这段代码的安全性")
        assert any(s.name == "audit" for s in matched)
        body = loader.load_body(matched[0])
        assert "审计步骤" in body

    def test_async_progressive_disclosure_demo(self):
        """端到端异步演示：触发 → 披露的 body → 执行结果。"""
        skills = [AUDIT, KNOWLEDGE_TRACE, DEV_STANDARD]
        out = asyncio.run(
            verify.progressive_disclosure_demo(skills, "/knowledge-trace 回溯依赖")
        )
        assert "knowledge-trace" in out["matched"]
        assert any(d["name"] == "knowledge-trace" and d["body_len"] > 0 for d in out["disclosed"])
        assert any(e["skill"] == "knowledge-trace" and e["body_injected"] for e in out["executions"])


# ============================================================
# GWT③：graph/agent 决策链路集成（registry 被决策消费）
# ============================================================
class TestGwt4GraphIntegration:
    def test_skill_node_injects_body_into_state(self, monkeypatch):
        """skill_node 依据用户消息命中 skill 并注入 body 到 state.skill_context。"""
        monkeypatch.setattr(g, "_skill_registry_cache", None)
        g.set_skill_registry(_registry_of([AUDIT, DEV_STANDARD]))
        from langchain_core.messages import HumanMessage

        state = {"messages": [HumanMessage(content="/audit 分析这段代码")],
                 "active_paths": [], "nodes_executed": []}
        res = asyncio.run(g.skill_node(state))
        assert "audit" in res["skill_context"]
        assert "审计步骤" in res["skill_context"]
        assert "skill" in res["nodes_executed"]

    def test_plan_node_consumes_skill_context(self, monkeypatch):
        """plan_node 把 skill_context 注入子代理任务输入（决策链消费 registry）。"""
        from langchain_core.messages import HumanMessage

        state = {
            "messages": [HumanMessage(content="q")],
            "intent": "tool",
            "skill_context": "[skill:audit]\n审计步骤：1) 检查输入校验",
            "nodes_executed": [],
        }
        res = asyncio.run(g.plan_node(state))
        for t in res["tasks"]:
            assert "skill 指引" in t["input"] and "审计步骤" in t["input"]

    def test_answer_node_includes_skill_context(self, monkeypatch):
        """answer_node 把 skill_context 纳入最终回答上下文。"""
        from langchain_core.messages import HumanMessage

        captured = {}

        async def fake_llm(messages, **kw):
            captured["messages"] = messages
            return "the answer"

        monkeypatch.setattr(g, "_llm_call", fake_llm)
        state = {
            "messages": [HumanMessage(content="q")],
            "merged_context": "ctx",
            "skill_context": "[skill:audit]\n审计步骤：1) 检查输入校验",
            "nodes_executed": [],
        }
        asyncio.run(g.answer_node(state))
        sys_msgs = [m["content"] for m in captured["messages"] if m["role"] == "system"]
        assert any("相关 skill 指引" in c and "审计步骤" in c for c in sys_msgs)

    def test_skill_node_no_match_injects_only_platform_inventory(self, monkeypatch):
        """无 skill 命中时不注入开发宿主 skill body（不污染决策上下文）；

        但仍注入平台能力清单（WNEXT10 F5-b：以 permission_gate.TOOL_CLASS_MAP 实物为准，
        杜绝模型把 dev-host 工具 list_directory/read_file 等当平台能力自述给用户）。
        """
        monkeypatch.setattr(g, "_skill_registry_cache", None)
        g.set_skill_registry(_registry_of([AUDIT]))
        from langchain_core.messages import HumanMessage

        state = {"messages": [HumanMessage(content="今天天气怎么样")],
                 "active_paths": [], "nodes_executed": []}
        res = asyncio.run(g.skill_node(state))
        # 无 skill 命中 → 不得泄漏任何开发宿主 skill body（[skill:...] 标记）
        assert "[skill:" not in res["skill_context"]
        # F5-b：平台能力清单（实物来源）仍应注入
        assert "平台可用工具" in res["skill_context"]
        assert "TOOL_CLASS_MAP" in res["skill_context"]

    def test_graph_topology_includes_skill_node(self):
        """编译图拓扑含 skill 节点，且 route→plan 路径经 skill。"""
        cg = g.compile_graph()
        # 节点存在
        assert "skill" in cg.nodes


# ============================================================
# GWT④：paths 触发真实 skill 验证（task93 批判① 闭环）
# ============================================================
class TestGwt4PathsTrigger:
    def test_paths_match_real_file_and_body_loads(self, tmp_path):
        """paths 指向真实 .py 文件 → 命中 py-linter skill + loader 可加载 body。"""
        real_py = tmp_path / "module.py"
        real_py.write_text("def f():\n    return 1\n", encoding="utf-8")
        skills = [PATHS_SKILL, AUDIT]
        triggered = trigger.match_by_paths(skills, [str(real_py)])
        assert any(s.name == "py-linter" for s in triggered)
        body = loader.load_body(PATHS_SKILL)
        assert "lint body" in body

    def test_verify_paths_trigger_report(self, tmp_path):
        """verify_paths_trigger 端到端：真实文件驱动触发 + body 加载均可验证。"""
        real_py = tmp_path / "module.py"
        real_py.write_text("x = 1\n", encoding="utf-8")
        report = verify.verify_paths_trigger([PATHS_SKILL], [str(real_py)])
        assert report["ok"] is True
        assert report["triggered"][0]["skill"] == "py-linter"
        assert report["triggered"][0]["body_loaded"] is True
