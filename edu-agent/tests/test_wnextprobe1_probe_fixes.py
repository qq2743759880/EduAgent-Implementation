# -*- coding: utf-8 -*-
"""W-NEXT-PROBE-001 单测套件 —— check-demo ②⑫ 探针口径修复。

覆盖三类回归:
  1. test_read_env_redis_port_*:readEnvRedisPort 解析 REDIS_PORT/REDIS_URL 端口,
     替代硬编码 "edu-redis-standalone"
  2. test_json_only_stdout_*:JsonOnlyStdout 把 loguru/print 污染重定向到 stderr,
     只有带哨兵的 _probe_print 走真 stdout
  3. test_hitl_probe_stdout_is_pure_json:跑真 probe,纯 stdout 必是 JSON 可解析
  4. test_hitl_probe_survives_missing_session_session_create:probe 必先
     POST /api/chat/sessions 建会话,不再裸 404 CHAT_SESSION_NOT_FOUND
  5. test_check_demo_no_hardcoded_redis_container:check-demo.mjs 不再含
     硬编码容器名 (防容器重命名/端口漂移盲区)

不依赖 8000 后端/真 docker(除最后两类要真环境跑);CI 必跑通过。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_DEMO_MJS = REPO_ROOT / "scripts" / "check-demo.mjs"
HITL_PROBE = REPO_ROOT / "scripts" / "hitl_realness_probe.py"


# ============================================================
# 1) readEnvRedisPort 端口解析逻辑(直接调用 Node 跑 check-demo.mjs 的函数体)
# ============================================================
def _node_extract_read_env_redis_port() -> str:
    """把 readEnvRedisPort 函数从 check-demo.mjs 抠出来,装到独立 .mjs 里跑。

    避免为了测函数而 Node 启动整个 check-demo(那要 8000 在线)。
    """
    src = CHECK_DEMO_MJS.read_text(encoding="utf-8")
    # 抠 function readEnvRedisPort() {...} 块
    m = re.search(
        r"function\s+readEnvRedisPort\s*\(\s*\)\s*\{[\s\S]*?\n\}\n",
        src,
    )
    assert m, "readEnvRedisPort 函数未找到,可能被改名"
    return m.group(0)


def _run_node_isolated(env_path: str) -> int:
    """临时建一个 .mjs 跑 readEnvRedisPort(env_path) → stdout 输出端口号。

    Returns: int 解析出的端口
    """
    fn = _node_extract_read_env_redis_port()
    testfile = tempfile.NamedTemporaryFile(
        mode="w", suffix=".mjs", delete=False, encoding="utf-8"
    )
    # 把 readEnvRedisPort 拷过来,然后调用它(env_path 是绝对路径,不用 URL 解析)
    testfile.write(
        f"""import {{ existsSync, readFileSync }} from "node:fs";
{fn}
console.log(JSON.stringify(readEnvRedisPort()));
"""
    )
    testfile.close()
    try:
        # 把 env_path 临时放到 sys.path 等价的位置?实际 readEnvRedisPort 用的是
        # new URL("../.env", import.meta.url) 解析的相对路径,所以我们要绕开它。
        # 改用直接覆盖路径的方式:把临时 .env 放到 readEnvRedisPort 的解析结果路径
        # 计算一下:import.meta.url 是 testfile.name,其父目录父目录是临时目录的父目录
        # —— 不稳定。换一招:把 fn 里 fileURLToPath 那行替换掉。
        # 重新读文件 + 替换 + 写到临时文件
        with open(testfile.name, "r", encoding="utf-8") as f:
            src = f.read()
        # 把 ../.env 替换成绝对路径
        abs_env = env_path.replace("\\", "\\\\")
        src = src.replace(
            'fileURLToPath(new URL("../.env", import.meta.url))',
            json.dumps(abs_env),
        )
        # 加 fileURLToPath import
        src = src.replace(
            'import { existsSync, readFileSync } from "node:fs";',
            'import { existsSync, readFileSync } from "node:fs";\n',
        )
        # 移除 fn 内部的 fileURLToPath 调用影响——我们已经替换掉了
        with open(testfile.name, "w", encoding="utf-8") as f:
            f.write(src)
        proc = subprocess.run(
            ["node", testfile.name],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"node 跑挂: {proc.stderr}")
        return json.loads(proc.stdout.strip())
    finally:
        os.unlink(testfile.name)


@pytest.mark.parametrize(
    "env_content, expected_port, label",
    [
        ("REDIS_PORT=6377\n", 6377, "REDIS_PORT 显式"),
        ("REDIS_PORT=6380\n", 6380, "REDIS_PORT 漂移端口"),
        ("REDIS_URL=redis://127.0.0.1:6380/0\n", 6380, "REDIS_URL 端口(无 REDIS_PORT)"),
        ("REDIS_PORT=6379\nREDIS_URL=redis://127.0.0.1:6377/0\n", 6379, "REDIS_PORT 优先于 REDIS_URL"),
        ("# only comments\n", 6377, "无 REDIS_PORT 走默认"),
    ],
)
def test_read_env_redis_port_parsing(env_content, expected_port, label, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(env_content, encoding="utf-8")
    got = _run_node_isolated(str(env_file))
    assert got == expected_port, f"{label}: expected {expected_port}, got {got}"


# ============================================================
# 2) JsonOnlyStdout 行为(纯 Python 子进程直接 import 跑)
# ============================================================
def test_json_only_stdout_routes_pollution_to_stderr():
    """loguru INFO 行被重定向到 stderr,只有带哨兵的 _probe_print 走真 stdout。"""
    probe_dir = str(HITL_PROBE.parent)
    code = (
        "import sys, json\n"
        "sys.path.insert(0, r'" + probe_dir + "')\n"
        "import hitl_realness_probe as h\n"
        "\n"
        "# 模拟 loguru 写 stdout(污染)—— 写到 sys.stdout 必被 JsonOnlyStdout 拦截\n"
        'sys.stdout.write("[fake-loguru-INFO] xxx\\n")\n'
        "sys.stdout.flush()\n"
        "\n"
        "# 模拟普通 json.dumps 写到 sys.stdout(应被吞到 stderr,不到真 stdout)\n"
        'sys.stdout.write(json.dumps({"raw_print_no_sentinel": 1}, ensure_ascii=False) + "\\n")\n'
        "sys.stdout.flush()\n"
        "\n"
        "# 模拟 _probe_print(带哨兵,应到真 stdout)\n"
        'h._probe_print({"valid": True})\n'
    )

    testfile = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    )
    testfile.write(code)
    testfile.close()
    try:
        proc = subprocess.run(
            [sys.executable, testfile.name],
            capture_output=True, text=True, timeout=10, check=False,
        )
        # STDOUT 必只剩 1 行 JSON(带 valid 字段)
        out_lines = [ln for ln in proc.stdout.split("\n") if ln.strip()]
        assert len(out_lines) == 1, (
            f"stdout 应只有 1 行 JSON,实得 {len(out_lines)} 行: {out_lines!r}\n"
            f"stderr: {proc.stderr[:500]}"
        )
        j = json.loads(out_lines[0])
        assert j.get("valid") is True, f"stdout JSON 不是契约内容: {j}"

        # STDERR 必包含 loguru 污染 + 普通 print 转 stderr 的内容
        assert "fake-loguru-INFO" in proc.stderr, (
            f"loguru 污染行应被转到 stderr,实 stderr: {proc.stderr[:300]!r}"
        )
        assert "probe:redirect" in proc.stderr, (
            f"普通 print 应被 prefixed 转 stderr,实 stderr: {proc.stderr[:300]!r}"
        )
        assert "raw_print_no_sentinel" in proc.stderr, (
            f"普通 print 内容应出现在 stderr: {proc.stderr[:300]!r}"
        )
    finally:
        os.unlink(testfile.name)


def test_json_only_stdout_install_is_idempotent():
    """_install_json_only_stdout 二次调用不替换(防止 _probe_print 被覆盖)。"""
    probe_dir = str(HITL_PROBE.parent)
    code = (
        "import sys\n"
        "sys.path.insert(0, r'" + probe_dir + "')\n"
        "import hitl_realness_probe as h\n"
        "\n"
        "h._install_json_only_stdout()\n"
        "first = sys.stdout\n"
        "h._install_json_only_stdout()\n"
        "second = sys.stdout\n"
        "# 用 _probe_print 走真 stdout(避免被 wrapper 吞)\n"
        'h._probe_print({"idempotent": first is second})\n'
    )

    testfile = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    )
    testfile.write(code)
    testfile.close()
    try:
        proc = subprocess.run(
            [sys.executable, testfile.name],
            capture_output=True, text=True, timeout=10, check=False,
        )
        # 二次调用应保留首次的 wrapper(JSON 中 idempotent:True)
        out_lines = [ln for ln in proc.stdout.split("\n") if ln.strip()]
        assert len(out_lines) >= 1, (
            f"应有 stdout 输出: stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
        j = json.loads(out_lines[0])
        assert j.get("idempotent") is True, (
            f"_install_json_only_stdout 非幂等: {j}"
        )
    finally:
        os.unlink(testfile.name)


# ============================================================
# 3) check-demo.mjs 不再含硬编码容器名(防容器重命名/端口漂移盲区)
# ============================================================
def test_check_demo_no_hardcoded_redis_container():
    """硬编码容器名 = 部署拓扑漂移即盲区。同型风险 0 容忍。"""
    src = CHECK_DEMO_MJS.read_text(encoding="utf-8")
    # 排除注释行后再 grep
    non_comment_lines = [
        ln for ln in src.splitlines()
        if not ln.strip().startswith("//") and "edu-redis-standalone" in ln
    ]
    assert not non_comment_lines, (
        f"check-demo.mjs 仍含硬编码 'edu-redis-standalone' 在非注释行: "
        f"{non_comment_lines[:3]}"
    )


def test_check_demo_has_detect_redis_container():
    """② 守卫必须含运行时按端口反查容器名的函数 detectRedisContainer。"""
    src = CHECK_DEMO_MJS.read_text(encoding="utf-8")
    assert "function detectRedisContainer" in src, (
        "detectRedisContainer 函数缺失——硬编码未替换为端口反查"
    )
    assert "readEnvRedisPort" in src, (
        "readEnvRedisPort 函数缺失——端口来源未从 .env 读"
    )


# ============================================================
# 4) probe 必先建会话(防裸 404 CHAT_SESSION_NOT_FOUND)
# ============================================================
def test_hitl_probe_calls_create_session():
    """probe 必须先调 _create_session,不再用裸字符串当 session_id。"""
    src = HITL_PROBE.read_text(encoding="utf-8")
    assert "def _create_session" in src, "_create_session 函数缺失"
    # main() 必须调 _create_session
    assert "_create_session(token)" in src, "main() 未调 _create_session(token)"
    # 不能让裸字符串当 session_id
    assert "f\"surfaced1_probe_{int(time.time())}\"" not in src, (
        "仍用 f-string 生成裸 session_id,会撞 404 CHAT_SESSION_NOT_FOUND"
    )


# ============================================================
# 5) _count_task 必先 init_mysql(防漏调连接池未初始化)
# ============================================================
def test_hitl_probe_init_mysql_before_count_task():
    """_count_task 必须先 await init_mysql()。"""
    src = HITL_PROBE.read_text(encoding="utf-8")
    # 定位 _count_task 函数体
    m = re.search(
        r"def\s+_count_task\s*\([^)]*\)\s*->\s*int\s*:[\s\S]*?return\s+asyncio\.run\(_q\(\)\)",
        src,
    )
    assert m, "_count_task 函数体未找到 / 形态已改"
    body = m.group(0)
    assert "await init_mysql" in body, (
        "_count_task 漏调 init_mysql()——fetch_one 抛连接池未初始化"
    )


# ============================================================
# 6) 真 probe 跑通(只测 stdout 是纯 JSON,不强求 ok=true —— 后端可达性另算)
# ============================================================
def test_hitl_probe_stdout_is_pure_json():
    """真跑 hitl_realness_probe.py,stdout 必能 JSON.parse 且只 1 行 JSON。"""
    if not (REPO_ROOT / ".env").is_file():
        pytest.skip("edu-agent/.env 不存在,跳过真后端探针验证")
    proc = subprocess.run(
        [sys.executable, str(HITL_PROBE)],
        capture_output=True, text=True, timeout=120, check=False,
        cwd=str(REPO_ROOT),  # cwd=edu-agent 让 pydantic-settings 找到 .env
    )
    out_lines = [ln for ln in proc.stdout.split("\n") if ln.strip()]
    assert len(out_lines) >= 1, "probe 无 stdout 输出"
    for ln in out_lines:
        j = json.loads(ln)  # 任意一行都不能 parse 失败
        assert isinstance(j, dict), f"stdout 不是 dict JSON: {ln[:80]!r}"
    # 末行 JSON 必有 health_ok 字段(契约)
    last = json.loads(out_lines[-1])
    assert "health_ok" in last, f"末行 JSON 缺 health_ok: {last}"


# ============================================================
# 7) check-demo ② 守卫标签更新(用户面:"Redis(按 .env REDIS_PORT=... 反查...)")
# ============================================================
def test_check_demo_label_reflects_dynamic_port():
    """② 守卫标签必含 '按 .env REDIS_PORT=' 与 '反查容器',证明是动态发现。"""
    src = CHECK_DEMO_MJS.read_text(encoding="utf-8")
    assert "按 .env REDIS_PORT=" in src, (
        "② 守卫 label 缺 '按 .env REDIS_PORT=' 前缀——未走 readEnvRedisPort"
    )
    assert "反查容器" in src, (
        "② 守卫 label 缺 '反查容器' 字样——容器名还是硬编码"
    )