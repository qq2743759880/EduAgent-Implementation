#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
febe_contract_check.py — EduAgent 前后端契约「三方自动对账」探针（纯只读）
============================================================================
单写者门（FE-BE-CONTRACT / W-NEXT-FE-001）。全程只读：OpenAPI 路由 / 前端文件 / 契约 JSON。
**绝不**修改任何业务代码、绝不写数据库（无 DB 查询，仅参数化读取本地 JSON）。

三方对账：
  ① 断点(breakpoint)        = 前端调用归一化路径 − 后端 OpenAPI 路由归一化路径  （必须为空 → 红/阻断）
  ② 在用未冻结(in_use_unfrozen) = 前端调用 ∩ 后端路由 − 冻结契约            （前端在用但无契约 → 红/阻断，治理压力核心）
  ③ 未冻结仅后端(unfrozen_only)= 后端路由 − 冻结契约 − 在用未冻结         （后端有、前端未用、无契约 → WARN，不阻断）
  ④ 待接(to_connect)        = 后端路由 − 前端调用                          （逐条裁定，WARN 不阻断）

安全约束(Mimosa)：
  · 仅允许请求 http(s) 且目标 host 必须 == 127.0.0.1、port == 8000（写死，拒绝其他 host/port）。
  · 请求走 ProxyHandler({}) 绕过环境 HTTP_PROXY，避免 loopback 被代理吞成 502。
  · 无数据库查询（因此不涉及 SQL 参数绑定；如未来扩展，一律参数化）。

用法：
  python febe_contract_check.py                  # 跑四方对账，打印四类差异；断点>0 或 在用未冻结>0 → 退出码 1
  python febe_contract_check.py --quiet         # 仅打印 [SUMMARY] 行
  python febe_contract_check.py --emit-frontend-list [PATH]
                                                # 刷新 test-reports/_frontend_real_api.txt
  python febe_contract_check.py --emit-migration-status [PATH]
                                                # 刷新 test-reports/_frontend_migration_status.json
                                                # (W-NEXT-FRONTEND-CONTRACT-001 治理分类：plan/deferred/ops/unassigned)

退出码：
  0 = 断点=0 且 在用未冻结=0（待接/未冻结仅后端 仅 WARN，不阻断）
  1 = 断点>0 或 在用未冻结>0（契约漂移/前端无契约在用，阻断）
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
SRC_DIR = os.path.join(REPO_ROOT, "edu-frontend", "src")  # Next.js 迁移面（W-NEXT-FEBE-SCAN-002 扩扫）
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

# ---------------------------------------------------------------------------
# W-NEXT-FRONTEND-CONTRACT-001 待接清单治理分类（plan/deferred/ops/unknown）
# ---------------------------------------------------------------------------
# ⑩ 门 WARN 待接条数 = 后端路由 − 前端真实调用（W-NEXT-FEBE-SCAN-002 起前端含
# Next.js src 扩扫，条数由 109 收缩为实测值，见 [SUMMARY] to_connect；此处不再写死）。
# 落地治理时按"前端接入计划"拆桶，避免把"已知规划的待接"与"真正的契约漂移"混在一起：
#
#   plan     = Next.js 已有对应路由页面/组件、但具体端点暂未挂接（前端迁移进行中）
#   deferred = 后端 admin/MCP/交易域端点，Next.js 暂未迁移该域页面（按阶段计划）
#   ops      = 运维端点（健康检查/Prometheus 抓取/支付回调 mock），前端永不接入
#   unknown  = 当前无明确接入计划（需用户裁定）
#
# 设计约束（防遮蔽）：
#   · 仅做**分类输出**，不修改 to_connect 集合、不降低 to_connect 计数；
#   · 集合在此处显式列出，每条带 `// why/接入计划` 注释，便于人工/变更单追溯；
#   · 与 KNOWN_ROOT_PATHS / TO_CONNECT_AHEAD 风格一致——纯只读白名单；
#   · 不允许"批量加进 unknown 自动覆盖"——任一未列入集合的 tc 项会被标记 unknown。
#
# 列出顺序：方法 + 路径（与 ⑩ 门输出对齐）。任何修改必须附 PR 链接 + 用户签字。
# ---------------------------------------------------------------------------
NEXTJS_PLANNED_ENDPOINTS = frozenset({
    # ---- plan: Next.js 已有页面/组件、仅具体方法未挂接 ----
    # admin 课程域（page.tsx 已存在但 GET 单条/chapters/modules 未接入）
    ("GET", "/api/admin/courses/chapters/{x}"),         # src/app/(admin)/admin/courses/[seriesId]/page.tsx
    ("GET", "/api/admin/courses/modules/{x}"),          # 同上
    ("GET", "/api/admin/courses/sessions/{x}"),         # 同上
    # admin 题库（questions.ts 已有 wrapper，但 banks 集合细节未全部挂接）
    ("GET", "/api/admin/questions/banks"),              # question-bank.ts wrapper
    ("GET", "/api/admin/questions/banks/{x}/questions"),# question-bank.ts wrapper
    ("GET", "/api/admin/questions/exams"),               # 考试列表（待 admin/questions 页面实装）
    ("GET", "/api/admin/questions/exams/{x}"),          # 考试详情
    # community（community.ts 有完整 wrapper，但部分子资源未挂接）
    ("PATCH", "/api/community/posts/{x}"),               # post 编辑（待 admin 工具）
    # admin RAG 收集重建（TO_CONNECT_AHEAD；admin/rag 页面待实装）
    ("POST", "/api/admin/rag/collections/rebuild"),      # TO_CONNECT_AHEAD
    # user side：favorites/me/student-profile 等（lib/api/me.ts 已部分接入）
    ("GET", "/api/users/me/student-profile"),           # 学生画像（dashboard 阶段实装）
})

