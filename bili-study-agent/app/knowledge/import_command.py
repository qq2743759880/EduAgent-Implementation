# -*- coding: utf-8 -*-
"""G0-CMD（v2.5 §1.1 四态机）：知识导入入口 Command 迁移骨架 + side_effect_diff 捕获器。

契约来源：
- docs/yy-dev-plan-rag-v2.md G0-CMD 行
- docs/PRD-企业级RAG架构升级-v2.5-运行时治理附录.md §1.1 四态机 + §8 第 1 条
  side_effect_diff 三层 scope。

四态机（IMPORT_COMMAND_MODE，见 app/config.py；W2-S5 已落 primary 真实执行体）：
  legacy  = 入口直调 task_store.create_task，本模块零流量（默认态，全链行为与
            当前逐位一致）
  shadow  = 入口仍直调（真实产物为准），本模块 dry-run 影子执行并逐维 diff
            （结果落 test-reports/shadow/）
  primary = 入口改走 ImportCommandService；旧直调代码保留为 fallback（W2）
  cleanup = 旧直调代码删除，ImportCommandService 成为唯一执行事实源（W7）

side_effect_diff 三层 scope（PRD v2.5 §8 第 1 条；本模块只捕获 A 层）：
  A = command entry effects  —— 导入命令入口处的副作用（本批捕获，三入口插桩）
  B = runtime startup effects —— 运行时启动期副作用，**仅登记引用**（见
      test-reports/runtime-inventory/runtime-inventory.json 的
      side_effect_scope_b_registry，10 条），本模块不做捕获实现
  C = worker effects          —— 后台 worker 副作用（W3 实现捕获）

Import 面红线（治理约束，tests 有 AST 断言）：本模块只允许 import
app.config / app.knowledge.task_store / stdlib / loguru；**禁止 import
upload.py / executor.py（防循环）、worker_runtime / job_stream**。
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from loguru import logger

from app.config import settings
from app.knowledge import task_store

# ============================ 常量 ============================
# 三层 scope 声明（PRD v2.5 §8-1）：所有 diff 报告头部必须携带本声明，
# 禁止单层结论冒充全等价（A 层等价 ≠ B/C 层等价）。
SIDE_EFFECT_SCOPE: dict[str, str] = {
    "A": "command entry effects (captured)",
    "B": "runtime startup effects (listed-only, see runtime-inventory.json scope_b_registry)",
    "C": "worker effects (W3)",
}

# 四维副作用维度（A 层捕获面）
DIMENSIONS: tuple[str, ...] = (
    "storage_effects",      # MinIO put_object/upload_file 调用
    "metadata_effects",     # task_store.create_task 参数快照（五元组）
    "event_effects",        # 进程内可观测事件触发（当前扫描期 = 0 个已知触发点）
    "permission_effects",   # 入口 role/visibility/user 上下文快照
)

# 四态合法词汇
VALID_MODES: tuple[str, ...] = ("legacy", "shadow", "primary", "cleanup")

# shadow 结果落盘目录（仓库根 test-reports/shadow/，与 runtime-inventory 同根约定）
_SHADOW_DIR = Path(__file__).resolve().parents[2] / "test-reports" / "shadow"

# metadata_effects 快照的五元组键（create_task 签名对齐）
_META_KEYS: tuple[str, ...] = (
    "task_id", "task_type", "tenant_id", "visibility", "source_files_meta",
)


def _scope_declaration() -> str:
    """把三层 scope 声明压成单行（diff 报告头部用）。"""
    return "SIDE_EFFECT_SCOPE: " + " | ".join(f"{k}={v}" for k, v in SIDE_EFFECT_SCOPE.items())


def _summarize(value: Any, limit: int = 200) -> Any:
    """参数摘要化（shadow 报告 JSON 安全 + 防大对象撑爆日志）：list/dict 截断描述。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return f"<list len={len(value)}>"
    if isinstance(value, dict):
        return f"<dict keys={sorted(map(str, value.keys()))[:8]}>"
    return f"<{type(value).__name__}>"


