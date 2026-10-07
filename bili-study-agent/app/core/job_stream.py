# -*- coding: utf-8 -*-
"""job_stream 消息契约唯一 Owner 模块（G0-QSCH；RAG v2.5 §3 Queue Failure Semantics）。

职责边界（Ownership Map："Queue Contract Owner"，管消息契约、与 Runtime Manager 管进程分离）：
- 冻结 job_stream 消息 schema 版本（当前 v1）与四条 stream 命名（parser/ingest/graph_repair + DLQ）；
- ①~④ 提供消息/DLQ 格式的纯校验函数（import 即安全、零副作用）；
- ⑤（W3-01 实装）在同模块承载 Redis Streams I/O：enqueue/dequeue/ack/DLQ/reclaim/pending——
  Redis 连接一律复用 app.database.get_redis() 单例池，**禁止自建连接池**；
- 声明 consumer group 迁移职责：跨 schema 版本迁移一律走 ADR（v2.4-A8①），
  由本 Owner 统一执行，禁止任何 worker 私自兼容多版本载荷。

明确不做（红线）：
- 不启动任何进程/任务/自建连接池；
- **reclaim（XAUTOCLAIM）仅限 reconciler 调用，普通 worker 禁止竞争 PEL**（v2.2 §3-2 权威单点）；
- I/O 失败语义冻结为 fail-fast：**禁内存兜底、禁假成功**（enqueue/ack 返回 False、
  dequeue/reclaim 返回空批），重试与真相源收口归 MySQL + reconciler，绝不静默降级。

W3 变更记录（2026-09-27）：G0 阶段"本模块零 Redis I/O"红线自 W3 起解除——
①~④ 全部纯契约函数**零改动**保留（回归锁：tests/test_g0_job_stream_schema.py 持续全绿），
⑤ 节为 W3-01 新增的 Redis I/O 实装（原"实现落点 W3"占位声明由本节兑现）。

失败语义冻结见 PRD v2.5 §3 第一行：job_stream 高持久（MySQL 真相源 + Streams）、
必须重试（CAS epoch+1, MAX_RETRY）、必须 DLQ（job_stream:dlq + task 标 failed+reason）、
崩溃→lease 过期→reconciler 回收重投，终态前消息永不丢。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from redis.exceptions import ResponseError

from app.common.logging import logger

# ──────────────────────────────────────────────────────────────
# ① schema 版本与 stream 命名常量（契约冻结，改动 = 契约变更须走 ADR）
# ──────────────────────────────────────────────────────────────

#: 当前消息 schema 版本。W3 落位时 XADD 载荷必须携带此值。
JOB_STREAM_SCHEMA_VERSION = "v1"

#: 本 Owner 目前唯一支持的版本；出现 v2 时必须先过 ADR 并实现 assert_schema_compatible 迁移语义。
SUPPORTED_SCHEMA_VERSIONS: tuple[str, ...] = ("v1",)

#: parser 任务流（解析 job）
PARSER_JOBS_STREAM = "parser_jobs"
#: ingest 任务流（入库 job）
INGEST_JOBS_STREAM = "ingest_jobs"
#: 图谱修复任务流（graph repair job）
GRAPH_REPAIR_STREAM = "graph_repair"
#: 死信流（DLQ）：消费失败超限的消息统一落此，task 标 failed + reason 留痕
DLQ_STREAM = "job_stream:dlq"

#: 三条业务 stream（不含 DLQ；DLQ 是本 Owner 的兜底归宿，不是业务入口）
JOB_STREAMS: tuple[str, ...] = (PARSER_JOBS_STREAM, INGEST_JOBS_STREAM, GRAPH_REPAIR_STREAM)

# ──────────────────────────────────────────────────────────────
# ② 消息 schema（TypedDict + 纯校验函数；pydantic-free，避免拉重依赖进 worker）
# ──────────────────────────────────────────────────────────────

REQUIRED_KEYS: tuple[str, ...] = ("job_id", "task_id", "asset_id", "attempt_snapshot", "schema_version")
#: payload_ref 为可选键：指向 MySQL/OSS 中真实载荷的引用（高持久真相源），消息体只带引用不带大载荷
OPTIONAL_KEYS: tuple[str, ...] = ("payload_ref", "execution_epoch")


class JobStreamMessage(dict):
    """job_stream 消息（dict 子类型，便于 JSON 直序列化；结构见 validate_message）。

    必填：job_id / task_id / asset_id（str 非空）、attempt_snapshot（int ≥1，CAS epoch 快照）、
    schema_version（str，当前恒 "v1"）；可选：payload_ref（str|None，载荷引用）。
    允许携带额外键（向前兼容），校验只保证契约键的形状。
    """


def make_message(
    job_id: str,
    task_id: str,
    asset_id: str,
    attempt_snapshot: int,
    payload_ref: str | None = None,
    execution_epoch: int | None = None,
) -> JobStreamMessage:
    """构造一条带当前 schema_version 的合法消息（便捷工厂，供 W3 与测试使用）。"""
    msg = JobStreamMessage(
        job_id=job_id,
        task_id=task_id,
        asset_id=asset_id,
        attempt_snapshot=attempt_snapshot,
        schema_version=JOB_STREAM_SCHEMA_VERSION,
    )
    if payload_ref is not None:
        msg["payload_ref"] = payload_ref
    if execution_epoch is not None:
        msg["execution_epoch"] = execution_epoch
    return msg


def _is_nonempty_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validate_message(msg: Any) -> tuple[bool, list[str]]:
    """校验 job_stream 消息是否符合 v1 契约。纯函数，返回 (ok, errors)。

    检查三层：必填键存在性 → 类型/值域 → schema_version 归属。
    额外键放行（向前兼容，消费方按需忽略），契约键形状不对才 FAIL。
    """
    errors: list[str] = []
    if not isinstance(msg, dict):
        return False, [f"message 必须是 dict，实际 {type(msg).__name__}"]

    # 1) 必填键
    for key in REQUIRED_KEYS:
        if key not in msg:
            errors.append(f"缺少必填键: {key}")

    # 2) 类型/值域（bool 是 int 子类，显式排除）
    if "job_id" in msg and not _is_nonempty_str(msg["job_id"]):
        errors.append("job_id 必须为非空字符串")
    if "task_id" in msg and not _is_nonempty_str(msg["task_id"]):
        errors.append("task_id 必须为非空字符串")
    if "asset_id" in msg and not _is_nonempty_str(msg["asset_id"]):
        errors.append("asset_id 必须为非空字符串")
    if "attempt_snapshot" in msg and (
        isinstance(msg["attempt_snapshot"], bool)
        or not isinstance(msg["attempt_snapshot"], int)
        or msg["attempt_snapshot"] < 1
    ):
        errors.append("attempt_snapshot 必须为 int 且 ≥ 1")
    if "payload_ref" in msg and msg["payload_ref"] is not None and not isinstance(msg["payload_ref"], str):
        errors.append("payload_ref 可选，但出现时必须为 str 或 None")
    if "execution_epoch" in msg and (
        isinstance(msg["execution_epoch"], bool)
        or not isinstance(msg["execution_epoch"], int)
        or msg["execution_epoch"] < 0
    ):
        errors.append("execution_epoch 可选，但出现时必须为非负 int")

    # 3) schema_version 归属
    if "schema_version" in msg:
        v = msg["schema_version"]
        if not isinstance(v, str) or v not in SUPPORTED_SCHEMA_VERSIONS:
            errors.append(
                f"schema_version 非法: {v!r}（支持 {list(SUPPORTED_SCHEMA_VERSIONS)}；"
                f"跨版本迁移须走 ADR，禁止私自兼容）"
            )

    return (len(errors) == 0), errors


# ──────────────────────────────────────────────────────────────
# ③ DLQ 消息格式（v2.5 §3：job_stream 必须 DLQ；DLQ 需人工/工具处理并在 task 留痕）
# ──────────────────────────────────────────────────────────────

DLQ_REQUIRED_KEYS: tuple[str, ...] = (
    "original",          # 原消息（必须本身通过 validate_message，保真回放/人工排查用）
    "failed_at",         # 落 DLQ 时间（ISO 字符串）
    "failure_reason",    # 失败原因（人类可读，task 留痕同源）
    "attempt_at_dlq",    # 落 DLQ 时的尝试次数（int ≥ 1）
    "source_stream",     # 原始来源 stream（必须 ∈ JOB_STREAMS，DLQ 自身除外）
)


def make_dlq_message(
    original: dict,
    failure_reason: str,
    attempt_at_dlq: int,
    source_stream: str,
    failed_at: str,
) -> dict:
    """把一条失败消息包装成 DLQ 格式（便捷工厂；W3 落 DLQ 时使用）。"""
    return {
        "original": original,
        "failed_at": failed_at,
        "failure_reason": failure_reason,
        "attempt_at_dlq": attempt_at_dlq,
        "source_stream": source_stream,
    }


def validate_dlq_message(msg: Any) -> tuple[bool, list[str]]:
    """校验 DLQ 消息格式。纯函数，返回 (ok, errors)。

    除 DLQ 外壳五键外，内嵌 original 必须递归通过 validate_message（保真要求）。
    """
    errors: list[str] = []
    if not isinstance(msg, dict):
        return False, [f"DLQ message 必须是 dict，实际 {type(msg).__name__}"]

    for key in DLQ_REQUIRED_KEYS:
        if key not in msg:
            errors.append(f"DLQ 缺少必填键: {key}")

    if "failed_at" in msg and not _is_nonempty_str(msg["failed_at"]):
        errors.append("failed_at 必须为非空字符串（ISO 时间）")
    if "failure_reason" in msg and not _is_nonempty_str(msg["failure_reason"]):
        errors.append("failure_reason 必须为非空字符串")
    if "attempt_at_dlq" in msg and (
        isinstance(msg["attempt_at_dlq"], bool)
        or not isinstance(msg["attempt_at_dlq"], int)
        or msg["attempt_at_dlq"] < 1
    ):
        errors.append("attempt_at_dlq 必须为 int 且 ≥ 1")
    if "source_stream" in msg and msg["source_stream"] not in JOB_STREAMS:
        errors.append(f"source_stream 必须 ∈ JOB_STREAMS {list(JOB_STREAMS)}，实际 {msg['source_stream']!r}")
    if "original" in msg:
        ok, sub = validate_message(msg["original"])
        if not ok:
            errors.extend(f"original 内层消息非法: {e}" for e in sub)

    return (len(errors) == 0), errors


# ──────────────────────────────────────────────────────────────
# ④ 迁移职责声明（v2.5 §1.2 版本兼容 + v2.4-A8① ADR 路径）
# ──────────────────────────────────────────────────────────────

def assert_schema_compatible(from_v: str, to_v: str) -> bool:
    """声明两个 schema 版本间的消费兼容性（骨架；迁移执行归本 Owner，未来版本走 ADR）。

    当前契约只有 v1：仅 from==to=="v1" 恒真；任何其它组合一律 False（拒绝消费）。
    未来引入 v2 时，本函数是实现 consumer group 迁移策略（双读/灰度切换/停写窗口）的
    唯一裁决点：先过 ADR（v2.4-A8①）冻结迁移语义，再改本函数——
    禁止 worker 侧私自 isinstance 探测多版本载荷（那会把契约打散回各自实现）。
    """
    if from_v == to_v and from_v in SUPPORTED_SCHEMA_VERSIONS:
        return True
    return False


# ══════════════════════════════════════════════════════════════
# ⑤ Redis Streams I/O（W3-01 实装，兑现 G0 占位声明；PRD v2.2 §1/§3）
# ──────────────────────────────────────────────────────────────
# 设计冻结（与 ①~④ 纯契约层同体单文件，Queue Contract Owner 唯一持有）：
# - 连接：复用 app.database.get_redis() 全局单例池（decode_responses=True），禁自建池；
# - 扁平化：XADD field value 只收字符串，_flatten_field/_unflatten_field 严格互逆，
#   非 str 值走 `json:` 前缀 + JSON 编码，round-trip 无损（含"长得像数字/像前缀"的 str）；
# - 消费确认凭证：dequeue/reclaim 返回的消息注入传输元数据键 ENTRY_ID_KEY（entry id），
#   调用方处理成功后以之 ack()——ack 之外没有第二种"处理完成"的表达；
# - 防毒丸：dequeue/reclaim 遇 schema 非法消息一律 先 DLQ 后 ACK 当场终结（顺序不可换，
#   反过来会在两步之间崩溃时丢消息），绝不无限重投；
# - 失败语义 fail-fast：enqueue/ack False、dequeue/reclaim []、get_pending 抛原异常
#   （诊断函数不吞错，"查不到"不能伪装成"没有积压"）。
# ══════════════════════════════════════════════════════════════

#: 非扁平值（int/float/bool/None/dict/list）与被转义 str 共用的编码前缀（XADD 只收字符串）
_JSON_PREFIX = "json:"

#: dequeue/reclaim 返回消息中注入的传输元数据键（stream entry id，ack 的唯一凭证；非契约键）
ENTRY_ID_KEY = "_entry_id"

#: DLQ stream 滑动窗口 TTL（毫秒）：send_to_dlq 每次刷新——语义=「最后一条死信后 7 天内
#: 仍可人工处理」（Redis 不支持流内逐条过期，TTL 只能作用于整键，故取滑动窗口）
DLQ_TTL_MS = 7 * 24 * 3600 * 1000


def _get_redis():
    """获取全局 Redis 客户端（复用 app.database 单例；独立小函数便于测试 monkeypatch）。

    懒 import：保持本模块 import 期零副作用（app.database 未初始化也能安全 import
    本模块做纯函数校验），调用 I/O 时才触达连接——未初始化时抛 RuntimeError，
    由各 I/O 函数按 fail-fast 语义收敛为 False/[]。
    """
    from app.database import get_redis
    return get_redis()


def _flatten_field(value: Any) -> str:
    """把消息字段值扁平化为 XADD 可接受的 str（Redis stream field 只收字符串）。

    编码规则（与 _unflatten_field 严格互逆，round-trip 无损）：
    - str：原样透传；但以保留前缀 ``json:`` 开头的 str 会被 JSON 转义——防止
      合法 job_id 恰好叫 "json:1" 时被解码侧误还原成 int（歧义消除靠编码侧全包）；
    - 其余类型（int/float/bool/None/dict/list）：``json:`` 前缀 + JSON 文本。
    非可序列化值（如 set/自定义对象）抛 TypeError，由 enqueue 拒绝入流。
    """
    if isinstance(value, str):
        if value.startswith(_JSON_PREFIX):
            return _JSON_PREFIX + json.dumps(value, ensure_ascii=False)
        return value
    return _JSON_PREFIX + json.dumps(value, ensure_ascii=False)


def _unflatten_field(raw: Any) -> Any:
    """_flatten_field 的逆变换。编码侧已保证前缀后必为合法 JSON；
    解码失败按原文返回（防御脏数据，不让一条坏 field 炸掉整批消费）。"""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str) and raw.startswith(_JSON_PREFIX):
        try:
            return json.loads(raw[len(_JSON_PREFIX):])
        except (json.JSONDecodeError, ValueError, TypeError):
            return raw
    return raw


def _fields_to_message(entry_id: Any, fields: Any) -> dict:
    """stream entry（扁平 fields）→ 消息 dict：值反扁平化 + 注入传输元数据 ENTRY_ID_KEY。"""
    raw = fields or {}
    if isinstance(raw, dict):
        msg = {str(k): _unflatten_field(v) for k, v in raw.items()}
    else:  # 防御：非 dict 形态（理论上不出现）按无载荷处理
        msg = {}
    msg[ENTRY_ID_KEY] = entry_id if isinstance(entry_id, str) else str(entry_id)
    return msg


def _attempt_floor(msg: Any) -> int:
    """DLQ 外壳 attempt_at_dlq 取值：优先 attempt_snapshot（发送时快照），非法回退 1。

    注意 v2.2 §3-4：attempt 只是发送时快照，重试真相源在 MySQL（retry_count CAS），
    这里仅为 DLQ 人工排查保留当时看到的值。
    """
    v = (msg or {}).get("attempt_snapshot") if isinstance(msg, dict) else None
    if isinstance(v, int) and not isinstance(v, bool) and v >= 1:
        return v
    return 1


async def enqueue(stream_name: str, msg: dict) -> bool:
    """投递一条 job 消息到业务 stream（AT-LEAST-ONCE 的入口，v2.2 §1）。

    失败语义（fail-fast，红线）：
    - schema 不合法 → WARN + return False，**不写 Redis**（契约层先拦截，毒消息不入流）；
    - 字段值不可序列化 → WARN + return False，不写 Redis（同上，跨不了 wire 的消息不入流）；
    - Redis 不可达/异常 → WARN + return False，**禁内存兜底、禁返回 True**——
      调用方必须依赖 MySQL 真相源 + 重投/reconciler 收口，本函数绝不把
      "没投出去"包装成成功。
    """
    ok, errors = validate_message(msg)
    if not ok:
        logger.warning(f"[job_stream] enqueue 拒绝（schema 非法，不入流）stream={stream_name} errors={errors}")
        return False
    try:
        fields = {str(k): _flatten_field(v) for k, v in msg.items()}
    except (TypeError, ValueError) as e:
        logger.warning(f"[job_stream] enqueue 拒绝（字段值不可序列化，不入流）stream={stream_name}: {type(e).__name__}: {e}")
        return False
    try:
        await _get_redis().xadd(stream_name, fields)
        return True
    except Exception as e:  # noqa: BLE001 —— 任何 Redis 故障统一 fail-fast（禁兜底禁假成功）
        logger.warning(f"[job_stream] enqueue 失败（Redis 不可达/异常，fail-fast 不兜底）"
                       f"stream={stream_name} job_id={msg.get('job_id')!r}: {type(e).__name__}: {e}")
        return False


async def create_consumer_group(stream_name: str, group_name: str) -> bool:
    """幂等创建 consumer group（XGROUP CREATE MKSTREAM，起始 id=0-0）。

    - MKSTREAM：stream 尚不存在时先建空流——worker 先于首个 enqueue 启动也不报错；
    - 起始 id 固定 0-0（**不是 $**）：组创建之前已 enqueue 的消息同样可消费——
      AT-LEAST-ONCE 要求"先投递后建组"窗口不丢消息；
    - BUSYGROUP（组已存在）视为成功（幂等），其余 Redis 异常 WARN + return False。
    """
    try:
        await _get_redis().xgroup_create(stream_name, group_name, id="0-0", mkstream=True)
        return True
    except Exception as e:  # noqa: BLE001
        if "BUSYGROUP" in str(e):
            return True  # 幂等：组已存在即成功
        logger.warning(f"[job_stream] create_consumer_group 失败 stream={stream_name} "
                       f"group={group_name}: {type(e).__name__}: {e}")
        return False


async def dequeue(
    stream_name: str,
    group_name: str,
    consumer_name: str,
    count: int = 1,
    block_ms: int = 5000,
) -> list[dict]:
    """普通 worker 唯一取数路径（XREADGROUP ``>``，只取从未投递过的新消息）。

    - 返回消息 dict 列表，每条注入传输元数据 ENTRY_ID_KEY——处理成功后调用
      ``ack(stream, group, msg[ENTRY_ID_KEY])``；处理失败不 ack，留给 reconciler
      按 lease 过期回收（v2.2 §3，普通 worker 禁自行 XAUTOCLAIM）；
    - 防毒丸：反序列化后 validate_message 不通过的消息**不返回也不无限重投**——
      先 send_to_dlq 后 ack 当场终结（顺序保证崩溃窗口不丢）；
    - 幽灵 entry（消息体已被 MAXLEN/裁剪清空、PEL 残留空载荷）：无可保真数据，
      WARN + ACK 清账（DLQ 一个空壳只会制造噪声）；
    - Redis 不可达/异常 → WARN + []（消费循环按失败退避语义继续轮询，不 crash-loop）。
    """
    try:
        resp = await _get_redis().xreadgroup(
            group_name, consumer_name,
            {stream_name: ">"},
            count=max(1, count),
            block=max(0, block_ms),
        )
    except Exception as e:  # noqa: BLE001 —— Redis 故障按空批退避（§2.3 不 crash-loop）
        logger.warning(f"[job_stream] dequeue 失败（Redis 异常，按空批退避）"
                       f"stream={stream_name} group={group_name}: {type(e).__name__}: {e}")
        return []

    out: list[dict] = []
    for _stream, entries in resp or []:
        for entry_id, fields in entries or []:
            if not fields:
                logger.warning(f"[job_stream] dequeue 遇到空载荷幽灵 entry（ACK 清账）"
                               f"stream={stream_name} id={entry_id}")
                await ack(stream_name, group_name, entry_id)
                continue
            msg = _fields_to_message(entry_id, fields)
            ok, errors = validate_message(msg)
            if not ok:
                # 防毒丸：DLQ 成功后才 ACK。DLQ 不可写时保留在 PEL，等 reconciler 重试。
                if await send_to_dlq(stream_name, msg, f"dequeue 毒丸：schema 非法 {errors}"):
                    await ack(stream_name, group_name, entry_id)
                else:
                    logger.error("[job_stream] dequeue 毒丸 DLQ 失败，保留 PEL stream={} entry={}",
                                 stream_name, entry_id)
                continue
            out.append(msg)
    return out


async def ack(stream_name: str, group_name: str, entry_id: str) -> bool:
    """确认消费（XACK）。True=该 entry 确实从 PEL 移除；False=已确认过/不存在/Redis 异常。

    XACK 幂等：重复确认已 ACK 的 entry 返回 0（→ False）。调用方**不得**把 False
    当重试信号盲目重做 job——AT-LEAST-ONCE 下重复 ack 只说明"早已确认"，job 本体
    可能已成功（重做须走 CAS epoch，见 v2.2 §1-2/§3-3）。
    """
    try:
        n = await _get_redis().xack(stream_name, group_name, str(entry_id))
        return bool(n)
    except Exception as e:  # noqa: BLE001 —— 确认失败必须留痕（消息会滞留 PEL 等 reconciler）
        logger.warning(f"[job_stream] ack 失败（entry 将滞留 PEL，由 reconciler 兜底）"
                       f"stream={stream_name} entry={entry_id}: {type(e).__name__}: {e}")
        return False


async def send_to_dlq(source_stream: str, msg: dict, reason: str) -> bool:
    """把失败消息落 DLQ（v2.5 §3：终态前消息永不丢的兜底归宿）+ 续 7 天滑动 TTL。

    - DLQ 外壳用 make_dlq_message 构造：original 全量保真（含额外键与 _entry_id），
      failed_at 用 UTC ISO 时间，attempt_at_dlq 取 attempt_snapshot 快照（非法回退 1）；
    - **毒消息也必须能落 DLQ**（dequeue 防毒丸路径的 original 本身就不合法）——
      本函数不因 validate_dlq_message 不通过而拒写（拒写=毒丸永远出不了流），
      外壳校验不通过仅 WARN 留痕供人工甄别；
    - PEXPIRE 作用于 DLQ stream 整键（滑动窗口：每次落 DLQ 刷新为 7 天）。
    """
    dlq_msg = make_dlq_message(
        original=dict(msg or {}),
        failure_reason=str(reason or "unspecified"),
        attempt_at_dlq=_attempt_floor(msg),
        source_stream=source_stream,
        failed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    shell_ok, shell_errors = validate_dlq_message(dlq_msg)
    if not shell_ok:
        logger.warning(f"[job_stream] DLQ 外壳校验不通过仍落 DLQ（毒消息保底，人工甄别）: {shell_errors}")
    fields = {str(k): _flatten_field(v) for k, v in dlq_msg.items()}
    try:
        rd = _get_redis()
        await rd.xadd(DLQ_STREAM, fields)
        await rd.pexpire(DLQ_STREAM, DLQ_TTL_MS)
        return True
    except Exception as e:  # noqa: BLE001 —— DLQ 失败同样 fail-fast（调用方决定后续，不静默丢）
        logger.warning(f"[job_stream] send_to_dlq 失败（Redis 异常）source={source_stream} "
                       f"job_id={(msg or {}).get('job_id') if isinstance(msg, dict) else None!r}: "
                       f"{type(e).__name__}: {e}")
        return False


async def reclaim(
    stream_name: str,
    group_name: str,
    consumer_name: str,
    min_idle_ms: int,
    count: int = 10,
) -> list[dict]:
    """回收超过 min_idle_ms 未确认的消息（XAUTOCLAIM）——**仅 reconciler 可调用**。

    ⛔ 红线（v2.2 §3-2 reclaim 权威单点）：普通 worker **禁止**调用本函数竞争 PEL——
    "活着被抢"竞态必须结构消除：reconciler 只在 MySQL ``lease_until < now()`` 之后
    才对滞留 entry 做 XAUTOCLAIM（MinerU 8 分钟长任务靠 lease CAS 心跳保活，不会被
    短 idle 误抢）；claim 后由调用方对 asset 行原子 ``execution_epoch + 1``
    （fencing token，§3-3——旧 epoch worker 的提交按 fencing 规则丢弃）。

    返回消息同样注入 ENTRY_ID_KEY（回收方处理成功后 ack）；毒丸/幽灵 entry 处理
    与 dequeue 一致（先 DLQ 后 ACK / WARN+ACK 清账）。Redis 异常 → WARN + []
    （reconciler 周期性重扫即可，无消息不亏）。
    """
    try:
        try:
            result = await _get_redis().xautoclaim(
                stream_name, group_name, consumer_name,
                min_idle_time=max(0, min_idle_ms),
                start_id="0-0",
                count=max(1, count),
            )
            entries = result[1] if isinstance(result, (list, tuple)) and len(result) >= 2 else []
        except ResponseError as e:
            # Redis <6.2 兼容回退（原生 Windows Redis 5.0 环境）：XAUTOCLAIM 不可用 →
            # XPENDING 全量 PEL + 客户端按 idle 过滤 + XCLAIM（2.8+）。消费单点仍是
            # reconciler、idle 阈值同源，与 XAUTOCLAIM 语义等价；7.x 路径不受影响。
            # 注：Redis 5.0 的 XPENDING 不支持 IDLE 修饰符（syntax error），故在
            # 客户端按 time_since_delivered 过滤。
            if "XAUTOCLAIM" not in str(e):
                raise
            pending = await _get_redis().xpending_range(
                stream_name, group_name, min="-", max="+", count=max(1, count) * 4,
            )
            min_idle = max(0, min_idle_ms)
            ids = [p["message_id"] for p in pending or []
                   if int(p.get("time_since_delivered") or 0) >= min_idle][:max(1, count)]
            entries = await _get_redis().xclaim(
                stream_name, group_name, consumer_name,
                min_idle_time=min_idle, message_ids=ids,
            ) if ids else []
    except Exception as e:  # noqa: BLE001 —— Redis 故障按空批退避，等下轮重扫
        logger.warning(f"[job_stream] reclaim 失败（Redis 异常）stream={stream_name} "
                       f"group={group_name}: {type(e).__name__}: {e}")
        return []
    out: list[dict] = []
    for entry_id, fields in entries or []:
        if not fields:
            logger.warning(f"[job_stream] reclaim 遇到空载荷幽灵 entry（ACK 清账）"
                           f"stream={stream_name} id={entry_id}")
            await ack(stream_name, group_name, entry_id)
            continue
        msg = _fields_to_message(entry_id, fields)
        ok, errors = validate_message(msg)
        if not ok:
            if await send_to_dlq(stream_name, msg, f"reclaim 毒丸：schema 非法 {errors}"):
                await ack(stream_name, group_name, entry_id)
            else:
                logger.error("[job_stream] reclaim 毒丸 DLQ 失败，保留 PEL stream={} entry={}",
                             stream_name, entry_id)
            continue
        out.append(msg)
    return out


async def get_pending(stream_name: str, group_name: str) -> dict:
    """PEL 摘要（XPENDING）：{pending, min, max, consumers:[{name, pending}]}。

    诊断/验收函数：Redis 异常**原样抛出**（不吞错、不返回伪零）——运维看板上
    "查不到"必须显性失败，不能伪装成"没有积压"。
    """
    return await _get_redis().xpending(stream_name, group_name)