NEXTJS_DEFERRED_ENDPOINTS = frozenset({
    # ---- deferred: 后端域管理/MCP/交易/智能体 — Next.js 暂未迁移该域页面 ----
    # admin 课程域暂未接入的 GET 单条/聚合
    ("GET", "/api/admin/courses/cohorts/{x}"),
    ("GET", "/api/admin/courses/cohorts/{x}/sessions"),
    # admin 评价/退款/审核/概览
    ("DELETE", "/api/admin/reviews/{x}"),
    ("GET", "/api/admin/reviews"),
    ("GET", "/api/admin/refunds"),
    ("GET", "/api/admin/trade/overview"),
    ("POST", "/api/admin/refunds/{x}/approve"),
    ("POST", "/api/admin/refunds/{x}/reject"),
    # admin RAG / 题库发布 / 收集重建
    ("GET", "/api/admin/rag/audit-log"),
    ("GET", "/api/admin/rag/presets"),
    ("POST", "/api/admin/rag/presets"),
    ("POST", "/api/admin/rag/search"),
    ("POST", "/api/admin/questions/exams"),
    ("POST", "/api/admin/questions/exams/{x}/publish"),
    ("PATCH", "/api/admin/questions/exams/{x}"),
    # admin 用户/记忆
    ("GET", "/api/admin/users"),
    ("POST", "/api/memory/admin/dream/run"),
    # admin 章节 PATCH（page.tsx 有 button 但 PATCH 暂未挂）
    ("PATCH", "/api/admin/courses/chapters/{x}"),
    # MCP 域（智能体/内部端点 — Next.js 暂未迁移）
    ("DELETE", "/api/mcp/sessions/{x}"),
    ("GET", "/api/mcp/servers/{x}"),
    ("GET", "/api/mcp/servers/{x}/discover-live"),
    ("GET", "/api/mcp/servers/{x}/tools"),
    ("GET", "/api/mcp/sessions"),
    ("GET", "/api/mcp/sessions/{x}"),
    ("POST", "/api/mcp/servers/{x}/raw-rpc"),
    ("POST", "/api/mcp/sessions"),
    ("POST", "/api/mcp/sessions/{x}/touch"),
    ("POST", "/api/mcp/description-review"),
    ("POST", "/api/mcp/health-scan-async"),
    ("POST", "/api/mcp/servers/import-url"),
    ("GET", "/api/mcp/health-scan/{x}"),
    ("GET", "/api/mcp/call-log/{x}"),
    ("GET", "/api/mcp/description-review-log"),
    # knowledge 域（内部/智能体）
    ("POST", "/api/knowledge/upload"),
    ("GET", "/api/knowledge/status/{x}"),
    # 交易域（trade/after_sales/ticket/payment） — Next.js 暂未迁移交易 UI
    ("GET", "/api/trade/after_sales/ticket/{x}"),
    ("GET", "/api/trade/after_sales/tickets"),
    ("GET", "/api/trade/order/{x}"),
    ("GET", "/api/trade/orders"),
    ("GET", "/api/trade/payment/{x}"),
    ("GET", "/api/trade/payments"),
    ("GET", "/api/trade/payments/reconcile"),
    ("POST", "/api/trade/after_sales/ticket"),
    ("POST", "/api/trade/after_sales/ticket/{x}/satisfaction"),
    ("POST", "/api/trade/order/{x}/cancel"),
    ("POST", "/api/trade/payment/{x}"),
    ("POST", "/api/trade/payment/{x}/cancel"),
    ("POST", "/api/trade/payment/{x}/mock-notify"),
    ("POST", "/api/trade/payment/{x}/retry"),
    ("POST", "/api/trade/payments/reconcile"),
})

