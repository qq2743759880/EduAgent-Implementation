"""source_asset_store.py —— W3-02 SOURCE-ASSET-STORE（源资产获取 + artifact 存取）。

契约来源（冻结）：
- docs/PRD-企业级RAG架构升级-v2.2-分布式正确性附录.md §2（import_source_asset 行内
  bucket/object_key/sha256/artifact_ref 字段）+ §4（artifact 指纹与路径治理 F-032）
- docs/handoffs/W2-to-W3-independent-audit-handoff.md §4 W3-B（真实 caller = Parser
  Worker，不允许孤儿 helper；失败必须删 temp；max_bytes 二次限制）

职责边界（Integration 冻结）：
- 本模块只做「获取/存储」：fetch_to_temp（流式下载+sha256+限额）/ put_artifact /
  get_artifact_ref / cleanup_temp。
- 删除/回滚语义在 scripts/rollback_purge.py（那边是删除/回滚，这边是获取/存储），
  两边共享"MinIO 客户端直建、不 import app.database"的隔离纪律。

Artifact lifecycle 常量（冻结，provisioning 测试属 S8/W3-08）：
- SOURCE_RETENTION_DAYS = 30   —— 源资产留存（edu-upload 桶 30 天 lifecycle 兜底，
                                  与 minio_uploader.ensure_upload_bucket_lifecycle 同参）
- IR_ARTIFACT_RETENTION_DAYS = 90 —— IR/MD/HTML 产物审计留存（PRD v2.2 §4：90 天
                                  IR 审计与评测复现锚点）。⚠️ IR artifact 禁止写入
                                  edu-upload 桶——30 天 source lifecycle 会把 IR 一起
                                  删掉（W2→W3 handoff §4-B 红线），须独立桶/前缀。
- GOLDEN_RETENTION = "permanent" —— golden 评测资产永久保留（W1 golden 唯一考卷）。

安全边界（同 rollback_purge.py 模式，核实 2026-09-27）：
- 禁止 import app.main / app.database（防 lifespan 装配链触发）——MinIO 客户端
  minio.Minio(endpoint, access_key, secret_key, secure) 直建，配 urllib3 短超时
  （connect 3s / read 30s，流式大文件按"字节间"超时语义），杜绝 300s 挂起。
- 本模块为纯新增文件，revert 即消失（Rollback 契约）。
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

from loguru import logger

# ============================================================
# Artifact lifecycle 常量（冻结，勿改值；provisioning 属 W3-08）
# ============================================================
SOURCE_RETENTION_DAYS = 30            # 源资产留存天数（edu-upload 30d lifecycle 同参）
IR_ARTIFACT_RETENTION_DAYS = 90       # IR/MD/HTML 产物审计留存天数（PRD v2.2 §4）
GOLDEN_RETENTION = "permanent"        # golden 评测资产永久保留

# 流式下载块大小（1MB：sha256 增量 + 限额检查粒度 + 内存占用的平衡点）
_STREAM_CHUNK_SIZE = 1024 * 1024
# 默认 max_bytes：与上传链路 500MB 上限内的 200MB 解析上限对齐（任务书冻结值）
DEFAULT_MAX_BYTES = 200 * 1024 * 1024


class SourceAssetError(Exception):
    """源资产存取失败（message 恒含 bucket / key / outcome 三要素）。

    outcome 冻结词汇（Parser Worker W3-04 按此分支）：
    - "sha256 mismatch"  ：下载内容与 expected_sha256 不符（可能对象损坏/被篡改）
    - "size exceeded"    ：超过 max_bytes 二次限额（防御性，上传侧已有限制）
    - "object not found" ：S3 NoSuchKey/NoSuchBucket（对象或桶不存在）
    - "download failed"  ：其余 MinIO S3Error（权限/网络等，detail 带原始 code）
    - "upload failed"    ：put_artifact 失败（本地文件缺失/MinIO 拒绝）
    - "stat failed"      ：get_artifact_ref 失败
    """

    def __init__(self, bucket: str, key: str, outcome: str, detail: str = "") -> None:
        self.bucket = bucket
        self.key = key
        self.outcome = outcome
        self.detail = detail
        # message 三要素拼接（bucket/key/outcome 恒在，detail 可选）
        msg = f"source_asset {outcome}: bucket={bucket} key={key}"
        if detail:
            msg = f"{msg} | {detail}"
        super().__init__(msg)


class SourceAssetStore:
    """源资产存取器（MinIO 直连，独立于 app.database 装配链）。

    用法（Parser Worker W3-04 真实 caller）：
        store = SourceAssetStore()
        tmp = store.fetch_to_temp(bucket, object_key, expected_sha256=asset_sha)
        try:
            ... parser 消费 tmp ...
        finally:
            store.cleanup_temp(tmp)
    """

    def __init__(self, client: Any | None = None) -> None:
        """client 可注入（单测 mock 用）；生产路径直建短超时客户端。"""
        self._client = client if client is not None else _build_minio_client()

    def ensure_ir_artifact_bucket(self) -> dict[str, Any]:
        """Provision the dedicated IR bucket and its 90 day lifecycle rule.

        This is idempotent and deliberately does not modify the source upload bucket.
        Existing lifecycle rules are preserved; an existing conflicting ``ir/`` rule
        fails closed instead of silently shortening artifact retention.
        """
        from app.config import settings
        bucket = settings.MINIO_BUCKET_ARTIFACTS
        try:
            if not self._client.bucket_exists(bucket):
                try:
                    self._client.make_bucket(bucket)
                except Exception as exc:
                    # Another worker may win the create race. Confirm ownership/existence.
                    if not self._client.bucket_exists(bucket):
                        raise exc

            from minio.commonconfig import Filter
            from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

            try:
                config = self._client.get_bucket_lifecycle(bucket)
                # MinIO SDK returns None (rather than NoSuchLifecycleConfiguration)
                # for a bucket with no lifecycle document.
                rules = list(config.rules) if config is not None else []
            except Exception as exc:
                if getattr(exc, "code", "") != "NoSuchLifecycleConfiguration":
                    raise
                rules = []

            matching = []
            for rule in rules:
                prefix = getattr(getattr(rule, "rule_filter", None), "prefix", None)
                if prefix == "ir/":
                    matching.append(rule)
            if matching:
                valid = all(
                    rule.status == "Enabled"
                    and rule.expiration is not None
                    and rule.expiration.days == IR_ARTIFACT_RETENTION_DAYS
                    for rule in matching
                )
                if not valid:
                    raise RuntimeError("edu-artifacts has a conflicting ir/ lifecycle rule")
                return {"bucket": bucket, "created": False, "lifecycle_days": IR_ARTIFACT_RETENTION_DAYS}

            rules.append(Rule(
                status="Enabled",
                rule_id="edu-ir-artifacts-90d",
                rule_filter=Filter(prefix="ir/"),
                expiration=Expiration(days=IR_ARTIFACT_RETENTION_DAYS),
            ))
            self._client.set_bucket_lifecycle(bucket, LifecycleConfig(rules))
            return {"bucket": bucket, "created": True, "lifecycle_days": IR_ARTIFACT_RETENTION_DAYS}
        except Exception as exc:
            raise SourceAssetError(bucket, "ir/", "provision failed", f"{type(exc).__name__}: {exc}") from exc

    # ------------------------------------------------------------
    # 1. fetch_to_temp：流式下载 + sha256 校验 + max_bytes 二次限额
    # ------------------------------------------------------------
    def fetch_to_temp(
        self,
        bucket: str,
        object_key: str,
        expected_sha256: str | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        temp_dir: str | Path | None = None,
    ) -> Path:
        """把 MinIO 对象流式下载到本地临时文件，成功返回 Path。

        流程（失败路径恒先删临时文件再抛 SourceAssetError）：
        1. tempfile.mkstemp(suffix=对象扩展名) 预建临时文件（fd 即关，由 open 覆写）；
        2. get_object 流式分块读：增量 sha256 + 累计字节数；
           - 累计 > max_bytes → 删临时文件 + raise("size exceeded")（立即中止，不读全文）；
        3. expected_sha256 非空且 mismatch → 删临时文件 + raise("sha256 mismatch")；
        4. NoSuchKey/NoSuchBucket → 删临时文件 + raise("object not found")；
        5. 成功 → 返回临时文件 Path（清理责任在调用方 cleanup_temp）。

        Args:
            bucket: MinIO 桶名（如 edu-upload）
            object_key: 对象键（import_source_asset.object_key）
            expected_sha256: 上传侧落库的 64 位 hex 摘要；None/空串跳过校验
            max_bytes: 二次大小限额（默认 200MB；取等号不超限，严格 > 才拒绝）
            temp_dir: 临时目录（None 用系统 temp；给定则必须可写）
        """
        # mkstemp 后缀 = 对象键扩展名（parser 依赖扩展名识别格式，如 .pdf/.md）
        suffix = Path(object_key).suffix or ".bin"
        if temp_dir is not None:
            temp_dir = Path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)  # 给定目录缺失则兜底创建
        fd, tmp_name = tempfile.mkstemp(suffix=suffix, dir=str(temp_dir) if temp_dir else None)
        os.close(fd)  # mkstemp 返回的 fd 立即关闭，下面用 open("wb") 覆写
        tmp_path = Path(tmp_name)

        try:
            hasher = hashlib.sha256()
            total = 0
            resp = self._client.get_object(bucket, object_key)
            try:
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(_STREAM_CHUNK_SIZE)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            # 二次限额：读满限额即中止，不再吞剩余字节
                            raise SourceAssetError(
                                bucket, object_key, "size exceeded",
                                f"{total} bytes > max_bytes={max_bytes}",
                            )
                        hasher.update(chunk)
                        f.write(chunk)
            finally:
                # MinIO 响应必须归还连接（漏 release 会耗尽连接池）
                try:
                    resp.close()
                    resp.release_conn()
                except Exception:
                    pass
        except SourceAssetError:
            _safe_unlink(tmp_path)  # 业务失败路径：删临时文件后原样上抛
            raise
        except Exception as exc:
            _safe_unlink(tmp_path)  # S3Error/网络失败路径同样必须删临时文件（fail-clean）
            # MinIO S3Error（含 NoSuchKey——get_object 惰性求值时可能在首次 read 才抛）
            # 或网络异常：归一为 SourceAssetError，保留原始异常链
            code = getattr(exc, "code", "") or ""
            if code in ("NoSuchKey", "NoSuchObject", "NoSuchBucket"):
                raise SourceAssetError(
                    bucket, object_key, "object not found", f"s3_code={code}"
                ) from exc
            raise SourceAssetError(
                bucket, object_key, "download failed",
                f"{type(exc).__name__}: {exc}",
            ) from exc

        # sha256 全量校验（expected 非空才校验；空串视同未提供）
        if expected_sha256:
            actual = hasher.hexdigest()
            if actual != expected_sha256:
                _safe_unlink(tmp_path)
                raise SourceAssetError(
                    bucket, object_key, "sha256 mismatch",
                    f"expected={expected_sha256} actual={actual} size={total}",
                )

        logger.info(
            f"[SourceAssetStore] fetch 成功: {bucket}/{object_key} "
            f"→ {tmp_path.name} ({total} bytes, sha256={hasher.hexdigest()[:16]}...)"
        )
        return tmp_path

    # ------------------------------------------------------------
    # 2. put_artifact：上传 IR/MD/HTML 产物
    # ------------------------------------------------------------
    def put_artifact(self, bucket: str, key: str, local_path: str | Path,
                     content_type: str = "application/octet-stream") -> dict[str, Any]:
        """上传 artifact（IR/MD/HTML 产物），返回 {bucket, key, size_bytes}。

        注意（PRD v2.2 §4 + lifecycle 红线）：IR artifact 必须落在 90 天留存语义的
        桶/前缀（IR_ARTIFACT_RETENTION_DAYS=90），禁止写 edu-upload（30 天会误删）。
        """
        path = Path(local_path)
        if not path.is_file():
            raise SourceAssetError(
                bucket, key, "upload failed", f"local file missing: {path}"
            )
        size = path.stat().st_size
        try:
            with open(path, "rb") as f:
                self._client.put_object(
                    bucket_name=bucket,
                    object_name=key,
                    data=f,
                    length=size,
                    content_type=content_type,
                )
        except Exception as exc:
            code = getattr(exc, "code", "") or ""
            raise SourceAssetError(
                bucket, key, "upload failed", f"s3_code={code} {type(exc).__name__}: {exc}"
            ) from exc
        logger.info(f"[SourceAssetStore] artifact 上传成功: {bucket}/{key} ({size} bytes)")
        return {"bucket": bucket, "key": key, "size_bytes": size}

    # ------------------------------------------------------------
    # 3. get_artifact_ref：对象元数据引用（落库 import_source_asset.artifact_ref）
    # ------------------------------------------------------------
    def get_artifact_ref(self, bucket: str, key: str) -> dict[str, Any]:
        """stat_object → {bucket, key, size, etag, last_modified}（ISO 字符串，JSON 友好）。

        异常归一 SourceAssetError("stat failed")，供 fan-in/评测 harness 对账。
        """
        try:
            stat = self._client.stat_object(bucket, key)
        except Exception as exc:
            code = getattr(exc, "code", "") or ""
            raise SourceAssetError(
                bucket, key, "stat failed", f"s3_code={code} {type(exc).__name__}: {exc}"
            ) from exc
        return {
            "bucket": bucket,
            "key": key,
            "size": stat.size,
            "etag": stat.etag,
            "last_modified": stat.last_modified.isoformat() if stat.last_modified else None,
        }

    # ------------------------------------------------------------
    # 4. cleanup_temp：安全删临时文件（幂等，绝不抛）
    # ------------------------------------------------------------
    def cleanup_temp(self, path: str | Path | None) -> bool:
        """删除 fetch_to_temp 产出的临时文件；幂等（已不存在=成功）。

        返回 True=本次实际删除，False=文件本就不存在/清理失败（仅告警不抛，
        供 Parser Worker finally 块安全调用）。
        """
        return _safe_unlink(path)


# ============================================================
# 模块级工具（无状态，便于测试复用）
# ============================================================

def _safe_unlink(path: str | Path | None) -> bool:
    """尽力删除文件：不存在返回 False；OSError 只告警不上抛（cleanup 幂等契约）。"""
    if not path:
        return False
    p = Path(path)
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False  # 幂等：目标已消失视为成功
    except OSError as exc:
        logger.warning(f"[SourceAssetStore] 临时文件删除失败（忽略）: {p} | {exc}")
        return False


def _build_minio_client() -> Any:
    """minio.Minio 直建（settings.MINIO_*，同 rollback_purge.py 模式）。

    绝不 import app.database——init_minio 会自动建桶（副作用）且依赖 lifespan
    装配链；本模块为独立短超时连接（connect 3s / read 30s），杜绝 300s 挂起。
    read=30 的依据：流式大文件的 read 超时是"字节间"语义，单块 1MB 局域网
    远小于 30s，同时给慢盘/抖动留余量。
    """
    from minio import Minio

    from app.config import settings  # 仅配置加载，无连接副作用（已核实）

    http_client = None
    try:
        import urllib3

        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=3.0, read=30.0),
            retries=urllib3.Retry(total=1, connect=1, read=0, redirect=0),
        )
    except Exception:
        http_client = None  # urllib3 异常时退回 minio 默认客户端（仍可工作）
    kwargs: dict[str, Any] = {
        "endpoint": settings.MINIO_ENDPOINT,
        "access_key": settings.MINIO_ACCESS_KEY,
        "secret_key": settings.MINIO_SECRET_KEY,
        "secure": settings.MINIO_SECURE,  # .env 显式 false（192.168.85.101:9000 非 TLS）
    }
    if http_client is not None:
        kwargs["http_client"] = http_client
    return Minio(**kwargs)
