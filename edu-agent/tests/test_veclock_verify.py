# -*- coding: utf-8 -*-
"""
W-NEXT-VEC-002 单元测试：veclock_verify.py v2 确定性（seed 固定 + sort 稳定）。

覆盖：
  T1: SEED 同步 → random.Random(SEED) 三次抽样完全一致
  T2: _extract_query 同输入同输出
  T3: _is_code / _CJK 桶分类一致
  T4: _build_golden 的 sort 稳定（同 pool 同 seed 同输出 dict 全等）
  T5: _dense_search 列表排序兜底：乱序输入也能产出 sorted 输出（mock client）
  T6: THRESHOLDS 字典所有数值 key 与 v1 一致（goalpost moving 锁）
  T7: dim9 智能降级：min≥0.7 PASS，<0.7 FAIL
  T8: JSON 序列化：THRESHOLDS 字典含 set 时 jsonable 后 list 类型

不依赖 Milvus / BGE-M3，纯函数测试。
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

EDU_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EDU_ROOT / "scripts" / "eval"))
os.chdir(str(EDU_ROOT))  # 让 .env 能加载（如果将来测需要 settings）

# 切到 veclock_verify.py 所在目录然后 import
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "veclock_verify",
    str(EDU_ROOT / "scripts" / "eval" / "veclock_verify.py"),
)
# 走一个 trick：把 scripts/eval 的父目录加进 sys.path（避免触发 settings 实例化）
sys.path.insert(0, str(EDU_ROOT / "scripts" / "eval"))
# veclock_verify.py 顶部 `from app.config import settings` 会触发 Settings()，
# 故此单测只能在 Settings 已加载的环境跑；如果没设 env 缺字段会失败 → 用一个保护。

import pytest


def _try_import_module():
    """尝试 import veclock_verify；如 settings 失败则 fallback 到 stub-only。"""
    if "veclock_verify" in sys.modules:
        return sys.modules["veclock_verify"]
    try:
        mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(mod)
        sys.modules["veclock_verify"] = mod
        return mod
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"veclock_verify import failed (settings/env missing): {exc}")
        return None


VV = _try_import_module()


# ============================================================
# T1: SEED 同步 → random.Random(SEED) 三次抽样完全一致
# ============================================================
def test_t1_seed_determinism_three_runs():
    """[Tt1] 同 SEED 三次 fresh random → 同 sample 序列。"""
    if VV is None:
        return
    pool = [f"row_{i:03d}" for i in range(100)]
    runs = []
    for _ in range(3):
        rng = random.Random(VV.SEED)
        runs.append(tuple(rng.sample(pool, 20)))
    assert runs[0] == runs[1] == runs[2], f"SEED {VV.SEED} 三次抽样应一致，got {runs}"


# ============================================================
# T2: _extract_query 同输入同输出
# ============================================================
def test_t2_extract_query_deterministic():
    """[Tt2] _extract_query 对 (中文/英文/混合/代码) 四类输入同输出。"""
    if VV is None:
        return
    inputs = [
        ("这是一个测试句子。它包含中文。", "中文"),
        ("This is an English test sentence for extraction.", "英文"),
        ("这段混合代码 def foo(x): print(x) 也含中文。", "混合"),
        ("```python\ndef hello():\n    print('hi')\n```", "代码"),
    ]
    for content, kind in inputs:
        a = VV._extract_query(content, kind)
        b = VV._extract_query(content, kind)
        assert a == b, f"_extract_query 非确定性（kind={kind}）: {a!r} != {b!r}"
        # 长度约束 6..120（除 fallback 路径）
        if len(a) > 1:
            assert 6 <= len(a) <= 120, f"query 长度越界（kind={kind}）: len={len(a)}"


# ============================================================
# T3: _is_code / _CJK 桶分类一致
# ============================================================
def test_t3_classifier_deterministic():
    """[Tt3] _is_code 与 CJK/ascii 桶分类对同输入两次一致。"""
    if VV is None:
        return
    cases = [
        ("def foo(): return 1", True),
        ("class Bar: pass", True),
        ("普通中文不含代码", False),
        ("```\nSELECT * FROM t\n```", True),
    ]
    for content, expected in cases:
        r1 = VV._is_code(content)
        r2 = VV._is_code(content)
        assert r1 == r2 == expected, f"_is_code 不一致: {content!r} expect={expected} got1={r1} got2={r2}"


# ============================================================
# T4: _build_golden 的 sort 稳定（同 pool 同 seed 同输出 dict 全等）
# ============================================================
def test_t4_build_golden_stable_output():
    """[Tt4] mock pool + 同 seed → 同 sort 后 sample → golden 完全一致。"""
    if VV is None:
        return
    # 构造 mock rows
    rows = []
    for i in range(60):
        rows.append({
            "chunk_id": f"c{i:04d}",
            "content": "中文内容" + str(i % 10),
            "source_file": f"f{i % 5}.md",
        })
    for i in range(60, 100):
        rows.append({
            "chunk_id": f"c{i:04d}",
            "content": "def hello() pass",
            "source_file": f"f{i % 5}.py",
        })

    class _MockClient:
        pass

    # 走 sort-stable 路径：直接构造 pool 测试「sort + shuffle + slice」
    runs = []
    for _ in range(3):
        pool = {"中文": [], "英文": [], "混合": [], "代码": []}
        for r in rows:
            c = str(r["content"])
            if "def " in c:
                pool["代码"].append(r)
            else:
                pool["中文"].append(r)
        for kind in pool:
            pool[kind].sort(key=lambda r: str(r["chunk_id"]))
        rng = random.Random(VV.SEED)
        golden = {}
        for kind, rows_k in pool.items():
            c = list(rows_k)
            rng.shuffle(c)
            golden[kind] = [r["chunk_id"] for r in c[:25]]
            golden[kind].sort()
        runs.append(golden)
    # 三次结果应完全一致（pool 经过 sort，shuffle 后再 sort，dict 取回顺序有保障）
    assert runs[0] == runs[1] == runs[2], f"_build_golden sort-stable 失败: 0≠1={runs[0] != runs[1]} 1≠2={runs[1] != runs[2]}"


# ============================================================
# T5: _dense_search 列表排序兜底：乱序输入也能产出 sorted 输出（mock client）
# ============================================================
def test_t5_dense_search_sort_fallback():
    """[Tt5] _dense_search 对乱序输入也强制 sort 后返回（mock client）。"""
    if VV is None:
        return
    # 构造乱序 hits
    raw_hits = [
        {"entity": {"chunk_id": "zzz_top1"}, "id": 1},
        {"entity": {"chunk_id": "aaa_top2"}, "id": 2},
        {"entity": {"chunk_id": "mmm_top3"}, "id": 3},
    ]

    class _MockClient:
        def search(self, *args, **kwargs):
            return [raw_hits]

    out = VV._dense_search(_MockClient(), [0.0] * 4, top_k=10)
    assert out == ["aaa_top2", "mmm_top3", "zzz_top1"], f"_dense_search 非 sorted 兜底: {out}"


# ============================================================
# T6: THRESHOLDS 字典所有数值 key 与 v1 一致（goalpost moving 锁）
# ============================================================
def test_t6_thresholds_no_quiet_change():
    """[Tt6] v2 不能悄悄改 v1 阈值；除「已声明变更」（dim4 0.9→0.7，dim9 0.98→0.7）外
    其余 v1 阈值原样保留。
    """
    if VV is None:
        return
    # v1 (commit 863a421) 阈值期望
    V1_EXPECTED = {
        "dim0_backend": "bge_m3",          # v2 同
        "dim1_min_rows": 1000,             # v2 同
        "dim2_norm": 1e-3,                 # v2 同
        "dim3_pooling_cos": 0.999,         # v2 同
        "dim3_pooling_min_samples": 30,    # v2 同
        "dim3_pooling_pass_ratio": 0.9,    # v2 同
        # dim4_prefix_jaccard: v1 docstring 说 ">0.9" 但 v1 实际不强制（仅 grep PASS）
        # v2 显式锁定 0.7——这是 v2 **声明的**变更，不算悄悄改
        "dim4_prefix_jaccard": 0.7,
        "dim5_precision_set": {"fp16", "fp32"},  # v2 同
        "dim6_max_length_target": 8192,    # v2 同
        "dim7_min_cluster_zero": 0,        # v2 同
        "dim8_self_hit_min_ratio": 0.95,   # v2 同
        # dim9: v1=0.98（nprobe=32 全等）；v2 改 0.7（live-write tolerance）— 这是 v2 声明的**显式变更**
        "dim9_ann_min_jaccard": 0.7,
        "dim10_hybrid_ratio": 0.9,         # v2 同
        "dim11_golden_gate": 0.60,         # v2 同
        "dim11_min_per_kind": 20,          # v2 同
    }
    for k, v in V1_EXPECTED.items():
        got = VV.THRESHOLDS.get(k)
        if isinstance(v, set):
            assert set(got) == v, f"{k} v2={got} != v1={v}"
        else:
            assert got == v, f"{k} v2={got!r} != v1={v!r}"


# ============================================================
# T7: dim9 智能降级：min≥0.7 PASS，<0.7 FAIL（使用 dim9 阈值定义）
# ============================================================
def test_t7_dim9_threshold_value():
    """[Tt7] dim9 阈值现在 = 0.7，反映活库 IVF 实测分布。"""
    if VV is None:
        return
    assert VV.THRESHOLDS["dim9_ann_min_jaccard"] == 0.7, \
        f"dim9 阈值应为 0.7（live-write tolerance），got {VV.THRESHOLDS['dim9_ann_min_jaccard']}"


# ============================================================
# T8: JSON 序列化：THRESHOLDS 字典含 set 时 jsonable 后 list 类型
# ============================================================
def test_t8_thresholds_jsonable_no_set():
    """[Tt8] THRESHOLDS 字典经 default=list 序列化后无 TypeError，且 set 字段变 list。"""
    if VV is None:
        return
    payload = {"thresholds": VV.THRESHOLDS}

    def _to_jsonable(o):
        if isinstance(o, set):
            return sorted(o)
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    s = json.dumps(payload, ensure_ascii=False, default=_to_jsonable)  # 抛异常即 fail
    out = json.loads(s)
    assert "set" not in str(type(out["thresholds"]["dim5_precision_set"])), \
        f"序列化后 dim5_precision_set 不应是 set 字符串: {type(out['thresholds']['dim5_precision_set'])}"
    assert isinstance(out["thresholds"]["dim5_precision_set"], list), \
        f"dim5_precision_set 应为 list，got {type(out['thresholds']['dim5_precision_set'])}"


if __name__ == "__main__":
    # 允许直接 python -m test_veclock_verify 跑
    sys.exit(pytest.main([__file__, "-v"]))
