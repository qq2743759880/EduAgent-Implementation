# -*- coding: utf-8 -*-
"""task-S1 全流程 HITL 护栏（非单点审批）。

统一护栏 HitlGate：四步状态机 explain → propose → approve → execute。
高风险动作（write_file / exec_command / network_access / refund）执行前必过 Gate，未批准零执行（AC1）。
可选 AI 审查 AI（reviewer 子代理，对齐 Codex auto-review）：同动作类型连续 3 次被拒 →
第 4 次熔断升级（status=escalated，需管理员 force_approve）（AC4）。

设计对齐：
  - Claude 解释→提议→同意→行动 透明护栏
  - Codex auto-review 3 连续拒绝熔断（https://developers.openai.com/codex/concepts/sandboxing/auto-review）

纯逻辑与 IO 分离（对齐 task-T1 retry_loop 设计）：
  - `run_hitl_gate` 接受注入的 store / reviewer_fn / executor_fn，可在**无 DB / 无 LLM / 无 Redis**
    环境下纯测（契约测试用 MemHitlStore + fake reviewer + fake executor）。
  - DB / Redis / OTel / reviewer 子代理等 IO 全部**惰性导入**，模块级 import 不触发任何外部依赖。
"""
from __future__ import annotations

import inspect
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Protocol


# ═══════════════════════════════════════════════════════
# 枚举与数据契约
# ═══════════════════════════════════════════════════════
class HitlActionType(str, Enum):
    WRITE_FILE = "write_file"
    EXEC_COMMAND = "exec_command"
    NETWORK_ACCESS = "network_access"
    REFUND = "refund"


class RiskLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class HitlStatus(str, Enum):
    PENDING = "pending"      # 已生成 explain/propose，等待人工/AI 审批
    APPROVED = "approved"    # 人工已批准，但尚无执行器（调用方后续执行）
    REJECTED = "rejected"    # 被拒绝（人工拒绝 / 超时自动拒绝）
    EXECUTED = "executed"    # 批准后已执行
    ESCALATED = "escalated"  # AI 审查拒绝 / 熔断，需管理员 force_approve


@dataclass
class HitlAction:
    """一个待审批的高风险动作。"""
    action_type: HitlActionType
    target: str
    params: dict = field(default_factory=dict)
    risk_level: str = "L2"
    explain_text: str = ""
    propose_text: str = ""
    trace_id: str = ""
    operator: str = ""          # 触发者 / 待审批操作者标识
    action_id: str = ""         # 空 → 自动生成
    server_id: int | None = None  # MCP 写工具场景：来源 server（供执行阶段定位）


@dataclass
class HitlResult:
    action_id: str
    status: str
    explain_text: str = ""
    propose_text: str = ""
    executed: bool = False
    result: Any = None
    ai_verdict: str = ""        # approve | reject | escalate | breaker
    ai_reason: str = ""
    ai_confidence: float | None = None
    needs_admin: bool = False   # escalated 状态需管理员放行
    reject_count: int = 0
    record: dict | None = None  # 落库后的完整审计记录


@dataclass
class HitlConfig:
    risk_threshold: str = "L2"
    pending_ttl_s: int = 600
    ai_review: bool = False
    reject_breaker: int = 3
    operator: str = ""


# ═══════════════════════════════════════════════════════
# 类型别名
# ═══════════════════════════════════════════════════════
class HitlApprovalStore(Protocol):
    """审批存储后端协议（测试注入 MemHitlStore；生产用 MysqlHitlStore）。"""
    async def create(self, record: dict) -> str: ...
    async def get(self, action_id: str) -> dict | None: ...
    async def update(self, action_id: str, *, status: str | None = None, **fields) -> None: ...
    async def get_reject_count(self, action_type: str) -> int: ...
    async def incr_reject(self, action_type: str, ttl_s: int) -> int: ...
    async def reset_reject(self, action_type: str) -> None: ...
    async def load_pending_expired(self, before_ts: float) -> list[dict]: ...


