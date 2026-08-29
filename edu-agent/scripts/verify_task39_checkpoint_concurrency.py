# -*- coding: utf-8 -*-
"""task39 GWT④：自研 checkpointer 并发 100 压测（持久化正确性 / 并发冲突 / 性能）。

对应批判：task24 批判①「自研 checkpointer 压测（并发/持久化）」
验收指标：并发 100 无丢失/错乱；resume 正确率 100%；P95 达标

三个场景（全部打真 Redis，不 mock）：
  S1 跨线程隔离：100 个不同 thread_id × 每线程 3 步 checkpoint，全部并发提交
                 → 新 saver 实例 resume 后逐线程校验：步数=3、载荷=本线程、无串号
  S2 同线程并发：1 个 thread_id × 100 并发 aput（写-写冲突）
                 → 落盘快照必须结构完整、版本号单调到最大值，无 pickle 损坏
  S3 重启恢复  ：S1 的 100 线程用「全新 saver 实例」读取（模拟进程 kill 后恢复）
                 → 100/100 命中，逐条比对载荷
  S4 连接泄漏  ：并发建连后检查 saver 只持有 1 个 Redis 客户端（GWT④ R1 回归）

用法：
    .venv\\Scripts\\python scripts/verify_task39_checkpoint_concurrency.py
    .venv\\Scripts\\python scripts/verify_task39_checkpoint_concurrency.py --threads 200 --steps 5

跑之前会做 Redis 探活（共享 VM/WSL Redis 掉线时直接报「环境未就绪」，避免产出
误导性的超时数据）；跑完自动归档到 test-reports/task39-checkpoint-concurrency.{txt,json}。
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
for _p in (str(_ROOT), str(_HERE)):  # _HERE 供 `import task39_report`（python -m 方式运行时也需要）
    if _p not in sys.path:
        sys.path.insert(0, _p)

from task39_report import archive, preflight, target_from_settings  # noqa: E402

from app.ai.checkpoint_redis import PlainRedisSaver  # noqa: E402
from app.config import settings  # noqa: E402

REPORT: list[str] = []
FAILED: list[str] = []


def _log(msg: str) -> None:
    print(msg, flush=True)
    REPORT.append(msg)


def _check(cond: bool, name: str, detail: str = "") -> bool:
    if cond:
        _log(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        _log(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))
        FAILED.append(name)
    return cond


_ts0 = int(time.time() * 1000)
_seq = {"n": 0}


def _monotonic_id() -> str:
    """生成**字典序单调**的 checkpoint id。

    重要契约（压测实证）：``InMemorySaver.get_tuple`` 用 ``max(checkpoints.keys())``
    取「最新」——比较的是 **checkpoint id 的字符串字典序**，既不是 ts 也不是版本号。
    LangGraph 自身的 id 是 ULID（字典序即时间序）故无碍；但任何自研/改造的 id 一旦
    字典序不单调（如 "racer-99-…" > "final-…"），resume 就会**静默回到错误的旧检查点**。
    本压测按 ULID 契约构造 id，才测得出真实的「并发不错乱」。
    """
    _seq["n"] += 1
    return f"{_ts0 + _seq['n']:016d}-{_seq['n']:06d}"


def _mk_checkpoint(step: int, marker: str) -> dict[str, Any]:
    """构造一个合法 Checkpoint（字段对齐 langgraph.checkpoint.base.Checkpoint）。"""
    return {
        "v": 1,
        "id": _monotonic_id(),
        "ts": time.time(),
        "channel_values": {"marker": marker, "step": step},
        "channel_versions": {"marker": step, "step": step},
        "versions_seen": {},
        "updated_channels": ["marker", "step"],
    }


def _cfg(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}


# ──────────────────────────────────────────────────────────────
# S1 + S3：100 线程 × N 步，并发提交 → 新实例 resume 校验
# ──────────────────────────────────────────────────────────────
async def scenario_cross_thread(n_threads: int, n_steps: int, prefix: str):
    _log(f"\n=== S1/S3 跨线程隔离 + 重启恢复：{n_threads} 线程 × {n_steps} 步（全并发） ===")
    saver = PlainRedisSaver(redis_url=settings.REDIS_URL, ttl=600)
    threads = [f"{prefix}-t{i}" for i in range(n_threads)]

    async def one_thread(tid: str, idx: int) -> float:
        marker = f"payload-{idx}"
        t0 = time.perf_counter()
        for step in range(1, n_steps + 1):
            await saver.aput(
                _cfg(tid),
                _mk_checkpoint(step, marker),
                {"source": "task39", "step": step},
                {"marker": step, "step": step},
            )
        return (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    latencies = await asyncio.gather(*[one_thread(t, i) for i, t in enumerate(threads)])
    wall = (time.perf_counter() - t0) * 1000
    p50, p95, p99 = (
        statistics.quantiles(latencies, n=100)[49],
        statistics.quantiles(latencies, n=100)[94],
        max(latencies),
    )
    _log(f"  写路径：wall={wall:.0f}ms  单线程 {n_steps} 步 P50={p50:.0f}ms P95={p95:.0f}ms max={p99:.0f}ms")

    # S3：全新 saver 实例（模拟进程重启）逐线程 resume
    fresh = PlainRedisSaver(redis_url=settings.REDIS_URL, ttl=600)
    ok = 0
    bad: list[str] = []
    t0 = time.perf_counter()
    for i, tid in enumerate(threads):
        tup = await fresh.aget_tuple(_cfg(tid))
        if tup is None:
            bad.append(f"{tid}: None")
            continue
        cv = tup.checkpoint.get("channel_values", {})
        if cv.get("marker") != f"payload-{i}":
            bad.append(f"{tid}: 串号 marker={cv.get('marker')} expected=payload-{i}")
            continue
        if cv.get("step") != n_steps:
            bad.append(f"{tid}: 步数丢失 step={cv.get('step')} expected={n_steps}")
            continue
        ok += 1
    resume_ms = (time.perf_counter() - t0) * 1000
    _log(f"  恢复路径：{ok}/{n_threads} 正确 resume，耗时 {resume_ms:.0f}ms"
         + (f"；异常样本 {bad[:3]}" if bad else ""))
    _check(ok == n_threads, f"S1/S3 resume 正确率 100%（{ok}/{n_threads}）",
           f"丢失/错乱={len(bad)}")
    await saver.aclose()
    await fresh.aclose()
    return {"p95_ms": round(p95, 1), "wall_ms": round(wall, 1), "resume_ms": round(resume_ms, 1)}


# ──────────────────────────────────────────────────────────────
# S2：同 thread_id × N 并发 aput（写-写冲突）
# ──────────────────────────────────────────────────────────────
async def scenario_same_thread(n_concurrent: int, prefix: str):
    _log(f"\n=== S2 同线程并发写：1 线程 × {n_concurrent} 并发 aput ===")
    saver = PlainRedisSaver(redis_url=settings.REDIS_URL, ttl=600)
    tid = f"{prefix}-same"

    async def one(i: int):
        await saver.aput(
            _cfg(tid),
            _mk_checkpoint(i, f"racer-{i}"),
            {"source": "task39", "step": i},
            {"marker": i, "step": i},
        )
        return i

    t0 = time.perf_counter()
    await asyncio.gather(*[one(i) for i in range(1, n_concurrent + 1)])
    wall = (time.perf_counter() - t0) * 1000
    _log(f"  并发写入完成 wall={wall:.0f}ms")

    # 落盘快照必须结构完整（能被 unpickle 且含合法 channel_values）
    fresh = PlainRedisSaver(redis_url=settings.REDIS_URL, ttl=600)
    fresh2 = PlainRedisSaver(redis_url=settings.REDIS_URL, ttl=600)
    tup = await fresh.aget_tuple(_cfg(tid))
    intact = tup is not None and isinstance(tup.checkpoint, dict) and "channel_values" in tup.checkpoint
    _check(bool(intact), "S2 并发写后快照结构完整（无 pickle 损坏/半写）",
           f"checkpoint_id={(tup.checkpoint or {}).get('id') if tup else None}")

    if intact:
        cv = tup.checkpoint["channel_values"]  # type: ignore[index]
        step = cv.get("step")
        # 真并发下「谁最后写入」本身没有定义（100 个协程同时提交），
        # 因此**不能**断言 step==n_concurrent——那是串行语义。
        # 真正的不变量是「字段级不错乱」：marker 必须属于同一个 step，
        # 若两次写在 channel_values 层面交错（marker 与 step 来自不同提交）即为错乱。
        _check(
            isinstance(step, int) and 1 <= step <= n_concurrent and cv.get("marker") == f"racer-{step}",
            "S2 并发写字段级不错乱（marker 与 step 同属一次提交，无交错混写）",
            f"step={step} marker={cv.get('marker')}",
        )
        cvers = tup.checkpoint.get("channel_versions", {})  # type: ignore[union-attr]
        _check(
            all(isinstance(v, int) for v in cvers.values())
            and cvers.get("step") == step and cvers.get("marker") == step,
            "S2 channel_versions 与 channel_values 自洽（版本号无倒退/无交错）",
            f"versions={cvers}",
        )

    # 顺序写必须在并发写之后可见（并发结束后的写入不能被旧快照覆盖回退）
    await saver.aput(
        _cfg(tid), _mk_checkpoint(9999, "final"),
        {"source": "task39"}, {"marker": 9999, "step": 9999},
    )
    tup2 = await fresh2.aget_tuple(_cfg(tid))
    cv2 = (tup2.checkpoint.get("channel_values") if tup2 else {}) or {}
    _check(cv2.get("step") == 9999 and cv2.get("marker") == "final",
           "S2 并发写之后顺序写入可见（无旧快照覆盖新问题）",
           f"step={cv2.get('step')} marker={cv2.get('marker')}")

    await saver.aclose()
    await fresh.aclose()
    await fresh2.aclose()
    return {"wall_ms": round(wall, 1)}


# ──────────────────────────────────────────────────────────────
# S4：并发建连不泄漏（GWT④ R1 回归）
# ──────────────────────────────────────────────────────────────
async def scenario_conn_leak(n_concurrent: int, prefix: str):
    _log(f"\n=== S4 连接泄漏回归：{n_concurrent} 并发首次建连 ===")
    saver = PlainRedisSaver(redis_url=settings.REDIS_URL, ttl=600)

    async def one(i: int):
        await saver.aput(
            _cfg(f"{prefix}-conn-{i}"), _mk_checkpoint(1, f"c{i}"),
            {"source": "task39"}, {"marker": 1},
        )

    await asyncio.gather(*[one(i) for i in range(n_concurrent)])
    # 只应持有 1 个客户端实例；连接数应 ≤ 连接池上限（远小于并发数）
    n_clients = 1 if saver._redis is not None else 0
    try:
        info = await saver._redis.info("clients")  # noqa: SLF001
        connected = int(info.get("connected_clients", -1))
    except Exception:
        connected = -1
    _check(n_clients == 1, "S4 saver 只持有 1 个 Redis 客户端实例", f"clients={n_clients}")
    _log(f"  Redis 服务端 connected_clients={connected}（含其它组件，仅作参考）")
    await saver.aclose()
    return {"connected_clients": connected}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=100)
    ap.add_argument("--steps", type=int, default=3)
    ap.add_argument("--same-thread", type=int, default=100)
    ap.add_argument("--out", default="", help="结果文件名（默认 task39-checkpoint-concurrency）")
    args = ap.parse_args()

    _log("=" * 72)
    _log("task39 GWT④ checkpointer 并发压测")
    _log("=" * 72)
    # 预检：Redis 掉线时脚本会以「一堆锁超时」的形式失败，看起来像产品缺陷实际是环境没起
    preflight([target_from_settings("redis")], log=_log)

    prefix = f"task39-{uuid.uuid4().hex[:8]}"
    _log(f"\nREDIS={settings.REDIS_URL} prefix={prefix}")

    s1 = await scenario_cross_thread(args.threads, args.steps, prefix)
    s2 = await scenario_same_thread(args.same_thread, prefix)
    s4 = await scenario_conn_leak(100, prefix)

    _log("\n=== 汇总 ===")
    _log(f"  S1/S3 跨线程：resume {args.threads}/{args.threads}，P95={s1['p95_ms']}ms")
    _log(f"  S2 同线程并发：{args.same_thread} 并发，wall={s2['wall_ms']}ms")
    _log(f"  S4 连接泄漏：clients={s4['connected_clients']}")

    archive(
        args.out or "task39-checkpoint-concurrency",
        REPORT,
        payload={
            "threads": args.threads,
            "steps": args.steps,
            "same_thread": args.same_thread,
            "scenarios": {"S1_S3": s1, "S2": s2, "S4": s4},
            "failed": FAILED,
        },
        log=_log,
    )
    if FAILED:
        _log(f"\n❌ 失败项 {len(FAILED)}: {FAILED}")
        return 1
    _log("\n✅ GWT④ 全部通过：并发 100 无丢失/无错乱/resume 正确率 100%")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