NEXTJS_OPS_ENDPOINTS = frozenset({
    # ---- ops: 运维端点（前端永不接入） ----
    # health/metrics 已在 KNOWN_ROOT_PATHS 收录（contract 冻结），但 ⑩ 门 WARN
    # 待接仍会逐条列出。这里集中登记让分类完整（plan/deferred/ops/unknown = 109）。
    ("GET", "/"),                                       # 根 landing — KNOWN_ROOT_PATHS
    ("GET", "/health"),                                 # 健康检查 — KNOWN_ROOT_PATHS
    ("GET", "/health/detail"),                          # 健康检查详情 — KNOWN_ROOT_PATHS
    ("GET", "/health/warmup"),                          # 模型/依赖预热 — KNOWN_ROOT_PATHS
    ("GET", "/metrics"),                                # Prometheus 抓取 — KNOWN_ROOT_PATHS
    ("POST", "/payment-notifications/mock"),            # 支付回调 mock — 仅测试夹具
})

NEXTJS_UNASSIGNED = frozenset({
    # ---- unknown: 当前无明确接入计划、需用户裁定 ----
    # 学端非 admin/非 MCP/非 trade 的资源 — 多数是规划中但暂未排期。
    ("DELETE", "/api/favorites/{x}"),
    ("GET", "/api/coding/challenges"),
    ("GET", "/api/coding/challenges/{x}"),
    ("GET", "/api/cohorts/{x}"),
    ("GET", "/api/cohorts/{x}/modules"),
    ("GET", "/api/community/posts"),
    ("GET", "/api/enrollments/me/cohorts/{x}"),
    ("GET", "/api/enrollments/me/cohorts/{x}/progress"),
    ("GET", "/api/enrollments/me/cohorts/{x}/status"),
    ("GET", "/api/interactive/quiz/types"),
    ("GET", "/api/interactive/quiz/wrong-next"),
    ("GET", "/api/math/practice"),
    ("GET", "/api/memory/history/{x}"),
    ("GET", "/api/metrics/cache-context-dashboard"),
    ("GET", "/api/metrics/otel"),
    ("GET", "/api/metrics/trace/{x}"),
    ("GET", "/api/mindmap/course/{x}"),
    ("GET", "/api/mindmap/me/{x}"),
    ("GET", "/api/mindmap/prerequisite"),
    ("GET", "/api/mindmap/subject/{x}"),
    ("GET", "/api/progress/courses"),
    ("GET", "/api/recommend/next"),
    ("GET", "/api/recommend/path"),
    ("GET", "/api/refunds"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/chat"),
    ("POST", "/api/chat/search"),
    ("POST", "/api/coding/hint"),
    ("POST", "/api/coding/run"),
    ("POST", "/api/coding/submit"),
    ("POST", "/api/community/posts/{x}/favorite"),
    ("POST", "/api/gamification/me/award"),
    ("POST", "/api/gamification/me/check-badges"),
    ("POST", "/api/math/explain"),
    ("POST", "/api/math/step-check"),
    ("POST", "/api/memory/rewind"),
    ("POST", "/api/progress/exam/submit"),
    ("POST", "/api/progress/homework/submit"),
    ("POST", "/api/progress/video/tick-batch"),
    ("POST", "/api/recommend/feedback"),
    ("POST", "/api/refunds"),
    ("POST", "/api/refunds/{x}/cancel"),
    ("POST", "/api/study/sessions/{x}/complete"),
    # 2026-09-18 后端新增（KG + Analytics 域）——前端暂未接入
    ("GET", "/api/analytics/learning-events/stream-stats"),
    ("GET", "/api/analytics/learning-events/summary"),
    ("GET", "/api/kg/chapter/{x}/downstream"),
    ("GET", "/api/kg/chapter/{x}/upstream"),
    ("GET", "/api/kg/course/{x}/path"),
})

# 相对路径契约的已知父上下文（verified_today_batch1 的嵌套资源都挂在课程管理域下）。
# 解析相对路径时优先拼此父上下文再回退后缀匹配，避免误匹配到 /api/cohorts 等其它资源。
KNOWN_REL_PARENTS = ("/api/admin/courses",)

# 根路径/运维端点白名单（W-NEXT-FE-003 + W-NEXT-FE-CONTRACT-002）：这些绝对路径
# 不以 /api/ 开头但属于运维探活/landing/监控语义，契约里可以直接写「GET /」/「GET /health」等。
# 经归一化（去 query / 去尾斜杠）后命中此集合即直接入冻结集合，不再走相对路径兜底（避免
# lstrip("/") 后变空串被短路的漏洞）。新增运维端点必须显式加入此白名单——禁止泛化。
KNOWN_ROOT_PATHS = frozenset({
    "/",                  # 根 landing（app.name/version/message/docs）
    "/health",            # 健康检查
    "/health/detail",     # 健康检查详情
    "/health/warmup",     # 模型/依赖预热
    "/metrics",           # Prometheus 抓取
})


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
    # Query-suffix 模板尾巴归一（W-NEXT-FEBE-SCAN-002）：JS 模板串常把 query string
    # 以变量拼在路径尾（`.../cohorts${qs}`、`.../series/${id}${q}`），字面量归一化后
    # 会产出「非 / 分隔的 {x} 尾巴」。合法 URL 的路径参数必以 / 分隔，因此把结尾处
    # 不以 / 分隔的 {x} 游程剥掉（它们是 query/片段尾巴，不是路径段）。
    # 反遮蔽：被剥尾巴的路径逐条记录进 _QUERY_SUFFIX_STRIPPED，非 quiet 输出可见。
    stripped = re.sub(r"(?:(?<!/)\{x\})+$", "", path)
    if stripped != path:
        _QUERY_SUFFIX_STRIPPED.append(path)
    path = stripped
    return norm_path(path)


# 反遮蔽诊断：本次扫描中被「query-suffix 尾巴归一」剥掉 {x} 尾巴的路径（归一化前形态）
_QUERY_SUFFIX_STRIPPED = []


# --------------------------------------------------------------------------- #
# 扫描前端
# --------------------------------------------------------------------------- #
API_RE = re.compile(r"\bEAPI\.(get|post|put|patch|del)\s*\(\s*")
FETCH_RE = re.compile(r"\bfetch\s*\(\s*")
# 注意：字符类里的引号需用三引号原始串，避免 " 提前结束字符串字面量
XHR_RE = re.compile(r'''\.open\s*\(\s*([\'"])(GET|POST|PUT|PATCH|DELETE)\1\s*,''')
# Next.js src 客户端封装（W-NEXT-FEBE-SCAN-002）：lib/api-client.ts http.* 与
# lib/api/admin.ts admin* 系列。泛型允许一层嵌套（adminGet<AdminPage<QuestionBank>>(...)）。
HTTP_CLIENT_RE = re.compile(
    r"\bhttp\.(get|post|put|patch|delete|del)\b\s*(?:<(?:[^<>]|<[^<>]*>)*>)?\s*\(\s*"
)
ADMIN_CLIENT_RE = re.compile(
    r"\badmin(Get|Post|Put|Patch|Delete)\b\s*(?:<(?:[^<>]|<[^<>]*>)*>)?\s*\(\s*"
)

# src 扫描范围：Next.js 运行源码；排除测试/故事/类型声明（mock 域，不对 8000 发真实请求，
# 其中的假路径（/api/auth/anything 等）不是契约断点）。
SRC_FILE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SRC_SKIP_DIRS = {"node_modules", ".next", "__tests__", "e2e", "stories", "coverage"}
SRC_SKIP_FILE_MARKERS = (".test.", ".spec.", ".stories.", ".d.ts")


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


def _iter_src_files(src_dir):
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in SRC_SKIP_DIRS]
        for fn in sorted(files):
            if not fn.endswith(SRC_FILE_EXTS):
                continue
            if any(mk in fn for mk in SRC_SKIP_FILE_MARKERS):
                continue
            yield os.path.join(root, fn)


