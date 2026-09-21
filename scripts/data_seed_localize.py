#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DATA-SEED-1 种子外链占位本地化（DB 变更三核闸：备份 / 行数一致 / 幂等）

背景：种子数据把封面与头像指向不可达的占位域 ``https://cdn.example.com``，前端 <img>
渲染裂图、门禁 G8(zero-external-requests)/G6/G7(console-errors) 据此红。本脚本是**数据订正**
（非业务写），只重写下列列，不新增/删除任何业务行：

  series.cover_url          https://cdn.example.com/course/<slug>.jpg    -> /assets/seed/covers/<slug>.svg
  sys_user.avatar_url       https://cdn.example.com/avatar/<digits>.png  -> /assets/seed/avatar-default.svg
  user_profile.avatar_url   https://cdn.example.com/avatars/x.png        -> /assets/seed/avatar-default.svg

三核闸与 mode 对应：
  闸① 备份  --mode backup   受影响行落 deploy/backups/seed-<date>/（mysqldump + TSV 双份），行数留档
  闸② 变更  --mode apply    仅命中占位域的行，WHERE 精确谓词；变更后行数与备份断言一致
  闸③ 幂等  --mode apply 重跑零变化（WHERE 谓词已带本地路径，不匹配）；--mode verify 断言残留=0

用法（须用 edu-agent/.venv 的 python 运行）：
  python scripts/data_seed_localize.py --mode inventory
  python scripts/data_seed_localize.py --mode assets
  python scripts/data_seed_localize.py --mode backup
  python scripts/data_seed_localize.py --mode apply
  python scripts/data_seed_localize.py --mode verify

环境：MYSQL_HOST 默认 127.0.0.1（.env 里的 localhost 会解析到 ::1）。
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / "edu-agent" / ".env"
PUBLIC_DIR = REPO_ROOT / "edu-frontend" / "public"
SEED_DIR = PUBLIC_DIR / "assets" / "seed"
COVERS_DIR = SEED_DIR / "covers"
BACKUP_ROOT = REPO_ROOT / "deploy" / "backups"

PLACEHOLDER_HOST = "cdn.example.com"
COVER_FROM_PREFIX = f"https://{PLACEHOLDER_HOST}/course/"
COVER_DEST_PREFIX = "/assets/seed/covers/"
AVATAR_DEFAULT = "/assets/seed/avatar-default.svg"

# theme.css 表面色令牌（edu-frontend/public/theme.css :root）——占位图只用令牌色系
PALETTE = [
    ("moss", "#B8D8A8", "#8FBF7B"),
    ("sky", "#9EC9F0", "#6FA9DC"),
    ("peach", "#FFB59E", "#F58F72"),
    ("mint", "#7DD4A8", "#4FB884"),
    ("lemon", "#F5D77A", "#E0BC3F"),
    ("lavender", "#B8A6FF", "#9480E8"),
]
INK = "#2E2A3F"          # --text-strong
MUTED = "#6B6580"        # --text-muted
SURFACE = "#F7F5FB"      # --bg-app
FONT_STACK = '"Microsoft YaHei","PingFang SC","Segoe UI",sans-serif'

TIER_SUFFIX = re.compile(r"[·・](直播|录播|面授|在线|线下)$")


# --------------------------------------------------------------------------- db

def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env[key.strip()] = val.strip()
    return env


def connect():
    import pymysql  # noqa: PLC0415 — 延迟导入，使 --mode assets 无需 DB 驱动

    env = load_env()
    host = os.environ.get("MYSQL_HOST") or env.get("MYSQL_HOST") or "127.0.0.1"
    if host in ("localhost", ""):
        host = "127.0.0.1"
    return pymysql.connect(
        host=host,
        port=int(os.environ.get("MYSQL_PORT") or env.get("MYSQL_PORT") or 3306),
        user=os.environ.get("MYSQL_USER") or env.get("MYSQL_USER") or "root",
        password=os.environ.get("MYSQL_PASSWORD") or env.get("MYSQL_PASSWORD") or "",
        database=os.environ.get("MYSQL_DATABASE") or env.get("MYSQL_DATABASE") or "edu",
        charset="utf8mb4",
        autocommit=False,
    )


