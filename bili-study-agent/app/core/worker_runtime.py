# -*- coding: utf-8 -*-
"""G0-OWNER：进程外 worker 生命周期接口骨架（RAG 架构升级 v2.5 §2.2 冻结字段）。

治理归属（PRD-企业级RAG架构升级-v2.5-运行时治理附录.md §2.2 Owner 行）：
  **Application Runtime Manager** 持有本模块（管「进程生命周期」）；
  消息契约（stream schema / consumer group / DLQ 格式）归 **Queue Contract Owner**，
  落位 `app/core/job_stream.py`——两模块**互不 import**，职责分离（§8-4）。

设计输入（**必须消费，不得凭空设计**，计划 P7 约束）：
  `test-reports/runtime-inventory/runtime-inventory.json`（G0-RUNTIME-INVENTORY 产出，
  git_rev=d5ad7a4）——15 个生命周期单元当前全部 execution_model=in-process、
  owner_scope=app-lifespan（lifespan 单函数集中持有 start/stop 装配点）。
  本模块是**未来进程外 worker（W3 Parser/Ingest Worker）**实现时继承/复用的接口骨架，
  **本任务不改任何现有 in-process worker 行为**（memory/event worker 代码零接触）。

迁移定性（计划 P4 + §8-3 ready 链，核心）：
  `Infrastructure ready → Web ready → Worker ready → Accept jobs`
  - **进程内 worker**（memory worker / event worker，inventory 单元 memory_worker /
    event_worker）：**沿用现状不等待**——它们与 Web 同进程同生共死，lifespan 装配顺序
    已隐式保证存储初始化先行，无跨进程 ready 问题；
  - **进程外 worker**（W3 起的 parser/ingest 独立进程）：**必须先过
    `wait_for_web_ready()` 再进入消费循环**——Web 侧在 lifespan 存储初始化完成后写
    Redis 键 `runtime:web_ready`（app/main.py G0-OWNER 写入点，v2.5 §8-3），
    worker 侧阻塞轮询该键，存在才放行。

边界（红线）：
  - 本模块**不实现任何真实消费 I/O**（无 XREADGROUP、无 Milvus/模型加载）——纯接口 + 协议；
  - 与 `app/core/job_stream.py` 的关系：它管消息契约（schema 校验），本模块管进程
    生命周期（启动/心跳/退出），互不 import；
  - 不引入新协调服务（ready 协议只用既有 Redis，§8-3）。

W3 实现方对接方式：
  1. 定义 `WorkerSpec`（见下）登记 worker 元信息（name/entry_script/streams_subscribed/
     heartbeat_key/startup_deps）；
  2. 继承 `WorkerLifecycle` 实现五阶段（startup/run_loop/heartbeat/shutdown/health）；
  3. `run_loop()` 首行必须先 `await wait_for_web_ready(...)`（P4 负向锁由
     `run_forever` 内置前置检查承载，见 `_pre_run_gate`）。
"""
from __future__ import annotations

import json
import os
import time
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Protocol
from pathlib import Path

from app.common.logging import logger
from app.config import settings

# ============================================================
# 常量（协议键名冻结，Web 写入点 app/main.py 与本模块共用）
# ============================================================
WEB_READY_KEY = "runtime:web_ready"        # Web 侧 ready 键（v2.5 §8-3）
WEB_READY_TTL_S = 24 * 3600                # Web 侧写入 TTL=24h（重启自愈：过期自动失效）
WEB_READY_POLL_INTERVAL_S = 2.0            # worker 轮询间隔
WEB_READY_WARN_EVERY_S = 60.0              # 超时 WARN 节流周期（不 crash-loop，持续等待）
HEARTBEAT_KEY_FMT = "worker:alive:{name}"  # 心跳键格式（v2.5 §2.2 健康行）
DEFAULT_SHUTDOWN_DEADLINE_S = 30.0         # SIGTERM → 当前 job 收尾默认上限（v2.5 §2.2 退出行）

# W3 worker 的 infra 依赖词汇（与 inventory units 的 7 类存储对齐，取 worker 自检子集）
VALID_STARTUP_DEPS = frozenset({"mysql", "redis", "minio", "milvus", "mongo", "neo4j"})


def _get_redis():
    """获取全局 Redis 客户端（复用 database 单例；未初始化抛 RuntimeError）。

    独立小函数而非直接 import 调用，便于测试 monkeypatch。
    """
    from app.database import get_redis
    return get_redis()


