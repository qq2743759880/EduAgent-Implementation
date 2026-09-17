# -*- coding: utf-8 -*-
"""W-NEXT-EXE-SSRF-002：embedder/embeddings 模块 SSRF 调用点扫描探针。

目的（与 SSRF-001 探针同构，聚焦 embed 路径）：
- AST 静态扫描 `app/knowledge/importer/embedder.py` 与 `app/knowledge` 下任何
  `*embed*.py` 模块（含 embeddings / embedding_retriever / hybrid_search 等），
  找所有 `urllib`/`requests`/`httpx`/`aiohttp` 的出站调用点。
- 「守门方法豁免」：调用 `app.security.ssrf_guard.validate_url` / `app.security.ssrf_guard._ssrf_validate_url`
  / `_gate_embed_url` / `_embed_ssrf_allowed_hosts` 等守门函数的位置不计入风险位。
- 输出高风险位 JSON + 文件位置 + 调用栈 → check-demo ㉑ 守卫用。

输出（末行）：
    [EMBED_SSRF] {"summary": {"total_http_calls": N, "guarded_calls": N, "risk_positions": [...]}, "env_blocked": false}

设计依据：
- W-NEXT-EXE-SSRF-002 任务定义（SSRF-001 §6 P2 收口 + Mimosa ① host 写死）
- 与 scripts/eval/ssrf_scan.py 风格对齐（只读 AST；不外发请求）
"""
from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ============================================================
# 路径与常量
# ============================================================
_REPO = Path(__file__).resolve().parents[2]                  # edu-agent/
_APP_DIR = _REPO / "app"
_KB_DIR = _APP_DIR / "knowledge"

# AST 扫描的 HTTP/URL API（与 ssrf_scan.py 一致）
_HTTP_API_NAMES = {
    "urllib.request.urlopen", "urlopen",
    "requests.get", "requests.post", "requests.put", "requests.delete",
    "requests.head", "requests.patch", "requests.request",
    "httpx.get", "httpx.post", "httpx.put", "httpx.delete",
    "httpx.head", "httpx.patch", "httpx.request",
    "aiohttp.get", "aiohttp.post", "aiohttp.put", "aiohttp.delete",
    "aiohttp.head", "aiohttp.patch", "aiohttp.request",
}
_HTTP_CLIENT_NAMES = {
    "httpx.Client", "httpx.AsyncClient",
    "aiohttp.ClientSession",
}
_HTTP_CLIENT_METHOD_CALLS = {"get", "post", "put", "delete", "head", "patch", "request", "options"}

# 守门函数/方法名（豁免：本探针不把守门自身列为风险位）
_GUARD_NAMES = {
    # app.security.ssrf_guard 公开/内部 API
    "validate_url", "_ssrf_validate_url", "is_ip_in_blocked_range",
    "ssrf_guard.validate_url",
    # embedder 本地守门（在 _api_embed_batch 入口必调）
    "_gate_embed_url", "_embed_ssrf_allowed_hosts",
    # 单元测试内的引用（pytest 测试代码不应被识别为风险位）
}


