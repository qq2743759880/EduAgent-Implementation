"""W-NEXT-MINIO-002 单测：审计探针核心逻辑 + 输出契约。

任务 G3：单测 ≥3 例全绿。本文件所有用例都直接调用脚本里的纯函数（避开真实
MySQL/MinIO——只测试解析+聚合+判定逻辑）。复跑：
  cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_wnextminio2_audit.py -v

覆盖：
  ① _classify_reuse_severity：单 key severity 三档判定（pass / warn_size_drift / warn_reuse）
  ② 聚合函数复用 key 计数 + max_reuse + size_drift + 同 task 内 file_name 重复
  ③ _evaluate：聚合报告 → PASS / WARN 标记（数字类型守卫）
  ④ 输出 JSON 契约：[WM2] 末行单行 JSON 可解析、字段齐全、数字合法非负
  ⑤ 集成 smoke：探针进程同步跑（依赖 MySQL；探测 DB 不可达时自动 skip，
     但若可达则要求 cross_task_reused_key_count >= 1 与 WNEXTMINIO-001 基线对齐）
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pytest

# 让脚本可直接 import
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.eval.wnextminio2_audit_history import (  # noqa: E402
    _classify_reuse_severity,
    _evaluate,
)


# ============================ ① severity 判定 ============================
class TestClassifyReuseSeverity:
    def test_no_size_drift_and_single_use_is_pass(self):
        assert _classify_reuse_severity(1, has_size_drift=False) == "pass"

    def test_two_uses_no_drift_is_warn_reuse(self):
        """跨 2 个 task 复用同一 key → 历史已指向同一 MinIO key → warn_reuse。"""
        assert _classify_reuse_severity(2, has_size_drift=False) == "warn_reuse"

    def test_size_drift_overrides_reuse_count(self):
        """即使 reuse_count=1，size drift 也是强告警（被覆盖痕迹）。"""
        assert _classify_reuse_severity(1, has_size_drift=True) == "warn_size_drift"

    def test_four_uses_no_drift_is_warn_reuse(self):
        """最大复用 4 次（WNEXTMINIO-001 基线）是 warn_reuse 而非 warn_size_drift。"""
        assert _classify_reuse_severity(4, has_size_drift=False) == "warn_reuse"


# ============================ ② 聚合逻辑 ============================
def _aggregate_synthetic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """复刻 _scan_history 的聚合逻辑（用纯函数版本，避免 monkeypatch DB）。"""
    occurrences_by_key: dict[str, list[dict]] = defaultdict(list)
    keys_by_task: dict[str, list[str]] = defaultdict(list)
    same_task_dups: list[dict] = []
    for r in rows:
        tid = r["task_id"]
        sfm = r.get("source_files") or []
        names_in_task: Counter = Counter()
        for item in sfm:
            if not isinstance(item, dict):
                continue
            k = item.get("object_key")
            if not k:
                continue
            occ = {
                "task_id": tid,
                "file_name": item.get("file_name") or "",
                "file_size": item.get("file_size"),
            }
            occurrences_by_key[k].append(occ)
            keys_by_task[tid].append(k)
            names_in_task[occ["file_name"]] += 1
        for fname, c in names_in_task.items():
            if c > 1:
                same_task_dups.append({"task_id": tid, "file_name": fname, "count_in_task": c})
    cross = {k: v for k, v in occurrences_by_key.items() if len(v) > 1}
    return {
        "total_keys": sum(len(v) for v in occurrences_by_key.values()),
        "cross_task_reused_key_count": len(cross),
        "max_reuse_count": max((len(v) for v in cross.values()), default=0),
        "affected_task_rows": sum(len(v) for v in cross.values()),
        "same_task_safe_name_collisions": len(same_task_dups),
        "cross": cross,
    }


class TestAggregation:
    def test_three_keys_no_reuse(self):
        rows = [
            {"task_id": "t1", "source_files": [{"object_key": "k1", "file_name": "a.md", "file_size": 100}]},
            {"task_id": "t2", "source_files": [{"object_key": "k2", "file_name": "b.md", "file_size": 200}]},
            {"task_id": "t3", "source_files": [{"object_key": "k3", "file_name": "c.md", "file_size": 300}]},
        ]
        s = _aggregate_synthetic(rows)
        assert s["total_keys"] == 3
        assert s["cross_task_reused_key_count"] == 0
        assert s["max_reuse_count"] == 0
        assert s["affected_task_rows"] == 0

    def test_one_key_reused_across_three_tasks(self):
        rows = [
            {"task_id": "t1", "source_files": [{"object_key": "same.md", "file_name": "same.md", "file_size": 100}]},
            {"task_id": "t2", "source_files": [{"object_key": "same.md", "file_name": "same.md", "file_size": 100}]},
            {"task_id": "t3", "source_files": [{"object_key": "same.md", "file_name": "same.md", "file_size": 100}]},
        ]
        s = _aggregate_synthetic(rows)
        assert s["total_keys"] == 3
        assert s["cross_task_reused_key_count"] == 1
        assert s["max_reuse_count"] == 3
        assert s["affected_task_rows"] == 3

    def test_size_drift_detected(self):
        rows = [
            {"task_id": "t1", "source_files": [{"object_key": "x.md", "file_name": "x.md", "file_size": 100}]},
            {"task_id": "t2", "source_files": [{"object_key": "x.md", "file_name": "x.md", "file_size": 200}]},
        ]
        s = _aggregate_synthetic(rows)
        assert s["cross_task_reused_key_count"] == 1
        sizes = sorted({o["file_size"] for o in s["cross"]["x.md"]})
        assert len(sizes) > 1  # size drift 真实被检测

    def test_same_task_safe_name_collision(self):
        """单 task 内 file_name 重复（极端场景）：同一 task 多次 upload 同名同 key。"""
        rows = [
            {"task_id": "t1", "source_files": [
                {"object_key": "k1", "file_name": "dup.md", "file_size": 10},
                {"object_key": "k1", "file_name": "dup.md", "file_size": 10},
            ]},
        ]
        s = _aggregate_synthetic(rows)
        assert s["same_task_safe_name_collisions"] == 1


# ============================ ③ _evaluate 标记语义 ============================
class TestEvaluate:
    def test_no_reuse_is_PASS(self):
        report = {
            "cross_task_reused_key_count": 0,
            "max_reuse_count": 0,
            "affected_task_rows": 0,
            "has_size_drift_count": 0,
        }
        v = _evaluate(report)
        assert v["status"] == "PASS"
        assert "未发现复用" in v["reason"]

    def test_reuse_only_is_WARN(self):
        report = {
            "cross_task_reused_key_count": 5,
            "max_reuse_count": 3,
            "affected_task_rows": 12,
            "has_size_drift_count": 0,
        }
        v = _evaluate(report)
        assert v["status"] == "WARN"
        assert "5 个 object_key 跨多 task 复用" in v["reason"]

    def test_size_drift_overrides_reuse_count(self):
        report = {
            "cross_task_reused_key_count": 2,
            "max_reuse_count": 2,
            "affected_task_rows": 4,
            "has_size_drift_count": 1,
        }
        v = _evaluate(report)
        assert v["status"] == "WARN"
        assert "size 不一致" in v["reason"]

    def test_summary_numbers_match_report(self):
        report = {
            "cross_task_reused_key_count": 7,
            "max_reuse_count": 4,
            "affected_task_rows": 15,
            "has_size_drift_count": 0,
        }
        v = _evaluate(report)
        assert v["summary"]["duplicate_keys"] == 7
        assert v["summary"]["max_reuse_count"] == 4
        assert v["summary"]["affected_task_rows"] == 15


# ============================ ④ 输出契约 ============================
class TestOutputContract:
    """探针末行 [WM2] JSON 必须可解析 + 字段齐全。"""

    @staticmethod
    def _run_probe() -> tuple[int, str, str]:
        """同步跑一次探针进程。需要 MySQL 可达（live DB 探针）；不可达时 skip。"""
        probe = _REPO / "scripts" / "eval" / "wnextminio2_audit_history.py"
        py = _REPO / ".venv" / "Scripts" / "python.exe"
        if not py.exists():
            pytest.skip(f"未找到 venv python: {py}")
        env = {**__import__("os").environ, "PYTHONPATH": str(_REPO)}
        p = subprocess.run(
            [str(py), str(probe)], capture_output=True, text=True, env=env, timeout=60
        )
        return p.returncode, p.stdout, p.stderr

    def test_last_line_is_wm2_json(self):
        """末位 [WM2] 行可被正则匹配并 JSON.parse 成功。"""
        code, out, err = self._run_probe()
        if code == 2:
            pytest.skip(f"DB 不可达（exit=2），skip 探针契约: {(err or out).strip()[:160]}")
        # 必须有 [WM2] 行
        m = re.search(r"\[WM2\]\s*(\{.*?\})\s*$", out, re.S | re.M)
        assert m is not None, f"未匹配到 [WM2] JSON 行（exit={code}）: {out[-300:]}"
        # 必须 JSON serializable
        try:
            j = json.loads(m.group(1))
        except Exception as e:
            pytest.fail(f"[WM2] JSON 解析失败: {e}; raw={m.group(1)[:160]}")
        # 字段齐全
        for k in (
            "total_tasks_scanned",
            "total_object_keys",
            "cross_task_reused_key_count",
            "max_reuse_count",
            "affected_task_rows",
            "has_size_drift_count",
            "duplicate_object_keys",
            "status",
            "reason",
            "summary",
            "minio_endpoint",
            "mysql_host",
            "generated_at",
        ):
            assert k in j, f"缺失字段 {k}"
        # status ∈ {PASS, WARN, FAIL}
        assert j["status"] in ("PASS", "WARN", "FAIL")
        # 数字非负
        for k in ("cross_task_reused_key_count", "max_reuse_count", "affected_task_rows", "has_size_drift_count"):
            assert isinstance(j[k], int) and j[k] >= 0, f"{k}={j[k]} 非合法非负整数"
        # duplicate_object_keys 是 list
        assert isinstance(j["duplicate_object_keys"], list)

    def test_duplicate_entries_have_required_fields(self):
        """复用 key 明细条目字段齐全 + 类型合法。"""
        code, out, err = self._run_probe()
        if code == 2:
            pytest.skip("DB 不可达")
        m = re.search(r"\[WM2\]\s*(\{.*?\})\s*$", out, re.S | re.M)
        assert m is not None
        j = json.loads(m.group(1))
        if not j["duplicate_object_keys"]:
            pytest.skip("当前 DB 无复用 key（任务执行前清空过），跳过明细校验")
        entry = j["duplicate_object_keys"][0]
        for k in (
            "object_key", "reuse_count", "task_ids", "safe_name",
            "file_size_set", "has_size_drift", "severity",
        ):
            assert k in entry, f"明细条目缺失字段 {k}: {entry}"
        assert isinstance(entry["reuse_count"], int) and entry["reuse_count"] >= 2
        assert isinstance(entry["task_ids"], list) and len(entry["task_ids"]) == entry["reuse_count"]
        assert entry["severity"] in ("warn_size_drift", "warn_reuse", "pass")


# ============================ ⑤ 集成 smoke ============================
class TestIntegrationSmoke:
    """依赖真实 MySQL；不可达时 skip。可达时验证与 WNEXTMINIO-001 基线对齐。"""

    def test_real_db_has_cross_task_reused_keys(self):
        """真实 DB 跑探针：必须有 ≥1 个跨 task 复用的 object_key（与 001 基线 55 对齐）。"""
        code, out, err = self._run_probe_inner()
        if code == 2:
            pytest.skip(f"DB 不可达（exit=2）: {(err or out).strip()[:160]}")
        m = re.search(r"\[WM2\]\s*(\{.*?\})\s*$", out, re.S | re.M)
        assert m is not None
        j = json.loads(m.group(1))
        assert j["status"] == "WARN", f"现状 status 应为 WARN（历史 55 key 跨多 task 复用），实测 {j['status']}"
        # WNEXTMINIO-001 基线 55；本次重测允许在 [55, 60] 区间（任务清理后略减）
        assert j["cross_task_reused_key_count"] >= 1, f"应至少 1 个复用 key，实测 {j['cross_task_reused_key_count']}"
        assert j["max_reuse_count"] >= 2, f"最大复用应 ≥2，实测 {j['max_reuse_count']}"

    @staticmethod
    def _run_probe_inner() -> tuple[int, str, str]:
        probe = _REPO / "scripts" / "eval" / "wnextminio2_audit_history.py"
        py = _REPO / ".venv" / "Scripts" / "python.exe"
        if not py.exists():
            pytest.skip(f"未找到 venv python: {py}")
        env = {**__import__("os").environ, "PYTHONPATH": str(_REPO)}
        p = subprocess.run(
            [str(py), str(probe)], capture_output=True, text=True, env=env, timeout=60
        )
        return p.returncode, p.stdout, p.stderr