# ============================================================
# WorkerSpec：worker 进程注册元信息（W3 启停脚本按此注册表拉起）
# ============================================================
@dataclass(frozen=True)
class WorkerSpec:
    """worker 进程注册元信息（v2.5 §2.2 + v2.5 §1 架构图冻结字段）。

    对应 inventory 对照：W3 起进程外 worker 将作为新增单元出现（独立进程，
    owner_scope=runtime-manager），与现存 15 个 in-process 单元并列登记。
    """

    name: str                    # consumer 名（横幅/心跳键/日志均携带），如 "parser-worker"
    entry_script: str            # 进程入口（如 scripts/run_parser_worker.py），启停脚本按此拉起
    streams_subscribed: tuple[str, ...]   # 订阅的 stream 名（契约归 job_stream.py，本字段仅登记）
    heartbeat_key: str           # Redis 心跳键，必须等于 HEARTBEAT_KEY_FMT.format(name=name)
    startup_deps: tuple[str, ...] = ()    # infra 依赖清单（VALID_STARTUP_DEPS 子集），启动自检顺序
    extra: dict = field(default_factory=dict)  # 预留扩展（flag 快照等），不参与相等比较语义冻结

    def validate(self) -> list[str]:
        """注册表静态校验（W3 拉起前调用，非法 spec 直接拒绝启动）。"""
        errors: list[str] = []
        if not self.name or ":" in self.name:
            errors.append(f"name 非法: {self.name!r}（禁止空值与冒号，冒号保留给 key 分段）")
        if not self.entry_script:
            errors.append("entry_script 不能为空（启停脚本按此拉起进程）")
        if not self.streams_subscribed:
            errors.append("streams_subscribed 不能为空（worker 必须显式声明订阅流）")
        expected_key = HEARTBEAT_KEY_FMT.format(name=self.name)
        if self.heartbeat_key != expected_key:
            errors.append(f"heartbeat_key 必须为 {expected_key!r}，实际 {self.heartbeat_key!r}")
        bad_deps = set(self.startup_deps) - VALID_STARTUP_DEPS
        if bad_deps:
            errors.append(f"startup_deps 含未登记依赖: {sorted(bad_deps)}（合法: {sorted(VALID_STARTUP_DEPS)}）")
        return errors


# ============================================================
# RedisPort：Redis 最小端口协议（测试注入 stub 用，生产走 _get_redis）
# ============================================================
class RedisPort(Protocol):
    """worker_runtime 依赖的 Redis 最小接口（async，redis.asyncio 同形子集）。"""

    async def get(self, key: str): ...
    async def set(self, key: str, value, ex: int = ...): ...
    async def delete(self, *keys: str): ...
    async def exists(self, *keys: str) -> int: ...