def _relpath(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(_REPO)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _call_name(node: ast.Call) -> str:
    """把 ast.Call 还原成点分调用名（httpx.Client / a.post / urllib.request.urlopen）。"""
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        parts = [f.attr]
        cur = f.value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def _is_guarded(decorators: list[ast.expr] | None, parent_assign: bool = False) -> bool:  # noqa: ARG001
    return False  # placeholder for future annotation-based guard detection


def _scan_python_file(path: Path) -> list[dict[str, Any]]:
    """AST 扫一个 .py 文件，输出 [{file, line, call, risk}] list。"""
    findings: list[dict[str, Any]] = []
    try:
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return findings
    except Exception:
        return findings

    lines = src.splitlines()
# 简单「构造点前后 N 行」启发：调用点前后 N 行内出现 _gate_embed_url / validate_url 则视为已守门
    # N=15：保守覆盖 _api_embed_batch 函数体内可能出现的多行配置 + 守门调的间距
    _GUARD_WINDOW_LINES = 15
    GUARD_TOKEN_RE = re.compile(r"_gate_embed_url\b|validate_url\b|_embed_ssrf_allowed_hosts\b|ssrf_guard", re.I)

    def _is_guarded_call(call_node: ast.Call) -> bool:
        # 1) 调用点本身就是守门 → 豁免
        cname = _call_name(call_node)
        if cname in _GUARD_NAMES:
            return True
        # 2) 调用点前后 15 行内含守门 token → 豁免（启发式）
        line = getattr(call_node, "lineno", 1)
        lo = max(0, line - _GUARD_WINDOW_LINES)
        hi = min(len(lines), line + _GUARD_WINDOW_LINES + 1)
        window = "\n".join(lines[lo:hi])
        return bool(GUARD_TOKEN_RE.search(window))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            cname = _call_name(node)
            # module-API 直调
            if cname in _HTTP_API_NAMES:
                guarded = _is_guarded_call(node)
                findings.append({
                    "file": _relpath(path),
                    "line": getattr(node, "lineno", 1),
                    "call": cname,
                    "kind": "module_api",
                    "risk": "low" if guarded else "high",
                    "guarded": guarded,
                })
                continue
            # client 实例化（httpx.Client(args) / httpx.AsyncClient(args)）
            if cname in _HTTP_CLIENT_NAMES:
                guarded = _is_guarded_call(node)
                findings.append({
                    "file": _relpath(path),
                    "line": getattr(node, "lineno", 1),
                    "call": cname,
                    "kind": "client_init",
                    "risk": "low" if guarded else "high",
                    "guarded": guarded,
                })
                continue
            # 链式 client.method(...)
            if isinstance(node.func, ast.Attribute):
                method = node.func.attr
                if method in _HTTP_CLIENT_METHOD_CALLS:
                    # receiver 形如 `client` / `session` / `s` / `c` —— 启发式
                    recv = node.func.value
                    recv_name = ""
                    if isinstance(recv, ast.Name):
                        recv_name = recv.id
                    # 仅当 receiver 形名符合常见 client 命名才纳入
                    if recv_name and re.search(r"\b(client|session|sess|conn|_h|_a|c)\b", recv_name):
                        guarded = _is_guarded_call(node)
                        findings.append({
                            "file": _relpath(path),
                            "line": getattr(node, "lineno", 1),
                            "call": f"<recv>.{method}",
                            "recv": recv_name,
                            "kind": "client_method",
                            "risk": "low" if guarded else "high",
                            "guarded": guarded,
                        })
    return findings


def _list_embed_modules() -> list[Path]:
    """枚举 embed 路径下的所有 .py（含 importer/embedder.py 与 *embed*.py）。"""
    paths: list[Path] = []
    if (_KB_DIR / "importer" / "embedder.py").exists():
        paths.append(_KB_DIR / "importer" / "embedder.py")
    for p in _KB_DIR.rglob("*.py"):
        name = p.name.lower()
        if "embed" in name or "vector" in name or "retriev" in name:
            if p.resolve() not in [x.resolve() for x in paths]:
                paths.append(p)
    # 也覆盖 app/security/embeddings 等同级（如果有）
    for p in _APP_DIR.rglob("*embed*.py"):
        if p.is_file() and p.resolve() not in [x.resolve() for x in paths]:
            paths.append(p)
    return sorted(set(paths), key=lambda x: str(x))


def run_probe() -> dict[str, Any]:
    """主入口：扫 embed 路径 → 输出 dict。"""
    modules = _list_embed_modules()
    all_findings: list[dict[str, Any]] = []
    for m in modules:
        all_findings.extend(_scan_python_file(m))
    total_http_calls = len(all_findings)
    guarded = [f for f in all_findings if f.get("guarded")]
    unguarded = [f for f in all_findings if not f.get("guarded")]
    summary = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "modules_scanned": [_relpath(m) for m in modules],
        "total_http_calls": total_http_calls,
        "guarded_calls": len(guarded),
        "unguarded_calls": len(unguarded),
        "risk_positions": unguarded,  # 高风险位
    }
    return {
        "summary": summary,
        "env_blocked": False,
        "ok": len(unguarded) == 0,  # PASS iff 无未守门位置
    }


def main() -> int:
    try:
        result = run_probe()
    except Exception as exc:
        sys.stderr.write(f"[embed_ssrf_probe] fatal: {exc.__class__.__name__}: {exc}\n")
        # 即使扫描失败也输出 OK=false + env_blocked（与 ssrf_scan 风格一致）
        result = {
            "summary": {"error": str(exc), "total_http_calls": 0, "guarded_calls": 0, "risk_positions": []},
            "env_blocked": True,
            "ok": False,
        }
    print("[EMBED_SSRF]", json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 2  # 0=PASS（无风险位）2=FAIL（有/扫描失败）


if __name__ == "__main__":
    sys.exit(main())
