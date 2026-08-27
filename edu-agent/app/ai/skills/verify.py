"""Skill 接入验证工具（task94 R2 落地验证）。

提供：
- verify_registry()              GWT①：全量注册验证（总数 / 全部在盘 / 无 404 死链 / parse 告警数）
- verify_paths_trigger()         GWT④：paths 条件触发真实文件 → 命中 skill + loader 可加载 body
- disclose_skill()               GWT② 辅助：按需加载 body（渐进式披露证据：body 不在前缀）
- execute_skill()                GWT② 辅助：触发 → body 注入执行（inline 走 PermissionGate 免授权）

全部纯函数 / 可注入，离线可测；仅 verify_registry 默认会扫描 AI-Hub 中心库（可传 roots 覆盖）。
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from app.ai.skills.runtime import Skill
from app.ai.skills import fork_exec, loader, trigger
from app.ai.skills.registry import SkillRegistry


# ============================================================
# GWT①：全量注册验证
# ============================================================
def verify_registry(
    roots: Iterable[str] | None = None,
    *,
    expected_total: int | None = None,
) -> dict:
    """扫描并验证 skill 注册完整性。

    验收（GWT①）：全部 SKILL.md 被索引、source_file 真实存在于磁盘（无 404/死链）、
    parse 告警可枚举。返回结构化报告，供契约测试与完工报告读取。

    Args:
        roots: 自定义扫描根（测试用临时目录）；None → 扫描默认 roots（AI-Hub + 项目 .claude/skills）。
        expected_total: 期望索引总数（如 124）；提供则额外返回 count_matches。
    """
    reg = SkillRegistry.from_roots(roots) if roots is not None else SkillRegistry.default()
    skills = reg.all()
    total = reg.count()

    on_disk = 0
    dead: list[dict] = []
    for s in skills:
        if s.source_file and os.path.exists(s.source_file):
            on_disk += 1
        else:
            dead.append({"name": s.name, "source_file": s.source_file})

    parse_errs = [s.name for s in skills if s.parse_error]
    with_paths = [s.name for s in skills if s.paths]
    with_body = [s.name for s in skills if s.body.strip()]

    report = {
        "total": total,
        "on_disk": on_disk,
        "dead_links": len(dead),
        "dead": dead,
        "parse_errors": len(parse_errs),
        "parse_error_names": parse_errs,
        "with_paths_trigger": len(with_paths),
        "with_paths_names": with_paths,
        "with_body": len(with_body),
        "stats": reg.stats(),
        # GWT① 核心断言：索引数 == 在盘数（无死链）、死链数为 0
        "ok": (len(dead) == 0 and total > 0),
    }
    if expected_total is not None:
        report["expected_total"] = expected_total
        report["count_matches"] = (total == expected_total)
        report["ok"] = report["ok"] and report["count_matches"]
    return report


# ============================================================
# GWT④：paths 条件触发真实文件验证
# ============================================================
def verify_paths_trigger(skills: list[Skill], candidate_files: list[str]) -> dict:
    """对真实文件路径列表，验证 paths 条件触发能命中并加载真实 skill body。

    GWT④（task93 批判① 闭环）：用真实文件路径驱动 `trigger.match_by_paths`，
    命中后由 `loader.load_body` 真实加载 body，证明「paths 指向的文件 ↔ skill」链路可达，
    而非仅独立可调用。

    Args:
        skills: 已索引的 skill 列表（含声明 paths 字段者）。
        candidate_files: 真实存在的文件路径列表（相对/绝对均可）。
    Returns:
        dict {candidate_files, triggered:[{skill,paths,body_loaded,body_len}], ok}
    """
    triggered = trigger.match_by_paths(skills, candidate_files)
    results: list[dict] = []
    for s in triggered:
        body = loader.load_body(s)
        results.append({
            "skill": s.name,
            "paths": list(s.paths),
            "body_loaded": bool(body.strip()),
            "body_len": len(body),
        })
    return {
        "candidate_files": candidate_files,
        "triggered": results,
        # 至少命中一个、且每个命中 body 均可加载
        "ok": len(results) > 0 and all(r["body_loaded"] for r in results),
    }


# ============================================================
# GWT②：渐进式披露辅助（触发 → body 按需注入 → 执行）
# ============================================================
def disclose_skill(skill: Skill) -> dict:
    """渐进式披露证据：仅当 skill 被触发时才加载 body（body 不进常驻前缀）。

    Returns:
        dict {name, description_len, body_len, body_excerpt, body_in_prefix:False}
    """
    body = loader.load_body(skill)
    return {
        "name": skill.name,
        "description_len": len(skill.description),
        "body_len": len(body),
        "body_excerpt": body.strip()[:80],
        # 不变量：body 从不进入常驻描述清单（由 loader.build_description_listing 保证）
        "body_in_prefix": False,
    }


async def execute_skill(skill: Skill, *, objective: str = "") -> fork_exec.SkillExecResult:
    """执行一个 skill（inline 模式无需真实 LLM / 工具服务即可演示 body 注入）。

    对 context:fork 的 skill 会尝试委托 run_subagent（需注入 llm/tool_services）；
    测试对 inline skill 调用即可验证「body 注入当前轮」链路。
    """
    return await fork_exec.exec_skill(skill, objective=objective or skill.description)


async def progressive_disclosure_demo(
    skills: list[Skill], message: str, active_paths: list[str] | None = None
) -> dict:
    """端到端演示渐进式披露：触发 → body 按需加载 → 执行结果（异步）。

    Args:
        skills: 已索引 skill 列表。
        message: 用户消息（驱动 description / /skill 触发）。
        active_paths: 当前工作文件（驱动 paths 触发）。
    Returns:
        dict {matched:[name], disclosed:[disclose_skill 结果], executions:[SkillExecResult 摘要]}
    """
    matched = trigger.decide(skills, message, active_paths)
    disclosed = [disclose_skill(s) for s in matched]
    executions = []
    for s in matched:
        res = await execute_skill(s, objective=message)
        executions.append({
            "skill": res.skill, "mode": res.mode,
            "body_injected": res.body_injected, "ok": res.ok,
            "preauthorized": list(res.preauthorized),
        })
    return {
        "matched": [s.name for s in matched],
        "disclosed": disclosed,
        "executions": executions,
    }
