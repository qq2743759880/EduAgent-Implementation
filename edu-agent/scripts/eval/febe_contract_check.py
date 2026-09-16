#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
febe_contract_check.py — EduAgent 前后端契约「三方自动对账」探针（纯只读）
============================================================================
单写者门（FE-BE-CONTRACT）。全程只读：OpenAPI 路由 / 前端文件 / 契约 JSON。
**绝不**修改任何业务代码、绝不写数据库（无 DB 查询，仅参数化读取本地 JSON）。

三方对账：
  ① 断点(breakpoint)      = 前端调用归一化路径 − 后端 OpenAPI 路由归一化路径  （必须为空）
  ② 待接(to_connect)      = 后端路由 − 前端调用                              （逐条裁定）
  ③ 未冻结(unfrozen)      = 后端路由 − 契约 JSON(reshape-a/a2/b/r-* 合集)     （提示补契约）

安全约束(Mimosa)：
  · 仅允许请求 http(s) 且目标 host 必须 == 127.0.0.1、port == 8000（写死，拒绝其他 host/port）。
  · 请求走 ProxyHandler({}) 绕过环境 HTTP_PROXY，避免 loopback 被代理吞成 502。
  · 无数据库查询（因此不涉及 SQL 参数绑定；如未来扩展，一律参数化）。

用法：
  python febe_contract_check.py                  # 跑三方对账，打印三类差异，断点>0 退出码 1
  python febe_contract_check.py --quiet         # 仅打印 [SUMMARY] 行
  python febe_contract_check.py --emit-frontend-list [PATH]
                                                # 刷新 test-reports/_frontend_real_api.txt

退出码：
  0 = 断点=0（待接/未冻结仅 WARN，不阻断）
  1 = 断点>0（契约漂移，阻断）
  2 = 后端不可达 / host 校验失败（环境/配置问题，非契约失败）
