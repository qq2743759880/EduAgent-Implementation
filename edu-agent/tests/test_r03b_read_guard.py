# -*- coding: utf-8 -*-
"""W-NEXT-R03BGUARD-001：r03b_verify 防漏读 guard 新逻辑单测（MILVUSFLUSH-001 处置建议 §六-1 方案 B）。

覆盖矩阵：
  - 三/多分区全闭合无重复          → PASS
  - 分区闭合 + 跨分区重复 PK       → WARN（附重复 id 清单，不再 FAIL）
  - 分区 count != 枚举（真漏读）   → FAIL（并在 _read_all_light 接线层 raise）
  - 分区闭合但整表差无法归因       → FAIL（防 ghost 漏网）
  - Σ分区 count != 整表 count      → FAIL（对拍不闭合）
  - 同分区重复 PK                  → FAIL
  - 同 PK 三副本（gap=2）          → WARN（按冗余副本数而非去重 id 数归因）
  - _read_all_light 接线（伪客户端）: WARN 放行返回 (rows, guard) / FAIL raise RuntimeError

全部纯内存，不连 Milvus。
"""
from __future__ import annotations

import pytest

from scripts.eval import r03b_verify as m


def _ladder(*parts) -> list[dict]:
    """parts: (partition_name, count, ids)；enumerate 由 ids 长度派生（真实口径=枚举行数）。"""
    return [{"partition": n, "count": c, "enumerate": len(ids), "ids": list(ids)}
            for n, c, ids in parts]


# ---------- 纯函数 _read_guard_verdict ----------

def test_pass_multi_partition_closed_no_dup():
    # 三分区全闭合、无跨分区重复 → PASS
    ladder = _ladder(("_default", 2, [1, 2]), ("user_1", 1, [3]), ("course_public", 0, []))
    g = m._read_guard_verdict(ladder, whole_count=3, whole_enumerate=3)
    assert g["verdict"] == "PASS"
    assert g["duplicate_ids"] == []
    assert g["gap"] == 0
    assert all(p["closed"] for p in g["partitions"])


def test_pass_milvusflush_real_shape():
    # MILVUSFLUSH1 实证形态缩样：_default 3 行 + user_1 2 行（id=10 双副本各一份）
    # 整表 count=5（=Σ分区 count）、整表枚举=4（=去重唯一 id 数，PK reduce 视图）、
    # gap=1=冗余副本数=重复 PK 数 → WARN
    ladder = _ladder(("_default", 3, [1, 2, 10]), ("user_1", 2, [10, 20]))
    g = m._read_guard_verdict(ladder, whole_count=5, whole_enumerate=4)
    assert g["verdict"] == "WARN"
    assert g["duplicate_ids"] == [10]
    assert g["redundant_copies"] == g["gap"] == 1
    assert "正常语义" in g["reason"]


def test_warn_duplicate_ids_listed_not_fail():
    ladder = _ladder(("a", 4, [1, 2, 30, 40]), ("b", 3, [30, 40, 50]))
    g = m._read_guard_verdict(ladder, whole_count=7, whole_enumerate=5)
    assert g["verdict"] == "WARN"
    assert g["duplicate_ids"] == [30, 40]
    # WARN 语义要点：不再 FAIL
    assert g["verdict"] != "FAIL"


def test_fail_partition_count_mismatch_true_missing():
    # 分区 count(2) != 枚举(1)：count 可见而枚举不可读的真漏读/ghost → FAIL
    ladder = _ladder(("a", 2, [1]), ("b", 1, [3]))
    g = m._read_guard_verdict(ladder, whole_count=3, whole_enumerate=2)
    assert g["verdict"] == "FAIL"
    assert "真漏读" in g["reason"]


def test_fail_unexplained_gap_all_partitions_closed():
    # 分区全闭合、无重复、Σ分区 count==整表 count，但整表枚举(3) < 分区去重唯一 id 数(4)
    # → 整表差(1)无法由跨分区重复（冗余副本=0）解释 → FAIL（防整表枚举漏行 ghost 漏网）
    ladder = _ladder(("a", 3, [1, 2, 3]), ("b", 1, [4]))
    g = m._read_guard_verdict(ladder, whole_count=4, whole_enumerate=3)
    assert g["verdict"] == "FAIL"
    assert "无法由跨分区重复" in g["reason"] or "ghost" in g["reason"]