# ============================================================
# WorkerLifecycle：五阶段生命周期抽象基类（v2.5 §2.2 冻结字段逐行对应）
# ============================================================
class WorkerLifecycle(ABC):
    """进程外 worker 五阶段生命周期接口（两 worker 共用，v2.5 §2.2）。

    五阶段 ↔ PRD §2.2 表格映射：
      startup()   ↔ 启动：读 config → 注册消费组占位 → 启动横幅（git_rev/flag 快照/consumer 名）
                    → 懒加载重模型钩子（不阻塞启动）
      run_loop()  ↔ 运行：消费循环占位 + 心跳调用点
      heartbeat() ↔ 心跳：`worker:alive:{name}` TTL=3×周期 续约（liveness 判据=键存在）
      shutdown()  ↔ 退出：停止取新单 → 当前 job 收尾（deadline 默认 30s）→ 退出码 0
      health()    ↔ 健康：liveness = heartbeat key 存在性（不做 HTTP 端口，§1 架构图）
    """

    def __init__(self, spec: WorkerSpec, redis: Optional[RedisPort] = None):
        self.spec = spec
        self._redis = redis            # None → 运行时走 _get_redis()；测试注入 stub
        self._shutdown_requested = False

    # -- redis 访问（测试可注入） --------------------------------
    def _rd(self) -> RedisPort:
        if self._redis is not None:
            return self._redis
        return _get_redis()  # type: ignore[return-value]

    # -- 阶段 1：startup -----------------------------------------
    @abstractmethod
    async def startup(self) -> None:
        """启动阶段（W3 实现方义务，本骨架只冻结义务清单）：

        1. 读 config（单源 config.py，禁止 worker 自带第二配置入口）；
        2. 注册消费组（XGROUP CREATE MKSTREAM 幂等）——本骨架**不实现**真实
           XREADGROUP/XGROUP（红线：本任务无真实消费 I/O），实现方在此占位；
        3. 打印启动横幅：含 git_rev / flag 快照 / consumer 名（`_startup_banner`）；
        4. 懒加载重模型钩子（MinerU / BGE-M3，不阻塞启动——重模型在首个 job
           或显式预热任务里再加载）。
        """

    # -- 阶段 2：run_loop ----------------------------------------
    @abstractmethod
    async def run_loop(self) -> None:
        """消费循环（W3 实现方义务：XREADGROUP → 处理 → XACK）。

        调用约定：**必须经由 `run_forever()`**——后者内置 ready 前置检查
        （P4 负向锁）与心跳调用点；直接裸调 run_loop 会绕过 ready 协议。
        """

    # -- 阶段 3：heartbeat ---------------------------------------
    async def heartbeat(self, period_s: float = 10.0) -> bool:
        """进程存活心跳（G0-HARDENING OWNER-H1 拆分：liveness 专用）。

        写 `worker:alive:{name}` EX TTL=3×周期（v2.5 §2.2 健康行）——回答
        "worker 进程活着吗"；**不**回答"这个 job 的租约还有效吗"（那是
        `job_lease_heartbeat` 的职责，消费侧 CAS asset_id+epoch 续租）。
        两者必须分开：进程活着但执行权已丢失（reclaim 过户）时，liveness 心跳
        必须照常继续，lease 心跳必须停止——混用会造出"僵死执行权续命"。

        返回 True=续约成功；False=Redis 异常（调用方记日志，不 crash——
        连续失败由 reconciler 按 lease 过期回收兜底，§2.3）。
        """
        key = HEARTBEAT_KEY_FMT.format(name=self.spec.name)
        try:
            await self._rd().set(key, json.dumps({
                "name": self.spec.name, "ts": time.time(),
            }), ex=max(1, int(period_s * 3)))
            return True
        except Exception as e:  # noqa: BLE001 —— 心跳失败不炸 worker（§2.3 失败退避语义）
            logger.warning(f"[worker:{self.spec.name}] 心跳续约失败（继续运行，运维可见）: "
                           f"{type(e).__name__}: {e}")
            return False

    async def maintain_heartbeat(self, stop: asyncio.Event, period_s: float = 10.0) -> None:
        """Refresh process liveness while a single job blocks the consumer loop."""
        while not stop.is_set():
            await self.heartbeat(period_s=period_s)
            try:
                await asyncio.wait_for(stop.wait(), timeout=period_s)
            except asyncio.TimeoutError:
                continue

    async def job_lease_heartbeat(
        self,
        *,
        asset_id: str,
        epoch: int,
        lease_s: float = 120.0,
        renew: bool = True,
    ) -> bool:
        """job 租约心跳（G0-HARDENING OWNER-H1 新增：执行权续租，CAS 语义）。

        与 `heartbeat()`（进程 liveness）严格分离——本方法回答"我仍持有
        asset_id@execution_epoch 的执行权吗"，是 v2.2 §3 fencing token 的
        运行时承载：
          - renew=True：CAS 续租——仅当 `worker:lease:{asset_id}` 当前值仍为
            本 worker 的 `{name}@{epoch}` 时延长 TTL（脚本式原子判定，owner 不
            匹配 = 执行权已被 reclaim → 返回 False，调用方必须立即停止该 job
            的后续提交，v2.2 §3-3 fencing 语义）；
          - renew=False：纯查询（判定执行权归属，不延长）。
        返回 False（含 Redis 异常）= 执行权存疑 → 调用方停止提交，结果按
        fencing 规则丢弃（artifact 可留，状态不写）。

        W3 落地注意：当前为契约骨架（键格式与 CAS 判定语义冻结）；真实 Lua
        原子脚本在 W3 parser/ingest worker 实装时接入，届时用真实 Redis 加
        契约测试（owner 不匹配→False 且 TTL 不变）。
        """
        lease_key = f"worker:lease:{asset_id}"
        owner_token = f"{self.spec.name}@{epoch}"
        try:
            rd = self._rd()
            if not renew:
                return await rd.get(lease_key) == owner_token
            # CAS 续租：GET → 比对 owner → 匹配才 SETEX（W3 换 Lua 原子化）
            current = await rd.get(lease_key)
            if isinstance(current, bytes):
                current = current.decode()
            if current != owner_token:
                logger.warning(
                    f"[worker:{self.spec.name}] lease 心跳失败：执行权已过户"
                    f"（lease={lease_key} current={current!r} mine={owner_token!r}）"
                    f"——停止该 job 后续提交（fencing）")
                return False
            await rd.set(lease_key, owner_token, ex=max(1, int(lease_s)))
            return True
        except Exception as e:  # noqa: BLE001 —— 租约异常 = 执行权存疑（保守 False）
            logger.warning(f"[worker:{self.spec.name}] lease 心跳异常（按执行权存疑处理）: "
                           f"{type(e).__name__}: {e}")
            return False

    # -- 阶段 4：shutdown ----------------------------------------
    @abstractmethod
    async def shutdown(self, deadline_s: float = DEFAULT_SHUTDOWN_DEADLINE_S) -> int:
        """退出阶段（v2.5 §2.2 退出行）：停止取新单 → 当前 job 收尾（或到 deadline）→ 返回退出码。

        返回 int 退出码：0=干净退出；非 0=超时强退（reconciler 按 lease 过期兜底）。
        """

    # -- 阶段 5：health ------------------------------------------
    async def health(self) -> bool:
        """liveness = heartbeat key 存在性（v2.5 §2.2 健康行；不做 HTTP 端口）。"""
        key = HEARTBEAT_KEY_FMT.format(name=self.spec.name)
        try:
            return bool(await self._rd().exists(key))
        except Exception:  # noqa: BLE001 —— Redis 不可达时 liveness 判 False（保守）
            return False

    # -- 组装：run_forever（ready 前置检查 + 心跳调用点） ----------
    async def run_forever(self, ready_timeout_s: float = 600.0) -> int:
        """进程主入口：ready 门 → startup → 循环心跳 + run_loop → shutdown。

        P4 负向锁承载点：`_pre_run_gate`（=wait_for_web_ready）不通过绝不进入
        消费循环——job 计数保持 0。
        """
        gate_ok = await self._pre_run_gate(timeout_s=ready_timeout_s)
        if not gate_ok:
            logger.error(f"[worker:{self.spec.name}] ready 门未通过（前置检查异常退出），退出码 2")
            return 2
        exit_code = 1
        try:
            await self.startup()
            while not self._shutdown_requested:
                stop_file = Path(__file__).resolve().parents[2] / "logs" / "worker-pids" / f"{self.spec.name}.stop"
                if stop_file.is_file():
                    self.request_shutdown()
                    break
                if not await self.heartbeat():
                    pass  # 心跳失败已 WARN；不 crash（§2.3 不 crash-loop）
                await self.run_loop()
        finally:
            try:
                exit_code = await self.shutdown()
            finally:
                try:
                    await self._rd().delete(HEARTBEAT_KEY_FMT.format(name=self.spec.name))
                except Exception as e:  # noqa: BLE001 — TTL remains the crash recovery path
                    logger.warning(f"[worker:{self.spec.name}] 心跳键清理失败: {type(e).__name__}: {e}")
        return exit_code

    async def _pre_run_gate(self, timeout_s: float) -> bool:
        """ready 前置检查（P4 负向锁的代码锚点）：未过 web_ready 不消费任何 job。"""
        try:
            await wait_for_web_ready(
                timeout_s=timeout_s, poll_interval=WEB_READY_POLL_INTERVAL_S,
                redis=self._redis, worker_name=self.spec.name,
            )
            return True
        except Exception as e:  # noqa: BLE001 —— 门异常（如 Redis 不可达）不放行
            logger.warning(f"[worker:{self.spec.name}] ready 前置检查异常（不放行进入消费循环）: "
                           f"{type(e).__name__}: {e}")
            return False

    # -- 工具：启动横幅 / 退出信号 --------------------------------
    def _startup_banner(self) -> str:
        """启动横幅文本（v2.5 §2.2 启动行冻结字段：git_rev / flag 快照 / consumer 名）。"""
        git_rev = _git_rev()
        flag_snapshot = {
            "debug": settings.DEBUG,
            "embed_backend": getattr(settings, "EMBED_BACKEND", None),
            "mcp_search_top_k_max": getattr(settings, "MCP_SEARCH_TOP_K_MAX", None),
        }
        return (f"[worker:{self.spec.name}] startup | consumer={self.spec.name} | "
                f"git_rev={git_rev} | flags={json.dumps(flag_snapshot, ensure_ascii=False)} | "
                f"streams={list(self.spec.streams_subscribed)} | deps={list(self.spec.startup_deps)}")

    def request_shutdown(self) -> None:
        """SIGTERM 处理器调用：置位后 run_forever 循环退出并收尾（退出码 0 路径）。"""
        self._shutdown_requested = True