def q(cur, sql: str, args=None):
    # 注意：pymysql 会对 query 做 % 插值，LIKE '%x%' 里的 % 在无参调用时必须避开插值
    if args is None:
        cur.execute(sql)
    else:
        cur.execute(sql, args)
    return cur.fetchall()


# ---------------------------------------------------------------- 受影响目标定义

TARGETS = [
    {
        "key": "series_cover_url",
        "table": "series",
        "column": "cover_url",
        "predicate": "`cover_url` LIKE 'https://cdn.example.com/course/%'",
        "after_predicate": "`cover_url` LIKE '/assets/seed/covers/%'",
        "select": "SELECT id, cover_url FROM series WHERE cover_url LIKE 'https://cdn.example.com/course/%' ORDER BY id",
        "select_after": "SELECT id, cover_url FROM series WHERE cover_url LIKE '/assets/seed/covers/%' ORDER BY id",
    },
    {
        "key": "sys_user_avatar_url",
        "table": "sys_user",
        "column": "avatar_url",
        "predicate": "`avatar_url` LIKE 'https://cdn.example.com/%'",
        "after_predicate": "`avatar_url` = '/assets/seed/avatar-default.svg'",
        "select": "SELECT id, avatar_url FROM sys_user WHERE avatar_url LIKE 'https://cdn.example.com/%' ORDER BY id",
        "select_after": "SELECT id, avatar_url FROM sys_user WHERE avatar_url = '/assets/seed/avatar-default.svg' ORDER BY id",
    },
    {
        "key": "user_profile_avatar_url",
        "table": "user_profile",
        "column": "avatar_url",
        "predicate": "`avatar_url` LIKE 'https://cdn.example.com/%'",
        "after_predicate": "`avatar_url` = '/assets/seed/avatar-default.svg'",
        "select": "SELECT id, avatar_url FROM user_profile WHERE avatar_url LIKE 'https://cdn.example.com/%' ORDER BY id",
        "select_after": "SELECT id, avatar_url FROM user_profile WHERE avatar_url = '/assets/seed/avatar-default.svg' ORDER BY id",
    },
]


def local_cover_path(slug: str) -> str:
    return f"{COVER_DEST_PREFIX}{slug}.svg"


def slug_of_cover_url(url: str) -> str:
    return url[len(COVER_FROM_PREFIX):].rsplit(".", 1)[0]


def rewrite_value(table: str, value: str) -> str:
    """把占位域值映射为本地路径（纯函数，模式与 SQL 侧改写逐字一致）。"""
    if table == "series":
        return local_cover_path(slug_of_cover_url(value))
    return AVATAR_DEFAULT


def base_course_name(name: str) -> str:
    return TIER_SUFFIX.sub("", name or "").strip() or "课程"


def palette_for(slug: str):
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()
    return PALETTE[int(digest[:8], 16) % len(PALETTE)]


# ------------------------------------------------------------------ mode: inventory

def mode_inventory() -> int:
    conn = connect()
    try:
        with conn.cursor() as cur:
            print("=== DATA-SEED-1 只读盘点（占位域 %s）===" % PLACEHOLDER_HOST)
            total = 0
            for tgt in TARGETS:
                rows = q(cur, tgt["select"])
                distinct = len({r[1] for r in rows})
                total += len(rows)
                print(
                    f"  {tgt['table']}.{tgt['column']:<11} 受影响行={len(rows):>7}  distinct值={distinct:>7}"
                )
                if rows and tgt["table"] != "sys_user":
                    for rid, val in rows[:5]:
                        print(f"      id={rid} -> {val}")
            print(f"  ---- 合计受影响行 = {total}")
            print("  （对照：开工令预估 5+1=6 —— 差异见 REPORT-DATA-SEED-1.md §差异说明）")
    finally:
        conn.close()
    return 0


