# -*- coding: utf-8 -*-
"""
test_check_demo_timeouts.py — W-NEXT-CHECKDEMO-002 单测（防 timeout 回退）
========================================================================
任务背景：W-NEXT-CHECKDEMO-001 修了 fileURLToPath，⑰⑱ 转 PASS，但⑲ 守卫仍
FAIL——runPy 默认 timeout 不够（BGE-M3 mmap 重 load + 5 个串行 inference
batch 实测 30s+）。本单测锁住 timeout 下限，避免后续 commit 把数字改回。

设计：
  - 静态层（必跑）：grep check-demo.mjs 验证指定探针 timeout 下限
  - 动态层（按需跑）：实跑 check-demo ⑲ 段，断言 ≤ 5min（CI 反复跑用 --fail-drill 不动）

覆盖矩阵（与 W-NEXT-CHECKDEMO-002 GWT 对齐）：

  GWT                 守卫      当前 target  真实（task 起步）   本单测断言
  ─────────────────    ─────    ──────────   ──────────────     ──────────
  CHECKDEMO2-G1      ⑲ VECLOCK ≥ 300000     600000 (已超)        >= 300000
  CHECKDEMO2-G1(顺手) ⑬ tristate ≥  60000     60000               >= 60000
  CHECKDEMO2-G1(顺手) ⑰ cross-perm ≥ 60000    30000→60000 (改)    >= 60000
  CHECKDEMO2-G1(顺手) ⑱ febe_health ≥ 60000   60000               >= 60000

动态层 G2：实跑 ⑲ 段 → 期望 ≤ 5min（CI 反复跑：300000ms 上限）
动态层 G3：≥4 例单测全绿 + 0 回归（与其他套件无冲突）

环境注意：
  - 静态层零外部依赖，可在任何环境跑
  - 动态层需 Milvus + 8000 + BGE-M3 mmap 环境；不可达时 pytest.skip
  - Windows 内存压力下 BGE-M3 mmap 偶发 os error 1455 → 探针会提早退出 12/12
    FAIL；本单测对 ⑲ 段 PASS 不强求（受环境约束），仅断言「不超 5min」
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]  # .../EduAgent实施手册
CHECK_DEMO = REPO / "edu-agent" / "scripts" / "check-demo.mjs"


# ─────────────────────────────────────────────────────────────────────────
# 静态层：timeout 下限（4 例，与 G1 对齐）
# ─────────────────────────────────────────────────────────────────────────

_TIMEOUT_PATTERNS = [
    # (test_id, regex on check-demo.mjs,  min_ms, desc)
    (
        "test_19_veclock_timeout_at_least_5min",
        r"runPy\s*\(\s*EDU_PY\s*,\s*\[VECLOCK_VERIFY\]\s*,\s*(\d+)\s*\)",
        300_000,
        "⑲ VECLOCK verify（防 30s timeout 误杀 BGE-M3 重 load）",
    ),
    (
        "test_13_tristate_timeout_at_least_60s",
        r"runPy\s*\(\s*EDU_PY\s*,\s*\[TRISTATE_PROBE\]\s*,\s*(\d+)\s*\)",
        60_000,
        "⑬ MCP 三态（防 capability 探针慢于 30s）",
    ),
    (
        "test_17_cross_perm_timeout_at_least_60s",
        r"runPy\s*\(\s*EDU_PY\s*,\s*\[CROSSPERM_PROBE\]\s*,\s*(\d+)\s*\)",
        60_000,
        "⑰ MCP 跨权限（防 17 行 audit + AST 链慢于 30s）",
    ),
    (
        "test_18_febe_health_timeout_at_least_60s",
        r"runPy\s*\(\s*py\s*,\s*\[probe\]\s*,\s*(\d+)\s*\)",
        60_000,
        "⑱ febe root path（防 febe_health_gate_probe 慢于 30s）",
    ),
]


@pytest.mark.parametrize(
    "test_id,pattern,min_ms,desc",
    _TIMEOUT_PATTERNS,
    ids=[t[0] for t in _TIMEOUT_PATTERNS],
)
def test_check_demo_timeout_floor(test_id, pattern, min_ms, desc):
    """锁住 check-demo.mjs 各守卫 timeout 下限（W-NEXT-CHECKDEMO-002 G1）。"""
    assert CHECK_DEMO.exists(), f"check-demo.mjs 不存在: {CHECK_DEMO}"
    src = CHECK_DEMO.read_text(encoding="utf-8")
    m = re.search(pattern, src)
    assert m, f"未在 check-demo.mjs 匹配到 {desc} 的 timeout：pattern={pattern}"
    actual_ms = int(m.group(1))
    assert actual_ms >= min_ms, (
        f"{desc} timeout={actual_ms}ms < 下限 {min_ms}ms——"
        f"防 BGE-M3 mmap / 探针慢于 timeout 被误杀（W-NEXT-CHECKDEMO-002 G1）"
    )


# ─────────────────────────────────────────────────────────────────────────
# 动态层：⑲ 段实跑不超过 5 分钟（G2）
# 标记 slow：默认跳过，需手动 --run-slow 或 -k test_run_19 才跑
# ─────────────────────────────────────────────────────────────────────────

VECLOCK_PROBE_REL = "../scripts/eval/veclock_verify.py"


def _milvus_reachable() -> bool:
    """Milvus 192.168.85.101:19530 TCP 可达性（与 check-demo.mjs ① Milvus 同语义）。"""
    import socket

    s = socket.socket()
    s.settimeout(2.0)
    try:
        s.connect(("192.168.85.101", 19530))
        return True
    except Exception:
        return False
    finally:
        s.close()


def _backend_reachable() -> bool:
    """8000 /health 可达性（保留供后续用）。"""
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


# 实际跑过的⑲ 探针 wall-clock（W-NEXT-CHECKDEMO-002 G2 实证 2026-09-17）：
#   veclock_verify.py 直接跑 = 1m57.146s real（12/12 PASS）
#   check-demo.mjs ⑲ 段经 runPy 路径 = 135745ms（2m15s，12/12 PASS）
#   全 check-demo（含 19 段顺序跑）= 2m53.471s real（含环境性红项）
# 实测全在 5min 内 G2 PASS。本单测为自动回归保护。


@pytest.mark.slow
def test_run_19_veclock_under_5min():
    """实跑 check-demo ⑲ 段所对应的 veclock_verify.py 探针，断言 ≤ 5min（G2 GWT）。

    设计选择：
      - check-demo.mjs 顺序跑全 19 段（含依赖 8000/3000/Redis/Mongo/Milvus 等
        环境），环境不全时即使⑲ 段已 PASS 也会因其他段超时把总时长推至 5min+。
      - 本单测**只测⑲ 段**——直接 spawn veclock_verify.py，模拟 check-demo.mjs
        ⑲ runPy(EDU_PY, [VECLOCK_VERIFY], 600000) 的代码路径。
      - 不强求 12/12 PASS（受 BGE-M3 mmap Windows 偶发 1455 影响），仅断言
        wall-clock ≤ 5min（G2 GWT）。
      - 依赖：Milvus + venv python + BGE-M3 mmap 环境；不达则 skip。
    """
    veclock_probe = REPO / "edu-agent" / "scripts" / "eval" / "veclock_verify.py"
    edu_py = REPO / "edu-agent" / ".venv" / "Scripts" / "python.exe"
    if not veclock_probe.exists():
        pytest.skip(f"veclock_verify.py 不存在: {veclock_probe}")
    if not edu_py.exists():
        pytest.skip(f"venv python 不存在: {edu_py}")
    if not _milvus_reachable():
        pytest.skip("Milvus 192.168.85.101:19530 不可达，⑲ 探针无法跑（环境受限，非代码问题）")

    timeout_seconds = 5 * 60 + 30  # 5:30 容差
    t0 = time.time()
    proc = subprocess.run(
        [str(edu_py), str(veclock_probe)],
        cwd=str(REPO / "edu-agent"),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    elapsed = time.time() - t0
    out = proc.stdout + "\n" + proc.stderr
    last_summary_line = next(
        (l for l in reversed(out.splitlines()) if "[veclock] 汇总" in l), "(no summary)"
    )
    print(f"\n[⑲ veclock_verify.py wall-clock] {elapsed:.1f}s  line={last_summary_line.strip()}")
    assert elapsed <= 5 * 60, (
        f"⑲ veclock_verify 实测 {elapsed:.1f}s > 5min（G2 FAIL）\n"
        f"  末行: {last_summary_line.strip()}\n"
        f"  tail: {out[-400:]}"
    )


# ─────────────────────────────────────────────────────────────────────────
# 集成层：单测集合自身一致性（≥4 例 + 跑得起）
# ─────────────────────────────────────────────────────────────────────────

def test_static_test_count():
    """锁住本单测套件静态例数 ≥4（G3 GWT）。"""
    # 4 例 _TIMEOUT_PATTERNS + 1 例 slow + 1 例 count = 6
    # slow 单独 marker，CI 默认不跑；count 总是跑
    expected_static = 4  # 仅_TIMEOUT_PATTERNS
    assert len(_TIMEOUT_PATTERNS) == expected_static, (
        f"静态 timeout 例数 {len(_TIMEOUT_PATTERNS)} ≠ 预期 {expected_static}"
        f"——_TIMEOUT_PATTERNS 与 G1 GWT 矩阵须同步"
    )


# ─────────────────────────────────────────────────────────────────────────
# 静态层：runPy 签名（W-NEXT-CHECKDEMO-002 关键修复）
# ─────────────────────────────────────────────────────────────────────────
#
# 根因：原 runPy(python, args) 只有 2 个参数，所有调用点第三参数 timeoutMs 被
# 静默丢弃,所有 runPy 实际都是 60000ms。⑲ veclock_verify 实测 1m57s 必然撞
# 60s 红断(BGE-M3 mmap 重 load + 5 串行 inference batch)。修复后 runPy 签名
# 必须带 timeoutMs 参数。本套单测锁住这条修复，防回归。

def test_runpy_signature_accepts_timeoutms():
    """runPy 签名必须含 timeoutMs 参数（防回退到默认 60000）。"""
    src = CHECK_DEMO.read_text(encoding="utf-8")
    # 找到 function runPy(...) 的函数头（非注释行：必须不在 // 之后）
    m = re.search(r"^function\s+runPy\s*\(([^)]*)\)", src, re.MULTILINE)
    assert m, "未找到 function runPy(...) 的真实定义"
    params = m.group(1)
    assert "timeoutMs" in params, (
        f"runPy 签名缺 timeoutMs 参数: ({params})\n"
        f"——W-NEXT-CHECKDEMO-002 关键修复,丢失则⑲ 600000/⑯ 300000/⑭ 90000 全被吞"
    )


def test_runpy_default_timeout_at_least_60s():
    """runPy 默认 timeoutMs 兜底必须 ≥ 60s（防有人改回 30000）。"""
    src = CHECK_DEMO.read_text(encoding="utf-8")
    m = re.search(r"^function\s+runPy\s*\(([^)]*)\)", src, re.MULTILINE)
    assert m, "未找到 function runPy(...) 的真实定义"
    params = m.group(1)
    # 期望形如: function runPy(python, args, timeoutMs = 60000)
    dm = re.search(r"timeoutMs\s*=\s*(\d+)", params)
    assert dm, f"runPy 缺 timeoutMs 兜底: ({params})"
    default_ms = int(dm.group(1))
    assert default_ms >= 60_000, (
        f"runPy 默认 timeout={default_ms}ms < 60000ms——"
        f"防 BGE-M3 类慢探针撞默认 timeout 误杀"
    )


def test_runpy_error_message_includes_timeout():
    """runPy 拒绝时错误消息必须含 timeoutMs 数值（便于排查）。"""
    src = CHECK_DEMO.read_text(encoding="utf-8")
    # 找到 runPy 函数体内的 reject(new Error(...)) 行
    m = re.search(r"reject\s*\(\s*new\s+Error\s*\(\s*[`\"']([^`\"']*timeoutMs[^`\"']*)[`\"']\s*", src)
    # 上面的精确正则可能不命中（模板字符串拼接），退而求其次：找 timeoutMs 是否出现在 Error 构造附近
    if not m:
        # 宽松匹配：reject(new Error(`...timeoutMs...`))
        idx = src.find("timeoutMs")
        assert idx > 0, "runPy 体内未引用 timeoutMs（防回退）"
        # 上下文 200 字符内必须含 reject + new Error
        ctx = src[max(0, idx - 200): idx + 200]
        assert "reject" in ctx and "Error" in ctx, (
            f"timeoutMs 上下文非 reject/Error:\n{ctx}"
        )


# ─────────────────────────────────────────────────────────────────────────
# 集成层：单测集合自身一致性（≥4 例 + 跑得起）
# ─────────────────────────────────────────────────────────────────────────

def test_static_test_count():
    """锁住本单测套件静态例数（参数化 + 固定 = ≥ 8）。"""
    # 4 例 _TIMEOUT_PATTERNS + 3 例 runPy 签名 + 1 例 count = 8
    expected_static = 4 + 3  # 7 静态 + 1 count
    assert len(_TIMEOUT_PATTERNS) + 3 == expected_static, (
        f"静态 timeout + runPy 例数与预期不符："
        f"timeout={len(_TIMEOUT_PATTERNS)} runPy=3 total={expected_static}"
    )


def test_check_demo_file_syntax():
    """check-demo.mjs 必须能 node --check 通过（0 回归基线）。"""
    if not CHECK_DEMO.exists():
        pytest.skip("check-demo.mjs 不存在")
    proc = subprocess.run(
        ["node", "--check", str(CHECK_DEMO)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, (
        f"node --check 退出码 {proc.returncode}: {proc.stderr[:300]}"
    )