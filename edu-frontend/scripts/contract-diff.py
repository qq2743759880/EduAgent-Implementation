# -*- coding: utf-8 -*-
"""
task40 契约比对工具：前端 TS interface vs 后端 Pydantic schemas（字段集 diff）。

权威源（映射表驱动，后续任务冻结新域契约后追加条目即可）：
  1. 课程域（契约冻结②，task11 交接单）
     backend  = edu-agent/app/domains/course/schemas.py
     frontend = edu-frontend/src/lib/api/curriculum.ts
  2. 学习统计（progress 域已实证对齐的 2 类）
     backend  = edu-agent/app/progress/schemas.py
     frontend = edu-frontend/src/lib/api/dashboard.ts

范围说明：
  - learning.ts 的 CourseProgressOut/ModuleProgressOut 等为宽松防御形状，
    progress 域契约待 task14 冻结后接入（当前后端该域尚未冻结）。

用法：
  python scripts/contract-diff.py             # 汇总输出；零差异 exit 0，有差异 exit 1
  python scripts/contract-diff.py --verbose   # 逐类打印字段清单
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # edu-frontend/
BACKEND_ROOT = ROOT.parent / "edu-agent"

# (后端 schemas 相对路径, 后端类名, 前端 ts 相对路径, 前端接口名)
CONTRACT_MAP: list[tuple[str, str, str, str]] = [
    # ---- 课程域（契约冻结②）----
    ("app/domains/course/schemas.py", "PageMeta", "src/lib/api/curriculum.ts", "PageMeta"),
    ("app/domains/course/schemas.py", "SeriesListItem", "src/lib/api/curriculum.ts", "SeriesListItem"),
    ("app/domains/course/schemas.py", "SeriesListData", "src/lib/api/curriculum.ts", "SeriesListData"),
    ("app/domains/course/schemas.py", "CategoryBrief", "src/lib/api/curriculum.ts", "CategoryBrief"),
    ("app/domains/course/schemas.py", "SeriesDetail", "src/lib/api/curriculum.ts", "SeriesDetail"),
    ("app/domains/course/schemas.py", "Cohort", "src/lib/api/curriculum.ts", "Cohort"),
    ("app/domains/course/schemas.py", "Module", "src/lib/api/curriculum.ts", "Module"),
    ("app/domains/course/schemas.py", "SessionVideo", "src/lib/api/curriculum.ts", "SessionVideo"),
    ("app/domains/course/schemas.py", "Session", "src/lib/api/curriculum.ts", "Session"),
    ("app/domains/course/schemas.py", "ModuleWithSessions", "src/lib/api/curriculum.ts", "ModuleWithSessions"),
    ("app/domains/course/schemas.py", "CohortDetail", "src/lib/api/curriculum.ts", "CohortDetail"),
    ("app/domains/course/schemas.py", "CohortModulesData", "src/lib/api/curriculum.ts", "CohortModulesData"),
    # ---- 学习统计（progress 域实证形状）----
    ("app/progress/schemas.py", "DailyStatItem", "src/lib/api/dashboard.ts", "DailyStatItem"),
    ("app/progress/schemas.py", "DashboardOut", "src/lib/api/dashboard.ts", "DashboardOut"),
    # ---- 售后工单（契约⑫ task22）----
    ("app/domains/after_sales/schemas.py", "Ticket", "src/lib/api/tickets.ts", "Ticket"),
    ("app/domains/after_sales/schemas.py", "TicketPage", "src/lib/api/tickets.ts", "TicketPage"),
]


def parse_py_models(path: Path) -> dict[str, dict]:
    """解析 Pydantic BaseModel：字段名 + 基类（用于展平继承链）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    models: dict[str, dict] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = []
        for b in node.bases:
            name = getattr(b, "id", None) or getattr(b, "attr", None)
            if name and name != "BaseModel":
                bases.append(name)
        fields = set()
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                fields.add(stmt.target.id)
        models[node.name] = {"fields": fields, "bases": bases}
    return models