# --------------------------------------------------------------------- mode: assets

def render_cover_svg(label: str, tier: str, c1: str, c2: str, name_en: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450" role="img" aria-label="{html.escape(label)}">
  <title>{html.escape(label)}</title>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{c1}"/>
      <stop offset="1" stop-color="{c2}"/>
    </linearGradient>
  </defs>
  <rect width="800" height="450" fill="url(#bg)"/>
  <circle cx="706" cy="74" r="132" fill="{SURFACE}" opacity="0.26"/>
  <circle cx="86" cy="404" r="96" fill="{SURFACE}" opacity="0.18"/>
  <circle cx="628" cy="352" r="58" fill="{INK}" opacity="0.07"/>
  <rect x="56" y="56" width="118" height="40" rx="20" fill="{INK}" opacity="0.86"/>
  <text x="115" y="83" text-anchor="middle" font-family='{FONT_STACK}' font-size="19" font-weight="700" fill="{SURFACE}">{html.escape(tier)}</text>
  <text x="56" y="234" font-family='{FONT_STACK}' font-size="52" font-weight="800" fill="{INK}">{html.escape(label)}</text>
  <text x="58" y="288" font-family='{FONT_STACK}' font-size="21" font-weight="600" fill="{MUTED}">{html.escape(name_en)}</text>
  <rect x="56" y="330" width="330" height="6" rx="3" fill="{INK}" opacity="0.34"/>
  <text x="56" y="386" font-family='{FONT_STACK}' font-size="18" font-weight="600" fill="{MUTED}">本地占位封面 · EduAgent 演示种子</text>
</svg>
"""


def render_avatar_svg() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200" role="img" aria-label="默认头像">
  <title>默认头像</title>
  <defs>
    <linearGradient id="abg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{PALETTE[0][1]}"/>
      <stop offset="1" stop-color="{PALETTE[5][1]}"/>
    </linearGradient>
  </defs>
  <rect width="200" height="200" fill="url(#abg)"/>
  <circle cx="164" cy="40" r="52" fill="{SURFACE}" opacity="0.24"/>
  <circle cx="100" cy="78" r="34" fill="{INK}" opacity="0.82"/>
  <path d="M100 124c-31 0-56 17-56 39v37h112v-37c0-22-25-39-56-39z" fill="{INK}" opacity="0.82"/>
</svg>
"""


def mode_assets() -> int:
    conn = connect()
    try:
        with conn.cursor() as cur:
            rows = q(
                cur,
                "SELECT SUBSTRING_INDEX(SUBSTRING_INDEX(cover_url,'/',-1),'.',1) AS slug, "
                "MIN(series_name) AS nm, COUNT(*) AS n "
                "FROM series WHERE cover_url LIKE 'https://cdn.example.com/course/%' "
                "GROUP BY slug ORDER BY slug",
            )
    finally:
        conn.close()

    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "DATA-SEED-1 种子外链占位本地化",
        "cover_dir": "/assets/seed/covers/",
        "avatar_default": AVATAR_DEFAULT,
        "covers": [],
    }
    for slug, name, n in rows:
        label = base_course_name(name)
        tier = ("基础" if slug.endswith("_foundation") else
                "实战" if slug.endswith("_practice") else
                "进阶" if slug.endswith("_advanced") else "课程")
        pname, c1, c2 = palette_for(slug)
        svg = render_cover_svg(label, tier, c1, c2, slug.replace("_", " "))
        (COVERS_DIR / f"{slug}.svg").write_text(svg, encoding="utf-8")
        manifest["covers"].append(
            {"slug": slug, "file": local_cover_path(slug), "label": label,
             "palette": pname, "series_rows": int(n)}
        )

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    (SEED_DIR / "avatar-default.svg").write_text(render_avatar_svg(), encoding="utf-8")
    (SEED_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[assets] covers={len(manifest['covers'])} -> {COVERS_DIR}")
    print(f"[assets] avatar -> {SEED_DIR / 'avatar-default.svg'}")
    print(f"[assets] manifest -> {SEED_DIR / 'manifest.json'}")
    return 0


# --------------------------------------------------------------------- mode: backup

def _mysqldump(table: str, where: str, out: Path) -> None:
    env = load_env()
    real_env = dict(os.environ)
    real_env["MYSQL_PWD"] = os.environ.get("MYSQL_PASSWORD") or env.get("MYSQL_PASSWORD") or ""
    host = os.environ.get("MYSQL_HOST") or env.get("MYSQL_HOST") or "127.0.0.1"
    if host in ("localhost", ""):
        host = "127.0.0.1"
    exe = os.environ.get("MYSQLDUMP_BIN") or r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"
    cmd = [
        exe, "-h", host,
        "-P", str(os.environ.get("MYSQL_PORT") or env.get("MYSQL_PORT") or 3306),
        "-u", os.environ.get("MYSQL_USER") or env.get("MYSQL_USER") or "root",
        "--default-character-set=utf8mb4", "--no-create-info", "--skip-add-locks",
        "--complete-insert", "--where", where, "--skip-comments",
        os.environ.get("MYSQL_DATABASE") or env.get("MYSQL_DATABASE") or "edu", table,
    ]
    with out.open("wb") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.PIPE, env=real_env)
    if proc.returncode != 0:
        raise RuntimeError(f"mysqldump {table} failed: {proc.stderr.decode('utf-8', 'replace')[:400]}")


