"""W-NEXT-MINIO-001 契约单测：MinIO object_key 防覆盖。

背景（T14 报告 §10 P2 观察）：
旧 ``_upload_to_minio`` 把 ``safe_name`` 原样作为 ``object_key`` 传给 MinIO 的
``upload_file`` → 多次导入同名文件（不同用户 / 不同时刻 / 同/不同内容）都会沿用
同一 key → MinIO ``put_object`` 静默覆盖，导致 source_files 留存错位、无法按
object_key 反查历史版本。

修复（W-NEXT-MINIO-001）：在 ``upload.py`` 派生 ``f"{content_hash8}_{rand6}_{safe_name}"``
作为 MinIO object_key；本文件验证：
  1) 纯函数 ``_make_minio_object_key`` 在 4 个典型场景下的形态与防覆盖语义；
  2) ``_write_upload_to_disk`` 在文件落盘时正确算出 sha256 并返回；
  3) 端到端真 HTTP：两次 admin/upload 同名文件 → task 表 object_key 集合为 2 个不同 key
     （使用 MinIO 实际 list_objects 二次确认 bucket 内确有 2 个独立对象）；
  4) WNEXTRAG1 契约测试零回归（loader.classify_internal 路径不受影响）。
"""
from __future__ import annotations

import hashlib
import io
import os
import socket
import time
import uuid
from pathlib import Path

import httpx
import pytest
from fastapi import UploadFile

from app.knowledge.routers.upload import (
    _make_minio_object_key,
    _make_upload_basename,
    _write_upload_to_disk,
)


# ============================ 配置 ============================
ADMIN_USER = "adm02test"
ADMIN_PASS = "Test@123456"
HTTP_PORT = int(os.environ.get("WMINIO_HTTP_PORT", "8010"))
HTTP_BASE = f"http://127.0.0.1:{HTTP_PORT}"
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "192.168.85.101:9000")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "edu-upload")


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ============================ 1) 纯函数层面 ============================
class TestMakeMinioObjectKey:
    """_make_minio_object_key 必须保证同名不同内容 + 同名同内容都产生不同 key。"""

    def test_shape_and_components(self):
        """形态：hash8 + _ + uuid6 + _ + safe_name。"""
        sha = "0123456789abcdef" * 4  # 64 chars
        k = _make_minio_object_key("教案.md", sha)
        parts = k.split("_", 2)
        assert len(parts) == 3, f"key 段数不符: {k}"
        assert parts[0] == "01234567", f"hash8 取前 8 不对: {k}"
        assert len(parts[1]) == 6, f"uuid6 长度不对: {k}"
        assert parts[2] == "教案.md", f"safe_name 段丢了或截断: {k}"

    def test_same_name_same_content_different_random_suffix(self):
        """同名同内容：hash 相同 → 仍由 random6 区分 → 2 个不同 key（不覆盖）。

        任务规约口径 ①：不覆盖。两份独立对象保留（运维可在外部按 sha256 自行去重）。
        """
        a = _make_minio_object_key("a.md", "f" * 64)
        b = _make_minio_object_key("a.md", "f" * 64)
        assert a != b, f"同名同内容也必须产不同 key: {a}"
        # hash 段必须相同
        assert a.split("_", 2)[0] == b.split("_", 2)[0] == "f" * 8

    def test_same_name_different_content_different_keys(self):
        """同名不同内容：sha256 不同 → hash8 不同 → 2 个不同 key（不覆盖）。

        任务规约口径 ②：笔记 v1 / v2 改了几个字也绝不互相覆盖。
        """
        a = _make_minio_object_key("notes.md", "a" * 64)
        b = _make_minio_object_key("notes.md", "b" * 64)
        assert a.split("_", 2)[0] == "a" * 8
        assert b.split("_", 2)[0] == "b" * 8
        assert a != b

    def test_empty_sha256_falls_back_to_zeroes(self):
        """空 sha256（理论边界）应回退到 8 个 '0'，不抛异常。"""
        k = _make_minio_object_key("x.md", "")
        assert k.startswith("00000000_"), k