def _snapshot_meta(payload: dict) -> dict:
    """从入口 payload 提取 create_task 五元组参数快照（值做 JSON 安全摘要）。"""
    return {k: _summarize(payload.get(k)) for k in _META_KEYS}


# ============================ SideEffectProbe（A 层捕获器） ============================
class StorageCallRecorder:
    """请求级（request-scoped）存储副作用记录器（G0-HARDENING CMD-H1）。

    设计裁定（审核 CMD-H1）：**禁止**在并发生产请求上对 MinioUploader 类做全局
    monkey-patch —— 类级补丁跨请求共享状态，A 请求的调用会记进 B 请求的探针
    （跨请求污染）。改为**显式传参注入**：入口把 `recorder` 传进
    ``_upload_to_minio(recorder=...)``，上传 helper 在调用点把 MinIO 方法调用
    逐次 ``recorder.record_storage(...)``——捕获链路是调用图上的显式数据流，
    无全局可变状态，天然并发安全。

    这不是全局 patch 的替代品，而是 A 层捕获的唯一合法形态：单测/离线工具
    （无并发）仍可用 SideEffectProbe 的类补丁模式；生产 shadow 观测一律走本类。
    """

    def __init__(self, *, entry: str = "unknown") -> None:
        self.entry = entry
        self.storage_calls: list[dict] = []

    def record_storage(self, *, method: str, object_key: str = "",
                       bucket: str = "", outcome: str = "ok",
                       detail: str = "") -> None:
        """记录一次存储调用（参数做 JSON 安全摘要）。"""
        self.storage_calls.append({
            "method": method,
            "object_key": _summarize(object_key),
            "bucket": _summarize(bucket),
            "outcome": outcome,      # ok | degraded（MinIO 不可用降级也算副作用事实）
            "detail": _summarize(detail),
            "at": datetime.now().isoformat(timespec="seconds"),
        })

    def snapshot(self) -> dict:
        return {"count": len(self.storage_calls), "calls": self.storage_calls}


