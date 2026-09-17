# -*- coding: utf-8 -*-
"""W-NEXT-SSRF-001 SSRF 风险位探针（只读静态扫描 + 极少量主动探活）。

目的：Mimosa 安全 hook 强约束 ① "host 写死 127.0.0.1" ② DB 参数绑定 ③ 密钥仅从环境变量读。
本探针验证代码层是否真在每次 URL/host 操作前都校验 host=127.0.0.1（及项目内网白名单），
作为自动化探针以供回归门（SSRF-G1）。

策略：
1. AST-级扫描（只读）：
   - 扫 urllib.request.urlopen / requests.{get,post,put,delete,head,request}
   - 扫 httpx.{get,post,put,delete,head,request} / httpx.Client / httpx.AsyncClient
   - 扫 aiohttp.{get,post,put,delete,head,request} / aiohttp.ClientSession
   - 标记「URL 构造 + host 校验」组合：构造点前后 5 行内有无 host 白名单/127.0.0.1 检查
   - 输出 file:line + level(high/medium/low) + 函数名/上下文

2. 入口路由扫描：定位接受 URL/body 字段含 URL 的 HTTP 路由（SSRF 风险入口）

3. 主动探活（受控）：
   - 仅对 127.0.0.1 + 192.168.85.101 做 TCP connect 探测（端口 8000/Milvus-19530/Mongo-27017/
     MinIO-9000/Neo4j-7687），确认「项目依赖的内部网络主机是否真可达」。
   - 不发送任何外网请求（绝对不外呼）。

运行（在 edu-agent/ 下）：
    .venv/Scripts/python.exe scripts/eval/ssrf_scan.py
或：
    python scripts/eval/ssrf_scan.py --active-probe

输出：
    deploy/backups/ssrf_scan_<UTC>.json 包含 findings + active_probe_results

设计依据：
- W-NEXT-SSRF-001 任务定义（编排者 full-progress-audit-2026-09-16.md §三 P0 序号 2 同型风险）
- knowledge_uploads 可能接 URL（p8_import_url 接受 http(s) URL 入参）
- Milvus/Mongo/MinIO/Neo4j connection URL 当前是否经 host 校验？
- Mimosa 强约束：所有外部连接 host 必须白名单（127.0.0.1 / 项目内网）
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ============================================================
# 路径与常量
# ============================================================
_REPO = Path(__file__).resolve().parents[2]            # edu-agent/
_BACKUP_ROOT = _REPO.parent / "deploy" / "backups"
_APP_DIR = _REPO / "app"

# 项目依赖的主机白名单（config.py 默认值）
TRUSTED_HOSTS = {"127.0.0.1", "localhost", "::1"}
# 项目依赖的内网段（config.py 实证：MILVUS_URI/MONGO_URI 默认 192.168.85.101）
INTERNAL_NET_HOSTS = {"192.168.85.101", "10.0.0.1"}
# 项目依赖端口（用于主动探活）
PROBE_PORTS = {
    "127.0.0.1": [8000, 8601, 6379, 9000, 7687, 8080],  # 本机常见服务
    "192.168.85.101": [19530, 27017],  # Milvus / Mongo
}

# AST 扫描的 HTTP/URL API
# Direct module API (requests.get / httpx.post / aiohttp.get / urllib.request.urlopen)
_HTTP_API_NAMES = {
    "urllib.request.urlopen", "urlopen",
    "requests.get", "requests.post", "requests.put", "requests.delete",
    "requests.head", "requests.patch", "requests.request",
    "httpx.get", "httpx.post", "httpx.put", "httpx.delete",
    "httpx.head", "httpx.patch", "httpx.request",
    "aiohttp.get", "aiohttp.post", "aiohttp.put", "aiohttp.delete",
    "aiohttp.head", "aiohttp.patch", "aiohttp.request",
}
# Client 实例（httpx.Client / AsyncClient / aiohttp.ClientSession）—— alias 形式
# _httpx.AsyncClient / _aiohttp.ClientSession 等价（executor.py 实证）
_HTTP_CLIENT_NAMES = {
    "httpx.Client", "httpx.AsyncClient",
    "aiohttp.ClientSession",
}
# Client 实例上的方法（client.post / session.get），AST 不直接命中，需额外识别
_HTTP_CLIENT_METHOD_CALLS = {"get", "post", "put", "delete", "head", "patch", "request", "options"}

# 判定 host 校验的关键词（构造点前后 5 行内出现即视为有 host 校验）
_HOST_VALIDATION_TOKENS = {
    "127.0.0.1", "TRUSTED_HOSTS", "INTERNAL_NET_HOSTS",
    "_is_trusted_host", "_validate_host", "_check_host",
    "host_whitelist", "allowed_hosts",
}


# ============================================================
# AST 扫描
# ============================================================
def _is_http_call(node: ast.Call, names: set[str]) -> tuple[bool, str]:
    """判断 ast.Call 是否为已知 HTTP API 调用，返回 (命中?, 名字)。"""
    func = node.func
    if isinstance(func, ast.Attribute):
        # requests.get / httpx.post / aiohttp.ClientSession
        if isinstance(func.value, ast.Name):
            full = f"{func.value.id}.{func.attr}"
        elif isinstance(func.value, ast.Attribute):
            # urllib.request.urlopen / _httpx.AsyncClient
            if isinstance(func.value.value, ast.Name):
                full = f"{func.value.value.id}.{func.value.attr}.{func.attr}"
            else:
                return False, ""
        else:
            return False, ""
        return (full in names, full)
    if isinstance(func, ast.Name):
        # 直接 urlopen()
        return (func.id in names, func.id)
    return False, ""


def _is_client_method_call(node: ast.Call) -> tuple[bool, str]:
    """识别 client.post(...) / session.get(...) / c.request(...) 形式的方法调用。
    仅当 URL/路径在 kwarg 中含 'url' 且参数为字面 URL（http(s)://）才承认。
    否则大量 .post(json=...) 噪声会淹没问题点。"""
    func = node.func
    if not isinstance(func, ast.Attribute):
        return False, ""
    if func.attr not in _HTTP_CLIENT_METHOD_CALLS:
        return False, ""
    if not isinstance(func.value, ast.Name):
        return False, ""
    # 必须有 url / base_url 形参
    for kw in node.keywords:
        if kw.arg in ("url", "base_url") and isinstance(kw.value, ast.Constant):
            v = str(kw.value.value).lower()
            if v.startswith(("http://", "https://", "ftp://", "ws://", "wss://")):
                return True, f"<client>.{func.attr}"
    return False, ""


def _range_text(src_lines: list[str], node: ast.AST, *, before: int = 8, after: int = 3) -> str:
    """抓取节点附近代码文本，用于本地上下文中是否含 host 校验。"""
    ln = getattr(node, "lineno", 1)
    a = max(1, ln - before)
    b = min(len(src_lines), ln + after)
    return "\n".join(src_lines[a - 1:b])


def _has_host_validation(src_lines: list[str], call_node: ast.Call) -> bool:
    """判断调用点附近 8 行前后 + 调用行本身是否存在 host 校验关键词。"""
    chunk = _range_text(src_lines, call_node, before=8, after=3)
    return any(tok in chunk for tok in _HOST_VALIDATION_TOKENS)


def _looks_like_host_literal(src_lines: list[str], call_node: ast.Call) -> bool:
    """判断调用本身的 URL 是否为字面常量（含 host）。"""
    if not call_node.args:
        return False
    a0 = call_node.args[0]
    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
        return a0.value.lower().startswith(("http://", "https://", "ftp://", "ws://", "wss://"))
    # URL 拼接：BaseURL + ... 形式
    chunk = _range_text(src_lines, call_node, before=2, after=2)
    return any(t in chunk for t in ("base_url", "BASE_URL", "_URI", "settings.MILVUS_URI", "settings.MONGO_URI"))


def _classify_risk(level_hint: str, has_validation: bool, is_runtime_dynamic: bool) -> str:
    """综合评估 SSRF 风险等级。"""
    if level_hint == "endpoint" and not has_validation:
        return "high"        # 明显是用户可控 URL，无 host 校验
    if is_runtime_dynamic and not has_validation:
        return "medium"      # 字符串拼接但未校验
    if not has_validation:
        return "low"         # 字面常量但未自我声明 127.0.0.1
    return "low"


def scan_python_file(path: Path) -> list[dict]:
    """扫描单个 .py 文件，提取所有 HTTP/URL 调用点的风险信息。"""
    findings: list[dict] = []
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings
    src_lines = src.splitlines()
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return findings

    # 提前扫：是否有"已知 HTTP 客户端"构造（alias 形式或 alias 局部变量）
    # 例如 _httpx.AsyncClient(...)、aiohttp.ClientSession()
    has_http_client_construction = False
    alias_names: set[str] = set()        # 已识别的 client 变量名
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            hit, name = _is_http_call(node, _HTTP_CLIENT_NAMES)
            if hit:
                has_http_client_construction = True
                # 抓取绑定到的变量名（with ctx mgr / AsyncClient()）
                # 简单识别：`alias = httpx.AsyncClient(...)` / `async with _httpx.AsyncClient(...) as alias:`
                parent = getattr(node, "parent", None)  # ast 没 parent；改用源码前后文
    # 找 alias 变量名（含 _httpx / _aiohttp 的 with 形式）
    for i, line in enumerate(src_lines, 1):
        m = re.search(
            r"async\s+with\s+(?P<cli>[A-Za-z_][\w\.]*)\.(?:AsyncClient|ClientSession|Client)\([^)]*\)(?:\s+as\s+(?P<alias>\w+))?",
            line,
        )
        if m:
            alias_names.add(m.group("alias") or "")

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            hit, name = _is_http_call(node, _HTTP_API_NAMES | _HTTP_CLIENT_NAMES)
            is_client_method, cm_name = _is_client_method_call(node)
            if not hit and not is_client_method:
                continue
            api_name = name if hit else cm_name
            is_client = (name in _HTTP_CLIENT_NAMES) if hit else True
            # 区分 method-style 与 Client-style
            has_dynamic = _looks_like_host_literal(src_lines, node)
            has_validation = _has_host_validation(src_lines, node)
            # URL 字面 / 拼接方式识别
            arg0 = node.args[0] if node.args else None
            arg_url_kind = "none"
            if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                v = arg0.value.lower()
                if v.startswith("http://127.0.0.1") or v.startswith("http://localhost"):
                    arg_url_kind = "loopback_literal"
                elif v.startswith(("https://", "http://", "ftp://", "ws://", "wss://")):
                    arg_url_kind = "external_literal"
            elif arg0 is not None and not isinstance(arg0, ast.Name):
                arg_url_kind = "dynamic"
            elif is_client_method and node.args:
                # client.post("http://...", ...) 形式：URL 在 kwargs 或 base_url
                # 看 kwargs base_url / url
                kw_url = None
                for kw in node.keywords:
                    if kw.arg in ("url", "base_url") and isinstance(kw.value, ast.Constant):
                        kw_url = kw.value.value
                        break
                if kw_url:
                    v = kw_url.lower()
                    if v.startswith("http://127.0.0.1") or v.startswith("http://localhost"):
                        arg_url_kind = "loopback_literal"
                    elif v.startswith(("https://", "http://")):
                        arg_url_kind = "external_literal"
                else:
                    # 抓 client 构造点的 base_url 字面 / 或 base_url=settings.XXX
                    if has_dynamic:
                        arg_url_kind = "dynamic"
                    else:
                        arg_url_kind = "dynamic"        # 未字面 URL，则归动态（保守）
            # 跳过明显"安全 sink"：trust_env=False + proxy=None
            sink_safe = (
                "trust_env=False" in (_range_text(src_lines, node, before=4, after=0) or "")
                and "proxy=None" in (_range_text(src_lines, node, before=4, after=0) or "")
            )
            # 客户端模式若 alias 在 50 行内出现了 with httpx.AsyncClient() 等，且
            # 已有 has_http_client_construction 标志 → 不重复 high 标记（同一字节流仅 1 finding）
            level = _classify_risk(
                level_hint="endpoint" if arg_url_kind in ("external_literal", "dynamic") else "literal",
                has_validation=has_validation,
                is_runtime_dynamic=(arg_url_kind == "dynamic"),
            )
            findings.append({
                "file": str(path.relative_to(_REPO)),
                "line": int(getattr(node, "lineno", 0)),
                "api": api_name,
                "client_style": bool(is_client),
                "url_kind": arg_url_kind,
                "has_host_validation": bool(has_validation),
                "trust_env_false": bool(sink_safe),
                "risk": level,
            })
    return findings


def _settings_url_fields() -> list[dict]:
    """扫 config.py 里所有 URI / URL / ENDPOINT 字面配置（连接入口面）。"""
    out: list[dict] = []
    cfg = _REPO / "app" / "config.py"
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return out
    for i, line in enumerate(text.splitlines(), 1):
        if re.search(r"_(URI|URL|ENDPOINT)\s*:", line):
            m = re.search(r"=\s*[\"']([^\"']+)[\"']", line)
            url = m.group(1) if m else ""
            host = ""
            if url and "://" in url:
                host = url.split("://", 1)[1].split("/", 1)[0].split("@", 1)[-1]
                if ":" in host:
                    host = host.split(":", 1)[0]
            out.append({
                "file": str(cfg.relative_to(_REPO)),
                "line": i,
                "url": url,
                "host": host,
            })
    return out


# ============================================================
# 入口路由扫描：寻找接受 URL/body 的 endpoint
# ============================================================
def scan_url_ingest_endpoints() -> list[dict]:
    """定位接受 URL 字段作为入参的 FastAPI 路由（SSRF 风险入口）。"""
    endpoints: list[dict] = []
    url_field_patterns = {"url", "source_url", "import_url", "fetch_url", "callback", "webhook"}

    for py in _APP_DIR.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        try:
            src = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # 1) 找 pydantic / BaseModel / TypedDict 含 url 字段
        for m in re.finditer(r"class\s+\w+\s*(?:\(|=\s*BaseModel|:)", src):
            cls_start = m.start()
            # 取类签名最多 250 字符 + 紧接 3 行（字段定义）
            cls_window = src[cls_start:cls_start + 800]
            # 找字段定义：url: str | url : str | url : str | Optional[str] ...
            field_hits = re.findall(
                r"^\s*(url|source_url|import_url|fetch_url|callback|webhook)\s*[:=]\s*[^\n]*?(str|HttpUrl)",
                cls_window,
                flags=re.MULTILINE,
            )
            if not field_hits:
                continue
            # 看类名
            cls_name_match = re.search(r"class\s+(\w+)", src[cls_start:])
            cls_name = cls_name_match.group(1) if cls_name_match else "?"
            endpoints.append({
                "file": str(py.relative_to(_REPO)),
                "model": cls_name,
                "fields": [h[0] for h in field_hits],
            })
    return endpoints


# ============================================================
# 主动探活（受控）
# ============================================================
def _probe_tcp(host: str, port: int, timeout: float = 0.6) -> bool:
    """纯 TCP connect 探测（不发任何应用层数据）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def run_active_probe(hosts: dict[str, list[int]]) -> list[dict]:
    """仅对 127.0.0.1 + 192.168.85.101 做 TCP 端口可达性探测（绝不发外网）。"""
    out: list[dict] = []
    for host, ports in hosts.items():
        if host not in TRUSTED_HOSTS and host not in INTERNAL_NET_HOSTS:
            continue        # 防御性：探活白名单与 TRUSTED 一致，绝不外呼
        for p in ports:
            t0 = time.perf_counter()
            ok = _probe_tcp(host, p)
            ms = int((time.perf_counter() - t0) * 1000)
            out.append({
                "host": host,
                "port": p,
                "reachable": bool(ok),
                "rtt_ms": ms,
            })
    return out