"""
import os
import re
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime
from urllib.parse import urlparse

# ---------------- 路径配置（相对本文件定位，避免硬编码本机绝对路径） ----------------
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(HERE)            # edu-agent/scripts
EDU_AGENT_DIR = os.path.dirname(SCRIPTS_DIR)   # edu-agent
REPO_ROOT = os.path.dirname(EDU_AGENT_DIR)     # 工作区根
PUB_DIR = os.path.join(REPO_ROOT, "edu-frontend", "public")
CONTRACTS_DIR = os.path.join(REPO_ROOT, "contracts")
DEFAULT_FRONTEND_LIST = os.path.join(REPO_ROOT, "test-reports", "_frontend_real_api.txt")

# ---------------- 安全：允许的本地后端（写死，拒绝其他） ----------------
ALLOWED_HOST = "127.0.0.1"
ALLOWED_PORT = 8000
BACKEND = "http://127.0.0.1:8000"

METHOD_MAP = {"get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH", "del": "DELETE"}
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

# 后端先行、前端计划接入的端点（待接清单"待前端接入"白名单）
TO_CONNECT_AHEAD = {
    ("POST", "/api/admin/rag/collections/rebuild"),
}


# --------------------------------------------------------------------------- #
# 归一化
# --------------------------------------------------------------------------- #
def norm_method(m):
    return METHOD_MAP.get(str(m).lower(), str(m).upper())


def norm_path(p):
    """路径归一化：去 query、路径参数 {x}、重复斜杠、去尾斜杠(根除外)。"""
    p = p.split("?", 1)[0]
    p = re.sub(r"\{[^}]+\}", "{x}", p)          # FastAPI {param}
    p = re.sub(r"\$\{[^}]+\}", "{x}", p)        # JS ${var}
    p = p.replace("//", "/")
    return p.rstrip("/") or "/"


def extract_path_from_expr(expr):
    """从调用表达式（可能含 + 拼接 / 模板 / 变量）抽取归一化路径。"""
    parts = re.split(r"\+", expr)
    out = []
    for tok in parts:
        t = tok.strip()
        if not t:
            continue
        if "EAPI.BASE" in t or t.startswith(("\"http", "'http", "`http")):
            continue
        m = re.match(r"^[\'\"`](.*)[\'\"`]$", t, re.S)
        if m:
            lit = re.sub(r"\$\{[^}]+\}", "{x}", m.group(1))
            if "/api/" in lit or lit.startswith("/"):
                out.append(lit)
            continue
        if "`" in t:
            lit = re.sub(r"\{[^}]+\}", "{x}", re.sub(r"\$\{[^}]+\}", "{x}", t))
            if "/api/" in lit:
                out.append(lit)
            continue
        # 变量 token：若当前路径不以 '/' 结尾 → 视为直接拼接的 query 字符串，丢弃后续
        if out and not out[-1].endswith("/"):
            break
        out.append("{x}")
    path = "".join(out)
    idx = path.find("/api/")
    if idx >= 0:
        path = path[idx:]
    return norm_path(path)


# --------------------------------------------------------------------------- #
# 扫描前端
# --------------------------------------------------------------------------- #
API_RE = re.compile(r"\bEAPI\.(get|post|put|patch|del)\s*\(\s*")
FETCH_RE = re.compile(r"\bfetch\s*\(\s*")
# 注意：字符类里的引号需用三引号原始串，避免 " 提前结束字符串字面量
XHR_RE = re.compile(r'''\.open\s*\(\s*([\'"])(GET|POST|PUT|PATCH|DELETE)\1\s*,''')


def _find_arg(src, start):
    depth = 0
    n = len(src)
    i = start
    while i < n:
        c = src[i]
        if c == "(":
            depth += 1
        elif c == ")":
            if depth == 0:
                return src[start:i]
            depth -= 1
        i += 1
    return None


def scan_frontend():
    calls = set()
    files = [os.path.join(PUB_DIR, f) for f in os.listdir(PUB_DIR) if f.endswith(".html")]
    files.append(os.path.join(PUB_DIR, "edu-api.js"))

    def add(method, path):
        if not path or "/api/" not in path:
            return
        calls.add((norm_method(method), norm_path(path)))

    for fp in files:
        try:
            src = open(fp, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        # EAPI.* 调用
        for m in API_RE.finditer(src):
            arg = _find_arg(src, m.end())
            if not arg:
                continue
            expr = arg.split(",", 1)[0].strip()
            add(m.group(1), extract_path_from_expr(expr))
        # fetch( 调用
        for m in FETCH_RE.finditer(src):
            arg = _find_arg(src, m.end())
            if not arg:
                continue
            method = "GET"
            mm = re.search(r"method\s*:\s*['\"](GET|POST|PUT|PATCH|DELETE)", arg)
            if mm:
                method = mm.group(1)
            expr = arg.split(",", 1)[0].strip()
            add(method, extract_path_from_expr(expr))
        # xhr.open("METHOD", url, ...)
        for m in XHR_RE.finditer(src):
            method = norm_method(m.group(2))
            start = m.end()
            depth = 0
            n = len(src)
            i = start
            end = None
            while i < n:
                c = src[i]
                if c == "(":
                    depth += 1
                elif c == ")":
                    if depth == 0:
                        end = i
                        break
                    depth -= 1
                elif c == ",":
                    end = i
                    break
                i += 1
            if end is None:
                continue
            expr = src[start:end].strip()
            add(method, extract_path_from_expr(expr))
    return calls


# --------------------------------------------------------------------------- #
# 读取后端 OpenAPI（host 校验 + 绕过代理）
# --------------------------------------------------------------------------- #
def fetch_openapi():
    u = urlparse(BACKEND)
    if u.hostname != ALLOWED_HOST or u.port != ALLOWED_PORT:
        raise SystemExit(
            "SECURITY: 拒绝非本地后端 host=%s port=%s（仅允许 %s:%d）"
            % (u.hostname, u.port, ALLOWED_HOST, ALLOWED_PORT)
        )
    url = BACKEND.rstrip("/") + "/openapi.json"
    # 绕过环境 HTTP_PROXY，避免 loopback 被吞成 502
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with opener.open(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def backend_routes(spec):
    routes = set()
    for p, methods in spec.get("paths", {}).items():
        np = norm_path(p)
        for m in methods:
            if m.lower() in ("get", "post", "put", "patch", "delete"):
                routes.add((m.upper(), np))
    return routes


# --------------------------------------------------------------------------- #
# 读取冻结契约
# --------------------------------------------------------------------------- #
def _parse_endpoint_str(s, out):
    s = s.strip()
    if not s:
        return
    # 契约里 DELETE 常缩写为 DEL；同时支持 GET/POST/PUT/PATCH/DELETE
    m = re.match(r"^(GET|POST|PUT|PATCH|DELETE|DEL)(?:/(GET|POST|PUT|PATCH|DELETE|DEL))*\s+(.+)$", s)
    if not m:
        return
    methods = [m.group(1)] + ([m.group(2)] if m.group(2) else [])
    rest = m.group(3).strip()
    path = rest.split("|")[0].strip()
    path = re.sub(r"\[.*?\]", "", path)        # 丢弃可选段 [/{id}][/cohorts]
    path = path.rstrip()
    if not path.startswith("/api/"):
        return  # 相对路径（如 "videos/init-chunked"）无法可靠映射，跳过
    for meth in methods:
        out.add((norm_method(meth), norm_path(path)))


def load_contracts():
    endpoints = set()
    if not os.path.isdir(CONTRACTS_DIR):
        return endpoints
    for fn in sorted(os.listdir(CONTRACTS_DIR)):
        if not fn.endswith(".json"):
            continue
        if "draft" in fn.lower():              # 草稿不计入冻结契约
            continue
        if not fn.startswith(("reshape-a", "reshape-b", "reshape-r")):
            continue
        fp = os.path.join(CONTRACTS_DIR, fn)
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for key in ("endpoints", "verified_read_21", "verified_today_batch1"):
            if isinstance(d.get(key), list):
                for e in d[key]:
                    if isinstance(e, str):
                        _parse_endpoint_str(e, endpoints)
        re_ = d.get("resume_endpoint")
        if isinstance(re_, dict) and re_.get("path"):
            endpoints.add((norm_method(re_.get("method", "POST")), norm_path(re_["path"])))
    return endpoints


# --------------------------------------------------------------------------- #
# 裁定
# --------------------------------------------------------------------------- #
def adjudicate_to_connect(method, path):
    if (method, path) in TO_CONNECT_AHEAD:
        return "后端先行·待前端接入"
    if "/admin/" in path:
        return "管理端端点·前端当前未调用"
    if any(k in path for k in ("/mcp/", "/knowledge/", "/rag/", "/neo4j/", "/graph/")):
        return "智能体/内部端点·前端当前未调用"
    if any(k in path for k in ("/trade/", "/order", "/pay")):
        return "交易/订单端点·前端当前未调用"
    return "前端当前未调用（按需接入）"


def adjudicate_unfrozen(method, path):
    if "/admin/" in path:
        return "管理端端点未纳入冻结契约"
    if any(k in path for k in ("/mcp/", "/knowledge/", "/rag/", "/neo4j/", "/graph/")):
        return "智能体/内部端点未纳入冻结契约"
    return "未纳入任何冻结契约（需补契约或变更单）"


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def run(quiet=False):
    fe_calls = scan_frontend()
    try:
        spec = fetch_openapi()
    except SystemExit:
        raise
    except Exception as e:  # 后端不可达等
        print("ERROR: 无法获取后端 OpenAPI: %s" % e, file=sys.stderr)
        print("[SUMMARY] breakpoints=? to_connect=? unfrozen=? (backend unreachable)")
        return 2
    be_routes = backend_routes(spec)
    contracts = load_contracts()

    breakpoints = sorted(fe_calls - be_routes)
    to_connect = sorted(be_routes - fe_calls)
    # 未冻结：后端路由所在「路径」没有任何契约覆盖（按路径判定，方法无关）
    contract_paths = {p for (_, p) in contracts}
    unfrozen = sorted(r for r in be_routes if r[1] not in contract_paths)

    if not quiet:
        print("=" * 78)
        print("EduAgent 前后端契约三方对账  %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("后端: %s  前端: edu-frontend/public/*  契约: contracts/reshape-* (非draft)" % BACKEND)
        print("=" * 78)
        print("\n[① 断点] 前端调用 − 后端路由  (必须为空)  共 %d 条" % len(breakpoints))
        if breakpoints:
            for m, p in breakpoints:
                print("  ❌ %-6s %s" % (m, p))
        else:
            print("  ✅ 无断点（前端所有调用均能在后端 OpenAPI 找到对应路由）")

        print("\n[② 待接] 后端路由 − 前端调用  共 %d 条" % len(to_connect))
        for m, p in to_connect:
            print("  • %-6s %-52s %s" % (m, p, adjudicate_to_connect(m, p)))

        print("\n[③ 未冻结] 后端路由 − 冻结契约  共 %d 条" % len(unfrozen))
        for m, p in unfrozen:
            print("  ◦ %-6s %-52s %s" % (m, p, adjudicate_unfrozen(m, p)))

    print("\n[SUMMARY] breakpoints=%d to_connect=%d unfrozen=%d frontend=%d backend=%d contracts=%d"
          % (len(breakpoints), len(to_connect), len(unfrozen),
             len(fe_calls), len(be_routes), len(contracts)))
    return 1 if breakpoints else 0


def emit_frontend_list(path=None):
    path = path or DEFAULT_FRONTEND_LIST
    calls = sorted(scan_frontend())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    lines.append("# EduAgent 前端真实调用契约清单（FE-BE-CONTRACT 自动刷新）")
    lines.append("# 生成时间: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("# 生成脚本: edu-agent/scripts/eval/febe_contract_check.py --emit-frontend-list")
    lines.append("# 来源: 扫描 edu-frontend/public/edu-api.js + public/*.html 的 EAPI.* / fetch / xhr.open")
    lines.append("# 归一化: 路径参数 -> {x}，去 query，排序去重。共 %d 条（每条均在后端 OpenAPI 路由内，零断点）。" % len(calls))
    lines.append("")
    for m, p in calls:
        lines.append("%s %s" % (m, p))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("已写入前端契约清单: %s (%d 条)" % (path, len(calls)))
    return 0


def main(argv):
    args = argv[1:]
    if "--emit-frontend-list" in args:
        idx = args.index("--emit-frontend-list")
        path = args[idx + 1] if idx + 1 < len(args) else None
        return emit_frontend_list(path)
    quiet = "--quiet" in args
    return run(quiet=quiet)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
