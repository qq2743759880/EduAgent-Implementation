# -*- coding: utf-8 -*-
"""R-M2 §M-2 制品归档层（app/common/artifact_store.py）测试。

覆盖（方案: .ai-hub/plans/neo4j-mongo-activation-plan.md §M-2）:
  - mongo GridFS round-trip: bytes/dict, sha256 一致（含 >1MB 跨 chunk 大制品）
  - 幂等: 同 (name, sha256) 重复 save 复用 aid, GridFS 不翻倍
  - 降级链: mongo 不可达 → 本地 test-reports/artifacts_local + WARN, 绝不抛异常
  - 双降级失败 → backend="none" 留痕, 仍不抛
  - local_copy 同字节工作副本; list_artifacts 前缀过滤（mongo/本地双后端）

Mongo 用专用测试库 edu_agent_rm2_test（模块收尾 drop），不污染 edu_agent。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid

import pytest

from app.common import artifact_store as st

TEST_DB = "edu_agent_rm2_test"
UNREACHABLE_URI = "mongodb://127.0.0.1:1/"


def _mongo_reachable() -> bool:
    try:
        st._reset_client()
        st._get_gridfs()
        st._client.admin.command("ping")
        return True
    except Exception:
        st._reset_client()
        return False


_mongo_up = _mongo_reachable()
mongo_needed = pytest.mark.skipif(not _mongo_up, reason="MongoDB 不可达, GridFS 用例跳过")


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch, tmp_path):
    """每个用例: 专用 mongo 测试库 + 独立本地降级目录, 用例间零串扰。"""
    monkeypatch.setenv("ARTIFACT_MONGO_DB", TEST_DB)
    monkeypatch.setenv("ARTIFACT_LOCAL_DIR", str(tmp_path / "artifacts_local"))
    st._reset_client()
    yield
    st._reset_client()


def _drop_test_db_explicit() -> None:
    """用显式 client 只删 TEST_DB——绝不走 _mongo_config() 的库名回落:
    P0 教训(前任 skip 根因): module 级 fixture 里 ARTIFACT_MONGO_DB 未设( monkeypatch
    仅函数级生效) → _mongo_config() 回落 settings.MONGO_DB='edu_agent'(生产库) →
    收尾 drop 竟删生产库; rm2_test 永不清理 → 残留制品致 dedup 断言假失败。"""
    from pymongo import MongoClient  # noqa: PLC0415

    uri, _ = st._mongo_config()
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.drop_database(TEST_DB)
    finally:
        client.close()


@pytest.fixture(scope="module", autouse=True)
def _drop_test_db():
    """模块开始/收尾均清空专用测试库——开始清库防「上次中断运行残留」（前任 skip 根因:
    崩溃运行无 teardown, 重跑时同名同 sha 制品已存在 → dedup 断言失败）。"""
    try:
        _drop_test_db_explicit()
    except Exception:
        pass
    st._reset_client()
    yield
    try:
        _drop_test_db_explicit()
    except Exception:
        pass
    st._reset_client()


# ================================================================
# GridFS 主路径
# ================================================================
@mongo_needed
def test_roundtrip_bytes_sha256_consistent():
    data = b"rm2-roundtrip-" + os.urandom(2048)
    desc = st.save_artifact("eval/test/roundtrip.bin", data,
                            metadata={"kind": "test", "source": "pytest"})
    assert desc["backend"] == "mongo" and desc["dedup"] is False
    back = st.load_artifact(desc["aid"])
    assert back == data
    assert hashlib.sha256(back).hexdigest() == desc["sha256"]


@mongo_needed
def test_roundtrip_dict_json():
    obj = {"hit_rate@5": 0.9688, "per_query": [{"query": "中文检索", "hit": True, "rr": 1.0}] * 5}
    desc = st.save_artifact("eval/test/report.json", obj)
    assert st.load_artifact_json(desc["aid"]) == obj
    # 字节级兼容: 与 eval 脚本原 json.dump(ensure_ascii=False, indent=2) 同字节
    assert st.load_artifact(desc["aid"]) == json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


@mongo_needed
def test_roundtrip_large_artifact_over_1mb():
    """>1MB 大制品（跨 GridFS 255KB chunk 边界）——id_map 1.87MB 场景等价。"""
    data = os.urandom(1024 * 1024 + 777)
    desc = st.save_artifact("eval/test/large.bin", data)
    assert desc["size"] == len(data) and desc["backend"] == "mongo"
    assert st.load_artifact(desc["aid"]) == data


@mongo_needed
def test_idempotent_same_name_and_content():
    data = b"rm2-idempotent-payload"
    d1 = st.save_artifact("eval/test/idem.json", {"k": 1})
    d2 = st.save_artifact("eval/test/idem.json", {"k": 1})
    assert d2["aid"] == d1["aid"] and d2["dedup"] is True
    d3 = st.save_artifact("eval/test/idem.json", data)  # 同名不同内容 → 新版本
    assert d3["aid"] != d1["aid"] and d3["dedup"] is False
    files = list(st._db["artifacts.files"].find({"filename": "eval/test/idem.json"}))
    assert len(files) == 2  # 两份内容, 无重复副本


@mongo_needed
def test_metadata_required_fields():
    desc = st.save_artifact("eval/test/meta.json", {"a": 1}, metadata={"kind": "k", "source": "s"})
    for key in ("sha256", "size", "created_at", "source", "aid", "name"):
        assert desc.get(key), key
    assert desc["source"] == "s" and desc["metadata"]["kind"] == "k"


@mongo_needed
def test_local_copy_written_byte_identical(tmp_path):
    data = b"rm2-local-copy-check"
    local = tmp_path / "downstream" / "copy.json"
    desc = st.save_artifact("eval/test/copy.json", {"v": 1}, local_copy=str(local))
    assert desc["local_copy_written"] is True
    assert local.read_bytes() == st.load_artifact(desc["aid"])


@mongo_needed
def test_list_artifacts_prefix_filter_mongo():
    st.save_artifact("eval/runs/a.json", {"n": 1})
    st.save_artifact("eval/runs/b.json", {"n": 2})
    st.save_artifact("other/c.json", {"n": 3})
    names = {a["name"] for a in st.list_artifacts(prefix="eval/runs/")}
    assert names == {"eval/runs/a.json", "eval/runs/b.json"}


@mongo_needed
def test_list_artifacts_first_call_mongo():
    """回归: list_artifacts 进程内首调用（无先导 save）必须走 mongo 而非误降级本地
    （WIP 2e216e8 缺陷: 直接用 _db 未先 _get_gridfs() → _db=None → TypeError → 静默回退本地空索引）。"""
    st._reset_client()  # 模拟进程首调: 客户端懒加载缓存为空
    desc = st.save_artifact("eval/first/call.json", {"first": True})
    st._reset_client()
    names = [a["name"] for a in st.list_artifacts(prefix="eval/first/")]
    assert names == ["eval/first/call.json"]
    assert st.load_artifact_json(desc["aid"]) == {"first": True}


def test_sanitize_and_type_errors():
    assert st._sanitize_name("/eval//a b/怪名.json") == "eval/a_b/怪名.json".replace("怪名", "_")
    with pytest.raises(TypeError):
        st._sanitize_name("  ")
    with pytest.raises(TypeError):
        st.save_artifact("eval/test/bad.json", 12345)  # 不支持的类型 → 编程错误 fail-fast


def test_load_missing_raises_keyerror():
    with pytest.raises(KeyError):
        st.load_artifact(f"local-{uuid.uuid4().hex}")


# ================================================================
# 降级链（mongo 不可达 → 本地 → none）
# ================================================================
def _degrade(monkeypatch):
    monkeypatch.setenv("ARTIFACT_MONGO_URI", UNREACHABLE_URI)
    st._reset_client()


def test_degraded_local_roundtrip(monkeypatch, tmp_path, caplog):
    _degrade(monkeypatch)
    with caplog.at_level(logging.WARNING, logger="app.common.artifact_store"):
        desc = st.save_artifact("eval/deg/report.json", {"degraded": True, "n": 42})
    assert desc["backend"] == "local" and desc["aid"].startswith("local-")
    assert any("降级" in r.message for r in caplog.records)  # WARN 落痕
    got = st.load_artifact(desc["aid"])
    assert json.loads(got) == {"degraded": True, "n": 42}
    assert hashlib.sha256(got).hexdigest() == desc["sha256"]
    arts = st.list_artifacts(prefix="eval/deg/")
    assert len(arts) == 1 and arts[0]["backend"] == "local" and arts[0]["sha256"] == desc["sha256"]
    # 本地文件确实在 artifacts_local 下
    flat = os.path.join(st.local_fallback_dir(), "eval__deg__report.json")
    assert os.path.exists(flat)


def test_degraded_local_idempotent(monkeypatch, tmp_path):
    _degrade(monkeypatch)
    d1 = st.save_artifact("eval/deg/idem.json", {"same": 1})
    d2 = st.save_artifact("eval/deg/idem.json", {"same": 1})
    assert d1["aid"] == d2["aid"]
    assert d2["dedup"] is True  # 本地降级路径的 dedup 标志如实上报
    assert len(st._index_read()) == 1  # 索引不翻倍


def test_degraded_local_copy_written(monkeypatch, tmp_path):
    _degrade(monkeypatch)
    local = tmp_path / "down" / "r.json"
    desc = st.save_artifact("eval/deg/copy.json", {"v": 7}, local_copy=str(local))
    assert desc["backend"] == "local" and desc["local_copy_written"] is True
    assert json.loads(local.read_bytes().decode("utf-8")) == {"v": 7}


def test_both_stores_fail_returns_none_no_raise(monkeypatch, tmp_path):
    _degrade(monkeypatch)
    # 本地降级目录置于「文件」之下 → 建目录必败
    impossible = os.path.join(str(tmp_path), "is_a_file", "sub")
    with open(os.path.join(str(tmp_path), "is_a_file"), "w") as f:
        f.write("x")
    monkeypatch.setenv("ARTIFACT_LOCAL_DIR", impossible)
    desc = st.save_artifact("eval/none/x.json", {"x": 1})  # 绝不抛
    assert desc["backend"] == "none" and "mongo=" in desc.get("error", "")
    assert "local=" in desc.get("error", "")


def test_list_degraded_prefix_filter(monkeypatch, tmp_path):
    _degrade(monkeypatch)
    st.save_artifact("eval/deg/a.json", {"n": 1})
    st.save_artifact("eval/deg/b.json", {"n": 2})
    st.save_artifact("other/d.json", {"n": 3})
    names = {a["name"] for a in st.list_artifacts(prefix="eval/deg/")}
    assert names == {"eval/deg/a.json", "eval/deg/b.json"}


@mongo_needed
def test_mongo_recovered_after_degradation(monkeypatch, tmp_path):
    """降级后恢复: 新 save 回到 mongo; 后端切换后首次入库 dedup=False。
    name 带随机后缀: 防外部写入者/残留库干扰（前任 skip + 本次复跑 flake 根因）,
    同名同 sha 去重语义已由 test_idempotent_same_name_and_content 覆盖。"""
    name = f"eval/rec/x-{uuid.uuid4().hex[:8]}.bin"
    data = b"rm2-recovery"
    monkeypatch.setenv("ARTIFACT_MONGO_URI", UNREACHABLE_URI)
    st._reset_client()
    d_local = st.save_artifact(name, data)
    assert d_local["backend"] == "local"
    monkeypatch.delenv("ARTIFACT_MONGO_URI")
    st._reset_client()
    d_mongo = st.save_artifact(name, data)
    assert d_mongo["backend"] == "mongo" and d_mongo["dedup"] is False  # 后端切换后首次入库
    assert st.load_artifact(d_mongo["aid"]) == data