class SideEffectProbe:
    """A 层副作用捕获器（上下文管理器）。

    捕获四维（DIMENSIONS）：
      - storage_effects：monkey-patch 式包装 MinioUploader.put_object / upload_file
        （退出时还原），记录调用方法名 + 参数摘要；
      - metadata_effects：create_task 收到的参数快照（五元组），经
        ``capture_metadata()`` 或 ``run_shadow_comparison`` 注入；
      - event_effects：进程内可观测事件触发。**当前代码库扫描期 = 0 个已知事件
        触发点**，登记为空列表（不硬造）；待后续接入事件总线后补 TODO；
      - permission_effects：入口传入的 role/visibility/user 上下文快照，经
        ``capture_permission()`` 注入。

    TODO(G0-CMD-followup): event_effects 当前为占位空集，PRD §8 要求后续
    接入进程内事件总线后补真实触发计数。

    并发注意（G0-HARDENING CMD-H1）：本类的类级 monkey-patch **只允许**在单测/
    离线工具（无并发）使用；生产 shadow 观测一律走 `StorageCallRecorder`（显式
    传参注入，请求级隔离）。
    """

    def __init__(self) -> None:
        self.storage_calls: list[dict] = []       # storage_effects 记录
        self.metadata_snapshot: dict | None = None  # metadata_effects 快照
        self.event_effects: list[dict] = []       # event_effects（当前恒空）
        self.permission_snapshot: dict | None = None  # permission_effects 快照
        self._patched: list[tuple[Any, str, Any]] = []  # (owner, attr, 原函数)

    # ---------- 上下文管理器协议 ----------
    def __enter__(self) -> "SideEffectProbe":
        self._install_patches()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._restore_patches()
        return False  # 不吞异常

    # ---------- storage_effects：MinIO 方法包装 ----------
    def _install_patches(self) -> None:
        # 延迟 import，避免模块加载期拉起 MinIO 客户端依赖链
        from app.services.minio_uploader import MinioUploader

        probe = self

        def _wrap(method_name: str):
            original = getattr(MinioUploader, method_name)

            def wrapper(self_uploader, *args, **kwargs):  # noqa: ANN001
                probe.storage_calls.append({
                    "method": method_name,
                    "args_summary": [_summarize(a) for a in args[:3]],
                    "kwargs_summary": {k: _summarize(v) for k, v in
                                       list(kwargs.items())[:5]},
                    "at": datetime.now().isoformat(timespec="seconds"),
                })
                return original(self_uploader, *args, **kwargs)

            wrapper.__name__ = f"probe_{method_name}"
            return original, wrapper

        for name in ("put_object", "upload_file"):
            original, wrapped = _wrap(name)
            setattr(MinioUploader, name, wrapped)
            self._patched.append((MinioUploader, name, original))

    def _restore_patches(self) -> None:
        for owner, name, original in self._patched:
            try:
                setattr(owner, name, original)
            except Exception:  # noqa: BLE001  还原失败不吞（防御性，理论不可达）
                logger.warning(f"[import_command] 还原 MinioUploader.{name} 失败")
        self._patched.clear()

    # ---------- metadata / permission 快照注入 ----------
    def capture_metadata(self, payload: dict) -> None:
        """记录 create_task 收到的参数快照（五元组，见 _META_KEYS）。"""
        self.metadata_snapshot = _snapshot_meta(payload)

    def capture_permission(
        self,
        *,
        role: str | None = None,
        visibility: str | None = None,
        user_id: Any = None,
        tenant_id: str | None = None,
    ) -> None:
        """记录入口权限上下文快照（role/visibility/user/tenant）。"""
        self.permission_snapshot = {
            "role": _summarize(role),
            "visibility": _summarize(visibility),
            "user_id": _summarize(user_id),
            "tenant_id": _summarize(tenant_id),
        }

    # ---------- 快照导出 ----------
    def snapshot(self) -> dict:
        """导出四维快照（diff / 落盘统一格式）。"""
        return {
            "storage_effects": {
                "count": len(self.storage_calls),
                "calls": self.storage_calls,
            },
            "metadata_effects": self.metadata_snapshot or {},
            "event_effects": {
                # TODO(G0-CMD-followup): 进程内事件总线接入前恒空（不硬造）
                "known_trigger_points": 0,
                "fired": self.event_effects,
            },
            "permission_effects": self.permission_snapshot or {},
        }


# ============================ diff ============================
def diff(old_capture: dict, new_capture: dict) -> dict:
    """逐维对比两份四维快照。

    输出 ``{dimension: {same: bool, detail}}``——参数一致但副作用不一致必须能
    暴露（例：metadata_effects same=True 而 storage_effects same=False）。

    G0-HARDENING CMD-H1 storage 维判定修正：比较对象是**调用清单**（calls），
    不是 {count, calls} 整包——no-recorder 侧的 ``note`` 标记不应参与相等性
    （否则 Count(0)+note vs Count(0) 永远 same=False，空集冒充禁令误伤无存储面
    入口的合法等价）。判定语义：
      - 双方 calls 为空 → same=True（且 detail 携带 note 供人工核查）；
      - calls 非空且逐项不等 → same=False（真实副作用分歧）。
    """
    out: dict[str, dict] = {}
    for dim in DIMENSIONS:
        old_v, new_v = old_capture.get(dim), new_capture.get(dim)
        if dim == "storage_effects":
            old_calls = (old_v or {}).get("calls") or []
            new_calls = (new_v or {}).get("calls") or []
            same = old_calls == new_calls
            detail: dict[str, Any] = {
                "same": same,
                "old_count": (old_v or {}).get("count"),
                "new_count": (new_v or {}).get("count"),
            }
            if (old_v or {}).get("note"):
                detail["old_note"] = old_v["note"]
        else:
            same = old_v == new_v
            detail = {"same": same}
            if not same:
                if dim == "event_effects":
                    detail["old_fired"] = (old_v or {}).get("fired")
                    detail["new_fired"] = (new_v or {}).get("fired")
                else:
                    detail["old"] = old_v
                    detail["new"] = new_v
        out[dim] = detail
    return out