_TS_INTERFACE = re.compile(r"export\s+interface\s+(\w+)(?:\s+extends\s+([\w,\s]+))?\s*\{")
_TS_FIELD = re.compile(r"^([a-zA-Z_]\w*)\s*\??\s*:")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"^\s*//.*$", re.M)


def parse_ts_interfaces(path: Path) -> dict[str, dict]:
    """解析 TS interface：字段名 + extends（用于展平继承链）。"""
    text = path.read_text(encoding="utf-8")
    text = _BLOCK_COMMENT.sub("", text)
    text = _LINE_COMMENT.sub("", text)
    interfaces: dict[str, dict] = {}
    for m in _TS_INTERFACE.finditer(text):
        # 花括号配平截取 interface 体（内联对象字面量会计入 depth，不影响外层配平）
        depth = 0
        start = m.end() - 1
        body = ""
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    body = text[start + 1 : i]
                    break
        fields = set()
        for line in body.splitlines():
            line = line.strip()
            fm = _TS_FIELD.match(line)
            if fm:
                fields.add(fm.group(1))
        extends = [e.strip() for e in re.split(r"[,\s]+", m.group(2) or "") if e.strip()]
        interfaces[m.group(1)] = {"fields": fields, "bases": extends}
    return interfaces


def flatten(entry: dict, pool: dict[str, dict], seen: set[str] | None = None) -> set[str]:
    """沿继承链展平字段集（同文件内解析出的基类）。"""
    seen = seen or set()
    fields = set(entry["fields"])
    for base in entry["bases"]:
        if base in seen or base not in pool:
            continue
        seen.add(base)
        fields |= flatten(pool[base], pool, seen)
    return fields


def main() -> int:
    verbose = "--verbose" in sys.argv
    py_cache: dict[str, dict[str, dict]] = {}
    ts_cache: dict[str, dict[str, dict]] = {}
    total_diff = 0

    for be_rel, be_cls, fe_rel, fe_iface in CONTRACT_MAP:
        be_path = BACKEND_ROOT / be_rel
        fe_path = ROOT / fe_rel
        if be_rel not in py_cache:
            py_cache[be_rel] = parse_py_models(be_path)
        if fe_rel not in ts_cache:
            ts_cache[fe_rel] = parse_ts_interfaces(fe_path)

        be_model = py_cache[be_rel].get(be_cls)
        fe_model = ts_cache[fe_rel].get(fe_iface)
        if be_model is None:
            print(f"[MISSING-BACKEND] {be_rel}::{be_cls} 不存在")
            total_diff += 1
            continue
        if fe_model is None:
            print(f"[MISSING-FRONTEND] {fe_rel}::{fe_iface} 不存在")
            total_diff += 1
            continue

        be_fields = flatten(be_model, py_cache[be_rel])
        fe_fields = flatten(fe_model, ts_cache[fe_rel])
        missing = sorted(be_fields - fe_fields)   # 后端有、前端缺
        extra = sorted(fe_fields - be_fields)     # 前端有、后端无

        if verbose:
            print(f"\n== {be_cls} <-> {fe_iface}（{len(be_fields)} 字段）==")
            for f in sorted(be_fields):
                print(f"  {f}")

        if missing or extra:
            total_diff += 1
            print(f"[DIFF] {fe_rel}::{fe_iface} vs {be_rel}::{be_cls}")
            if missing:
                print(f"  前端缺失（后端有）: {', '.join(missing)}")
            if extra:
                print(f"  前端多余（后端无）: {', '.join(extra)}")
        else:
            print(f"[OK] {fe_rel}::{fe_iface} <-> {be_rel}::{be_cls}（{len(be_fields)} 字段零差异）")

    print(f"\n比对完成：{len(CONTRACT_MAP)} 对契约，{'零差异' if total_diff == 0 else f'{total_diff} 对存在差异'}")
    return 0 if total_diff == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