def _scan_file_calls(fp, calls):
    """单文件扫描全部调用族（EAPI / fetch / xhr / http.* / admin*），命中并入 calls。"""
    try:
        src = open(fp, encoding="utf-8", errors="ignore").read()
    except OSError:
        return

    def add(method, path):
        if not path or "/api/" not in path:
            return
        calls.add((norm_method(method), norm_path(path)))

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
    # http.get<T>(...) / http.post(...)（Next.js lib/api-client.ts 封装）
    for m in HTTP_CLIENT_RE.finditer(src):
        arg = _find_arg(src, m.end())
        if not arg:
            continue
        expr = arg.split(",", 1)[0].strip()
        add(m.group(1), extract_path_from_expr(expr))
    # adminGet<T>(...) / adminPost<T>(...)（Next.js lib/api/admin.ts 封装）
    for m in ADMIN_CLIENT_RE.finditer(src):
        arg = _find_arg(src, m.end())
        if not arg:
            continue
        expr = arg.split(",", 1)[0].strip()
        add(m.group(1).lower(), extract_path_from_expr(expr))


def _scan_public_frontend():
    """静态糖果页（public/*.html + edu-api.js）——W-NEXT-FE-001 原扫描面。"""
    calls = set()
    files = [os.path.join(PUB_DIR, f) for f in os.listdir(PUB_DIR) if f.endswith(".html")]
    files.append(os.path.join(PUB_DIR, "edu-api.js"))
    for fp in files:
        _scan_file_calls(fp, calls)
    return calls


def scan_frontend_src(src_dir=None):
    """Next.js src 扫描（W-NEXT-FEBE-SCAN-002 扩扫）。

    返回 (calls, scanned_files)：
      calls          —— (method, norm_path) 集合（与 public 扫描同口径）
      scanned_files  —— 实际扫描的文件相对路径列表（诊断/报告用）
    测试/故事/声明文件被排除（mock 域不对 8000 发真实请求）。
    """
    src_dir = src_dir or SRC_DIR
    calls = set()
    scanned = []
    if not os.path.isdir(src_dir):
        return calls, scanned
    for fp in _iter_src_files(src_dir):
        scanned.append(os.path.relpath(fp, src_dir))
        _scan_file_calls(fp, calls)
    return calls, scanned