ReviewerFn = Callable[[str, str, dict], Awaitable[dict]]
"""AI 审查函数：(action_type, propose_text, params) -> {verdict, reason, confidence}。"""
ExecutorFn = Callable[[HitlAction], Awaitable[Any]]
"""动作执行器：接收 HitlAction，返回执行结果（任意）。"""


# ═══════════════════════════════════════════════════════
# 解释 / 提议 模板（用户可见，AC2）
# ═══════════════════════════════════════════════════════
_ACTION_LABEL = {
    HitlActionType.WRITE_FILE: "写文件/写数据",
    HitlActionType.EXEC_COMMAND: "执行命令",
    HitlActionType.NETWORK_ACCESS: "网络访问",
    HitlActionType.REFUND: "退款",
}
_RISK_LABEL = {"L1": "低", "L2": "中", "L3": "高"}


def _default_explain(a: HitlAction) -> str:
    label = _ACTION_LABEL.get(a.action_type, a.action_type.value)
    return (f"即将执行【{label}】高风险操作（风险等级 {a.risk_level}）。"
            f"目标：{a.target}；该操作可能产生不可逆的副作用。"
            f"请在确认参数合法与权限充足后批准。")


def _default_propose(a: HitlAction) -> str:
    label = _ACTION_LABEL.get(a.action_type, a.action_type.value)
    return (f"执行方案：{label} → 目标 {a.target}；"
            f"参数摘要：{json.dumps(a.params, ensure_ascii=False, default=str)[:500]}。"
            f"批准后即按此方案执行，结果将记入审计。")


def _config_from_settings() -> HitlConfig:
    try:
        from app.config import settings
        return HitlConfig(
            risk_threshold=getattr(settings, "HITL_RISK_THRESHOLD", "L2"),
            pending_ttl_s=int(getattr(settings, "HITL_PENDING_TTL_S", 600)),
            ai_review=bool(getattr(settings, "HITL_AI_REVIEW", False)),
            reject_breaker=int(getattr(settings, "HITL_REJECT_BREAKER", 3)),
            operator=getattr(settings, "HITL_OPERATOR", "") or "",
        )
    except Exception:
        return HitlConfig()