# ============================ 2) 落盘 helper 层 ============================
@pytest.mark.asyncio
async def test_write_upload_to_disk_returns_real_sha256_of_payload(tmp_path, monkeypatch):
    """_write_upload_to_disk 必须在写盘同时算出 sha256，且与外部对相同内容独立计算的 sha256 一致。

    该 sha256 是构造唯一 object_key 的指纹 —— 必须保证算出的是文件真实内容（而非空值 / 路径），
    否则 hash8 段会跨文件碰撞。
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path))  # 影响 settings.DATA_DIR
    # 配置生效需要重新加载 settings（直接 patch 它，避免 import 顺序问题）
    from app import config as _cfg
    monkeypatch.setattr(_cfg.settings, "DATA_DIR", str(tmp_path), raising=True)

    payload = b"hello wnextminio1\nbytes " + uuid.uuid4().bytes
    expected_sha = hashlib.sha256(payload).hexdigest()

    # 构造一个 FastAPI UploadFile-like（SpooledTemporaryFile）
    f = UploadFile(filename="demo.md", file=io.BytesIO(payload))
    path, size, sha = await _write_upload_to_disk(f, user_id=4242)
    try:
        assert size == len(payload)
        assert sha == expected_sha, f"sha256 不一致: {sha} vs {expected_sha}"
        assert os.path.exists(path)
        with open(path, "rb") as fh:
            assert fh.read() == payload
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ============================ 3) 端到端真 HTTP（8010 临时实例） ============================
pytestmark_http = pytest.mark.skipif(
    not _port_open("127.0.0.1", HTTP_PORT),
    reason=f"{HTTP_BASE} 不可达（需 8010 临时实例运行当前工作树代码）",
)


@pytestmark_http
def test_real_http_same_name_two_uploads_yield_two_object_keys():
    """真 HTTP 验证：两次 admin/upload 同名同内容文件 → task 表里 object_key 集合为 2 个不同 key。

    严格任务规约口径：两次 admin/upload 同文件 → 两次 task 表 source_files[0].object_key 不同 →
    且 MinIO bucket 里确有 2 个对象（mc ls 等价能力，本测试直接用 minio Python SDK 的
    list_objects 验证）。
    """
    # ---- 0) 拿 admin JWT ----
    with httpx.Client(base_url=HTTP_BASE, timeout=20.0) as c:
        r = c.post("/api/auth/login", json={"account": ADMIN_USER, "password": ADMIN_PASS})
        if r.status_code != 200:
            r = c.post(
                "/api/auth/login",
                data={"account": ADMIN_USER, "password": ADMIN_PASS},
            )
        assert r.status_code == 200, f"登录失败: {r.status_code} {r.text[:200]}"
        login_data = r.json().get("data") or r.json()
        token = login_data.get("access_token") or login_data.get("token") or ""
        assert token, f"未拿到 token: {login_data!r}"
        headers = {"Authorization": f"Bearer {token}"}

        # ---- 1) 准备同名同内容文件 ----
        same_name = f"wnextminio1_same_{uuid.uuid4().hex[:6]}.md"
        payload = b"# wnextminio1 doc\nbody = " + uuid.uuid4().bytes + b"\n"

        def _upload_once() -> tuple[str, str]:
            files = {"files": (same_name, io.BytesIO(payload), "text/markdown")}
            resp = c.post(
                "/api/knowledge/admin/upload", files=files, headers=headers
            )
            assert resp.status_code == 200, (
                f"上传失败: {resp.status_code} {resp.text[:300]}"
            )
            data = (resp.json().get("data") or {})
            task_id = data["task_id"]
            # 等任务落到 MySQL，能读出 source_files 元数据（含 object_key）
            keys = []
            for _ in range(40):
                time.sleep(0.3)
                s = c.get(
                    f"/api/knowledge/status/{task_id}", headers=headers
                )
                if s.status_code == 200:
                    sd = (s.json().get("data") or {})
                    sfm = sd.get("source_files") or []
                    if sfm and sfm[0].get("object_key"):
                        keys = [x["object_key"] for x in sfm if x.get("object_key")]
                        break
            assert keys, f"task {task_id} 未产出 object_key"
            return task_id, keys[0]

        # 留 50ms 间隔确保同秒上传时间戳能区分（虽然 hash8+rand6 已充分避免）
        _, key1 = _upload_once()
        time.sleep(0.2)
        _, key2 = _upload_once()

        # ---- 2) 任务级断言 ----
        assert key1 != key2, f"同名上传应产出 2 个不同 object_key: {key1}"
        # 形态断言：hash8 + _ + uuid6 + _ + safe_name
        for k in (key1, key2):
            parts = k.split("_", 2)
            assert len(parts) == 3, f"形态不对: {k}"
            assert len(parts[0]) == 8 and all(c in "0123456789abcdef" for c in parts[0])
            assert len(parts[1]) == 6 and all(c in "0123456789abcdef" for c in parts[1])
            assert parts[2] == same_name, f"safe_name 段不匹配: {parts[2]} vs {same_name}"

        # hash8 应等于外部对同一 payload 计算的 sha256 前 8
        ext_sha = hashlib.sha256(payload).hexdigest()[:8]
        assert key1.split("_", 2)[0] == ext_sha, (
            f"hash8 段应等于内容指纹前 8: {key1[:8]} vs {ext_sha}"
        )
        assert key2.split("_", 2)[0] == ext_sha  # 同内容 → 同 hash8

        # ---- 3) MinIO bucket 二次确认：list_objects 确有 2 个独立对象 ----
        from app.config import settings as _s
        from app.database import get_minio_client, init_minio
        try:
            init_minio()
        except Exception:
            pass  # 已初始化则跳过
        client = get_minio_client()
        bucket = _s.MINIO_BUCKET_UPLOAD or MINIO_BUCKET
        # 整个 bucket 内查包含 same_name 的对象
        all_objs = list(client.list_objects(bucket, recursive=True))
        keys_in_bucket = [
            o.object_name for o in all_objs if o.object_name.endswith(same_name)
        ]
        assert len(keys_in_bucket) >= 2, (
            f"MinIO bucket 至少应有 2 个对象（key1/key2），实测 {len(keys_in_bucket)}："
            f"{keys_in_bucket[:5]}"
        )
        assert key1 in keys_in_bucket and key2 in keys_in_bucket, (
            f"key1/key2 至少有一个不在 bucket 内：{key1} / {key2} / bucket={keys_in_bucket[:10]}"
        )


# ============================ 4) WNEXTRAG1 契约回归（防误伤） ============================
def test_wn_extrag1_basename_contract_unchanged():
    """WNEXTRAG1 修复的不变量保留：``_make_upload_basename`` 仍以 ``up_{user_id}_`` 开头，
    不命中内部来源正则。
    """
    name = _make_upload_basename(1001, "linear_algebra.md")
    assert name.startswith("up_1001_"), name
    assert "linear_algebra.md" in name
