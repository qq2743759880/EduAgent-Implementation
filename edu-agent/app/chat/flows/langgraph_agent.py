# -*- coding: utf-8 -*-
"""LangGraph Agent 遗留模块 —— 死代码已清除（W-NEXT-DEADCODE-001）。

历史：本文件原为 Phase 4 的 4 节点 LangGraph Agent 图（agent → retrieve/tool → generate
循环，约 660 行），含导入即编译的 `agent_graph = build_agent_graph().compile()` 与入口
`run_agent`。审计 audit-edu-chat-langgraph.md P1-6 登记为死代码：六节点图（app/ai/graph.py，
非流式）与 graph_stream.py（R02 流式主路径）落地后生产链路零调用，且残留
`int(state.get("user_id", 1) or 1)` 硬编码兜底（retrieve_node/tool_node/run_agent 默认参）
——死代码中的硬编码身份是越权隐患面。W-NEXT-DEADCODE-001 已整块删除（三分类取证与
删除清单见 test-reports/WNEXTDEADCODE1-completion-report.md）。

唯一保留的活符号：`_hitl_risk_level` —— R11 HITL 写类挂起链的风险分级单一事实源。
生产消费链：graph_stream._enrich_hitl_pending_payload（graph_stream.py 内导入本符号）
→ run_chat_tool_calls(on_write_class_pending=...)（tool_calling.py：六节点图无 interrupt
节点、图内挂起不可达，写类挂起由流层承载）。消费方与测试（test_r11_hitl /
test_permission_gate / test_hitl_fix_integration）依赖本符号，禁改名/禁挪动。
"""
from __future__ import annotations


# ============================================================
# R11 HITL（contracts/reshape-r-hitl.json）：写类/外发类/危险级工具执行前 interrupt。
# 工具集 = R15 write_class_tools（admin_write）∪ course_write ∪ hitl_gate 高风险类
# （复用 executor._classify_hitl_action 分类，单一事实源，禁另造分类器）；
# 风险级用 hitl_gate.RiskLevel 映射到契约 low|medium|high。
# ============================================================
def _hitl_risk_level(tool_name: str) -> str | None:
    """判定工具是否需要 HITL 中断，返回契约风险级 low|medium|high；只读/未登记 → None（免中断）。"""
    from app.ai.hitl_gate import RiskLevel
    from app.ai.permission_gate import ADMIN_WRITE_TOOLS, COURSE_WRITE_TOOLS
    from app.mcp.executor import _classify_hitl_action

    n = (tool_name or "").strip().lower()
    risk_map = {RiskLevel.L1.value: "low", RiskLevel.L2.value: "medium", RiskLevel.L3.value: "high"}
    # W-NEXT-2 步骤3：ADMIN_WRITE_TOOLS/COURSE_WRITE_TOOLS = 契约挂起 ∪ **已注册实物**，
    # 上线后的 knowledge_import（admin_write）经此命中 high → interrupt 真实可触达（T8-C1）。
    if n in ADMIN_WRITE_TOOLS:
        return risk_map[RiskLevel.L3.value]   # write_class_tools（收藏写/积分/知识库导入/订单）→ high
    if n in COURSE_WRITE_TOOLS:
        return risk_map[RiskLevel.L2.value]   # 课程/题库写类 → medium
    if _classify_hitl_action(n) is not None:
        return risk_map[RiskLevel.L3.value]   # executor 高风险类（执行/网络/退款/写前缀）→ high
    return None