def _json(x: Any) -> str:
    try:
        return json.dumps(x if x is not None else {}, ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def _parse_json(s: Any) -> dict:
    if isinstance(s, dict):
        return s
    if isinstance(s, str) and s:
        try:
            return json.loads(s)
        except Exception:
            return {}
    return {}


def _emit_hitl_event(event: str, action_id: str, action_type: str, trace_id: str,
                     *, extra: dict | None = None) -> None:
    """best-effort 上报 HITL 埋点（task-O1 hitl 事件基座）。失败静默。"""
    try:
        from app.otel.exporter import get_otel_exporter
        exp = get_otel_exporter()
        if exp is None:
            return
        payload = {"event": event, "action_id": action_id, "action_type": action_type}
        if extra:
            payload.update(extra)
        exp.record("hitl", payload, trace_id=trace_id or None,
                   latency_ms=payload.get("latency_ms"))
    except Exception:
        pass


async def _safe_reviewer(reviewer_fn: ReviewerFn, action: HitlAction, propose_text: str, cfg: HitlConfig) -> dict:
    """调用注入的 reviewer，容错解析 verdict（异常→视为 escalate 安全优先）。支持 async reviewer_fn。"""
    try:
        out = reviewer_fn(action.action_type.value, propose_text, action.params)
        # 支持同步返回或协程（生产 reviewer 为 async fork 子代理）
        if inspect.isawaitable(out):
            out = await out
        if isinstance(out, dict) and out.get("verdict") in ("approve", "reject", "escalate"):
            return {
                "verdict": out["verdict"],
                "reason": str(out.get("reason") or ""),
                "confidence": out.get("confidence"),
            }
    except Exception as exc:  # pragma: no cover - 防御性
        return {"verdict": "escalate", "reason": f"reviewer 异常：{exc}", "confidence": None}
    return {"verdict": "escalate", "reason": "reviewer 返回无法解析", "confidence": None}


# ═══════════════════════════════════════════════════════
# 纯逻辑编排：四步状态机 + AI 审查 + 超时 + 熔断
# ═══════════════════════════════════════════════════════
async def run_hitl_gate(
    action: HitlAction,
    *,
    store: HitlApprovalStore,
    reviewer_fn: ReviewerFn | None = None,
    executor_fn: ExecutorFn | None = None,
    human_decision: bool | None = None,
    now: Callable[[], float] | None = None,
    config: HitlConfig | None = None,
    trace_id: str = "",
) -> HitlResult:
    """全流程 HITL 护栏主入口。

    流程：explain → propose → (AI 审查) → 人工 gate（approve/reject）→ execute。
    - AC1：未批准前 executor_fn **绝不**被调用（human_decision=None 或 False 都返回不执行）。
    - AC2：落库记录含 explain_text / propose_text / operator / trace_id 四字段，用户可见。
    - AC3：approval 阶段 now - created_at > pending_ttl_s → 自动 rejected（resume 时按原始创建时间）。
    - AC4：reviewer 返回 reject/escalate → escalated（需 admin）；同类型连续拒达 breaker → 第 4 次直接熔断。

    支持 resume：若 action.action_id 已存在且为 pending，则复用其审计字段与原始 created_at
    （用于超时判断），不重复建记录；若已为终态则幂等返回（避免重复执行/重复建单）。
    """
    cfg = config or _config_from_settings()
    now = now or (lambda: time.time())
    tid = trace_id or action.trace_id

    action_id = action.action_id
    existing = await store.get(action_id) if action_id else None

    if existing is not None:
        estatus = existing.get("status")
        action.action_id = action_id
        # 终态幂等返回（executed/rejected/escalated/approved 不再重复处理）
        if estatus in (HitlStatus.EXECUTED.value, HitlStatus.REJECTED.value,
                       HitlStatus.ESCALATED.value, HitlStatus.APPROVED.value):
            rec = existing
            return HitlResult(
                action_id=action_id, status=estatus,
                explain_text=rec.get("explain_text") or "",
                propose_text=rec.get("propose_text") or "",
                ai_verdict=rec.get("ai_verdict") or "",
                ai_reason=rec.get("ai_reason") or "",
                ai_confidence=rec.get("ai_confidence"),
                needs_admin=(estatus == HitlStatus.ESCALATED.value),
                reject_count=int(rec.get("reject_count") or 0),
                record=rec,
            )
        # pending → resume：复用原始 created_at / 审计字段；跳过 AI 审查（创建时已审）
        risk_level = existing.get("risk_level") or action.risk_level or "L2"
        explain_text = existing.get("explain_text") or action.explain_text or _default_explain(action)
        propose_text = existing.get("propose_text") or action.propose_text or _default_propose(action)
        created_at = float(existing.get("created_at") or now())
        operator = existing.get("operator") or action.operator or cfg.operator
    else:
        action_id = action_id or f"hitl-{action.action_type.value}-{uuid.uuid4().hex[:12]}"
        action.action_id = action_id
        risk_level = action.risk_level or "L2"
        explain_text = action.explain_text or _default_explain(action)
        propose_text = action.propose_text or _default_propose(action)
        created_at = now()
        operator = action.operator or cfg.operator
        record = {
            "action_id": action_id,
            "action_type": action.action_type.value,
            "target": action.target,
            "params_json": _json(action.params),
            "risk_level": risk_level,
            "status": HitlStatus.PENDING.value,
            "explain_text": explain_text,
            "propose_text": propose_text,
            "operator": operator,
            "approver": "",
            "trace_id": tid,
            "ai_verdict": "",
            "ai_reason": "",
            "ai_confidence": None,
            "reject_count": 0,
            "server_id": action.server_id,
            "created_at": created_at,
        }
        await store.create(record)
        _emit_hitl_event("pending_created", action_id, action.action_type.value, tid,
                         extra={"risk_level": risk_level})

    # ── AI 审查 AI（AC4，仅新建时执行；resume 跳过以免非确定重审）──
    if existing is None and cfg.ai_review and reviewer_fn is not None:
        rc = await store.get_reject_count(action.action_type.value)
        # 连续拒绝已达上限 → 第 4 次直接熔断，不再调 reviewer
        if rc >= cfg.reject_breaker:
            await store.update(
                action_id, status=HitlStatus.ESCALATED.value, ai_verdict="breaker",
                ai_reason=f"同动作类型（{action.action_type.value}）连续被拒达 {rc} 次，触发熔断，转人工升级（需管理员 force_approve）",
                reject_count=rc,
            )
            _emit_hitl_event("escalated_breaker", action_id, action.action_type.value, tid,
                             extra={"reject_count": rc})
            return HitlResult(action_id=action_id, status=HitlStatus.ESCALATED.value,
                             explain_text=explain_text, propose_text=propose_text,
                             ai_verdict="breaker",
                             ai_reason=f"同动作类型（{action.action_type.value}）连续被拒达 {rc} 次，触发熔断，转人工升级（需管理员 force_approve）",
                             needs_admin=True, reject_count=rc, record=await store.get(action_id))

        verdict = await _safe_reviewer(reviewer_fn, action, propose_text, cfg)
        if verdict["verdict"] in ("reject", "escalate"):
            new_rc = await store.incr_reject(action.action_type.value, cfg.pending_ttl_s)
            await store.update(
                action_id, status=HitlStatus.ESCALATED.value,
                ai_verdict=verdict["verdict"], ai_reason=verdict.get("reason", ""),
                ai_confidence=verdict.get("confidence"), reject_count=new_rc,
            )
            _emit_hitl_event(f"escalated_{verdict['verdict']}", action_id, action.action_type.value, tid,
                             extra={"reject_count": new_rc, "confidence": verdict.get("confidence")})
            return HitlResult(action_id=action_id, status=HitlStatus.ESCALATED.value,
                             explain_text=explain_text, propose_text=propose_text,
                             ai_verdict=verdict["verdict"], ai_reason=verdict.get("reason", ""),
                             ai_confidence=verdict.get("confidence"),
                             needs_admin=True, reject_count=new_rc, record=await store.get(action_id))
        # approve → 继续到人工 gate

    # ── 人工 gate（AC1：未批准前零执行）──
    if human_decision is None:
        return HitlResult(action_id=action_id, status=HitlStatus.PENDING.value,
                         explain_text=explain_text, propose_text=propose_text,
                         executed=False, record=await store.get(action_id))

    # AC3：超时自动拒绝（resume 时按原始 created_at 计算）
    if (now() - float(created_at)) > cfg.pending_ttl_s:
        await store.update(action_id, status=HitlStatus.REJECTED.value,
                          approver=operator,
                          ai_reason="审批超时自动拒绝")
        _emit_hitl_event("rejected_timeout", action_id, action.action_type.value, tid)
        return HitlResult(action_id=action_id, status=HitlStatus.REJECTED.value,
                         explain_text=explain_text, propose_text=propose_text,
                         executed=False, record=await store.get(action_id))

    if not human_decision:
        await store.update(action_id, status=HitlStatus.REJECTED.value,
                          approver=operator)
        _emit_hitl_event("rejected", action_id, action.action_type.value, tid)
        return HitlResult(action_id=action_id, status=HitlStatus.REJECTED.value,
                         explain_text=explain_text, propose_text=propose_text,
                         executed=False, record=await store.get(action_id))

    # 人工批准 → 执行
    if executor_fn is None:
        await store.update(action_id, status=HitlStatus.APPROVED.value,
                          approver=operator)
        return HitlResult(action_id=action_id, status=HitlStatus.APPROVED.value,
                         explain_text=explain_text, propose_text=propose_text,
                         executed=False, record=await store.get(action_id))
    result = await executor_fn(action)
    await store.update(action_id, status=HitlStatus.EXECUTED.value,
                      approver=operator, reject_count=0)
    try:
        await store.reset_reject(action.action_type.value)
    except Exception:
        pass
    _emit_hitl_event("executed", action_id, action.action_type.value, tid)
    return HitlResult(action_id=action_id, status=HitlStatus.EXECUTED.value,
                     explain_text=explain_text, propose_text=propose_text,
                     executed=True, result=result, record=await store.get(action_id))


async def force_approve(
    action_id: str,
    *,
    store: HitlApprovalStore,
    executor_fn: ExecutorFn | None = None,
    admin: str = "",
    now: Callable[[], float] | None = None,
) -> HitlResult:
    """管理员强制放行（escalated / pending / rejected 状态均可）：执行 + 落审计 + 重置拒绝计数。"""
    now = now or (lambda: time.time())
    rec = await store.get(action_id)
    if rec is None:
        raise ValueError(f"hitl action 不存在：{action_id}")
    action = HitlAction(
        action_type=HitlActionType(rec["action_type"]),
        target=rec.get("target") or "",
        params=_parse_json(rec.get("params_json")),
        risk_level=rec.get("risk_level") or "L2",
        explain_text=rec.get("explain_text") or "",
        propose_text=rec.get("propose_text") or "",
        action_id=action_id,
        trace_id=rec.get("trace_id") or "",
        operator=rec.get("operator") or "",
        server_id=rec.get("server_id"),
    )
    if executor_fn is not None:
        result = await executor_fn(action)
    else:
        result = None
    await store.update(action_id, status=HitlStatus.EXECUTED.value,
                      approver=admin or "admin", reject_count=0,
                      ai_reason=(rec.get("ai_reason") or "") + " | force_approve")
    try:
        await store.reset_reject(action.action_type.value)
    except Exception:
        pass
    _emit_hitl_event("force_approved", action_id, action.action_type.value, action.trace_id,
                     extra={"admin": admin})
    return HitlResult(action_id=action_id, status=HitlStatus.EXECUTED.value,
                     explain_text=action.explain_text, propose_text=action.propose_text,
                     executed=executor_fn is not None, result=result,
                     needs_admin=False, record=await store.get(action_id))


async def sweep_expired_pending(
    *, store: HitlApprovalStore, now: Callable[[], float] | None = None,
    ttl_s: int | None = None,
) -> dict:
    """后台扫描：pending 超 TTL → 自动拒绝（AC3 后台路径）。返回 {scanned, rejected}。"""
    now = now or (lambda: time.time())
    ttl = ttl_s if ttl_s is not None else _config_from_settings().pending_ttl_s
    before = now() - ttl
    expired = await store.load_pending_expired(before)
    rejected = 0
    for rec in expired:
        await store.update(rec["action_id"], status=HitlStatus.REJECTED.value,
                          ai_reason="审批超时自动拒绝（后台扫描）")
        rejected += 1
    return {"scanned": len(expired), "rejected": rejected}


# ═══════════════════════════════════════════════════════
# 内存实现（测试默认；生产降级也可用）
# ═══════════════════════════════════════════════════════
class MemHitlStore:
    """进程内审批存储（契约测试用，无外部依赖）。"""

    def __init__(self) -> None:
        self._by_id: dict[str, dict] = {}
        self._reject: dict[str, int] = {}
        self._reject_ttl: dict[str, float] = {}

    async def create(self, record: dict) -> str:
        self._by_id[record["action_id"]] = dict(record)
        return record["action_id"]

    async def get(self, action_id: str) -> dict | None:
        rec = self._by_id.get(action_id)
        return dict(rec) if rec else None

    async def update(self, action_id: str, *, status: str | None = None, **fields) -> None:
        rec = self._by_id.get(action_id)
        if rec is None:
            return
        if status is not None:
            rec["status"] = status
        for k, v in fields.items():
            rec[k] = v

    async def get_reject_count(self, action_type: str) -> int:
        return int(self._reject.get(action_type, 0))

    async def incr_reject(self, action_type: str, ttl_s: int) -> int:
        self._reject[action_type] = int(self._reject.get(action_type, 0)) + 1
        self._reject_ttl[action_type] = time.time() + ttl_s
        return self._reject[action_type]

    async def reset_reject(self, action_type: str) -> None:
        self._reject[action_type] = 0

    async def load_pending_expired(self, before_ts: float) -> list[dict]:
        out = []
        for rec in self._by_id.values():
            if rec.get("status") == HitlStatus.PENDING.value:
                ca = rec.get("created_at") or 0
                try:
                    ca = float(ca)
                except Exception:
                    ca = 0
                if ca < before_ts:
                    out.append(dict(rec))
        return out


# ═══════════════════════════════════════════════════════
# 生产实现：MySQL 表 + Redis 拒绝计数（惰性导入）
# ═══════════════════════════════════════════════════════
def _default_hitl_store() -> HitlApprovalStore:
    """生产默认存储后端（MySQL hitl_approval 表 + Redis 拒绝计数）。"""
    return MysqlHitlStore()


class _RedisRejectCounter:
    """同动作类型拒绝计数（Redis `hitl:reject:{action_type}`，TTL 兜底）。

    Redis 不可用时降级进程内 dict，保证熔断逻辑不因 Redis 抖动而崩。
    """

    def __init__(self, redis, *, ttl_s: int = 600) -> None:
        self._redis = redis
        self._ttl_s = ttl_s
        self._mem: dict[str, int] = {}

    async def get(self, action_type: str) -> int:
        if self._redis is not None:
            try:
                v = await self._redis.get(f"hitl:reject:{action_type}")
                return int(v) if v else 0
            except Exception:
                pass
        return int(self._mem.get(action_type, 0))

    async def increment(self, action_type: str) -> int:
        if self._redis is not None:
            try:
                key = f"hitl:reject:{action_type}"
                n = await self._redis.incr(key)
                if n == 1:
                    try:
                        await self._redis.expire(key, self._ttl_s)
                    except Exception:
                        pass
                return int(n)
            except Exception:
                pass
        self._mem[action_type] = int(self._mem.get(action_type, 0)) + 1
        return self._mem[action_type]

    async def reset(self, action_type: str) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(f"hitl:reject:{action_type}")
            except Exception:
                pass
        self._mem[action_type] = 0


class MysqlHitlStore:
    """生产存储：hitl_approval 审计表 + Redis 拒绝计数。"""

    def __init__(self) -> None:
        try:
            from app.database import get_redis
            self._rc = _RedisRejectCounter(get_redis(), ttl_s=600)
        except Exception:
            self._rc = _RedisRejectCounter(None, ttl_s=600)

    async def create(self, record: dict) -> str:
        from app.database import execute_write
        await execute_write(
            "INSERT INTO hitl_approval "
            "(action_id, action_type, target, params_json, risk_level, status, explain_text,"
            " propose_text, operator, approver, trace_id, ai_verdict, ai_reason, ai_confidence,"
            " reject_count, server_id, created_at) VALUES "
            "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FROM_UNIXTIME(%s))",
            (record["action_id"], record["action_type"], str(record.get("target") or ""),
             record.get("params_json") or "{}", record.get("risk_level") or "L2",
             record.get("status") or "pending", record.get("explain_text") or "",
             record.get("propose_text") or "", record.get("operator") or "",
             record.get("approver") or "", record.get("trace_id") or "",
             record.get("ai_verdict") or "", record.get("ai_reason") or "",
             record.get("ai_confidence"), int(record.get("reject_count") or 0),
             int(record["server_id"]) if record.get("server_id") else None,
             float(record.get("created_at") or time.time())),
        )
        return record["action_id"]

    async def get(self, action_id: str) -> dict | None:
        from app.database import fetch_one
        return await fetch_one("SELECT * FROM hitl_approval WHERE action_id=%s AND yn=1 LIMIT 1",
                               (action_id,))

    async def update(self, action_id: str, *, status: str | None = None, **fields) -> None:
        from app.database import execute_write
        sets: list[str] = []
        args: list[Any] = []
        if status is not None:
            sets.append("status=%s")
            args.append(status)
        allowed = {"approver", "ai_verdict", "ai_reason", "ai_confidence", "reject_count",
                   "explain_text", "propose_text", "operator", "target", "params_json"}
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k}=%s")
                args.append(v)
        if not sets:
            return
        sets.append("updated_at=NOW(3)")
        args.append(action_id)
        await execute_write(
            f"UPDATE hitl_approval SET {', '.join(sets)} WHERE action_id=%s AND yn=1",
            tuple(args),
        )

    async def get_reject_count(self, action_type: str) -> int:
        return await self._rc.get(action_type)

    async def incr_reject(self, action_type: str, ttl_s: int) -> int:
        return await self._rc.increment(action_type)

    async def reset_reject(self, action_type: str) -> None:
        await self._rc.reset(action_type)

    async def load_pending_expired(self, before_ts: float) -> list[dict]:
        from app.database import fetch_all
        return await fetch_all(
            "SELECT * FROM hitl_approval WHERE status='pending' AND yn=1 AND created_at < FROM_UNIXTIME(%s)",
            (before_ts,),
        )


