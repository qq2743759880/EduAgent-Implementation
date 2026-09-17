"""W-NEXT-INT-001A ⑭ 健康门探针 —— 内部可见性 student 0 / admin >0。

走真实 HTTP（login 双角色 + /api/chat/search），调 5 个内部关键词，
末行输出 [WINT1A] {env_blocked?, student_hits_total, admin_hits_total, student_hits_zero}。

环境阻塞（后端/DB 不可达）→ env_blocked=true，check-demo ⑭ 走 WARN 不阻断；
真正失败 → env_blocked=false，对应字段供 ⑭ 阻断判据消费。

用法：
  python wnextint1a_visibility_probe.py --base http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# W-NEXT-CHECKDEMO-004 修:.env 加载兜底 ——
# 现象:check-demo.mjs ⑭ 守卫 spawn 子进程时 cwd=仓库根,不是 edu-agent/。
#       本探针已有 os.chdir(REPO) 兜后,但 REPO 仍基于脚本路径而非 cwd,先 chdir 再 load_dotenv
#       也行;为对齐 W-NEXT-CHECKDEMO-003 (⑲) 同型根因,在 sys.path 之前显式 load_dotenv,
#       防「chdir 之前 requests 触发底层包 import settings 的隐式 load」陷阱。
#       pydantic-settings env_file='.env' 是 cwd-相对,cwd=仓库根时找不到 edu-agent/.env。
#       本探针不显式 import app.config,但 requests 间接依赖缺失变量(SSL/TLS 探测链路)。
# 修复:入口处显式 load_dotenv(EDU_ROOT/.env)。不依赖 cwd,不依赖父进程的 env 注入。
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
_ENV_PATH = os.path.join(REPO, ".env")
if os.path.isfile(_ENV_PATH):
    from dotenv import load_dotenv  # noqa: E402
    load_dotenv(_ENV_PATH, override=False)  # 已有环境变量优先,避免覆盖 CI 注入
else:
    print(f"[wnextint1a_visibility_probe] WARN .env not found at {_ENV_PATH} — pydantic Field required 风险", file=sys.stderr)

sys.path.insert(0, REPO)
os.chdir(REPO)

import requests

# Mimosa：host 写死本地
LOCAL_HOST = "127.0.0.1"
DEFAULT_BASE = "http://127.0.0.1:8000"

INTERNAL_QUERIES = [
    "restore_admin 强制技术批判",
    "kickoff W-NEXT-INT",
    "task09 WNEXT10 F5-a",
    "sys_user_auth 用户表结构",
    "编排者 验收 GWT",
]

# 固定测试账号（DB 种子）
ADMIN = {"account": "adm02test", "password": "Test@123456"}
STUDENT = {"account": "user000001", "password": "Test@123456"}


def login(base: str, who: dict, timeout: int = 10) -> str | None:
    try:
        r = requests.post(f"{base}/api/auth/login", json=who, timeout=timeout)
        if r.status_code != 200:
            return None
        data = r.json().get("data") or {}
        return data.get("access_token")
    except Exception:
        return None


def search(base: str, token: str, q: str, timeout: int = 30) -> list[dict]:
    try:
        r = requests.post(
            f"{base}/api/chat/search",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "query": q,
                "top_k": 10,
                "use_hyde": False,
                "enable_graph": False,
                "use_mcp_tools": False,
                "format_docs": False,
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return []
        data = r.json().get("data") or {}
        return data.get("docs") or []
    except Exception:
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    args = ap.parse_args()

    base = args.base
    # Mimosa host 校验
    if LOCAL_HOST not in base:
        print(json.dumps({
            "env_blocked": True,
            "detail": f"非本地 host（{base}），Mimosa 要求 127.0.0.1",
        }, ensure_ascii=False))

    # 双角色 login
    stu_tok = login(base, STUDENT)
    adm_tok = login(base, ADMIN)
    if not stu_tok or not adm_tok:
        print(json.dumps({
            "env_blocked": True,
            "detail": f"login 失败：stu={bool(stu_tok)} adm={bool(adm_tok)}（后端不可达或 DB 无种子）",
        }, ensure_ascii=False))
        return

    student_total = 0
    admin_total = 0
    student_zero_all = True
    admin_pos_some = False
    per_query = []

    for q in INTERNAL_QUERIES:
        s_docs = search(base, stu_tok, q)
        a_docs = search(base, adm_tok, q)
        # 仅统计 doc_chunk + hex 临时名（真内部特征）
        s_dc = [d for d in s_docs if d.get("content_type") == "doc_chunk"]
        a_dc = [d for d in a_docs if d.get("content_type") == "doc_chunk"]
        s_hits = len(s_dc)
        a_hits = len(a_dc)
        student_total += s_hits
        admin_total += a_hits
        if s_hits > 0:
            student_zero_all = False
        if a_hits > 0:
            admin_pos_some = True
        per_query.append({"q": q, "student_doc_chunk": s_hits, "admin_doc_chunk": a_hits})

        # 轻节流防限流（5 query 60s 上限够用，但稳妥起见间隔 1s）
        time.sleep(1.0)

    out = {
        "env_blocked": False,
        "student_hits_total": student_total,
        "admin_hits_total": admin_total,
        "student_hits_zero": student_zero_all,
        "admin_has_hits": admin_pos_some,
        "queries": len(INTERNAL_QUERIES),
        "per_query": per_query,
    }
    print(f"[WINT1A] {json.dumps(out, ensure_ascii=False)}")


if __name__ == "__main__":
    main()