# ============================ primary 执行体（W2-S5） ============================
# MinIO 源文件留存 bucket（upload.py _upload_to_minio 的固定 bucket，30 天生命周期）
_PRIMARY_UPLOAD_BUCKET = settings.MINIO_BUCKET_UPLOAD
# 无 MinIO 对象的 degrade 约定标注（W2 任务书裁定：MCP 仅本地路径 / MinIO 降级
# 均不阻断导入，资产行落 bucket/object_key 双 NULL + error 留痕，legacy 分支语义）
_NO_MINIO_OBJECT_ERROR = "no-minio-object(legacy-local-path)"


def _build_source_assets(source_files_meta: list[dict]) -> list[dict]:
    """primary 态源资产行构造（每文件一行，PRD v2.2 §2/§5——身份随 asset 持久化）。

    - document_id：每文件生成 uuid 短 id；调用方 meta 里显式带 document_id 时
      尊重调用方（幂等重放需要稳定 id 的口子，task_store 同纪律）；
    - bucket/object_key：有 MinIO 对象 → 显式 bucket（缺省 edu-upload）+ key；无对象（MCP 仅本地
      路径 / MinIO 降级）→ 双 None + ``error= no-minio-object(legacy-local-path)``
      degrade 留痕（禁止让 MCP 入口被 MinIO 契约阻断——管道由入口本地路径兜底）；
    - sha256/mime/size_bytes/file_name：入口 meta 有则透传（upload 两入口补
      sha256；MCP 路径无 sha256 落 NULL，不硬造）；
    - stage 不在此指定：task_store.create_source_assets 冻结起点
      queued_parser，不接受调用方指定。
    """
    assets: list[dict] = []
    for i, m in enumerate(source_files_meta or []):
        m = m if isinstance(m, dict) else {}
        object_key = m.get("object_key") or None
        assets.append({
            "file_index": i,
            "bucket": (m.get("bucket") or _PRIMARY_UPLOAD_BUCKET) if object_key else None,
            "object_key": object_key,
            "file_name": m.get("file_name"),
            "sha256": m.get("sha256"),
            "size_bytes": m.get("file_size"),
            "mime": m.get("content_type"),
            "document_id": m.get("document_id") or uuid.uuid4().hex,
            "error": None if object_key else _NO_MINIO_OBJECT_ERROR,
        })
    return assets