def scan_frontend():
    """前端真实调用 = 静态糖果页(public) ∪ Next.js src（W-NEXT-FEBE-SCAN-002 扩扫）。"""
    _QUERY_SUFFIX_STRIPPED.clear()
    calls = _scan_public_frontend()
    src_calls, _ = scan_frontend_src()
    calls |= src_calls
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
# 解析相对路径契约 → 拼全 /api/ 路径（W-NEXT-FE-001 P0-2 修复）
# --------------------------------------------------------------------------- #
def resolve_relative(methods, rel_path, be_routes):
    """
    把相对路径契约（如 'videos/init-chunked'、'cohorts/{id}/modules'）解析为完整的
    (method, /api/...) 路由。返回解析出的 (method, path) 列表；无法可靠解析返回 None。

    解析优先级（避免误匹配 /api/cohorts 等其它资源）：
      1) 已知父上下文 /api/admin/courses/<rel> —— verified_today_batch1 的嵌套资源都在此域下；
         只要该父路径下有任一合法 (method, path) 命中即采用（不再回退，避免误抓 video-chapters 之类）。
      2) 裸 /api/<rel>。
      3) 后缀匹配全部后端路由，优先取 /api/admin/courses/ 候选；仍无则 None（交由调用方标记 [MALFORMED]）。
    """
    rel = norm_path(rel_path).lstrip("/")
    if not rel:
        return None
    method_set = {norm_method(m) for m in methods}

    def _match(base):
        return [(mm, base) for mm in method_set if (mm, base) in be_routes]

    for parent in list(KNOWN_REL_PARENTS) + ["/api"]:
        base = norm_path(parent + "/" + rel)
        hits = _match(base)
        if hits:
            return hits
        # 基路径无方法命中（如 'chapters' 仅集合 POST 存在，而契约写 GET/DELETE）
        # → 尝试 {id} 子路由（/api/admin/courses/chapters/{x}），避免误匹配到 video-chapters 之类
        hits_id = _match(norm_path(base + "/{x}"))
        if hits_id:
            return hits_id

    # 后缀兜底：匹配所有以 rel 结尾的后端路由（优先 /api/admin/courses/ 候选）
    suffix = [(m, p) for (m, p) in be_routes
              if p.lstrip("/") == rel or p.lstrip("/").endswith("/" + rel)]
    if not suffix:
        return None
    admin = [(m, p) for (m, p) in suffix if "/api/admin/courses/" in p]
    pool = admin if admin else suffix
    result = [(m, p) for (m, p) in pool if m in method_set]
    return result if result else None


# --------------------------------------------------------------------------- #
# 读取冻结契约
# --------------------------------------------------------------------------- #
def _parse_endpoint_str(s, out, relative_out=None):
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
    path = re.sub(r"\[.*?\]", "", path)        # 丢弃可选段 [?session_id=...][/{id}]
    path = path.rstrip()
    if not path.startswith("/api/"):
        # 根路径/运维端点白名单（KNOWN_ROOT_PATHS）：不以 /api/ 开头但仍属业务可观测面，
        # 经归一化（去尾斜杠/去 query）后命中即直接入冻结集合，避免走相对路径兜底导致
        # root path 在 lstrip("/") 后变空串被短路漏检（⑱ 门要求 unfrozen_only=0）。
        normalized = norm_path(path)
        if normalized in KNOWN_ROOT_PATHS:
            for meth in methods:
                out.add((norm_method(meth), normalized))
            return
        # 相对路径（如 "videos/init-chunked"）：不再静默丢弃，
        # 交给调用方在已知后端路由上下文中解析；解析不了再标 [MALFORMED]。
        if relative_out is not None:
            relative_out.append((methods, path))
        return
    for meth in methods:
        out.add((norm_method(meth), norm_path(path)))


def load_contracts(be_routes=None):
    """
    读取冻结契约（reshape-a/a2/b/r-* 非 draft）。

    返回 (endpoints, malformed)：
      - endpoints: 解析后的 (method, norm_path) 集合（绝对路径 + 已解析的相对路径）
      - malformed: 相对路径契约中无法可靠解析的 [(methods, rel_path), ...]

    当 be_routes 为 None（无后端上下文）时，相对路径一律计入 malformed（显式可见，不再静默丢弃）。
    """
    endpoints = set()
    relative = []
    if not os.path.isdir(CONTRACTS_DIR):
        return endpoints, relative
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
                        _parse_endpoint_str(e, endpoints, relative)
        re_ = d.get("resume_endpoint")
        if isinstance(re_, dict) and re_.get("path"):
            endpoints.add((norm_method(re_.get("method", "POST")), norm_path(re_["path"])))
    malformed = []
    if be_routes is None:
        malformed.extend(relative)
        return endpoints, malformed
    for methods, rel_path in relative:
        resolved = resolve_relative(methods, rel_path, be_routes)
        if resolved is None:
            malformed.append((methods, rel_path))
        else:
            endpoints.update(resolved)
    return endpoints, malformed