# ═══════════════════════════════════════════════════════
# 生产 reviewer_fn 工厂（fork task92 reviewer 子代理；仅窗口内）
# ═══════════════════════════════════════════════════════
_REVIEWER_SYSPROMPT = """你是 HITL AI 审查官。给定一项高风险动作的「提议执行方案」与参数，
判断该动作是否安全可放行。只输出 JSON：
{"verdict": "approve"|"reject"|"escalate", "reason": "<简短理由>", "confidence": 0.0~1.0}
- approve：风险可控、参数合法，可转人工批准。
- reject：存在明显风险/越权/参数异常，应阻断并升级管理员。
- escalate：不确定或影响重大，转人工升级。"""


def _parse_reviewer_output(text: str) -> dict:
    if not text:
        return {"verdict": "escalate", "reason": "空输出", "confidence": None}
    t = text.strip()
    import re
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        t = m.group(0)
    try:
        obj = json.loads(t)
        if obj.get("verdict") in ("approve", "reject", "escalate"):
            return {"verdict": obj["verdict"], "reason": str(obj.get("reason") or ""),
                    "confidence": obj.get("confidence")}
    except Exception:
        pass
    return {"verdict": "escalate", "reason": "无法解析 reviewer 输出", "confidence": None}


def make_reviewer_fn() -> ReviewerFn:
    """生产 reviewer：fork task92 reviewer 子代理（独立上下文）对 propose_text 做风险审查。"""
    async def _reviewer(action_type: str, propose_text: str, params: dict) -> dict:
        from app.ai.subagents.runner import SubagentSpec, run_subagent
        spec = SubagentSpec(
            name="hitl_reviewer", description="HITL AI 审查官", tools=(),
            model="fast", maxTurns=1, system_prompt=_REVIEWER_SYSPROMPT,
        )
        objective = json.dumps(
            {"action_type": action_type, "propose": propose_text, "params": params},
            ensure_ascii=False, default=str,
        )
        res = await run_subagent(spec, objective=objective, summary_budget=300)
        return _parse_reviewer_output(res.summary)
    return _reviewer