# ============================ ImportCommand ============================
class ImportCommand:
    """知识导入命令服务——v2.5 §1.1 四态机的执行体收口点（W2-S5 起 primary 真实执行）。

    四态行为（W2 落到 primary，cleanup 留 W7）：
      - legacy 态：入口直调 task_store.create_task，本类零流量（被直调时仅同签名
        转发，行为与 G0 骨架期逐位一致）；
      - shadow 态：入口仍直调（真实产物为准），run_shadow_comparison 做 dry-run
        影子执行并 diff；本类被直调时仍为纯转发（shadow 能力走 shadow_hook）；
      - primary 态：真实执行导入前半链——task 落库（user_id/document_id）+
        每文件一条 source asset 落库，返回 task dict（入口消费形态不变）；
      - cleanup：旧直调删除（W7，本 Wave 不做）。
    """

    def __init__(self, *, mode: str | None = None) -> None:
        self.mode = mode or getattr(settings, "IMPORT_COMMAND_MODE", "legacy")
        if self.mode not in VALID_MODES:
            raise ValueError(
                f"IMPORT_COMMAND_MODE 非法：{self.mode!r}（仅允许 {VALID_MODES}）"
            )

    async def create_import_task(
        self,
        *,
        task_id: str,
        task_type: str,
        tenant_id: str,
        visibility: str,
        source_files_meta: list[dict],
        total_chunks: int = 0,
        user_id: int | None = None,
        security_scope: str = "default",
    ) -> dict:
        """创建导入任务（W2-S5：primary=真实执行体，legacy/shadow=同签名转发）。

        四态机声明（PRD v2.5 §1.1）：
          legacy  入口直调，本类零流量
          shadow  入口仍直调，本类 dry-run 影子执行并 diff
          primary 入口改走本类；旧直调代码保留为 fallback（W2）
          cleanup 旧直调删除（W7）

        primary 语义（真实执行，异常原样上抛——primary 就是正式路径，入口侧
        由 HTTP 500 正常呈现）：
          1) task_store.create_task（user_id/document_id 落库；document_id=首文件
             标识，PRD v2.2 §5）；
          2) task_store.create_source_assets（每文件一条 asset，stage 由
             task_store 冻结为 queued_parser 起步）；
          3) 返回 create_task 的 task dict（原入口消费形态不变）。

        转发语义（legacy/shadow）：参数逐位透传、返回值原样返回；user_id 仅在
        显式传入时透传——保持 G0 骨架期"六参逐位透传"契约
        （tests/test_g0_import_command.py ① 锁定）。
        """
        logger.info(
            "[import_command] create_import_task 审计: "
            f"mode={self.mode} task_id={task_id} task_type={task_type} "
            f"tenant_id={tenant_id} visibility={visibility} "
            f"files={len(source_files_meta or [])} total_chunks={total_chunks} "
            f"user_id={user_id}"
        )
        if self.mode == "primary":
            return await self._execute_primary(
                task_id=task_id,
                task_type=task_type,
                tenant_id=tenant_id,
                visibility=visibility,
                source_files_meta=source_files_meta,
                total_chunks=total_chunks,
                user_id=user_id,
                security_scope=security_scope,
            )
        # legacy/shadow：同签名转发（行为不变）
        forward_kwargs: dict[str, Any] = dict(
            task_id=task_id,
            task_type=task_type,
            tenant_id=tenant_id,
            visibility=visibility,
            source_files_meta=source_files_meta,
            total_chunks=total_chunks,
        )
        if user_id is not None:
            forward_kwargs["user_id"] = user_id
        if security_scope != "default":
            forward_kwargs["security_scope"] = security_scope
        return await task_store.create_task(**forward_kwargs)

    async def _execute_primary(
        self,
        *,
        task_id: str,
        task_type: str,
        tenant_id: str,
        visibility: str,
        source_files_meta: list[dict],
        total_chunks: int = 0,
        user_id: int | None = None,
        security_scope: str = "default",
    ) -> dict:
        """primary 真实执行体：task + 每文件 asset 两条写路径收敛（唯一执行事实源）。

        写序：先 task 后 asset——task 是 1 侧真相源，asset 依赖 task_id；asset
        写失败时异常上抛（primary 正式路径不吞错，task 行留存 status=pending
        供人工/对账发现）。
        """
        assets = _build_source_assets(source_files_meta)
        # Generated document IDs must also identify task metadata consumed by ParserWorker.
        source_files_meta = [dict(meta, document_id=asset["document_id"])
                             for meta, asset in zip(source_files_meta, assets)]
        first_document_id = assets[0]["document_id"] if assets else None
        # 1) task 行（user_id 发起者归属 + document_id 主文档标识落库）
        task = await task_store.create_task(
            task_id=task_id,
            task_type=task_type,
            tenant_id=tenant_id,
            visibility=visibility,
            source_files_meta=source_files_meta,
            total_chunks=total_chunks,
            user_id=user_id,
            document_id=first_document_id,
            security_scope=security_scope,
        )
        # 2) 每文件一条 source asset（stage 由 task_store 冻结 queued_parser 起步；
        #    首文件 document_id 与 task 行一致——create_task 已直写，回填 UPDATE 幂等跳过）
        if assets:
            await task_store.create_source_assets(task_id, assets)
        logger.info(
            "[import_command] primary 执行完成: "
            f"task_id={task_id} assets={len(assets)} document_id={first_document_id}"
        )
        return task


