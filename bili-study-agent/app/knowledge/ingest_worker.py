# -*- coding: utf-8 -*-
"""W3-05：Ingest Worker（ingest_jobs 消费者——IR artifact → 向量/图谱入库）。

职责边界（Ownership Map，本模块**只消费不修改**上游契约）：
- 消息契约：app/core/job_stream.py（Queue Contract Owner：dequeue/ack/enqueue/DLQ）；
- 进程生命周期：app/core/worker_runtime.WorkerLifecycle（Runtime Manager 五阶段骨架）；
- 入库管道：W4 从 IR seeds 生成 token-budget chunks，再复用既有
  contextualize_node / embed_node / load_node / graph_build_node；legacy ImportState
  仍走原 chunk_node。仅按节点返回的 patch 顺序合并状态（与
  pipeline.LinearImportPipeline 同款合并语义，只是剔除 parse 节点——IR 已由 Parser 产出）；
- artifact 读取：app/services/source_asset_store.SourceAssetStore（fetch_to_temp/cleanup_temp）；
- 状态推进：app/knowledge/task_store（update_asset_stage CAS / update_task / get_task_stage）。

失败语义（PRD v2.5 §3 + 任务书冻结）：
- graph_build 失败 → graph_status=degraded + 投 graph_repair（**不停机**，向量入库照常终态）；
- Milvus/embed 失败 → retry_count CAS +1 → stage 回退 ir_ready 重投；超限 → stage=failed
  + DLQ（job_stream:dlq）+ task 终态 failed；
- 红线：禁止 XAUTOCLAIM（reclaim 仅 reconciler）；**先持久状态后 XACK**；
  Redis/MySQL I/O 失败不 ACK（消息留 PEL，由 reconciler 兜底），绝不静默丢消息。

幂等闸门（AT-LEAST-ONCE 重复投递的防重）：
- 认领 CAS：``update_asset_stage(asset_id, "ingesting", expected_stage="ir_ready")``，
  0 行 = 已处理/他人认领 → ACK 跳过，绝不重做。

source-scoped replace（本单接口冻结；完整 generation 版本管理属后续单）：
- 候选 chunk 完整写入并发布后，按 tenant/document 精确退役旧 generation；
  候选失败时保留旧有效版本。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from app.config import settings
from app.core import job_stream as js
from app.core.worker_runtime import (
    WEB_READY_POLL_INTERVAL_S,
    WorkerLifecycle,
    WorkerSpec,
    wait_for_web_ready,
)
from app.database import execute_write
from app.knowledge import task_store
from app.knowledge.importer import loader as milvus_loader
from app.knowledge.importer.chunker import chunk_node
from app.knowledge.importer.contextualize import contextualize_node
from app.knowledge.importer.embedder import embed_node
from app.knowledge.importer.graph_builder import graph_build_node
from app.knowledge.importer.pipeline import load_node
from app.knowledge.chunk_preparation import ChunkPreparationPolicy, prepare_chunks
from app.knowledge.ir import (
    IRArtifact,
    IR_SCHEMA_VERSION,
    BlockType,
    ParsedDocument,
    SecurityMeta,
    SeedKnowledgeChunk,
    join_blocks_text,
)
from app.knowledge.models import (
    ASSET_STAGE_FAILED,
    ASSET_STAGE_IR_READY,
    ASSET_STAGE_INGESTED,
    ChunkStrategy,
    ContentType,
    ImportState,
    KnowledgeChunk,
    Visibility,
)
from app.services.source_asset_store import SourceAssetStore

# ============================================================
# 常量（consumer group / 重试上限 / in-flight 阶段词）
# ============================================================

#: ingest_jobs 的 consumer group（幂等创建，多 worker 同组竞争消费）
INGEST_CONSUMER_GROUP = "ingest_worker_group"

#: 单批最多取多少条消息（XREADGROUP count）
INGEST_BATCH_SIZE = 10

#: 重试上限（真相源=MySQL import_source_asset.retry_count；CAS 超限 → DLQ）
MAX_INGEST_RETRY = 3
MYSQL_JOB_LEASE_SECONDS = 180
MYSQL_LEASE_RENEW_SECONDS = 45

# W3-05 新增 in-flight 阶段词（任务书冻结 CAS 链：ir_ready → ingesting → ingested）。
# ⚠️ W2 冻结词汇表（models.IMPORT_ASSET_STAGES）未含 "ingesting"——task_store.
# aggregate_progress 对未知 stage 丢计数（in-flight 瞬态在 asset_progress 投影不可见）。
# 因此本 worker 的 task 终态判定**不依赖该聚合**（见 _maybe_finalize_task 的终态集合守卫），
# 只把「全部 asset 落 ingested/failed 终态」作为可结算判据。
ASSET_STAGE_INGESTING = "ingesting"

#: asset 终态集合（task 可结算判据：全部 asset 落入终态才允许写 task 终态）
_ASSET_TERMINAL_STAGES = frozenset({ASSET_STAGE_INGESTED, ASSET_STAGE_FAILED})

#: graph_build_node「失败不阻断」WARN 日志锚点（graph_builder.py 冻结文案前缀；
#  节点契约永不抛异常、不写 state.error → degraded 只能靠日志捕获，锚点变更须同步此处）
_GRAPH_WARN_ANCHOR_NEO4J = "Neo4j 图谱写入失败"
_GRAPH_WARN_ANCHOR_EXTRACT = "图谱关系抽取失败"


class IngestJobError(Exception):
    """ingest job 处理期业务失败（进入 retry/DLQ 语义；区别于 Redis/MySQL I/O 故障）。"""


async def _renew_mysql_lease(
    asset_id: str, epoch: int, owner: str,
    stop: asyncio.Event, lost: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=MYSQL_LEASE_RENEW_SECONDS)
            return
        except asyncio.TimeoutError:
            pass
        try:
            if not await task_store.renew_asset_lease(
                asset_id, execution_epoch=epoch, owner=owner,
                lease_seconds=MYSQL_JOB_LEASE_SECONDS,
            ):
                lost.set()
                return
        except Exception:
            logger.exception(f"[ingest-worker] MySQL lease renew failed asset_id={asset_id} epoch={epoch}")
            lost.set()
            return


# ============================================================
# WorkerSpec 注册元信息（W3 启停脚本按此拉起进程）
# ============================================================
def build_ingest_spec() -> WorkerSpec:
    """构造 ingest-worker 的 WorkerSpec（v2.5 §2.2 冻结字段）。

    heartbeat_key 必须等于 HEARTBEAT_KEY_FMT.format(name="ingest-worker")
    （WorkerSpec.validate 锁格式）。
    """
    return WorkerSpec(
        name="ingest-worker",
        entry_script="scripts/run_ingest_worker.py",
        streams_subscribed=(js.INGEST_JOBS_STREAM,),
        heartbeat_key="worker:alive:ingest-worker",
        startup_deps=("mysql", "redis", "minio", "milvus"),
    )


# ============================================================
# IR artifact 反序列化（读取契约冻结；producer=Parser Worker W3-04）
# ============================================================
def parse_artifact_json(
    data: dict, *, expected_task_id: str | None = None, expected_asset_id: str | None = None,
) -> tuple[ParsedDocument, Optional[list[SeedKnowledgeChunk]]]:
    """IR artifact JSON → (ParsedDocument, seeds|None)。

    读取契约（W3-05 冻结）::

        {"artifact_type": "ir_v1", "ir_schema_version": "v1", "document_id": "...",
         "parsed": <ParsedDocument.model_dump()>,
         "seeds":  [<SeedKnowledgeChunk.model_dump()>]}

    兼容形态（防 producer 半路改形炸消费）：
    - ``parsed`` 键缺省 → 顶层即 ParsedDocument；
    - ``seeds`` 键缺省/空 → 返回 None，由调用方按 F-025 从 blocks 现场推导
      （推导需要 security 上下文，见 ``seeds_from_blocks``）；
    - ``ir_schema_version`` 非 v1 → 拒绝消费（跨版本迁移走 ADR，同 job_stream 纪律）。
    """
    if not isinstance(data, dict):
        raise IngestJobError(f"IR artifact 必须是 JSON object，实际 {type(data).__name__}")
    artifact_type = data.get("artifact_type")
    try:
        artifact = IRArtifact.model_validate(data)
    except Exception as exc:
        raise IngestJobError(f"IRArtifact v1 contract 校验失败: {exc}") from exc
    if artifact_type != "ir_v1":
        raise IngestJobError(f"IR artifact_type 必须为 ir_v1，实际 {artifact_type!r}")
    if expected_task_id is not None and artifact.task_id != expected_task_id:
        raise IngestJobError("IR artifact task_id 与权威 asset/task 不一致")
    if expected_asset_id is not None and artifact.asset_id != expected_asset_id:
        raise IngestJobError("IR artifact asset_id 与权威 asset/task 不一致")
    if not artifact.seeds:
        raise IngestJobError("IR artifact v1 必须携带非空 seeds")
    return artifact.parsed, artifact.seeds


def seeds_from_blocks(
    blocks: list,
    *,
    document_id: str,
    visibility: str,
    owner_id: Optional[int] = None,
    security_scope: str = "default",
    parser_backend: str = "legacy_str",
) -> list[SeedKnowledgeChunk]:
    """从 blocks 现场推导 seeds（F-025：连续同类型 block 归一个 seed，跨类型必断）。

    仅作为 artifact 未携带 seeds 时的兜底推导（parser 侧正常都会产出 seeds）；
    text 用 ir.join_blocks_text（逐 block "\\n\\n" 连接 + block_span 无损映射），
    SeedKnowledgeChunk 校验器保证 span 与 text 一致（禁无映射 join）。
    """
    seeds: list[SeedKnowledgeChunk] = []
    group: list = []

    def _flush() -> None:
        if not group:
            return
        text, span = join_blocks_text(group)
        markdown = None
        if all(b.markdown for b in group):  # 组内均有 markdown 才拼（TABLE seed 用）
            markdown = "\n\n".join(b.markdown for b in group)
        seeds.append(
            SeedKnowledgeChunk(
                seed_id=f"{document_id}:w{len(seeds) + 1:04d}",
                document_id=document_id,
                block_ids=[b.block_id for b in group],
                block_type=group[0].block_type,
                page_start=min(b.page_start for b in group),
                page_end=max(b.page_end for b in group),
                parser_backend=parser_backend,
                text=text,
                markdown=markdown,
                block_span=span,
                security=SecurityMeta(
                    visibility=visibility, owner_id=owner_id, security_scope=security_scope
                ),
            )
        )
        group.clear()

    for b in blocks:
        if group and b.block_type is not group[0].block_type:
            _flush()  # 跨类型必断
        group.append(b)
    _flush()
    return seeds


def seed_to_chunk(
    seed: SeedKnowledgeChunk,
    *,
    parsed: ParsedDocument,
    source_file: str,
    seq: int,
) -> KnowledgeChunk:
    """SeedKnowledgeChunk → KnowledgeChunk（provenance 复制，与 parser._parse_node_ir 同纪律）。

    - first-class 字段 + extra 双写（loader 白名单按值透传 Milvus dynamic field；
      双写保证 first-class 缺失回落 extra 的读取路径兼容）；
    - parse_fingerprint 统一取 ParsedDocument.parse_fingerprint()（同输入稳定）；
    - visibility/security_scope 取 seed.security（fail-closed 契约，无 public 默认）；
    - chunk_id 为过渡值（loader 入库前以 canonical_id 统一覆写，R03 契约）。
    """
    fingerprint = parsed.parse_fingerprint()
    provenance_common: dict[str, Any] = {
        "parser_backend": seed.parser_backend,
        "parse_fingerprint": fingerprint,
        "document_id": seed.document_id,
        "security_scope": seed.security.security_scope,
    }
    if seed.security.owner_id is not None:
        provenance_common["owner_id"] = seed.security.owner_id
    extra: dict[str, Any] = {
        "block_ids": ",".join(seed.block_ids),
        "block_type": seed.block_type.value,
        "page_start": seed.page_start,
        "page_end": seed.page_end,
        **provenance_common,
        # seed 级无损映射（answer/审计侧可复原 per-block 视图）
        "block_span": [[b, s, e] for (b, s, e) in seed.block_span],
    }
    return KnowledgeChunk(
        chunk_id=_local_chunk_id(seed.text, seq),
        content=seed.text,
        content_type=ContentType.DOC_CHUNK,
        visibility=Visibility(seed.security.visibility),
        owner_id=seed.security.owner_id,
        source_file=source_file,
        chunk_strategy=ChunkStrategy.SEMANTIC_WINDOW,
        # ---- provenance first-class 字段 ----
        block_ids=list(seed.block_ids),
        block_type=seed.block_type.value,
        page_start=seed.page_start,
        page_end=seed.page_end,
        parser_backend=seed.parser_backend,
        parse_fingerprint=fingerprint,
        extra=extra,
    )


def _local_chunk_id(text: str, seq: int) -> str:
    """过渡态 chunk_id：内容稳定 + 文件内唯一（loader canonical_id 入库前统一覆写）。"""
    import hashlib

    h = hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]
    return f"c{h}_{seq:04d}"


# ============================================================
# source-scoped replace：按 document_id 删旧 generation（接口冻结）
# ============================================================
def delete_old_generation(document_id: str, tenant_id: str, active_fingerprint: str) -> int:
    """Retire prior versions only after candidate promotion succeeds.

    The predicate and partition both scope deletion to one tenant and one document.
    A missing active fingerprint is rejected; this function is never a broad cleanup.
    """
    if not all((document_id.strip(), tenant_id.strip(), active_fingerprint.strip())):
        raise ValueError("document_id, tenant_id and active_fingerprint are required")
    client = milvus_loader.get_milvus_client()
    if not client.has_collection(milvus_loader.COLLECTION_NAME):
        return 0
    def quote(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    partition = milvus_loader._get_partition_name(tenant_id)
    expr = (
        f"document_id == {quote(document_id)} and tenant_id == {quote(tenant_id)} "
        f"and (parse_fingerprint != {quote(active_fingerprint)} "
        f"or generation_state == \"candidate\")"
    )
    res = client.delete(
        collection_name=milvus_loader.COLLECTION_NAME,
        filter=expr, partition_name=partition,
    )
    n = 0
    if isinstance(res, dict):
        try:
            n = int(res.get("delete_count") or 0)
        except (TypeError, ValueError):
            n = 0
    logger.info(
        f"[ingest-worker] 旧 generation 退役: tenant={tenant_id} document={document_id} "
        f"active={active_fingerprint} deleted={n}"
    )
    return n


def _parse_artifact_ref(raw: Any) -> Optional[dict[str, Any]]:
    """Parse the full persisted object stat/fingerprint reference; never guess a key."""
    if not raw:
        return None
    if isinstance(raw, dict):
        d = raw
    elif isinstance(raw, str):
        s = raw.strip()
        if s.startswith("{"):
            try:
                d = json.loads(s)
            except json.JSONDecodeError:
                return None
        else:
            return None
    else:
        return None
    bucket, key = d.get("bucket"), d.get("key")
    required = ("bucket", "key", "sha256", "etag", "parse_fingerprint", "size")
    if not bucket or not key or any(d.get(name) in (None, "") for name in required[2:]):
        return None
    try:
        size = int(d["size"])
    except (TypeError, ValueError):
        return None
    digest = str(d["sha256"]).lower()
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return None
    return {**{str(k): str(v) for k, v in d.items()}, "bucket": str(bucket),
            "key": str(key), "size": size, "sha256": digest}


def _merge_patch(state: ImportState, patch: dict | None) -> ImportState:
    """节点返回的 patch 合并进 ImportState（与 pipeline.LinearImportPipeline 同语义）。"""
    patch = patch or {}
    updates = {k: v for k, v in patch.items() if hasattr(state, k)}
    if updates:
        state = state.model_copy(update=updates)
    if "error" in patch and not state.error:
        state = state.model_copy(update={"error": patch["error"]})
    return state


# ============================================================
# IngestWorker
# ============================================================
class IngestWorker(WorkerLifecycle):
    """ingest_jobs 消费者（继承 WorkerLifecycle 五阶段）。

    用法（进程入口 scripts/run_ingest_worker.py）::

        worker = IngestWorker()
        # SIGTERM/SIGINT → worker.request_shutdown()
        exit_code = await worker.run_forever()

    测试/L2 可注入：redis（RedisPort stub）、store（SourceAssetStore stub）、
    stream/group（隔离测试流）、batch_size/block_ms（提速）。
    """

    def __init__(
        self,
        spec: WorkerSpec | None = None,
        redis: Any | None = None,
        store: SourceAssetStore | None = None,
        *,
        stream: str | None = None,
        group: str = INGEST_CONSUMER_GROUP,
        batch_size: int = INGEST_BATCH_SIZE,
        block_ms: int = 2000,
        max_retry: int = MAX_INGEST_RETRY,
        retire_old_generations: bool = True,
        requeue_on_failure: bool = True,
        enable_graph: bool = True,
        allowed_task_id: str | None = None,
        require_bge_m3: bool = False,
    ) -> None:
        super().__init__(spec or build_ingest_spec(), redis)
        self._store = store                      # None → 首用时直建（生产路径）
        self._stream = stream or js.INGEST_JOBS_STREAM
        self._group = group
        self._batch_size = max(1, int(batch_size))
        self._block_ms = max(0, int(block_ms))
        self._max_retry = max(1, int(max_retry))
        self._retire_old_generations = retire_old_generations
        self._requeue_on_failure = requeue_on_failure
        self._enable_graph = enable_graph
        self._allowed_task_id = allowed_task_id
        self._require_bge_m3 = require_bge_m3
        self._inflight = 0                       # 正在处理的 job 数（shutdown flush 判据）

    # ------------------------------------------------------------
    # 阶段 1：startup —— ready 门 → 注册消费组 → 预热 embedder → 横幅
    # ------------------------------------------------------------
    async def startup(self) -> None:
        """启动（任务书冻结顺序）：wait_for_web_ready → 注册消费组 → 加载 BGE-M3 → 横幅。

        - run_forever 的 _pre_run_gate 已先过 ready 门；此处再调一次 wait_for_web_ready
          是幂等快速探测（键存在即返回），保证 startup 独立可跑（直调 startup 的场景）；
        - spec.validate() 静态非法直接拒绝启动（启停脚本契约）。
        """
        errors = self.spec.validate()
        if errors:
            raise RuntimeError(f"[ingest-worker] WorkerSpec 非法，拒绝启动: {errors}")
        await wait_for_web_ready(
            timeout_s=600.0, poll_interval=WEB_READY_POLL_INTERVAL_S,
            redis=self._redis, worker_name=self.spec.name,
        )
        ok = await js.create_consumer_group(self._stream, self._group)
        if not ok:
            # 消费组建不起来 = 消费链路不可用，fail-fast（禁带病消费）
            raise RuntimeError(f"[ingest-worker] consumer group 创建失败: {self._stream}/{self._group}")
        warm = await asyncio.to_thread(self._warm_embedder)
        logger.info(self._startup_banner() + f" | embedder_warm={warm}")

    def _warm_embedder(self) -> dict:
        """BGE-M3 embedder 预热（复用 embedder 模块单例；失败仅 WARN 不阻断）。

        embed_node 首个 job 仍会再加载并自带降级语义（sha256 伪向量默认禁入库），
        这里只做「早失败早暴露」：模型路径/显存问题在启动期就可见。
        """
        info = {"jieba": False, "bge": False}
        try:
            from app.knowledge.importer.embedder import ensure_jieba_ready

            _stopwords, jieba_ok = ensure_jieba_ready()
            info["jieba"] = bool(jieba_ok)
        except Exception as exc:  # noqa: BLE001 —— 预热失败不阻断启动
            logger.warning(f"[ingest-worker] jieba 预热失败（不阻断，embed_node 会再试）: {exc!r}")
        try:
            from app.knowledge.importer.embedder import _get_bge_model  # 懒加载单例入口

            info["bge"] = _get_bge_model() is not None
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[ingest-worker] BGE-M3 预热失败（不阻断，embed_node 会再试）: {exc!r}")
        return info

    # ------------------------------------------------------------
    # 阶段 2：run_loop —— dequeue → 逐条处理（心跳由 run_forever 负责）
    # ------------------------------------------------------------
    async def run_loop(self) -> None:
        """单轮消费：取一批 → 逐条处理（先持久状态后 XACK）。

        shutdown 语义：request_shutdown 置位后**不再取新批**；已 dequeue 的本批
        全部处理完（flush）后由 run_forever 收尾退出。
        """
        if self._shutdown_requested:
            return
        msgs = await js.dequeue(
            self._stream, self._group, self.spec.name,
            count=self._batch_size, block_ms=self._block_ms,
        )
        for msg in msgs:
            # 已领取的消息必须处理完（flush 语义）；单条失败不炸整批
            try:
                await self._process_message(msg)
            except Exception as exc:  # noqa: BLE001 —— 防毒丸式单条崩溃带崩循环
                logger.exception(f"[ingest-worker] 消息处理骨架异常（继续下一条）"
                                 f"entry={msg.get(js.ENTRY_ID_KEY)}: {type(exc).__name__}: {exc}")

    # ------------------------------------------------------------
    # 阶段 4：shutdown —— 停止取新单 → flush（deadline 内）→ 退出码
    # ------------------------------------------------------------
    async def shutdown(self, deadline_s: float = 30.0) -> int:
        """退出（v2.5 §2.2 退出行）：等待 in-flight job 收尾（deadline 默认 30s）。

        返回 0=干净退出；1=超时强退（未收尾消息留 PEL，reconciler 按 lease 过期兜底）。
        """
        self._shutdown_requested = True
        deadline = time.monotonic() + max(0.0, float(deadline_s))
        while self._inflight > 0 and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        if self._inflight > 0:
            logger.warning(f"[ingest-worker] shutdown 超时强退（inflight={self._inflight}，"
                           f"未收尾消息留 PEL 由 reconciler 兜底）")
            return 1
        logger.info("[ingest-worker] 干净退出（exit_code=0）")
        return 0

    # ------------------------------------------------------------
    # 单条消息处理（状态机主体）
    # ------------------------------------------------------------
    async def process_one(self, msg: dict) -> str:
        """Process one already-dequeued message through the normal durable fences.

        A bounded caller must configure an isolated stream and allowed_task_id;
        this method never reads another message or starts a worker loop.
        """
        if self._allowed_task_id is None or self._stream == js.INGEST_JOBS_STREAM:
            raise ValueError("process_one requires an isolated stream and allowed_task_id")
        return await self._process_message(msg)

    async def _process_message(self, msg: dict) -> str:
        """处理一条 ingest job，返回 outcome 词汇：done/skip/retry/dlq/db_error。

        契约：任何终态先持久（MySQL stage/task/重投/DLQ），最后才 XACK。
        """
        entry_id = msg.get(js.ENTRY_ID_KEY)
        if not entry_id:
            logger.error(f"[ingest-worker] 消息缺 ENTRY_ID_KEY（无法 ack，留 PEL）: {msg.get('job_id')}")
            return "no_entry"
        job_id = str(msg.get("job_id") or "?")
        task_id = str(msg.get("task_id") or "")
        if self._allowed_task_id is not None and task_id != self._allowed_task_id:
            raise ValueError("bounded ingest cannot process another task")
        asset_id = str(msg.get("asset_id") or "")
        self._inflight += 1
        try:
            return await self._process_inner(msg, entry_id, job_id, task_id, asset_id)
        finally:
            self._inflight -= 1

    async def _process_inner(self, msg: dict, entry_id: str, job_id: str, task_id: str, asset_id: str) -> str:
        context = await task_store.get_authoritative_task_asset(task_id, asset_id)
        if context is None:
            logger.error(f"[ingest-worker] task/asset relation missing; leave PEL task_id={task_id} asset_id={asset_id} job_id={job_id}")
            return "db_error"
        task, asset = context
        epoch = msg.get("execution_epoch", 0)
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
            logger.error(f"[ingest-worker] invalid execution_epoch; leave PEL task_id={task_id} asset_id={asset_id} job_id={job_id}")
            return "db_error"
        owner = f"ingest:{os.getpid()}:{uuid.uuid4().hex[:20]}"
        try:
            claimed = await task_store.claim_asset(
                asset_id, task_id=task_id, source_stage=ASSET_STAGE_IR_READY,
                target_stage=ASSET_STAGE_INGESTING, execution_epoch=epoch,
                owner=owner, lease_seconds=MYSQL_JOB_LEASE_SECONDS,
            )
        except Exception as exc:
            logger.warning(f"[ingest-worker] MySQL claim failed; leave PEL task_id={task_id} asset_id={asset_id} epoch={epoch} job_id={job_id}: {exc}")
            return "db_error"
        if not claimed:
            current = await task_store.get_authoritative_task_asset(task_id, asset_id)
            if current and (
                current[1].get("stage") != ASSET_STAGE_IR_READY
                or int(current[1].get("execution_epoch") or 0) != epoch
            ):
                await js.ack(self._stream, self._group, entry_id)
                return "skip"
            return "claim_conflict"

        stop = asyncio.Event()
        lease_lost = asyncio.Event()
        renew_task = asyncio.create_task(_renew_mysql_lease(asset_id, epoch, owner, stop, lease_lost))
        heartbeat_task = asyncio.create_task(self.maintain_heartbeat(stop, period_s=10.0))
        try:
            try:
                state = await self._prepare_state(msg, task_id, asset_id, task=task, asset=asset)
            except Exception as exc:
                return await self._fail(
                    msg, entry_id, job_id, task_id, asset_id, owner, epoch,
                    f"{type(exc).__name__}: {exc}",
                )
            if lease_lost.is_set():
                return "lease_lost"

            state.extra["document_id"] = asset["document_id"]
            state.extra["parse_fingerprint"] = asset["parse_fingerprint"]
            if self._require_bge_m3:
                state.extra["required_embedding_backend"] = "bge_m3"
            for chunk in state.chunks:
                chunk.extra["generation_state"] = "candidate"
            state, (graph_degraded, graph_reason) = await asyncio.to_thread(
                self._run_pipeline_nodes, state
            )
            if state.error:
                return await self._fail(
                    msg, entry_id, job_id, task_id, asset_id, owner, epoch, state.error,
                )
            if not state.chunks or state.imported_count != len(state.chunks):
                return await self._fail(
                    msg, entry_id, job_id, task_id, asset_id, owner, epoch,
                    f"candidate write incomplete: {state.imported_count}/{len(state.chunks)}",
                )
            if lease_lost.is_set() or not await task_store.renew_asset_lease(
                asset_id, execution_epoch=epoch, owner=owner,
                lease_seconds=MYSQL_JOB_LEASE_SECONDS,
            ):
                lease_lost.set()
                return "lease_lost"

            # All candidate rows now exist and their write count matches. Promote the
            # distinct active IDs before the MySQL completion fence. The previous
            # generation remains queryable until that durable fence succeeds.
            for chunk in state.chunks:
                chunk.extra["generation_state"] = "active"
            promoted = await asyncio.to_thread(
                milvus_loader.load_chunks, state.chunks, state.tenant_id,
            )
            if promoted != len(state.chunks):
                return await self._fail(
                    msg, entry_id, job_id, task_id, asset_id, owner, epoch,
                    f"generation promotion incomplete: {promoted}/{len(state.chunks)}",
                )
            # Canonical IDs change on candidate → active. Project only the final IDs.
            from app.knowledge.document_graph import is_document_projection_chunk
            if self._enable_graph and any(is_document_projection_chunk(c) for c in state.chunks):
                state, (graph_degraded, graph_reason) = await asyncio.to_thread(self._run_graph_node, state)
            if lease_lost.is_set() or not await task_store.renew_asset_lease(
                asset_id, execution_epoch=epoch, owner=owner,
                lease_seconds=MYSQL_JOB_LEASE_SECONDS,
            ):
                lease_lost.set()
                return "lease_lost"
            error_note = f"graph_status=degraded: {graph_reason}" if graph_degraded else None
            completed = await task_store.transition_claimed_asset(
                asset_id, execution_epoch=epoch, owner=owner,
                expected_stage=ASSET_STAGE_INGESTING, stage=ASSET_STAGE_INGESTED,
                error=error_note,
                vector_status="succeeded",
                graph_status=("skipped" if not self._enable_graph else
                              "degraded" if graph_degraded else "succeeded"),
                graph_retry_needed=graph_degraded,
            )
            if not completed:
                logger.warning(f"[ingest-worker] fencing rejected late completion task_id={task_id} asset_id={asset_id} epoch={epoch}")
                return "lease_lost"
            if any(is_document_projection_chunk(chunk) for chunk in state.chunks):
                try:
                    await task_store.record_ingest_chunk_count(task_id, asset_id, epoch, len(state.chunks))
                except Exception as exc:
                    logger.warning(f"Ingest count update failed; durable asset remains ingested: {type(exc).__name__}")

            # Retire older active rows and this version's hidden candidates only
            # after the MySQL owner/epoch completion CAS has durably succeeded.
            # Cleanup failure is non-destructive: both published and prior rows
            # remain available, and the exact scope is visible in the warning.
            if self._retire_old_generations:
                try:
                    await asyncio.to_thread(
                        delete_old_generation, asset["document_id"], state.tenant_id,
                        asset["parse_fingerprint"],
                    )
                except Exception as exc:  # noqa: BLE001 — publication is durable; preserve data
                    logger.warning(
                        "[ingest-worker] generation retirement failed after publication; "
                        "older rows retained tenant=%s document=%s: %s",
                        state.tenant_id, asset["document_id"], exc,
                    )

            if graph_degraded and self._requeue_on_failure:
                repair = js.make_message(
                    job_id=f"{job_id}-graph-repair", task_id=task_id, asset_id=asset_id,
                    attempt_snapshot=1, payload_ref=str(msg.get("payload_ref") or ""),
                    execution_epoch=epoch,
                )
                if not await js.enqueue(js.GRAPH_REPAIR_STREAM, repair):
                    logger.warning("[ingest-worker] graph_repair enqueue failed; degraded status retained")
            await self._maybe_finalize_task(task_id)
            await js.ack(self._stream, self._group, entry_id)
            logger.info(
                f"[ingest-worker] job complete task_id={task_id} asset_id={asset_id} "
                f"epoch={epoch} job_id={job_id} chunks={len(state.chunks)} graph_degraded={graph_degraded}"
            )
            return "done"
        finally:
            stop.set()
            await asyncio.gather(renew_task, heartbeat_task, return_exceptions=True)
            await self.heartbeat()

    # ------------------------------------------------------------
    # artifact → ImportState（跳过 parse 节点的状态构造）
    # ------------------------------------------------------------
    async def _prepare_state(
        self, msg: dict, task_id: str, asset_id: str, *,
        task: dict | None = None, asset: dict | None = None,
    ) -> ImportState:
        """Load the exact DB-referenced IRArtifact and validate it against task/asset authority."""
        if task is None or asset is None:
            context = await task_store.get_authoritative_task_asset(task_id, asset_id)
            if context is None:
                raise IngestJobError(f"task/asset relation missing: {task_id}/{asset_id}")
            task, asset = context

        ref = _parse_artifact_ref(asset.get("artifact_ref"))
        if not ref:
            raise IngestJobError("artifact_ref missing or incomplete (expected full stat/SHA reference)")
        if ref["parse_fingerprint"] != asset.get("parse_fingerprint"):
            raise IngestJobError("artifact_ref fingerprint does not match MySQL asset fingerprint")

        visibility = task.get("visibility")
        task_type = str(task.get("task_type") or "")
        tenant_id = str(task.get("tenant_id") or "")
        scope = str(task.get("security_scope") or "")
        if visibility not in ("private", "public") or not tenant_id or not scope or not task_type:
            raise IngestJobError("authoritative task security metadata missing (fail-closed)")
        owner_raw = task.get("user_id")
        try:
            owner_id = int(owner_raw) if owner_raw is not None else None
        except (TypeError, ValueError) as exc:
            raise IngestJobError("authoritative task owner_id is invalid") from exc

        parsed, seeds = await asyncio.to_thread(
            self._load_artifact,
            ref["bucket"], ref["key"],
            expected_sha256=ref["sha256"], expected_size=ref["size"],
            expected_task_id=task_id, expected_asset_id=asset_id,
        )
        if parsed.source.document_id != str(asset.get("document_id") or ""):
            raise IngestJobError("IR document_id does not match authoritative asset")
        if parsed.source.sha256 != str(asset.get("sha256") or "").lower():
            raise IngestJobError("IR source sha256 does not match authoritative asset")
        if parsed.source.bucket != str(asset.get("bucket") or ""):
            raise IngestJobError("IR source bucket does not match authoritative asset")
        if parsed.source.object_key != str(asset.get("object_key") or ""):
            raise IngestJobError("IR source object_key does not match authoritative asset")
        if parsed.source.file_name != str(asset.get("file_name") or ""):
            raise IngestJobError("IR source file_name does not match authoritative asset")
        if parsed.source.mime != str(asset.get("mime") or ""):
            raise IngestJobError("IR source MIME does not match authoritative asset")
        if parsed.parse_fingerprint() != asset.get("parse_fingerprint"):
            raise IngestJobError("ParsedDocument fingerprint does not match authoritative asset")
        if not seeds:
            raise IngestJobError("IRArtifact v1 must contain nonempty seeds")
        for seed in seeds:
            if seed.document_id != asset.get("document_id"):
                raise IngestJobError(f"IR seed document_id mismatch: {seed.seed_id}")
            if (
                seed.security.visibility != visibility
                or seed.security.owner_id != owner_id
                or seed.security.security_scope != scope
            ):
                raise IngestJobError(f"IR seed security differs from MySQL task authority: {seed.seed_id}")

        source_file = parsed.source.file_name
        chunks = prepare_chunks(
            parsed,
            seeds,
            tenant_id=tenant_id,
            policy=ChunkPreparationPolicy(
                token_budget=max(1, int(settings.IR_CHUNK_TOKEN_BUDGET)),
            ),
        )
        return ImportState(
            task_id=task_id, tenant_id=tenant_id, task_type=task_type,
            visibility=visibility, owner_id=owner_id, security_scope=scope,
            chunks=chunks, extra={"w4_chunks_prepared": True, "parse_trace": parsed.blocks[0].metadata},
        )

    def _load_artifact(
        self, bucket: str, key: str, *,
        expected_sha256: str, expected_size: int,
        expected_task_id: str, expected_asset_id: str,
    ) -> tuple[ParsedDocument, list[SeedKnowledgeChunk]]:
        """Fetch and hash-check the artifact before applying the shared IR contract."""
        store = self._store if self._store is not None else SourceAssetStore()
        tmp = store.fetch_to_temp(bucket, key, expected_sha256=expected_sha256)
        try:
            raw = Path(tmp).read_bytes()
            if len(raw) != expected_size:
                raise IngestJobError(
                    f"artifact size differs from persisted stat: {len(raw)} != {expected_size}"
                )
            data = json.loads(raw.decode("utf-8"))
        finally:
            store.cleanup_temp(tmp)
        return parse_artifact_json(
            data, expected_task_id=expected_task_id, expected_asset_id=expected_asset_id,
        )

    # ------------------------------------------------------------
    # 节点复用执行器（chunk → contextualize → embed → load → graph_build）
    # ------------------------------------------------------------
    def _run_pipeline_nodes(self, state: ImportState) -> tuple[ImportState, tuple[bool, str]]:
        from app.observability.tracing import span, remote_parent
        parent = remote_parent(state.extra.get("parse_trace"))
        with span("knowledge.ingest", kind="consumer", parent=parent, attributes={"task.id": state.task_id}):
            return self._run_nodes(state)

    def _run_nodes(self, state: ImportState) -> tuple[ImportState, tuple[bool, str]]:
        """按序复用 pipeline 既有节点（**不新造管道**）；返回 (state, (degraded, reason))。

        - 前四节点任一写 state.error → 立即中止（后续节点自身也判 error 跳过）；
        - graph_build_node 单独跑：其契约「失败永不抛、不写 error」→ degraded 靠
          日志锚点捕获（见 _run_graph_node）。
        """
        nodes = [
            ("contextualize", contextualize_node),
            ("embed", embed_node),
            ("load", load_node),
        ]
        if not state.extra.get("w4_chunks_prepared"):
            nodes.insert(0, ("chunk", chunk_node))
        for name, fn in nodes:
            if state.error:
                break
            try:
                from app.observability.tracing import span
                with span("knowledge." + name, attributes={"task.id": state.task_id}):
                    state = _merge_patch(state, fn(state))
                if name == "embed" and self._require_bge_m3 and not state.error:
                    if not state.chunks or any(
                        not str(chunk.extra.get("embedding_model") or "").startswith("bge-m3@")
                        or chunk.extra.get("embed_fallback")
                        or chunk.extra.get("embed_normalized") != 1
                        for chunk in state.chunks
                    ):
                        return state.model_copy(update={"error": "bounded video ingest requires normalized local BGE-M3"}), (False, "")
            except Exception as exc:  # noqa: BLE001 —— 节点理论上全包裹；防御兜底
                return state.model_copy(update={"error": f"{name} 节点异常: {type(exc).__name__}: {exc}"}), (False, "")
        if state.error:
            return state, (False, "")
        from app.knowledge.document_graph import is_document_projection_chunk
        if not self._enable_graph or any(is_document_projection_chunk(c) for c in state.chunks):
            return state, (False, "")
        state, degraded = self._run_graph_node(state)
        return state, degraded

    def _run_graph_node(self, state: ImportState) -> tuple[ImportState, tuple[bool, str]]:
        """跑 graph_build_node 并捕获「失败不阻断」WARN → (state, (degraded, reason))。

        graph_builder.graph_build_node 契约：Neo4j 失败仅 loguru WARN（文案锚点冻结：
        "Neo4j 图谱写写失败" / "图谱关系抽取失败"），不抛异常不写 state.error——
        degraded 判定只能靠日志捕获（锚点变更须同步模块常量）。
        """
        captured: list[str] = []
        sink_id = logger.add(lambda m: captured.append(str(m)), level="WARNING")
        try:
            patch = graph_build_node(state) or {}
            state = _merge_patch(state, patch)
        except Exception as exc:  # noqa: BLE001 —— 理论不可达（节点全包裹）；防御降级
            return state, (True, f"graph_build 异常: {type(exc).__name__}: {exc}")
        finally:
            try:
                logger.remove(sink_id)
            except Exception:  # noqa: BLE001
                pass
        for line in captured:
            if _GRAPH_WARN_ANCHOR_NEO4J in line or _GRAPH_WARN_ANCHOR_EXTRACT in line:
                return state, (True, line.strip()[:200])
        return state, (False, "")

    # ------------------------------------------------------------
    # 失败路径：retry CAS → 重投 / 超限 DLQ
    # ------------------------------------------------------------
    async def _fail(
        self, msg: dict, entry_id: str, job_id: str, task_id: str, asset_id: str,
        owner: str, epoch: int, reason: str,
    ) -> str:
        """Durably retry with owner+epoch fencing; ACK only after requeue or DLQ succeeds."""
        reason_short = (reason or "unspecified")[:500]
        try:
            result = await task_store.retry_claimed_asset(
                asset_id, execution_epoch=epoch, owner=owner,
                expected_stage=ASSET_STAGE_INGESTING,
                retry_stage=ASSET_STAGE_IR_READY,
                max_retries=self._max_retry, reason=f"ingest: {reason_short}",
            )
        except Exception:
            logger.exception(f"[ingest-worker] retry CAS failed; original remains in PEL task_id={task_id} asset_id={asset_id} epoch={epoch} job_id={job_id}")
            return "db_error"
        if result is None:
            return "stale_owner"

        stage, new_epoch, _retry_count = result
        if not self._requeue_on_failure:
            # A bounded command leaves a durable retryable/failed asset and
            # reports failure to its caller. It never dispatches to shared queues.
            await self._maybe_finalize_task(task_id)
            await js.ack(self._stream, self._group, entry_id)
            return "bounded_failed" if stage == ASSET_STAGE_FAILED else "bounded_retry"
        if stage == ASSET_STAGE_FAILED:
            try:
                dlq_ok = await js.send_to_dlq(
                    self._stream, dict(msg),
                    f"ingest MAX_RETRY({self._max_retry}) exceeded: {reason_short}",
                )
                if not dlq_ok:
                    return "dlq_failed"
                await task_store.mark_asset_dlq(asset_id, execution_epoch=new_epoch)
                current = await task_store.get_authoritative_task_asset(task_id, asset_id)
                if not current or current[1].get("dlq_epoch") != new_epoch:
                    return "dlq_marker_failed"
                await self._maybe_finalize_task(task_id)
                await js.ack(self._stream, self._group, entry_id)
                return "dlq"
            except Exception:
                logger.exception("[ingest-worker] DLQ persistence failed; original remains in PEL")
                return "dlq_failed"

        current = await task_store.get_authoritative_task_asset(task_id, asset_id)
        if not current or current[1].get("stage") != ASSET_STAGE_IR_READY:
            return "requeue_failed"
        if not await task_store.dispatch_asset(current[1]):
            return "requeue_failed"
        latest = await task_store.get_authoritative_task_asset(task_id, asset_id)
        if not latest or latest[1].get("dispatched_epoch") != new_epoch:
            return "requeue_failed"
        await js.ack(self._stream, self._group, entry_id)
        return "retry"

    # ------------------------------------------------------------
    # task 终态判定（CAS 守卫：已终态不重写）
    # ------------------------------------------------------------
    async def _maybe_finalize_task(self, task_id: str) -> Optional[str]:
        """全部 asset 落终态时结算 task 终态（succeeded / failed），返回写入的终态或 None。

        终态守卫（两层）：
        1. task.status 已是 succeeded/failed → 跳过（终态 CAS：四态机无回退）；
        2. 存在非终态 asset（含 in-flight "ingesting"）→ 不结算——**不用**
           task_store.aggregate_progress 的 sum-based total（未知 stage 会被丢出
           总数，in-flight 瞬态可能被误判为「全部成功」，见 ASSET_STAGE_INGESTING 注）。
        """
        task = await task_store.get_task(task_id)
        if not task:
            return None
        if task.get("status") in (task_store.STATUS_SUCCEEDED, task_store.STATUS_FAILED):
            return None  # 终态 CAS：已终态不重写
        assets = await task_store.get_source_assets(task_id)
        if not assets:
            return None
        if any((a or {}).get("stage") not in _ASSET_TERMINAL_STAGES for a in assets):
            return None  # 仍有 in-flight/未结算 asset → 不结算

        stage = await task_store.get_task_stage(task, assets=assets)
        status: Optional[str] = None
        if stage == task_store.TASK_STAGE_DONE:
            status = task_store.STATUS_SUCCEEDED
        elif stage == task_store.TASK_STAGE_DONE_PARTIAL:
            # 公开四态无 partial——部分失败语义由 asset_progress additive 投影承载（F-019）
            status = task_store.STATUS_SUCCEEDED
        elif stage == task_store.TASK_STAGE_FAILED:
            status = task_store.STATUS_FAILED
        if status is None:
            return None
        try:
            await task_store.update_task(
                task_id=task_id, status=status, finished_at=datetime.now(),
                error="ingest done_partial（部分 asset failed，见 asset_progress）"
                if stage == task_store.TASK_STAGE_DONE_PARTIAL else None,
            )
        except Exception as exc:  # noqa: BLE001 —— task 终态写失败仅告警（asset 终态已是真相源）
            logger.warning(f"[ingest-worker] task 终态写入失败（不阻断）task={task_id}: {exc!r}")
            return None
        logger.info(f"[ingest-worker] task 终态结算 task={task_id} status={status}（stage={stage}）")
        return status
