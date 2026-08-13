# -*- coding: utf-8 -*-
"""
be-task01 集成外壳测试（在当前 pytest 环境无 fastapi/asyncmy 时也可运行）：

通过 subprocess 调用 kb311 venv（Python 3.11，含 fastapi/asyncmy/pytest/requests/pymysql）执行：
  1) 单元测试 tests/test_chat_delete.py —— mock 数据库层的 DELETE 逻辑断言
  2) 一键打靶 scripts/restart_uvicorn_and_chat_delete_hit.py
     —— 杀 8000 旧进程（防 SO_REUSEADDR 双进程）→ 按 .env DEBUG 分支启 uvicorn
        → 跑 chat_delete_hit.py（真实 HTTP + MySQL 直查 + 报告落盘）

两者 exit 0 即通过。报告落盘：test-reports/be-task01-hit-report.md。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

AGENT_ROOT = Path(r"E:\stu\project\stu\EduAgent实施手册\edu-agent")
PROJECT_ROOT = AGENT_ROOT.parent

_CANDIDATE = [
    os.environ.get("PYTHON_EXE") or "",
    r"Z:\anaconda3\envs\kb311\python.exe",
    r"E:\stu\project\libs\kb311\Scripts\python.exe",
]


def _pick_python() -> str:
    for p in _CANDIDATE:
        if not p or not os.path.exists(p):
            continue
        try:
            r = subprocess.run(
                [p, "-c", "import fastapi, asyncmy, pytest, requests, pymysql"],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode == 0:
                return p
        except Exception:
            continue
    raise RuntimeError("找不到含 fastapi/asyncmy/pytest/requests/pymysql 的 Python（kb311）")


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    print(f"\n$ {subprocess.list2cmdline(cmd)}")
    return subprocess.run(cmd, capture_output=False, timeout=timeout)


def test_be_task01_unit_tests() -> None:
    """chat DELETE 单元测试（200/403/404/幂等/软删 yn=0/事务共享 cur）。"""
    py = _pick_python()
    r = _run([py, "-m", "pytest", "tests/test_chat_delete.py", "-v"], timeout=600)
    assert r.returncode == 0, "chat DELETE 单元测试存在失败（见上方输出）"


def test_be_task01_delete_hit() -> None:
    """一键打靶：杀 8000 → 按 .env DEBUG 分支启 uvicorn → DELETE 断言矩阵 + DB 直查。"""
    py = _pick_python()
    r = _run([py, str(AGENT_ROOT / "scripts" / "restart_uvicorn_and_chat_delete_hit.py")], timeout=900)
    assert r.returncode == 0, "be-task01 打靶存在 FAIL（见上方输出与 test-reports/be-task01-hit-report.md）"
    report = PROJECT_ROOT / "test-reports" / "be-task01-hit-report.md"
    assert report.exists(), "打靶报告未落盘"