# 模块级单例（W2-S5 起三入口 primary 态各自按请求构造 ImportCommand() 以即时读取
# IMPORT_COMMAND_MODE；本单例保留供 shadow 路径与既有测试消费）
import_command = ImportCommand()


# ============================ shadow 执行入口 ============================
def _write_shadow_report(report: dict) -> Path:
    """落 shadow 报告到 test-reports/shadow/shadow-<ts>.json（头部含 scope 声明）。"""
    _SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = _SHADOW_DIR / f"shadow-{ts}-{uuid.uuid4().hex[:4]}.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def _build_command_capture(entry_payload: dict) -> dict:
    """Command 转发产物捕获：**只做参数构造与校验，不真写库**（dry-run）。

    - metadata_effects：按 create_task 签名重构五元组参数（缺省值补齐）；
    - storage_effects / event_effects：影子上下文中 Command 转发本身不触碰
      MinIO、不触发事件 → 空集（与旧路径入口真实发生过的副作用对比，正是
      shadow 要暴露的差异面）；
    - permission_effects：透传入口 payload 里的权限上下文。
    """
    # 参数构造与校验（primary 态 create_import_task 将以此真实调用）
    rebuilt = {
        "task_id": str(entry_payload.get("task_id") or ""),
        "task_type": str(entry_payload.get("task_type") or ""),
        "tenant_id": str(entry_payload.get("tenant_id") or ""),
        "visibility": str(entry_payload.get("visibility") or ""),
        "source_files_meta": list(entry_payload.get("source_files_meta") or []),
        "total_chunks": int(entry_payload.get("total_chunks") or 0),
    }
    missing = [k for k, v in rebuilt.items() if v in ("", None) and k != "total_chunks"]
    if missing:
        raise ValueError(f"entry_payload 缺少必填参数：{missing}")

    probe = SideEffectProbe()
    # 注意：这里不进入 __enter__（不安装 MinIO patch）——dry-run 不触碰真实副作用
    probe.capture_metadata(rebuilt)
    probe.capture_permission(
        role=entry_payload.get("role"),
        visibility=rebuilt["visibility"],
        user_id=entry_payload.get("user_id"),
        tenant_id=rebuilt["tenant_id"],
    )
    return probe.snapshot()


