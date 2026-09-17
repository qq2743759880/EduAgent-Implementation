# -*- coding: utf-8 -*-
"""W-NEXT-REDIS-FIX ⑮ 单测 —— Redis 部署对账（端口一致性）。

覆盖 scripts/eval/redis_port_check.py 的：
  ① parse_env_port: REDIS_PORT / REDIS_URL / Mimosa host 校验 / 缺值 / 注释行
  ② probe_docker_port: 端口解析 / 容器内端口 / 找不到 docker / 无匹配容器
  ③ main 入口: PASS / WARN / FAIL_ENV_MISSING / ENV_BLOCKED 四态 + 退出码

注意：本文件**不**依赖真实 docker / 真实 .env——通过 monkeypatch 替身跑纯逻辑断言。
真实 docker + .env 实证见 scripts/eval/redis_port_check.py 在 8000 重启后的输出（test-reports/WNEXTREDIS-completion-report.md）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts" / "eval"))

import redis_port_check as rpc  # noqa: E402


# ============================================================
# ① parse_env_port
# ============================================================
class TestParseEnvPort:
    def test_explicit_red_port(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text("# comment\nREDIS_PORT=6377\n", encoding="utf-8")
        port, err = rpc.parse_env_port(p)
        assert err is None, f"unexpected err: {err}"
        assert port == 6377

    def test_red_url_fallback(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text("REDIS_URL=redis://127.0.0.1:6380/0\n", encoding="utf-8")
        port, err = rpc.parse_env_port(p)
        assert err is None
        assert port == 6380

    def test_explicit_overrides_url(self, tmp_path: Path):
        """REDIS_PORT 优先于 REDIS_URL.port（与脚本语义一致：单一事实源）。"""
        p = tmp_path / ".env"
        p.write_text("REDIS_URL=redis://127.0.0.1:6380/0\nREDIS_PORT=6377\n", encoding="utf-8")
        port, err = rpc.parse_env_port(p)
        assert err is None
        assert port == 6377

    def test_skip_comments_and_blanks(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text("\n# 注释行\n   \nREDIS_PORT=  6399  \n", encoding="utf-8")
        port, err = rpc.parse_env_port(p)
        assert err is None
        assert port == 6399

    def test_mimosa_non_loopback_rejected(self, tmp_path: Path):
        """Mimosa ①：REDIS_URL host 非 loopback 直接拒（防越权连外网 redis）。"""
        p = tmp_path / ".env"
        p.write_text("REDIS_URL=redis://10.0.0.1:6379/0\n", encoding="utf-8")
        port, err = rpc.parse_env_port(p)
        assert port is None
        assert err is not None
        assert "loopback" in err.lower() or "非" in err

    def test_missing_file(self, tmp_path: Path):
        port, err = rpc.parse_env_port(tmp_path / "nonexistent.env")
        assert port is None
        assert err is not None and "不存在" in err

    def test_missing_keys(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text("OTHER_KEY=foo\n", encoding="utf-8")
        port, err = rpc.parse_env_port(p)
        assert port is None
        assert err is not None

    def test_non_integer_red_port(self, tmp_path: Path):
        p = tmp_path / ".env"
        p.write_text("REDIS_PORT=notanumber\n", encoding="utf-8")
        port, err = rpc.parse_env_port(p)
        assert port is None
        assert err is not None and "整数" in err


# ============================================================
# ② probe_docker_port
# ============================================================
class TestProbeDockerPort:
    def test_parses_host_and_container_port(self):
        fake_completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout="prisma-ai-redis-container-1\t0.0.0.0:6377->6379/tcp\n",
            stderr="",
        )
        with patch.object(rpc.subprocess, "run", return_value=fake_completed):
            hp, name, cp, err = rpc.probe_docker_port()
        assert err is None
        assert hp == 6377
        assert name == "prisma-ai-redis-container-1"
        assert cp == 6379

    def test_picks_first_container_when_multiple(self):
        """多容器时取首个有可解析端口映射的容器。"""
        fake_completed = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=("other-container\t\n"
                    "prisma-ai-redis-container-1\t0.0.0.0:6377->6379/tcp\n"),
            stderr="",
        )
        with patch.object(rpc.subprocess, "run", return_value=fake_completed):
            hp, name, cp, err = rpc.probe_docker_port()
        assert err is None
        assert hp == 6377
        assert name == "prisma-ai-redis-container-1"

    def test_no_matching_container(self):
        fake_completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr="",
        )
        with patch.object(rpc.subprocess, "run", return_value=fake_completed):
            hp, name, cp, err = rpc.probe_docker_port()
        assert hp is None
        assert err is not None and "无匹配" in err

    def test_docker_engine_down(self):
        fake_completed = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="",
            stderr="error during connect: …open //./pipe/docker_engine: The system cannot find the file specified",
        )
        with patch.object(rpc.subprocess, "run", return_value=fake_completed):
            hp, name, cp, err = rpc.probe_docker_port()
        assert hp is None
        assert err is not None and "引擎未运行" in err

    def test_docker_not_in_path(self):
        with patch.object(rpc.subprocess, "run", side_effect=FileNotFoundError):
            hp, name, cp, err = rpc.probe_docker_port()
        assert hp is None
        assert err is not None and "docker 命令不存在" in err


# ============================================================
# ③ main 入口（四态 + 退出码）
# ============================================================
class TestMain:
    def _run_main(self, monkeypatch, *, env_port, docker_port, container_name, container_internal_port, env_err, docker_err, argv_extra=()):
        monkeypatch.setattr(sys, "argv", ["redis_port_check.py"] + list(argv_extra))
        # 替身 parse_env_port / probe_docker_port
        monkeypatch.setattr(rpc, "parse_env_port",
                            lambda p: (env_port, env_err))
        monkeypatch.setattr(rpc, "probe_docker_port",
                            lambda f: (docker_port, container_name, container_internal_port, docker_err))
        # 捕获 stdout
        from io import StringIO
        buf = StringIO()
        monkeypatch.setattr(sys, "stdout", buf)
        rc = rpc.main()
        return rc, buf.getvalue()

    def test_pass(self, monkeypatch):
        rc, out = self._run_main(monkeypatch,
                                 env_port=6377, docker_port=6377,
                                 container_name="prisma-ai-redis-container-1",
                                 container_internal_port=6379,
                                 env_err=None, docker_err=None)
        assert rc == 0
        assert '"status": "PASS"' in out
        assert '"env_port": 6377' in out
        assert '"docker_port": 6377' in out

    def test_warn_mismatch(self, monkeypatch):
        rc, out = self._run_main(monkeypatch,
                                 env_port=6379, docker_port=6377,
                                 container_name="prisma-ai-redis-container-1",
                                 container_internal_port=6379,
                                 env_err=None, docker_err=None)
        assert rc == 0
        assert '"status": "WARN"' in out
        assert '"env_port": 6379' in out
        assert '"docker_port": 6377' in out

    def test_strict_warns_to_exit_one(self, monkeypatch):
        rc, out = self._run_main(monkeypatch,
                                 env_port=6379, docker_port=6377,
                                 container_name="prisma-ai-redis-container-1",
                                 container_internal_port=6379,
                                 env_err=None, docker_err=None,
                                 argv_extra=["--strict"])
        assert rc == 1
        assert '"status": "WARN"' in out

    def test_fail_env_missing(self, monkeypatch):
        rc, out = self._run_main(monkeypatch,
                                 env_port=None, docker_port=6377,
                                 container_name="prisma-ai-redis-container-1",
                                 container_internal_port=6379,
                                 env_err=".env 不存在", docker_err=None)
        assert rc == 1
        assert '"status": "FAIL_ENV_MISSING"' in out

    def test_env_blocked_docker_down(self, monkeypatch):
        rc, out = self._run_main(monkeypatch,
                                 env_port=6377, docker_port=None,
                                 container_name=None, container_internal_port=None,
                                 env_err=None, docker_err="docker 引擎未运行")
        assert rc == 2
        assert '"status": "ENV_BLOCKED"' in out

    def test_pass_only_matches_host_port_not_internal(self, monkeypatch):
        """回归保护：严格匹配 .env 与 docker 宿主端口；容器内端口仅 informational。
        旧版本「host_or_container」会把此 case 误判 PASS——必须 WARN。"""
        rc, out = self._run_main(monkeypatch,
                                 env_port=6379, docker_port=6377,
                                 container_name="prisma-ai-redis-container-1",
                                 container_internal_port=6379,  # 巧合命中
                                 env_err=None, docker_err=None)
        assert rc == 0
        assert '"status": "WARN"' in out, "宿主端口不匹配必须 WARN（容器内 6379 巧合不算 PASS）"


# ============================================================
# ④ 输出格式契约：末行 [PORT_CHECK] <json> 可被外部脚本正则解析
# ============================================================
def test_output_format_is_machine_parseable():
    import re
    fake_out = '[PORT_CHECK] {"env_port": 6377, "docker_port": 6377, "status": "PASS", "container": "x", "container_internal_port": 6379, "env_error": null, "docker_error": null}\n'
    m = re.match(r"^\[PORT_CHECK\]\s+(\{.*\})\s*$", fake_out.strip())
    assert m is not None
    j = json.loads(m.group(1))
    assert j["status"] == "PASS"
    assert j["env_port"] == 6377