def mode_backup(backup_dir: Path) -> int:
    backup_dir.mkdir(parents=True, exist_ok=True)
    conn = connect()
    counts = {}
    try:
        with conn.cursor() as cur:
            for tgt in TARGETS:
                rows = q(cur, tgt["select"])
                before_local = len(q(cur, tgt["select_after"]))
                table_total = q(cur, f"SELECT COUNT(*) FROM {tgt['table']}")[0][0]
                counts[tgt["key"]] = {
                    "table": tgt["table"], "column": tgt["column"],
                    "predicate": tgt["predicate"], "rows": len(rows),
                    "local_rows_before": before_local, "table_total": table_total,
                }
                tsv = backup_dir / f"{tgt['key']}.before.tsv"
                with tsv.open("w", encoding="utf-8", newline="\n") as fh:
                    fh.write(f"# {tgt['table']}.{tgt['column']} — 变更前快照\n")
                    fh.write("# id\told_value\n")
                    for rid, val in rows:
                        fh.write(f"{rid}\t{'' if val is None else val}\n")
                _mysqldump(tgt["table"], tgt["predicate"], backup_dir / f"{tgt['key']}.before.sql")
                print(f"[backup] {tgt['table']}.{tgt['column']}: rows={len(rows)} "
                      f"table_total={table_total} -> {tsv.name} + {tgt['key']}.before.sql")
    finally:
        conn.close()

    (backup_dir / "_counts.json").write_text(
        json.dumps(
            {"backed_up_at": datetime.now().isoformat(timespec="seconds"),
             "placeholder_host": PLACEHOLDER_HOST, "targets": counts},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[backup] counts -> {backup_dir / '_counts.json'}")
    return 0


# ---------------------------------------------------------------------- mode: apply

APPLY_SQL = {
    "series_cover_url": (
        "UPDATE series SET cover_url = CONCAT('/assets/seed/covers/', "
        "SUBSTRING_INDEX(SUBSTRING_INDEX(cover_url,'/',-1),'.',1), '.svg') "
        "WHERE cover_url LIKE 'https://cdn.example.com/course/%'"
    ),
    "sys_user_avatar_url": (
        "UPDATE sys_user SET avatar_url = '/assets/seed/avatar-default.svg' "
        "WHERE avatar_url LIKE 'https://cdn.example.com/%'"
    ),
    "user_profile_avatar_url": (
        "UPDATE user_profile SET avatar_url = '/assets/seed/avatar-default.svg' "
        "WHERE avatar_url LIKE 'https://cdn.example.com/%'"
    ),
}


def mode_apply(backup_dir: Path) -> int:
    counts_file = backup_dir / "_counts.json"
    if not counts_file.exists():
        print(f"[apply] 拒绝执行：未找到闸① 备份 {counts_file}（先跑 --mode backup）", file=sys.stderr)
        return 2
    before = json.loads(counts_file.read_text(encoding="utf-8"))["targets"]

    conn = connect()
    changed, result = {}, {}
    try:
        with conn.cursor() as cur:
            for tgt in TARGETS:
                key = tgt["key"]
                exp_rows = before[key]["rows"]                 # 备份时占位域行数
                exp_local = before[key]["local_rows_before"]   # 备份时本地路径行数
                exp_total = before[key]["table_total"]

                cur.execute(APPLY_SQL[key])
                changed[key] = cur.rowcount

                residual = len(q(cur, tgt["select"]))                       # 占位域残留
                local_now = len(q(cur, tgt["select_after"]))                # 本地路径行数
                total_now = q(cur, f"SELECT COUNT(*) FROM {tgt['table']}")[0][0]
                result[key] = dict(changed=changed[key], residual=residual,
                                   local_now=local_now, local_expected=exp_local + exp_rows,
                                   total_now=total_now, total_expected=exp_total)

                # 闸②：行不增不减（表总行数一致）+ 占位域清零 + 本地路径行数 = 备份本地 + 备份占位域
                assert residual == 0, f"{key}: 变更后仍残留 {residual} 行占位域值"
                assert local_now == exp_local + exp_rows, (
                    f"{key}: 本地路径行数 {local_now} != 期望 {exp_local + exp_rows}")
                assert total_now == exp_total, (
                    f"{key}: 表总行数 {total_now} != 备份 {exp_total}（禁止增删行）")
                # 首跑改写行数 == 备份行数；重跑（幂等）改写行数 == 0
                assert changed[key] in (0, exp_rows), (
                    f"{key}: 本次改写 {changed[key]} 既非 0（已幂等）也非备份行数 {exp_rows}")
                print(f"[apply] {tgt['table']}.{tgt['column']}: 本次改写={changed[key]:>7} "
                      f"备份占位域行数={exp_rows:>7} 残留={residual} "
                      f"本地路径行数={local_now}(期望 {exp_local + exp_rows}) "
                      f"表总行数={total_now}(期望 {exp_total})")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("[apply] 闸② 通过：占位域残留=0；本地路径行数 == 备份(本地+占位域)；表总行数一致（未增删行）")
    first_run = all(result[k]["changed"] == before[k]["rows"] for k in result)
    print("[apply] 本次运行性质：" + ("首跑（改写 %d 行）" % sum(changed.values()) if first_run
                                     else "幂等重跑（改写 0 行，零变化）"))
    return 0


def mode_verify() -> int:
    conn = connect()
    ok = True
    try:
        with conn.cursor() as cur:
            for tgt in TARGETS:
                left = q(cur, tgt["select"])
                n_left = len(left)
                ok &= n_left == 0
                print(f"[verify] {tgt['table']}.{tgt['column']}: 残留占位域行 = {n_left}")
            # 本地路径可达性：DB 里出现的 /assets/seed/* 必须都有对应文件
            covers = [r[0] for r in q(
                cur, "SELECT DISTINCT cover_url FROM series WHERE cover_url LIKE '/assets/seed/covers/%'")]
            avatars = [r[0] for r in q(
                cur, "SELECT DISTINCT avatar_url FROM sys_user WHERE avatar_url LIKE '/assets/seed/%'")]
            missing = []
            for url in covers:
                if not (PUBLIC_DIR / url.lstrip("/")).exists():
                    missing.append(url)
            for url in avatars:
                if not (PUBLIC_DIR / url.lstrip("/")).exists():
                    missing.append(url)
            print(f"[verify] DB 引用本地封面 {len(covers)} 个 / 本地头像 {len(avatars)} 个；缺失文件 {len(missing)}")
            for m in missing[:10]:
                print(f"         MISSING {m}")
            ok &= not missing
    finally:
        conn.close()
    print("[verify] " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ---------------------------------------------------------------------- mode: probe

def mode_probe() -> int:
    """前端复验：真 token 打 /api/favorites 与 /api/users/me/profile，断言返回本地路径且资源可达。"""
    import urllib.request  # noqa: PLC0415

    api = os.environ.get("DSL_API_BASE", "http://127.0.0.1:9988").rstrip("/")
    fe = os.environ.get("DSL_FE_BASE", "http://127.0.0.1:3322").rstrip("/")
    account = os.environ.get("DSL_ACCOUNT", "user000001")
    password = os.environ.get("DSL_PASSWORD", "Test@123456")
    # 环境 http_proxy 会把 loopback 请求吞成 502 —— 必须显式绕过代理
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(url, body=None, token=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with opener.open(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def head_status(url):
        req = urllib.request.Request(url, method="GET")
        try:
            with opener.open(req, timeout=20) as resp:
                return resp.status, resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            return exc.code, ""

    ok = True
    login = call(f"{api}/api/auth/login", {"account": account, "password": password})
    token = (login.get("data") or {}).get("access_token")
    print(f"[probe] login {account}: code={login.get('code')} token={'yes' if token else 'NO'}")
    if not token:
        return 1

    favs = call(f"{api}/api/favorites?page=1&page_size=20", token=token)
    items = (favs.get("data") or {}).get("items") or []
    print(f"[probe] GET /api/favorites → total={(favs.get('data') or {}).get('total')} items={len(items)}")
    for it in items:
        url = it.get("cover_url")
        local = bool(url) and url.startswith("/assets/seed/")
        st, ctype = head_status(f"{fe}{url}") if local else (None, "")
        ok &= local and st == 200
        print(f"    series_id={it.get('series_id'):<6} cover_url={url} local={local} HTTP={st} {ctype}")

    prof = call(f"{api}/api/users/me/profile", token=token)
    pdata = prof.get("data") or {}
    av = pdata.get("avatar_url")
    local = bool(av) and av.startswith("/assets/seed/")
    st, ctype = head_status(f"{fe}{av}") if local else (None, "")
    ok &= local and st == 200
    print(f"[probe] GET /api/users/me/profile → avatar_url={av} local={local} HTTP={st} {ctype}")

    me = call(f"{api}/api/users/me", token=token)
    av2 = (me.get("data") or {}).get("avatar_url")
    local2 = bool(av2) and av2.startswith("/assets/seed/")
    ok &= local2
    print(f"[probe] GET /api/users/me → avatar_url={av2} local={local2}")

    print("[probe] " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


# ------------------------------------------------------------------------------ cli

def main() -> int:
    ap = argparse.ArgumentParser(description="DATA-SEED-1 种子外链占位本地化（三核闸）")
    ap.add_argument("--mode", required=True,
                    choices=["inventory", "assets", "backup", "apply", "verify", "probe"])
    ap.add_argument("--backup-dir", default=str(BACKUP_ROOT / f"seed-{datetime.now():%Y%m%d}"))
    args = ap.parse_args()
    backup_dir = Path(args.backup_dir)

    if args.mode == "inventory":
        return mode_inventory()
    if args.mode == "assets":
        return mode_assets()
    if args.mode == "backup":
        return mode_backup(backup_dir)
    if args.mode == "apply":
        return mode_apply(backup_dir)
    if args.mode == "verify":
        return mode_verify()
    if args.mode == "probe":
        return mode_probe()
    return 2


if __name__ == "__main__":
    sys.exit(main())