def run_shadow_comparison(entry_payload: dict) -> dict:
    """shadow 模式对比入口（同步轻量，异常只 WARN 不上抛——影子永不阻断主链）。

    逻辑：旧路径产物（入口真实已发生的 create_task 结果 + 入口已发生的副作用
    快照）vs Command 转发产物（dry-run 参数重构 + 校验）逐维 diff，结果落
    ``test-reports/shadow/shadow-<ts>.json``（头部含 SIDE_EFFECT_SCOPE 声明）。

    entry_payload 契约（三入口插桩处构造）：
      task_id/task_type/tenant_id/visibility/source_files_meta/total_chunks
      —— create_task 五元组 + total_chunks；
      role/user_id —— 可选权限上下文；
      entry —— 入口标识（upload_user / upload_admin / mcp_executor）；
      legacy_task —— 入口 create_task 真实返回的 task dict；
      old_capture —— 可选：入口用 SideEffectProbe 真实捕获的四维快照（缺省时
      metadata_effects 以 legacy_task 反推，storage/event 恒空）。
    """
    started = time.perf_counter()
    entry = str(entry_payload.get("entry") or "unknown")
    report: dict[str, Any] = {
        "schema": "g0-cmd-shadow-report/v1",
        "scope_declaration": _scope_declaration(),
        "mode": getattr(settings, "IMPORT_COMMAND_MODE", "legacy"),
        "entry": entry,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        # Command 侧（dry-run：只做参数构造与校验，不真写库）
        new_capture = _build_command_capture(entry_payload)

        # 旧路径侧（G0-HARDENING CMD-H1）：优先用入口真实捕获快照（StorageCallRecorder
        # request-scoped 注入的 old_capture——storage 维含 MinIO 成功/降级真实事实）；
        # 无 recorder 的入口（如 MCP 无存储面）按参数反推 metadata、storage 恒空并
        # 在 detail 标注 "no-recorder"——**禁止再把空集冒充为真实捕获**。
        old_capture = entry_payload.get("old_capture")
        if not isinstance(old_capture, dict):
            legacy_task = entry_payload.get("legacy_task") or {}
            meta_source = (legacy_task or entry_payload).copy()
            if legacy_task and "source_files_meta" not in meta_source:
                meta_source["source_files_meta"] = legacy_task.get("source_files")
            old_capture = {
                "storage_effects": {"count": 0, "calls": [], "note": "no-recorder"},
                "metadata_effects": _snapshot_meta(meta_source),
                "event_effects": {"known_trigger_points": 0, "fired": []},
                "permission_effects": {
                    "role": _summarize(entry_payload.get("role")),
                    "visibility": _summarize(entry_payload.get("visibility")),
                    "user_id": _summarize(entry_payload.get("user_id")),
                    "tenant_id": _summarize(entry_payload.get("tenant_id")),
                },
            }
        else:
            # 合并入口真实捕获：recorder 只管 storage 维，metadata/permission 维
            # 以入口 payload 反推补齐（recorder 不重复记录这两维）
            legacy_task = entry_payload.get("legacy_task") or {}
            meta_source = (legacy_task or entry_payload).copy()
            if legacy_task and "source_files_meta" not in meta_source:
                meta_source["source_files_meta"] = legacy_task.get("source_files")
            old_capture = {
                "storage_effects": old_capture.get("storage_effects") or {"count": 0, "calls": []},
                "metadata_effects": old_capture.get("metadata_effects") or _snapshot_meta(meta_source),
                "event_effects": old_capture.get("event_effects")
                                or {"known_trigger_points": 0, "fired": []},
                "permission_effects": old_capture.get("permission_effects") or {
                    "role": _summarize(entry_payload.get("role")),
                    "visibility": _summarize(entry_payload.get("visibility")),
                    "user_id": _summarize(entry_payload.get("user_id")),
                    "tenant_id": _summarize(entry_payload.get("tenant_id")),
                },
            }

        dimension_diff = diff(old_capture, new_capture)
        all_same = all(d["same"] for d in dimension_diff.values())
        report.update({
            "diff": dimension_diff,
            "all_same": all_same,
            "conclusion": (
                "A-layer equivalent (B,C listed-only; runtime-inventory.json / W3)"
                if all_same else
                "A-layer DIFF detected — params may match while side effects diverge"
            ),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        })

        path = _write_shadow_report(report)
        report["report_path"] = str(path)
        logger.info(
            f"[import_command] shadow 对比完成 entry={entry} all_same={all_same} "
            f"report={path.name}"
        )
    except Exception as exc:  # noqa: BLE001  影子失败只 WARN，绝不影响入口主链
        report["error"] = f"{type(exc).__name__}: {exc}"
        logger.warning(f"[import_command] shadow 对比失败（忽略，不影响主链）: {exc!r}")
        try:
            path = _write_shadow_report(report)
            report["report_path"] = str(path)
        except Exception:  # noqa: BLE001  落盘也失败则放弃
            pass
    return report


def shadow_hook(entry_payload: dict) -> None:
    """三入口插桩点调用的最小钩子（fire-and-forget）。

    仅当 IMPORT_COMMAND_MODE == "shadow" 时做真实对比；legacy（默认）下零开销
    直接返回。任何异常吞掉只 WARN（影子永不阻断主链）。
    """
    if getattr(settings, "IMPORT_COMMAND_MODE", "legacy") != "shadow":
        return
    try:
        run_shadow_comparison(entry_payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[import_command] shadow hook 异常（忽略）: {exc!r}")
