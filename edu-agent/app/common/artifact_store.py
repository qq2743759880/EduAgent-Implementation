# -*- coding: utf-8 -*-
"""M-2 大制品归档层（MongoDB GridFS + 本地降级）。

方案: .ai-hub/plans/neo4j-mongo-activation-plan.md §M-2
动机: R03 id_map(51K 行/1.87MB)、R20 dualrun results(249KB) 等 eval 大 JSON 曾被迫
force-add 进 git；本模块把「大产物写入」收口为单一入口，真身入 GridFS，
git 只留 <1MB 摘要。MySQL/业务主链不感知。

API（eval 落盘层统一调用）:
    desc = save_artifact(name, content_bytes|str|dict|list, metadata=None, local_copy=None)
    data = load_artifact(aid)                # -> bytes
    obj  = load_artifact_json(aid)           # -> json.loads(load_artifact(aid))
    arts = list_artifacts(prefix="eval/runs/")

行为契约:
1. save_artifact **绝不因存储故障抛异常断主流程**: mongo 不可达 → 自动降级写本地
   test-reports/artifacts_local/（append _index.jsonl 索引）并 logger.warning；
   本地也失败 → 返回 backend="none"（错误留痕 error 字段），仍不 raise。
2. 元数据必含 sha256/size/created_at/source；source 默认取当前脚本名。
3. 幂等: 同 (name, sha256) 重复 save 不产生新副本（GridFS 按 files 查询去重，
   本地按 _index.jsonl 去重），返回既有 aid 并标记 dedup=True。
4. load_artifact: 先 GridFS，连接异常自动降级查本地索引；仅「真不存在」抛 KeyError
   （读侧 API 契约，非降级路径）。
5. local_copy: 归档同时把字节写到调用方指定路径（兼容既有下游读者，如
   r03b_verify 读 data/r20min_runs/{tag}.json），写失败仅警告。

Mongo 参数: 优先环境变量 ARTIFACT_MONGO_URI / ARTIFACT_MONGO_DB / ARTIFACT_MONGO_TIMEOUT_MS，
缺省回落 app.config.settings（MONGO_URI/MONGO_DB），再缺省 mongodb://192.168.85.101:27017 / edu_agent。

CLI（运维/实证用，cwd=edu-agent）:
    .venv/Scripts/python.exe -m app.common.artifact_store archive <file> <name> [--source S]
    .venv/Scripts/python.exe -m app.common.artifact_store get <aid> <out_file>
    .venv/Scripts/python.exe -m app.common.artifact_store list [prefix]
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("app.common.artifact_store")

# ---------------------------------------------------------------- 路径与配置
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))            # edu-agent/app/common
_EDU_AGENT_ROOT = os.path.dirname(os.path.dirname(_MODULE_DIR))     # edu-agent/

DEFAULT_MONGO_URI = "mongodb://192.168.85.101:27017"
DEFAULT_MONGO_DB = "edu_agent"
_GRIDFS_PREFIX = "artifacts"          # 集合: artifacts.files / artifacts.chunks
_INDEX_FILE = "_index.jsonl"
_NAME_RE = re.compile(r"[^A-Za-z0-9._/\-]+")   # name 白名单外字符 → '_'


def local_fallback_dir() -> str:
    d = os.environ.get("ARTIFACT_LOCAL_DIR") or os.path.join(
        _EDU_AGENT_ROOT, "test-reports", "artifacts_local")
    return d


def _mongo_config() -> tuple[str, str]:
    uri = os.environ.get("ARTIFACT_MONGO_URI")
    db = os.environ.get("ARTIFACT_MONGO_DB")
    if not uri or not db:
        try:
            from app.config import settings  # noqa: PLC0415 延迟导入, 隔离测试/脚本环境
            uri = uri or settings.MONGO_URI
            db = db or settings.MONGO_DB
        except Exception:
            uri = uri or DEFAULT_MONGO_URI
            db = db or DEFAULT_MONGO_DB
    return uri, db


# ---------------------------------------------------------------- 序列化/工具
def _serialize(content) -> bytes:
    """bytes 原样; str 编 utf-8; dict/list 定型 JSON（与 eval 脚本 json.dump 同参数）。

    其余类型属编程错误 → TypeError（fail-fast, 不属「存储降级」范畴）。
    """
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    if isinstance(content, str):
        return content.encode("utf-8")
    if isinstance(content, (dict, list)):
        return json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")
    raise TypeError(f"artifact content must be bytes|str|dict|list, got {type(content).__name__}")


def _sanitize_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise TypeError("artifact name must be non-empty str")
    n = name.strip().lstrip("/")
    n = _NAME_RE.sub("_", n)
    parts = [p for p in n.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise TypeError(f"artifact name sanitizes to empty: {name!r}")
    return "/".join(parts)


def _local_flat_name(name: str) -> str:
    return name.replace("/", "__")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_source() -> str:
    try:
        return os.path.splitext(os.path.basename(sys.argv[0]))[0] or "unknown"
    except Exception:
        return "unknown"


def _safe_meta(metadata: dict | None) -> dict:
    """元数据 BSON 化: 非 JSON 原生类型 stringify（GridFS files.metadata 须可编码）。"""
    if not metadata:
        return {}
    try:
        return json.loads(json.dumps(metadata, ensure_ascii=False, default=str))
    except Exception:
        return {"_meta_serialize_error": repr(metadata)[:200]}


def _base_descriptor(name: str, data: bytes, metadata: dict | None) -> dict:
    return {
        "name": name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "created_at": _now_iso(),
        "source": (metadata or {}).get("source") or _default_source(),
    }


# ---------------------------------------------------------------- Mongo 客户端（懒加载单例）
_client = None
_db = None
_gridfs = None


def _reset_client() -> None:
    """测试/换库用: 清空懒加载缓存。"""
    global _client, _db, _gridfs
    try:
        if _client is not None:
            _client.close()
    except Exception:
        pass
    _client = _db = _gridfs = None


def _get_gridfs():
    global _client, _db, _gridfs
    if _gridfs is None:
        from gridfs import GridFS  # noqa: PLC0415
        from pymongo import MongoClient  # noqa: PLC0415

        uri, db_name = _mongo_config()
        timeout_ms = int(os.environ.get("ARTIFACT_MONGO_TIMEOUT_MS", "5000"))
        _client = MongoClient(
            uri, serverSelectionTimeoutMS=timeout_ms, connectTimeoutMS=timeout_ms,
            socketTimeoutMS=max(timeout_ms, 10000),
        )
        _db = _client[db_name]
        # pymongo 4.x: GridFS(db, collection=...) — collection 名即 GridFS 前缀
        _gridfs = GridFS(_db, collection=_GRIDFS_PREFIX)
    return _gridfs


# ---------------------------------------------------------------- 本地降级索引
def _index_path() -> str:
    return os.path.join(local_fallback_dir(), _INDEX_FILE)


def _index_read() -> list[dict]:
    try:
        with open(_index_path(), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        return []
    except Exception as e:  # 索引损坏不阻断降级写
        logger.warning("本地制品索引读取失败(忽略): %s", e)
        return []


def _index_append(rec: dict) -> None:
    d = local_fallback_dir()
    os.makedirs(d, exist_ok=True)
    with open(_index_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _write_local(name: str, data: bytes, desc: dict) -> tuple[str, bool]:
    """降级写本地（幂等: 同 name+sha 复用 aid 不重复追加索引）。返回 (aid, dedup)。"""
    flat = _local_flat_name(name)
    path = os.path.join(local_fallback_dir(), flat)
    existing = next((r for r in _index_read()
                     if r.get("name") == name and r.get("sha256") == desc["sha256"]), None)
    os.makedirs(local_fallback_dir(), exist_ok=True)
    tmp = path + f".tmp-{uuid.uuid4().hex[:8]}"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)  # 原子替换, 防半写
    if existing:
        return existing["aid"], True
    aid = f"local-{uuid.uuid4().hex}"
    _index_append({
        "aid": aid, "name": name, "sha256": desc["sha256"], "size": desc["size"],
        "created_at": desc["created_at"], "source": desc["source"],
        "metadata": _safe_meta(desc.get("metadata")), "path": path,
    })
    return aid, False


def _write_local_copy(local_copy: str, data: bytes) -> bool:
    try:
        d = os.path.dirname(os.path.abspath(local_copy))
        os.makedirs(d, exist_ok=True)
        with open(local_copy, "wb") as f:
            f.write(data)
        return True
    except Exception as e:
        logger.warning("local_copy 写出失败(%s): %s", local_copy, e)
        return False


# ---------------------------------------------------------------- 公开 API
def save_artifact(name: str, content, metadata: dict | None = None,
                  local_copy: str | None = None) -> dict:
    """归档一个大产物。绝不因存储故障抛异常（降级链: mongo → 本地 → none）。

    返回描述符: {aid, name, sha256, size, created_at, source, backend, dedup, metadata[, error]}。
    backend: "mongo"=GridFS 真身; "local"=降级 artifacts_local; "none"=双降级失败(仅留痕)。
    """
    sane = _sanitize_name(name)
    data = _serialize(content)
    desc = _base_descriptor(sane, data, metadata)
    desc["metadata"] = _safe_meta(metadata)
    try:
        gfs = _get_gridfs()
        # 幂等: 同 (filename, sha256) 已存在 → 复用，不重复 put
        existing = _db[f"{_GRIDFS_PREFIX}.files"].find_one(
            {"filename": sane, "metadata.sha256": desc["sha256"]})
        if existing:
            desc.update({"aid": str(existing["_id"]), "backend": "mongo", "dedup": True})
        else:
            fid = gfs.put(data, filename=sane, metadata={
                "sha256": desc["sha256"], "size": desc["size"],
                "created_at": desc["created_at"], "source": desc["source"],
                **(desc["metadata"] or {}),
            })
            desc.update({"aid": str(fid), "backend": "mongo", "dedup": False})
        if local_copy:
            desc["local_copy_written"] = _write_local_copy(local_copy, data)
        return desc
    except Exception as e:  # noqa: BLE001 降级链不区分异常类型——一律降级
        logger.warning("MongoDB 不可达(%s: %s)，制品 %s 降级落本地 %s",
                       type(e).__name__, e, sane, local_fallback_dir())
        try:
            aid, deduped = _write_local(sane, data, desc)
            desc.update({"aid": aid, "backend": "local", "dedup": deduped})
            if local_copy:
                desc["local_copy_written"] = _write_local_copy(local_copy, data)
            return desc
        except Exception as e2:  # noqa: BLE001 本地也失败 → 留痕不抛
            logger.warning("制品 %s 本地降级亦失败: %s", sane, e2)
            desc.update({"aid": None, "backend": "none", "dedup": False,
                         "error": f"mongo={type(e).__name__}: {e}; local={type(e2).__name__}: {e2}"})
            if local_copy:
                desc["local_copy_written"] = _write_local_copy(local_copy, data)
            return desc


def load_artifact(aid: str) -> bytes:
    """按 aid 取回字节。mongo 连接异常自动降级查本地索引; 真不存在抛 KeyError。"""
    aid_s = str(aid)
    try:
        from bson import ObjectId  # noqa: PLC0415
        from gridfs import NoFile  # noqa: PLC0415

        gfs = _get_gridfs()
        try:
            return gfs.get(ObjectId(aid_s)).read()
        except NoFile:
            pass  # 非 mongo id / 已被清理 → 落本地索引查找
    except KeyError:
        raise
    except Exception as e:  # noqa: BLE001 连接级故障 → 降级
        logger.warning("MongoDB 读取不可达(%s: %s)，制品 %s 降级查本地索引",
                       type(e).__name__, e, aid_s)
    for rec in _index_read():
        if rec.get("aid") == aid_s:
            with open(rec["path"], "rb") as f:
                return f.read()
    raise KeyError(f"artifact not found: {aid_s}")


def load_artifact_json(aid: str):
    return json.loads(load_artifact(aid).decode("utf-8"))


def list_artifacts(prefix: str | None = None, limit: int = 200) -> list[dict]:
    """列出制品（新→旧）。mongo 不可达时降级返回本地索引。绝不抛异常。"""
    out: list[dict] = []
    try:
        _get_gridfs()  # 首调用时懒初始化 _client/_db（否则 _db=None 误降级本地索引）
        files = _db[f"{_GRIDFS_PREFIX}.files"]
        q = {"filename": {"$regex": "^" + re.escape(prefix)}} if prefix else {}
        cur = files.find(q).sort("uploadDate", -1).limit(int(limit))
        for doc in cur:
            meta = doc.get("metadata") or {}
            out.append({
                "aid": str(doc["_id"]), "name": doc.get("filename"),
                "sha256": meta.get("sha256"), "size": doc.get("length"),
                "created_at": meta.get("created_at") or str(doc.get("uploadDate")),
                "source": meta.get("source"), "backend": "mongo",
                "metadata": {k: v for k, v in meta.items()
                             if k not in ("sha256", "size", "created_at", "source")},
            })
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("MongoDB 列举不可达(%s: %s)，降级返回本地索引", type(e).__name__, e)
    for rec in reversed(_index_read()):  # 本地索引 append-only → 倒序=新→旧
        if prefix and not str(rec.get("name", "")).startswith(prefix):
            continue
        out.append({
            "aid": rec.get("aid"), "name": rec.get("name"), "sha256": rec.get("sha256"),
            "size": rec.get("size"), "created_at": rec.get("created_at"),
            "source": rec.get("source"), "backend": "local", "metadata": rec.get("metadata") or {},
        })
    return out[:limit]


# ---------------------------------------------------------------- CLI（运维/实证）
def _cli(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(argv) >= 2 and argv[0] == "archive":
        path, name = argv[1], argv[2]
        source = argv[argv.index("--source") + 1] if "--source" in argv else None
        with open(path, "rb") as f:
            data = f.read()
        desc = save_artifact(name, data, metadata={"source": source} if source else None)
        print(json.dumps(desc, ensure_ascii=False, indent=2))
        return 0 if desc.get("backend") != "none" else 1
    if len(argv) >= 2 and argv[0] == "get":
        data = load_artifact(argv[1])
        with open(argv[2], "wb") as f:
            f.write(data)
        print(f"sha256={hashlib.sha256(data).hexdigest()} size={len(data)} → {argv[2]}")
        return 0
    if len(argv) >= 1 and argv[0] == "list":
        arts = list_artifacts(argv[1] if len(argv) > 1 else None)
        print(json.dumps(arts, ensure_ascii=False, indent=2))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
