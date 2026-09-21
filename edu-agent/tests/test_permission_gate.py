# -*- coding: utf-8 -*-
"""R15b 权限门 + ACI 错误信封测试（契约 contracts/reshape-r-aci.json 已冻结）。

R15b 变更：映射表对账实物——TOOL_CLASS_MAP 只含真实注册工具，契约写类工具名转入
CONTRACT_PENDING_TOOLS（映射挂起，仍 fail-closed deny）。

W-NEXT-2 变更（步骤3 上线写类工具）：knowledge_import 从 CONTRACT_PENDING_TOOLS
迁出 → TOOL_CLASS_MAP["knowledge_import"]="admin_write"，注册面 7 → **8**，
挂起清单 10 → **9**；因此"实物工具全放行"不再成立，须按类别断言。

覆盖：
- G1 对账：TOOL_CLASS_MAP × executor 注册面（源码实采 + mcp_tool 表实采）逐名可比
- G1 矩阵：真实工具 × 三角色 全组合（按类别断言）；契约矩阵「类别→角色」语义未变
- G2 fail-closed：契约挂起工具 / 未登记工具 / 空角色 → 一律 deny
- G4 注入源守护：get_user_info_by_id 是真实 async DB 查询（防注入点被改名后测试空转）
- G6 信封质量抽查：message 全中文无 traceback；action_hint 可执行

W-NEXT-DEADCODE-001 退役说明：原 G3（langgraph_agent.tool_node 图级 deny 路径六用例）
与 G4 角色注入四用例（langgraph_agent.run_agent + agent_graph 替身）随该文件死代码图机器
删除而退役；活路径等价覆盖：权限门单元矩阵（本文件 G1/G2/G6）+ 流式路径权限门
（test_wnext2_write_tools W2-G2）+ HITL 风险分级归一（本文件
test_norm_eliminates_case_whitespace_dual_criterion，经活符号 _hitl_risk_level）。
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.ai.permission_gate import (
    ADMIN_WRITE_TOOLS,
    CONTRACT_PENDING_TOOLS,
    COURSE_WRITE_TOOLS,
    GateDecision,
    REGISTERED_BUILTIN_TOOLS,
    REGISTERED_MCP_TOOLS,
    REGISTERED_TOOLS,
    REGISTRY_EVIDENCE,
    TOOL_CLASS_MAP,
    audit_registry,
    can_use_tool,
    class_allowed_roles,
    classify_tool,
    classify_tool_intent,
    is_write_class,
    permission_denied_message,
)

_EXECUTOR_SRC = Path(__file__).resolve().parents[1] / "app" / "mcp" / "executor.py"

# 真实注册工具（10 个）：按类别拆分——public_read 全角色放行，admin_write 仅 admin
READ_TOOL = "search_knowledge"
REAL_TOOLS = sorted(REGISTERED_TOOLS)
REAL_READ_TOOLS = sorted(n for n in REGISTERED_TOOLS if classify_tool(n) == "public_read")
REAL_WRITE_TOOLS = sorted(n for n in REGISTERED_TOOLS if classify_tool(n) in ("course_write", "admin_write"))
REAL_ADMIN_WRITE_TOOL = "knowledge_import"     # W-NEXT-2 步骤3 上线实物
REAL_ADMIN_WRITE_HITL_TOOL = "course_create"   # AUTO20 T12（CR-WRITETOOLS-001 第二批）上线实物
# 契约挂起（无实物）代表工具
PENDING_COURSE_TOOL = "question_create"
PENDING_ADMIN_TOOL = "order_create"
ALL_ROLES = ["student", "manager", "admin"]


# ============================================================
# G1 对账（R15b 核心）：映射表 ↔ 真实注册面
# ============================================================
def _executor_registered_builtins() -> set[str]:
    """从 executor.py 源码实采 `register_builtin_tool("name", ...)`。"""
    src = _EXECUTOR_SRC.read_text(encoding="utf-8")
    return set(re.findall(r'register_builtin_tool\(\s*"([^"]+)"', src))


def test_registry_reconciliation_executor_source():
    """G1：TOOL_CLASS_MAP 里的内置工具与 executor 源码注册面完全一致（双向）。"""
    found = _executor_registered_builtins()
    assert found, "executor.py 未采集到任何 register_builtin_tool，采集逻辑或注册面异常"
    assert found == set(REGISTERED_BUILTIN_TOOLS), (
        f"内置注册面与映射表声明不一致: 源码={sorted(found)} 声明={sorted(REGISTERED_BUILTIN_TOOLS)}"
    )
    # 两个内置工具都必须真的在 TOOL_CLASS_MAP 里（不能只在 REGISTERED_* 常量里）
    for name in found:
        assert name in TOOL_CLASS_MAP, f"内置工具 {name} 未进 TOOL_CLASS_MAP"


def test_registry_reconciliation_pending_absent_from_executor():
    """G1：契约挂起工具名不得出现在 executor 源码（防再次臆译补名）。"""
    src = _EXECUTOR_SRC.read_text(encoding="utf-8")
    offenders = sorted(n for n in CONTRACT_PENDING_TOOLS if n in src)
    assert not offenders, f"executor.py 中出现了挂起工具名（需人工复核是否已真实注册）: {offenders}"


def _db_mcp_tool_names() -> set[str]:
    """直连只读采集 mcp_tool（yn=1）工具名集合；不触碰 app 连接池全局状态。"""
    import asyncmy
    from app.config import settings

    async def _run() -> set[str]:
        conn = await asyncmy.connect(
            host=settings.MYSQL_HOST, port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER, password=settings.MYSQL_PASSWORD,
            db=settings.MYSQL_DATABASE, autocommit=True,
        )
        try:
            async with conn.cursor() as cur:
                await cur.execute("SELECT tool_name FROM mcp_tool WHERE yn=1")
                rows = await cur.fetchall()
            return {str(r[0]) for r in rows}
        finally:
            conn.close()

    return asyncio.run(_run())


def test_registry_reconciliation_mcp_db():
    """G1：mcp_tool 表实采覆盖映射表声明的 MCP 工具；挂起清单不得已在库。"""
    try:
        names = _db_mcp_tool_names()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB 不可用，跳过 mcp_tool 实采对账: {type(exc).__name__}: {exc}")
    missing = sorted(REGISTERED_MCP_TOOLS - names)
    assert not missing, f"映射表声明已注册但 mcp_tool 缺失（虚构？）: {missing}"
    stale = sorted(set(CONTRACT_PENDING_TOOLS) & names)
    assert not stale, f"挂起清单中的工具已真实注册，应按补登记流程移入 TOOL_CLASS_MAP: {stale}"


def test_registry_reconciliation_audit_clean():
    """G1：audit_registry 三类差异全空（缺省口径 = 2026-09-15 核对值）。"""
    rep = audit_registry()
    assert rep["mapped_but_unregistered"] == [], f"映射表含未注册工具（虚构名）: {rep}"
    assert rep["registered_but_unmapped"] == [], f"注册面工具漏登记: {rep}"
    assert rep["pending_now_registered"] == [], f"挂起工具已注册未迁移: {rep}"


def test_registry_evidence_covers_every_mapped_tool():
    """G1：TOOL_CLASS_MAP 每个工具都有出处条目（报告逐名对账表可复现）。"""
    assert set(REGISTRY_EVIDENCE) == set(TOOL_CLASS_MAP)
    for name in TOOL_CLASS_MAP:
        assert REGISTRY_EVIDENCE[name].strip(), f"{name} 缺注册出处"


# ============================================================
# G1 矩阵：真实工具 × 三角色 全组合
# ============================================================
@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("tool", REAL_READ_TOOLS)
def test_matrix_real_read_tools_all_roles_allowed(role, tool):
    """真实注册工具中的公开只读 → student/manager/admin 全放行。"""
    d = can_use_tool(role, tool)
    assert d.allowed is True, f"{role} × {tool} 应放行（public_read）"


@pytest.mark.parametrize("tool", REAL_WRITE_TOOLS)
def test_matrix_real_write_tools_only_admin_allowed(tool):
    """W-NEXT-2：已注册写类实物（knowledge_import=admin_write）→ 仅 admin 放行，
    student/manager 一律 deny + action_hint（与契约类别语义一致）。"""
    assert can_use_tool("admin", tool).allowed is True, f"admin × {tool} 应放行"
    for role in ("student", "manager", "teacher"):
        d = can_use_tool(role, tool)
        assert d.allowed is False, f"{role} × {tool} 应 deny（{classify_tool(tool)}）"
        assert d.action_hint and d.action_hint.strip()


def test_knowledge_import_is_registered_admin_write():
    """W-NEXT-2 步骤3：knowledge_import 已从挂起迁入实物映射（admin_write）。"""
    assert REAL_ADMIN_WRITE_TOOL in REGISTERED_TOOLS
    assert classify_tool(REAL_ADMIN_WRITE_TOOL) == "admin_write"
    assert REAL_ADMIN_WRITE_TOOL not in CONTRACT_PENDING_TOOLS


def test_course_create_is_registered_admin_write_t12():
    """AUTO20 T12（CR-WRITETOOLS-001 第二批）：course_create 已从挂起迁入实物映射（admin_write）。

    P2 裁定：仅 admin=allow、manager=deny（原挂起 course_write「manager 放行」矩阵语义变更）。
    """
    assert REAL_ADMIN_WRITE_HITL_TOOL in REGISTERED_TOOLS
    assert classify_tool(REAL_ADMIN_WRITE_HITL_TOOL) == "admin_write"
    assert REAL_ADMIN_WRITE_HITL_TOOL not in CONTRACT_PENDING_TOOLS
    assert can_use_tool("admin", REAL_ADMIN_WRITE_HITL_TOOL).allowed is True
    for role in ("student", "manager", "teacher"):
        d = can_use_tool(role, REAL_ADMIN_WRITE_HITL_TOOL)
        assert d.allowed is False and d.action_hint, f"P2：{role} × course_create 必须 deny"


def test_contract_matrix_class_semantics_unchanged():
    """G3：契约矩阵「类别→允许角色」语义（CR-ACI-teacher-read 2026-09-15 用户签收后：
    public_read 增补 teacher；course_write/admin_write 语义不变）。"""
    assert class_allowed_roles("public_read") == frozenset({"student", "manager", "admin", "teacher"})
    assert class_allowed_roles("course_write") == frozenset({"manager", "admin"})
    assert class_allowed_roles("admin_write") == frozenset({"admin"})
    assert len(TOOL_CLASS_MAP) == len(REGISTERED_TOOLS) == 10, (
        "真实工具面应为 10 个（AUTO20 T12 起，course_create 上线：CR-WRITETOOLS-001 第二批）"
    )


# ============================================================
# G2 fail-closed
# ============================================================
@pytest.mark.parametrize("role", ALL_ROLES)
def test_fail_closed_unregistered_tool(role):
    d = can_use_tool(role, "nonexistent_tool")
    assert d.allowed is False
    assert d.action_hint


@pytest.mark.parametrize("role", ["", "  ", "unknown", "guest"])
def test_fail_closed_unknown_role(role):
    # 未知角色（含空白/未登录；CR-ACI-teacher-read 后 teacher 已入 KNOWN_ROLES，不再属未知）→ 公开只读也 deny
    assert can_use_tool(role, READ_TOOL).allowed is False


# ---- CR-ACI-teacher-read（2026-09-15 用户签收）：teacher = 公开只读 ----
def test_teacher_public_read_allowed():
    """G1：teacher × public_read（search_knowledge）= allowed。"""
    assert can_use_tool("teacher", "search_knowledge").allowed is True


@pytest.mark.parametrize("tool", ["question_create", "question_delete"])
def test_teacher_write_denied(tool):
    """G1：teacher × 课程/题库写类（挂起工具）= denied + action_hint。

    AUTO20 T12：course_create 已迁出挂起区（admin_write 实物）——teacher deny 断言
    由 test_course_create_is_registered_admin_write_t12 承接。
    """
    d = can_use_tool("teacher", tool)
    assert d.allowed is False and d.action_hint


@pytest.mark.parametrize("tool", ["order_create"])
def test_teacher_admin_write_denied(tool):
    """G1：teacher × admin 专属（挂起工具）= denied + action_hint。

    W-NEXT-WRITE1（CR-WRITETOOLS-001 P1）：favorite_add 已迁出挂起区、改类 user_write
    ——teacher 由 deny 反转为 allow（本人收藏），断言挪入本测试下方。
    """
    d = can_use_tool("teacher", tool)
    assert d.allowed is False and d.action_hint


def test_teacher_user_write_allowed():
    """W-NEXT-WRITE1 P1：teacher × user_write（favorite_add 实物）= allowed（本人收藏）。"""
    assert can_use_tool("teacher", "favorite_add").allowed is True


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("tool", sorted(CONTRACT_PENDING_TOOLS))
def test_pending_tools_denied_for_all_roles(role, tool):
    """G2：契约挂起（无实物）工具 —— 任意角色（含 admin）一律 deny，hint 非空。"""
    d = can_use_tool(role, tool)
    assert d.allowed is False, f"{role} × {tool}（无实物工具）必须 fail-closed deny"
    assert isinstance(d, GateDecision)
    assert d.action_hint and d.action_hint.strip()


def test_pending_tools_absent_from_tool_class_map():
    """G2：挂起名已从 TOOL_CLASS_MAP 移除，转入 CONTRACT_PENDING_TOOLS。

    AUTO20 T12 起为 **7** 个（course_create 已按 CR-WRITETOOLS-001 第二批 P2 裁定上线迁出，
    改类 admin_write；此前 W-NEXT-WRITE1 迁出 favorite_add 转 user_write、
    W-NEXT-2 迁出 knowledge_import 转 admin_write 实物映射）。
    """
    assert len(CONTRACT_PENDING_TOOLS) == 7
    assert set(TOOL_CLASS_MAP) & set(CONTRACT_PENDING_TOOLS) == set()
    for name in CONTRACT_PENDING_TOOLS:
        assert classify_tool(name) is None, f"{name} 不应出现在映射表（无实物注册）"
        assert classify_tool_intent(name) == CONTRACT_PENDING_TOOLS[name], (
            f"{name} 的契约意图类别应可查（HITL/缓存判定共用）"
        )
    # 兼容别名 = 契约挂起 ∪ 已注册实物（W-NEXT-2：写类别名不再等同于挂起清单）
    assert set(COURSE_WRITE_TOOLS) == (
        {n for n, c in CONTRACT_PENDING_TOOLS.items() if c == "course_write"}
        | {n for n in REGISTERED_TOOLS if classify_tool(n) == "course_write"}
    )
    assert set(ADMIN_WRITE_TOOLS) == (
        {n for n, c in CONTRACT_PENDING_TOOLS.items() if c == "admin_write"}
        | {n for n in REGISTERED_TOOLS if classify_tool(n) == "admin_write"}
    )
    assert set(CONTRACT_PENDING_TOOLS) <= (set(COURSE_WRITE_TOOLS) | set(ADMIN_WRITE_TOOLS))
    assert REAL_ADMIN_WRITE_TOOL in ADMIN_WRITE_TOOLS


def test_all_mapping_tools_classified():
    # 映射表每个工具都能被 classify（非 None），类别必须是枚举之一
    # （W-NEXT-WRITE1/CR-WRITETOOLS-001：四枚举——user_write 首例 favorite_add）
    for name, cls in TOOL_CLASS_MAP.items():
        assert classify_tool(name) == cls
        assert cls in ("public_read", "course_write", "admin_write", "user_write")
        assert classify_tool_intent(name) == cls, "已注册实物的契约意图必须与映射一致"


# ============================================================
# W-NEXT-2 步骤1（T4-C3/C1 根因）：写类分类单一事实源
# ============================================================
WRITE_CLASS_NAMES = sorted(
    set(CONTRACT_PENDING_TOOLS)
    | {n for n in REGISTERED_TOOLS if classify_tool(n) in ("course_write", "admin_write")}
)


def test_write_class_names_cover_10():
    """W2-G1：写类名共 9 个（7 个契约挂起 + 2 个已注册实物 knowledge_import/course_create）。

    W-NEXT-WRITE1（CR-WRITETOOLS-001 P1）：favorite_add 迁出改类 user_write（本人低危写，
    不属 WRITE_CLASSES HITL 面）→ 10→9；AUTO20 T12（第二批 P2）：course_create 由挂起迁入
    实物（挂起 -1、注册面 +1）→ 总数不变仍 **9**（挂起 7 + 实物 2）。
    user_write 角色收口走矩阵+executor 强属性，不在此集。
    """
    assert len(WRITE_CLASS_NAMES) == 9, f"写类名应为 9 个: {WRITE_CLASS_NAMES}"


@pytest.mark.parametrize("name", WRITE_CLASS_NAMES)
def test_write_class_names_classified_and_not_cached(name):
    """W2-G1：每个写类名 → is_write_class True、executor._classify_hitl_action='write_file'、
    _is_cached_call=False（写类操作严禁走缓存/幂等短路）。"""
    from app.mcp.executor import _classify_hitl_action, _is_cached_call

    assert is_write_class(name) is True
    assert _classify_hitl_action(name) == "write_file", f"{name} 应判为写类高风险动作"
    assert _is_cached_call(name, {"any": 1}) is False, f"{name} 写类操作不得被判为可缓存"


def test_norm_eliminates_case_whitespace_dual_criterion():
    """第二轮复验加固：**已登记名**的大小写/空格变体不得造成「HITL 判写类、权限门判非写类」双口径。

    复验实测（修复前）：`classify_tool` 原为严格查表（不归一），而 `langgraph_agent._hitl_risk_level`
    自己做 `strip().lower()` → 同一名字两种口径。修复：`permission_gate._norm` 统一归一。

    边界（有意为之的不对称，非缺陷）：**契约挂起名/未登记名** `classify_tool` 仍返回 None
    （无实物 → `can_use_tool` 一律 deny，fail-closed）；`is_write_class` 走 `classify_tool_intent`
    （契约意图，含挂起）故判写类 —— 两条防线在「门先 deny、工具不可能执行」上方向一致。
    """
    from app.chat.flows.langgraph_agent import _hitl_risk_level

    for variant in ("Knowledge_Import", " knowledge_import ", "KNOWLEDGE_IMPORT", "KnOwLeDgE_ImPoRt"):
        assert classify_tool(variant) == "admin_write", f"归一后应命中映射: {variant!r}"
        assert is_write_class(variant) is True, f"归一后应判写类: {variant!r}"
        assert _hitl_risk_level(variant) == "high", f"HITL 同为 high（双口径消除）: {variant!r}"
        assert can_use_tool("student", variant).allowed is False, f"写类对 student 必须 deny: {variant!r}"
        assert can_use_tool("admin", variant).allowed is True, f"admin 不得因大小写被误拒: {variant!r}"

    # fail-closed 方向不被归一放宽：未登记名对所有角色仍 deny（含 admin）
    for variant in ("  Unknown_Tool  ", "Echo_Typo"):
        assert classify_tool(variant) is None, f"未登记名不得被归一命中: {variant!r}"
        assert can_use_tool("admin", variant).allowed is False, f"未登记名对 admin 也必须 deny: {variant!r}"


# ============================================================
# G3 图级 tool_node deny 路径 —— W-NEXT-DEADCODE-001 已随 langgraph_agent
# 死代码图机器（tool_node）删除退役；活路径 deny 零执行语义见
# test_wnext2_write_tools.py W2-G2（tool_calling 流式权限门）。
# ============================================================


# ============================================================
# G4 注入源守护（R15 P0-3 反哺；W-NEXT-DEADCODE-001 后仅保留活符号守护）
#     mock DB 层的 run_agent 角色注入四用例随 langgraph_agent 死代码退役；
#     活路径角色解析（tool_calling.resolve_role → 权限门）由 W2-G2 用例覆盖。
# ============================================================
def test_get_user_info_by_id_symbol_is_real_db_lookup():
    """G4：注入源确实存在且是 async DB 查询（防注入点被改名/移除后测试空转）。"""
    from app.auth.service import get_user_info_by_id

    assert asyncio.iscoroutinefunction(get_user_info_by_id)


# ============================================================
# G6 信封质量抽查
# ============================================================
def test_envelope_quality_chinese_no_traceback():
    for role, tool in [
        ("student", PENDING_ADMIN_TOOL),
        ("manager", PENDING_ADMIN_TOOL),
        ("student", PENDING_COURSE_TOOL),
        ("admin", PENDING_ADMIN_TOOL),
        ("admin", "nonexistent_tool"),
    ]:
        msg = permission_denied_message(role, tool)
        assert msg
        assert "traceback" not in msg.lower()
        assert "Traceback" not in msg
        # 全中文（不含 ASCII 可读字符混杂的错误码堆砌）
        assert any("\u4e00" <= ch <= "\u9fff" for ch in msg)
        # 面向用户：不输出堆栈/对象地址
        assert "0x" not in msg and "File " not in msg
        d = can_use_tool(role, tool)
        if not d.allowed:
            assert d.action_hint and d.action_hint.strip()


def test_denied_action_hint_actionable():
    for role, tool in [("student", "order_create"), ("student", "knowledge_import"),
                       ("admin", "nonexistent_tool")]:
        d = can_use_tool(role, tool)
        assert d.allowed is False
        # 可行动建议：包含请求动词线索（登录 / 联系 / 开通）
        assert any(k in d.action_hint for k in ("登录", "联系", "开通"))