def test_fail_part_count_sum_mismatch():
    # Σ分区 count(3) != 整表 count(4) → 对拍不闭合（分区清单漂移/reduce 语义异常）→ FAIL
    ladder = _ladder(("a", 3, [1, 2, 3]))
    g = m._read_guard_verdict(ladder, whole_count=4, whole_enumerate=3)
    assert g["verdict"] == "FAIL"


def test_fail_same_partition_duplicate_pk():
    # 同分区重复 PK（upsert tombstone 失效）：分区枚举 > 分区 count → FAIL
    ladder = _ladder(("a", 2, [1, 1]), ("b", 1, [2]))
    g = m._read_guard_verdict(ladder, whole_count=3, whole_enumerate=3)
    assert g["verdict"] == "FAIL"


def test_warn_triplicate_pk_gap_two():
    # 同 PK 三副本：gap=2（冗余副本数），dup id 只列 1 个 → WARN
    ladder = _ladder(("a", 2, [7, 1]), ("b", 2, [7, 2]), ("c", 2, [7, 3]))
    g = m._read_guard_verdict(ladder, whole_count=6, whole_enumerate=4)
    assert g["verdict"] == "WARN"
    assert g["duplicate_ids"] == [7]
    assert g["redundant_copies"] == 2


# ---------- _read_all_light 接线（伪客户端，不连 Milvus） ----------

class _FakeClient:
    """duck-type MilvusClient：只实现 _read_all_light 用到的 query/list_partitions。"""

    def __init__(self, whole_rows, whole_count, part_counts, part_rows, parts):
        self._whole_rows = whole_rows
        self._whole_count = whole_count
        self._part_counts = part_counts
        self._part_rows = part_rows
        self._parts = parts

    def list_partitions(self, coll):
        return list(self._parts)

    def query(self, coll, filter=None, output_fields=None, limit=None,
              partition_names=None, timeout=None):  # noqa: A002
        if output_fields == ["count(*)"]:
            cnt = self._whole_count if not partition_names else self._part_counts[partition_names[0]]
            return [{"count(*)": cnt}]
        if partition_names:
            return list(self._part_rows[partition_names[0]])
        return list(self._whole_rows)


def test_read_all_light_warn_shape_passes_through():
    # 跨分区重复 PK：WARN 不 raise，返回 (rows, guard) 且 guard 判定可读
    whole_rows = [{"id": 1}, {"id": 2}, {"id": 10}, {"id": 20}]
    fake = _FakeClient(
        whole_rows=whole_rows, whole_count=5,
        part_counts={"a": 3, "b": 2},
        part_rows={"a": [{"id": 1}, {"id": 2}, {"id": 10}], "b": [{"id": 10}, {"id": 20}]},
        parts=["a", "b"],
    )
    rows, guard = m._read_all_light(fake)
    assert rows == whole_rows
    assert guard["verdict"] == "WARN"
    assert guard["duplicate_ids"] == [10]
    assert [p["partition"] for p in guard["partitions"]] == ["a", "b"]


def test_read_all_light_true_missing_raises():
    # 分区 b count=1 而枚举 0 → 真漏读 → RuntimeError（保持旧 guard 硬断言强度）
    fake = _FakeClient(
        whole_rows=[{"id": 1}], whole_count=2,
        part_counts={"a": 1, "b": 1},
        part_rows={"a": [{"id": 1}], "b": []},
        parts=["a", "b"],
    )
    with pytest.raises(RuntimeError, match="逐分区对拍"):
        m._read_all_light(fake)


def test_read_all_light_clean_pass():
    fake = _FakeClient(
        whole_rows=[{"id": 1}, {"id": 2}], whole_count=2,
        part_counts={"a": 1, "b": 1},
        part_rows={"a": [{"id": 1}], "b": [{"id": 2}]},
        parts=["a", "b"],
    )
    rows, guard = m._read_all_light(fake)
    assert guard["verdict"] == "PASS"
    assert len(rows) == 2