# ============================================================
# 输出
# ============================================================
def write_json(findings: dict[str, Any]) -> Path:
    """将 findings 写到 deploy/backups/ssrf_scan_<UTC>.json。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = _BACKUP_ROOT / f"ssrf_scan_{ts}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def print_summary(findings: dict[str, Any]) -> None:
    """stdout 简报（数字 + 分级计数），不落日志。"""
    rf = findings.get("http_call_findings", [])
    eps = findings.get("url_ingest_endpoints", [])
    settings_urls = findings.get("settings_url_fields", [])
    probe = findings.get("active_probe", [])
    by_level: dict[str, int] = {}
    for f in rf:
        by_level[f["risk"]] = by_level.get(f["risk"], 0) + 1
    print(f"[ssrf_scan] HTTP 调用扫描命中 = {len(rf)} 个")
    for lv, cnt in sorted(by_level.items()):
        print(f"   - {lv}: {cnt}")
    print(f"[ssrf_scan] URL-ingest endpoints (含 url 字段的 Pydantic 模型) = {len(eps)} 个")
    print(f"[ssrf_scan] 连接入口（config.py *_URI/*_URL/*_ENDPOINT）= {len(settings_urls)} 个")
    print(f"[ssrf_scan] 主动探活（仅 127.0.0.1 / 192.168.85.101）= {len(probe)} 项")
    for p in probe:
        print(f"   - {p['host']}:{p['port']} reachable={p['reachable']} rtt={p['rtt_ms']}ms")


# ============================================================
# 主流程
# ============================================================
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="W-NEXT-SSRF-001 SSRF 风险位探针")
    parser.add_argument("--active-probe", action="store_true", help="启用主动 TCP 探活")
    parser.add_argument("--out", type=str, default="", help="自定义输出 JSON 路径")
    args = parser.parse_args(argv)

    import re  # 局部 import 减 main 体积

    # 1) 扫 app/ 下所有 .py
    rf: list[dict] = []
    for py in sorted(_APP_DIR.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        rf.extend(scan_python_file(py))

    # 2) URL 入参模型
    eps = scan_url_ingest_endpoints()

    # 3) settings.*_URI/*_URL/*_ENDPOINT 连接入口
    settings_urls = _settings_url_fields()

    # 4) 主动探活（如启用）
    probe: list[dict] = []
    if args.active_probe:
        probe = run_active_probe(PROBE_PORTS)

    findings: dict[str, Any] = {
        "task": "W-NEXT-SSRF-001",
        "scanned_at_utc": datetime.now(timezone.utc).isoformat(),
        "trusted_hosts": sorted(TRUSTED_HOSTS | INTERNAL_NET_HOSTS),
        "scanned_root": str(_APP_DIR.relative_to(_REPO)),
        "http_call_findings": rf,
        "url_ingest_endpoints": eps,
        "settings_url_fields": settings_urls,
        "active_probe": probe,
        "summary": {
            "total_http_calls": len(rf),
            "high_risk": sum(1 for x in rf if x["risk"] == "high"),
            "medium_risk": sum(1 for x in rf if x["risk"] == "medium"),
            "low_risk": sum(1 for x in rf if x["risk"] == "low"),
            "url_ingest_endpoints": len(eps),
            "settings_url_fields": len(settings_urls),
            "active_probe_count": len(probe),
            "total_risk_positions": len(rf) + len(eps) + len(settings_urls),
        },
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(findings, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        out = write_json(findings)
    print_summary(findings)
    print(f"[ssrf_scan] 写出 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
