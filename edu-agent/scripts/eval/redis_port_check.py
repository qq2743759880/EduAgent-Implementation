# -*- coding: utf-8 -*-
"""
W-NEXT-REDIS-FIX ⑮ 健康门探针 —— Redis 部署对账（端口一致性）。

比对 .env 显式 REDIS_PORT 与 docker 容器实际暴露端口：
  - 一致 → status=PASS（exit 0）
  - 不一致 → status=WARN（exit 0，但提示需改 .env 或容器端口；不阻断以兼容「仅文档漂移」场景）
  - .env 缺 REDIS_PORT → status=FAIL_ENV_MISSING（exit 1）
  - 读不到 docker 容器（容器停/引擎未起） → status=ENV_BLOCKED（exit 2）

末行输出固定格式（check-demo ⑮ 解析用）：
  [PORT_CHECK] env_port=<int> docker_port=<int|None> status=<PASS|WARN|FAIL_ENV_MISSING|ENV_BLOCKED>
              container=<name> container_internal_port=<int>

用法：
  python scripts/eval/redis_port_check.py                  # 默认从 edu-agent/.env 读 + docker 探测
  python scripts/eval/redis_port_check.py --env /path/.env  # 自定 .env 路径

Mimosa 安全约束：
  ① host 写死本地（仅连 127.0.0.1，REDIS_URL host 非 loopback 即直接拒）
  ② 无 DB 写
  ③ 不读密钥
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------- 常量 ----------
HERE = Path(__file__).resolve().parent
DEFAULT_ENV = HERE.parent.parent / ".env"          # edu-agent/.env
DEFAULT_DOCKER_FILTER = "name=redis"
LOCAL_HOST = "127.0.0.1"                            # Mimosa ① host 锁本地

# PASS 判据：.env REDIS_PORT == docker 宿主端口（**严格匹配**）
#   后端走 `redis://127.0.0.1:<REDIS_PORT>/0`（宿主端口），容器内 6379 是 redis 进程监听端口，
#   不可与 .env 端口等价——容器内端口仅作 informational 字段打印，不参与 PASS 判定。
# 旧版本曾用 `host_or_container` 宽口径，会把「.env 6379 vs 宿主 6377 / 容器内 6379」误判 PASS
# （容器内 6379 命中）——这是错的，后端真连的是宿主端口，6379 已 dead。


# ---------- .env 解析 ----------
def parse_env_port(env_path: Path) -> tuple[int | None, str | None]:
    """从 .env 文件里抽 REDIS_PORT 与 REDIS_URL 的 port（REDIS_PORT 优先，回退 REDIS_URL）。"""
    if not env_path.exists():
        return None, f".env 不存在: {env_path}"
    url_host = None
    url_port = None
    explicit_port = None
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if key == "REDIS_PORT" and val:
            try:
                explicit_port = int(val)
            except ValueError:
                return None, f"REDIS_PORT 非整数: {val!r}"
        elif key == "REDIS_URL" and val:
            um = re.match(r"^redis://([^:/]+)(?::(\d+))?(?:/(\d+))?\s*$", val)
            if um:
                url_host = um.group(1)
                if um.group(2):
                    try:
                        url_port = int(um.group(2))
                    except ValueError:
                        return None, f"REDIS_URL port 非整数: {um.group(2)!r}"
    # Mimosa ①：REDIS_URL host 非 loopback 直接拒
    if url_host and url_host not in (LOCAL_HOST, "localhost", "::1"):
        return None, f"REDIS_URL host={url_host!r} 非 loopback（Mimosa 要求本地）"
    if explicit_port is not None:
        return explicit_port, None
    if url_port is not None:
        return url_port, None
    return None, ".env 既无 REDIS_PORT 也无 REDIS_URL port"


# ---------- docker 探测 ----------
def probe_docker_port(filter_name: str = DEFAULT_DOCKER_FILTER) -> tuple[int | None, str | None, int | None, str | None]:
    """调 docker ps 拿首个匹配容器的「宿主端口」「容器名」「容器内端口」。
    返回 (host_port, container_name, container_internal_port, err)。
    """
    try:
        proc = subprocess.run(
            ["docker", "ps", "--filter", filter_name, "--format",
             "{{.Names}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except FileNotFoundError:
        return None, None, None, "docker 命令不存在（PATH 缺 docker.exe）"
    except subprocess.TimeoutExpired:
        return None, None, None, "docker ps 超时(>8s)"
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip().splitlines()[0][:160] if (proc.stderr or proc.stdout).strip() else f"docker exit {proc.returncode}"
        if re.search(r"pipe|cannot find the file specified|engine not running", msg, re.IGNORECASE):
            return None, None, None, "docker 引擎未运行（Docker Desktop 未启动）"
        return None, None, None, msg or f"docker exit {proc.returncode}"
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if not lines:
        return None, None, None, "无匹配 redis 容器（docker ps --filter name=redis 0 行）"
    # 多容器场景：取健康且端口映射可解析的第一行
    for ln in lines:
        name, ports = ln.split("\t", 1) if "\t" in ln else (ln, "")
        # 端口解析："0.0.0.0:6377->6379/tcp" → 宿主 6377，容器内 6379
        hp = None
        cp = None
        # 抓所有 0.0.0.0:XXXX->YYYY/... 段
        for m in re.finditer(r"(?:[\d.]+|::):(\d+)->(\d+)/tcp", ports):
            hp = int(m.group(1))
            cp = int(m.group(2))
            break
        if hp is not None:
            return hp, name.strip(), cp, None
    return None, None, None, f"无法解析端口映射: {lines[0][:160]}"


# ---------- 主流程 ----------
def main() -> int:
    ap = argparse.ArgumentParser(description="Redis 部署对账（.env REDIS_PORT vs docker 宿主端口）")
    ap.add_argument("--env", default=str(DEFAULT_ENV), help=f".env 路径（默认 {DEFAULT_ENV}）")
    ap.add_argument("--filter", default=DEFAULT_DOCKER_FILTER, help=f"docker ps filter（默认 {DEFAULT_DOCKER_FILTER}）")
    ap.add_argument("--strict", action="store_true", help="WARN 也视为失败（exit 1），默认仅 FAIL_ENV_MISSING 退码 1")
    args = ap.parse_args()

    env_path = Path(args.env).resolve()
    env_port, env_err = parse_env_port(env_path)
    docker_port, container_name, container_internal_port, docker_err = probe_docker_port(args.filter)

    # 拼装结果
    if env_err is not None:
        status = "FAIL_ENV_MISSING"
        payload = {
            "env_port": env_port,
            "docker_port": docker_port,
            "status": status,
            "container": container_name,
            "container_internal_port": container_internal_port,
            "env_error": env_err,
            "docker_error": docker_err,
        }
        print(f"[PORT_CHECK] {json.dumps(payload, ensure_ascii=False)}")
        return 1

    if docker_err is not None:
        status = "ENV_BLOCKED"
        payload = {
            "env_port": env_port,
            "docker_port": None,
            "status": status,
            "container": None,
            "container_internal_port": None,
            "env_error": None,
            "docker_error": docker_err,
        }
        print(f"[PORT_CHECK] {json.dumps(payload, ensure_ascii=False)}")
        return 2

    # 对账：.env REDIS_PORT == docker 宿主端口 → PASS（严格匹配；容器内端口仅 informational）
    if env_port == docker_port:
        status = "PASS"
    else:
        status = "WARN"

    payload = {
        "env_port": env_port,
        "docker_port": docker_port,
        "status": status,
        "container": container_name,
        "container_internal_port": container_internal_port,
        "env_error": None,
        "docker_error": None,
    }
    print(f"[PORT_CHECK] {json.dumps(payload, ensure_ascii=False)}")

    # 人类可读附加行（不影响 [PORT_CHECK] 解析）
    if status == "PASS":
        print(f"OK: .env REDIS_PORT={env_port} 与 docker 端口一致（容器 {container_name}, 宿主 {docker_port}, 容器内 {container_internal_port}）")
    elif status == "WARN":
        print(f"WARN: .env REDIS_PORT={env_port} ≠ docker 宿主端口={docker_port}（容器内 {container_internal_port}）—— 请改 .env 或修容器端口映射")

    if args.strict and status == "WARN":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