# --------------------------------------------------------------------------- #
# 裁定
# --------------------------------------------------------------------------- #
def plan_bucket_broken(be_routes):
    """尾巴③（W-NEXT-FEBE-SCAN-002）plan 桶后端合法性校验。

    plan 桶语义 = 「后端已有、前端计划接入」——每一条都必须真实存在于后端
    OpenAPI 路由集合。若某条 plan 条目不在 be_routes 中，它是**非法 plan**
    （后端根本没有该路由，永远不可能从 to_connect 进入在用集合，此前会被
    `NEXTJS_PLANNED_ENDPOINTS ∩ to_connect` 静默吞掉）。返回 sorted 断条列表。
    """
    return sorted(NEXTJS_PLANNED_ENDPOINTS - set(be_routes))


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


def adjudicate_unfrozen_only(method, path):
    if "/admin/" in path:
        return "管理端端点未纳入冻结契约"
    if any(k in path for k in ("/mcp/", "/knowledge/", "/rag/", "/neo4j/", "/graph/")):
        return "智能体/内部端点未纳入冻结契约"
    return "未纳入任何冻结契约（需补契约或变更单）"


def adjudicate_in_use_unfrozen(method, path):
    return "前端实际在用但冻结契约缺失（治理压力核心，CI 红/阻断）"


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
        print("[SUMMARY] breakpoints=? in_use_unfrozen=? unfrozen_only=? to_connect=? "
              "frontend=? backend=? contracts=? malformed=? (backend unreachable)")
        return 2
    be_routes = backend_routes(spec)
    contracts, malformed = load_contracts(be_routes)

    breakpoints = sorted(fe_calls - be_routes)
    to_connect = sorted(be_routes - fe_calls)
    contract_paths = {p for (_, p) in contracts}
    unfrozen_mp = sorted(be_routes - contracts)                       # 后端有、契约无（method+path）
    in_use_unfrozen = sorted((fe_calls & be_routes) - contracts)       # 前端在用、契约无（method+path）
    unfrozen_only = sorted(set(unfrozen_mp) - set(in_use_unfrozen))   # 后端有、前端未用、契约无

    if not quiet:
        print("=" * 78)
        print("EduAgent 前后端契约四方对账  %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("后端: %s  前端: edu-frontend/public/* + src/**（W-NEXT-FEBE-SCAN-002 扩扫）  契约: contracts/reshape-* (非draft)" % BACKEND)
        print("=" * 78)
        if _QUERY_SUFFIX_STRIPPED:
            print("[QUERY-SUFFIX] 模板 query 尾巴归一（非 / 分隔的 {x} 尾巴被剥除，反遮蔽可见） 共 %d 处" % len(_QUERY_SUFFIX_STRIPPED))
            for p in sorted(set(_QUERY_SUFFIX_STRIPPED)):
                print("  ◦ %s" % p)
        print("\n[① 断点] 前端调用 − 后端路由  (必须为空)  共 %d 条  → %s"
              % (len(breakpoints), "红/阻断" if breakpoints else "PASS"))
        if breakpoints:
            for m, p in breakpoints:
                print("  ❌ %-6s %s" % (m, p))
        else:
            print("  ✅ 无断点（前端所有调用均能在后端 OpenAPI 找到对应路由）")

        print("\n[② 在用未冻结] 前端在用 ∩ 后端路由 − 冻结契约  共 %d 条  → %s"
              % (len(in_use_unfrozen), "红/阻断" if in_use_unfrozen else "PASS"))
        if in_use_unfrozen:
            for m, p in in_use_unfrozen:
                print("  🔴 %-6s %-52s %s" % (m, p, adjudicate_in_use_unfrozen(m, p)))
        else:
            print("  ✅ 前端在用的接口全部已有冻结契约")

        print("\n[③ 未冻结仅后端] 后端路由 − 冻结契约 − 前端在用  共 %d 条  → WARN（不阻断）"
              % len(unfrozen_only))
        for m, p in unfrozen_only:
            print("  ◦ %-6s %-52s %s" % (m, p, adjudicate_unfrozen_only(m, p)))

        print("\n[④ 待接] 后端路由 − 前端调用  共 %d 条  → WARN（不阻断）" % len(to_connect))
        for m, p in to_connect:
            print("  • %-6s %-52s %s" % (m, p, adjudicate_to_connect(m, p)))

        # ---- [PLANNED-BREAKDOWN] W-NEXT-FRONTEND-CONTRACT-001 治理分类 ----
        # 不修改 to_connect，仅按 4 桶分类输出，便于治理节奏追踪（plan/in_progress
        # vs ops/deferred vs unknown）。
        tc_set = set(to_connect)
        buckets = {
            "plan": (NEXTJS_PLANNED_ENDPOINTS & tc_set, "Next.js 页面已实装/迁移进行中"),
            "deferred": (NEXTJS_DEFERRED_ENDPOINTS & tc_set, "Next.js 暂未迁移该域（admin/MCP/交易）"),
            "ops": (NEXTJS_OPS_ENDPOINTS & tc_set, "运维端点·前端永不接入"),
            "unassigned": (NEXTJS_UNASSIGNED & tc_set, "无明确接入计划·待用户裁定"),
        }
        classified = sum(len(v[0]) for v in buckets.values())
        # 兜底：未归入任何桶的 to_connect 项也单独列出（理论上 0）
        all_classified = NEXTJS_PLANNED_ENDPOINTS | NEXTJS_DEFERRED_ENDPOINTS | NEXTJS_OPS_ENDPOINTS | NEXTJS_UNASSIGNED
        uncategorized = sorted(tc_set - all_classified)
        # 尾巴③（W-NEXT-FEBE-SCAN-002）：plan 桶后端合法性校验——plan 条目必须真实
        # 存在于后端 OpenAPI；不合法项显式入 plan_broken 并输出警告行（WARN，不改 ⑩ 红判据）。
        plan_broken = plan_bucket_broken(be_routes)
        print("\n[PLANNED-BREAKDOWN] 待接 %d 治理分类（plan/deferred/ops/unassigned/plan_broken）" % len(tc_set))
        print("  分类源：febe_contract_check.py 顶部的 NEXTJS_*_ENDPOINTS 显式清单（注释逐条 why）")
        for k, (items, label) in buckets.items():
            print("  %-10s %d 条  → %s" % (k, len(items), label))
        print("  --------  合计: %d / %d" % (classified, len(tc_set)))
        if uncategorized:
            print("  ⚠️ 未分类（理论应为 0）: %d 条" % len(uncategorized))
            for m, p in uncategorized:
                print("    - %-6s %s" % (m, p))
        print("  %-10s %d 条  → plan 桶含后端不存在路由（非法 plan·警告，非阻断）"
              % ("plan_broken", len(plan_broken)))
        for m, p in plan_broken:
            print("    ⚠️ %-6s %-52s 不在后端 OpenAPI（禁止保留为 plan，移出桶或走变更单）" % (m, p))

        if malformed:
            print("\n[MALFORMED] 无法可靠解析的相对路径契约  共 %d 条（未计入冻结集合）" % len(malformed))
            for methods, p in malformed:
                print("  ⚠️  %s %s" % ("/".join(norm_method(x) for x in methods), p))

    # 尾巴③：plan_broken 即便 quiet 也必须可见（WARN，不进 ⑩ 红判据；⑩/⑱ 只解析
    # [SUMMARY] 行，此行不影响其解析）。
    _pb = plan_bucket_broken(be_routes)
    if _pb:
        print("[PLAN-BROKEN] %d 条 plan 桶端点不在后端 OpenAPI（非法 plan·警告）: %s"
              % (len(_pb), ", ".join("%s %s" % (m, p) for m, p in _pb)))

    print("\n[SUMMARY] breakpoints=%d in_use_unfrozen=%d unfrozen_only=%d to_connect=%d "
          "frontend=%d backend=%d contracts=%d malformed=%d"
          % (len(breakpoints), len(in_use_unfrozen), len(unfrozen_only), len(to_connect),
             len(fe_calls), len(be_routes), len(contracts), len(malformed)))
    # 红/阻断：断点>0 或 前端在用却无契约>0；其余仅 WARN。
    return 1 if (breakpoints or in_use_unfrozen) else 0


def emit_frontend_list(path=None):
    path = path or DEFAULT_FRONTEND_LIST
    calls = sorted(scan_frontend())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = []
    lines.append("# EduAgent 前端真实调用契约清单（FE-BE-CONTRACT 自动刷新）")
    lines.append("# 生成时间: %s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("# 生成脚本: edu-agent/scripts/eval/febe_contract_check.py --emit-frontend-list")
    lines.append("# 来源: 扫描 edu-frontend/public/edu-api.js + public/*.html + src/**（Next.js，W-NEXT-FEBE-SCAN-002 扩扫，排除 *.test./*.spec./*.stories./.d.ts） 的 EAPI.* / fetch / xhr.open / http.* / admin*")
    lines.append("# 归一化: 路径参数 -> {x}，去 query，模板 query 尾巴剥除，排序去重。共 %d 条。" % len(calls))
    lines.append("")
    for m, p in calls:
        lines.append("%s %s" % (m, p))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("已写入前端契约清单: %s (%d 条)" % (path, len(calls)))
    return 0


# --------------------------------------------------------------------------- #
# W-NEXT-FRONTEND-CONTRACT-001: emit_migration_status
# --------------------------------------------------------------------------- #
# 输出待接清单的治理分类 JSON（含 plan/deferred/ops/unassigned 四桶 + uncategorized
# 兜底），写入 test-reports/_frontend_migration_status.json。便于 governance 跟进。
DEFAULT_MIGRATION_STATUS = os.path.join(REPO_ROOT, "test-reports", "_frontend_migration_status.json")


def emit_migration_status(path=None):
    path = path or DEFAULT_MIGRATION_STATUS
    try:
        spec = fetch_openapi()
    except SystemExit:
        raise
    except Exception as e:
        print("ERROR: 无法获取后端 OpenAPI: %s" % e, file=sys.stderr)
        return 2
    be_routes = backend_routes(spec)
    fe_calls = scan_frontend()
    to_connect = sorted(be_routes - fe_calls)
    tc_set = set(to_connect)
    # 尾巴③（W-NEXT-FEBE-SCAN-002）：plan 桶后端合法性校验
    plan_broken = plan_bucket_broken(be_routes)

    all_classified = (
        NEXTJS_PLANNED_ENDPOINTS
        | NEXTJS_DEFERRED_ENDPOINTS
        | NEXTJS_OPS_ENDPOINTS
        | NEXTJS_UNASSIGNED
    )
    uncategorized = sorted(tc_set - all_classified)

    out = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "edu-agent/scripts/eval/febe_contract_check.py --emit-migration-status",
        "task_id": "W-NEXT-FRONTEND-CONTRACT-001",
        "total_to_connect": len(to_connect),
        "buckets": {
            "plan": {
                "label": "Next.js 页面已实装/迁移进行中",
                "count": len(NEXTJS_PLANNED_ENDPOINTS & tc_set),
                "items": sorted(_method_path_list(NEXTJS_PLANNED_ENDPOINTS & tc_set)),
            },
            "deferred": {
                "label": "Next.js 暂未迁移该域（admin/MCP/交易）",
                "count": len(NEXTJS_DEFERRED_ENDPOINTS & tc_set),
                "items": sorted(_method_path_list(NEXTJS_DEFERRED_ENDPOINTS & tc_set)),
            },
            "ops": {
                "label": "运维端点·前端永不接入",
                "count": len(NEXTJS_OPS_ENDPOINTS & tc_set),
                "items": sorted(_method_path_list(NEXTJS_OPS_ENDPOINTS & tc_set)),
            },
            "unassigned": {
                "label": "无明确接入计划·待用户裁定",
                "count": len(NEXTJS_UNASSIGNED & tc_set),
                "items": sorted(_method_path_list(NEXTJS_UNASSIGNED & tc_set)),
            },
            "plan_broken": {
                "label": "plan 桶含后端不存在路由（非法 plan·警告；不在 to_connect 内，历史上被 ∩ 静默吞掉）",
                "count": len(plan_broken),
                "items": sorted(_method_path_list(plan_broken)),
            },
        },
        "uncategorized": {
            "label": "理论应为 0（未归入任何桶的待接）",
            "count": len(uncategorized),
            "items": [_method_path_str(m, p) for (m, p) in uncategorized],
        },
        "summary": {
            "classified": sum(
                len(b & tc_set)
                for b in (
                    NEXTJS_PLANNED_ENDPOINTS,
                    NEXTJS_DEFERRED_ENDPOINTS,
                    NEXTJS_OPS_ENDPOINTS,
                    NEXTJS_UNASSIGNED,
                )
            ),
            "uncategorized": len(uncategorized),
            "expected_total": len(to_connect),
            "plan_broken": len(plan_broken),
        },
    }

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(
        "已写入前端接入计划分类: %s (total=%d, plan=%d, deferred=%d, ops=%d, unassigned=%d, "
        "uncategorized=%d, plan_broken=%d)"
        % (
            path,
            out["total_to_connect"],
            out["buckets"]["plan"]["count"],
            out["buckets"]["deferred"]["count"],
            out["buckets"]["ops"]["count"],
            out["buckets"]["unassigned"]["count"],
            out["uncategorized"]["count"],
            out["buckets"]["plan_broken"]["count"],
        )
    )
    return 0


def _method_path_str(m, p):
    return "%s %s" % (m, p)


def _method_path_list(items):
    return [_method_path_str(m, p) for (m, p) in items]


def main(argv):
    args = argv[1:]
    if "--emit-frontend-list" in args:
        idx = args.index("--emit-frontend-list")
        path = args[idx + 1] if idx + 1 < len(args) else None
        return emit_frontend_list(path)
    if "--emit-migration-status" in args:
        idx = args.index("--emit-migration-status")
        path = args[idx + 1] if idx + 1 < len(args) else None
        return emit_migration_status(path)
    quiet = "--quiet" in args
    return run(quiet=quiet)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