def _git_rev() -> str:
    """读取 git_rev：优先环境变量 GIT_REV（部署注入），回退 'unknown'。

    红线：不在 import 期执行 git 子进程（worker 启动路径保持零副作用）。
    """
    return (os.environ.get("GIT_REV") or "unknown").strip() or "unknown"


def build_web_ready_payload() -> str:
    """构造 web_ready 键值（json{git_rev, ready_at}，v2.5 §8-3 冻结形态）。

    Web 侧（app/main.py G0-OWNER 写入点）与测试共用此工厂，避免两处手拼 JSON 漂移。
    """
    return json.dumps({"git_rev": _git_rev(), "ready_at": time.time()}, ensure_ascii=False)


# ============================================================
# ready 协议（P4 核心）：worker 侧阻塞等待 Web ready 键（v2.5 §8-3）
# ============================================================
async def wait_for_web_ready(
    timeout_s: float = 600.0,
    poll_interval: float = WEB_READY_POLL_INTERVAL_S,
    redis: Optional[RedisPort] = None,
    worker_name: str = "worker",
) -> bool:
    """阻塞轮询 Redis 键 `runtime:web_ready`，存在（且未过期）才返回 True。

    协议（v2.5 §8-3 启动 ready 链）：`Infrastructure ready → Web ready → Worker ready
    → Accept jobs`。Web 侧在 lifespan 存储初始化完成后写该键（值=json{git_rev, ready_at}，
    TTL=24h），worker 消费循环前置等待。

    超时行为：**WARN + 继续等待（不 crash-loop）**——不抛 TimeoutError，不退出进程；
    告警节流（每 WEB_READY_WARN_EVERY_S 一条），运维可见但不刷屏。返回 False 仅当
    调用方显式传 timeout_s<=0 的立即探测（探测模式，生产不用）。

    迁移定性（P4，本 docstring 即契约）：
      - 进程内 worker（memory/event，inventory 单元 memory_worker/event_worker）：
        **沿用现状不等待**——同进程同生共死，禁止引入本函数；
      - 进程外 worker（W3 起独立进程）：**必须先过本函数再进入消费循环**；
      - Redis 不可达：按「键不存在」处理（WARN 继续轮询），与 §2.3 失败退避语义一致。
    """
    rd: RedisPort = redis if redis is not None else _get_redis()  # type: ignore[assignment]
    deadline = time.monotonic() + timeout_s
    last_warn = 0.0
    polls = 0
    while True:
        polls += 1
        try:
            val = await rd.get(WEB_READY_KEY)
        except Exception as e:  # noqa: BLE001 —— Redis 不可达按键不存在处理（不 crash-loop）
            val = None
            if time.monotonic() - last_warn >= WEB_READY_WARN_EVERY_S:
                logger.warning(f"[worker:{worker_name}] ready 探测 Redis 异常（按未就绪继续等待）: "
                               f"{type(e).__name__}: {e}")
                last_warn = time.monotonic()
        if val:
            try:
                payload = json.loads(val if isinstance(val, str) else val.decode())
            except Exception:  # noqa: BLE001 —— 值损坏按未就绪处理，等 Web 重写
                payload = None
            if payload:
                logger.info(f"[worker:{worker_name}] web_ready 已就绪（git_rev={payload.get('git_rev')}，"
                            f"等待 {polls} 次轮询）→ 进入消费循环")
                return True
        if timeout_s <= 0:
            return False  # 立即探测模式：键不存在即 False
        if time.monotonic() >= deadline:
            logger.warning(f"[worker:{worker_name}] 等待 web_ready 超时 {timeout_s}s（共轮询 {polls} 次）"
                           f"——继续等待不退出（不 crash-loop，运维可见）")
            deadline = time.monotonic() + timeout_s  # 重置窗口，持续等待
            last_warn = time.monotonic()
        await _sleep(poll_interval)


async def _sleep(seconds: float) -> None:
    """轮询间隔 sleep（独立小函数便于测试 monkeypatch 提速）。"""
    import asyncio
    await asyncio.sleep(seconds)
