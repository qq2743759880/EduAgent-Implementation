# -*- coding: utf-8 -*-
"""H2b（P1-7/P2-14 热修）：演示库残留清理脚本。

目标（全部先 SELECT 核实特征签名，签名不符即 SKIP，绝不盲删）：
  ① task08 帖 post 97（title 前缀 'task08'）+ 其 15 条评论 + 连带 community_react；
     帖 88/89/90（title 前缀 'task118'，锁定测试帖）同样连带评论与反应。
  ② 订单 6-260906172441-86dcaa（order_status='pending'）+ order_item 关联 +
     券领取记录 coupon_receive_record 51122（task16 领取残留，unused）及
     订单关联领取记录（order.coupon_receive_record_id 指向的行）。
     红线：coupon 主表 1/2 等种子行一律不动（receive_count/used_count 聚合列为
     种子口径，保持原样，仅登记 cosmetic 说明）。
  ③ 软删测试系列级联：series_code 前缀 rst17886141 / jsnn17886141 / jsn17886141 /
     t13w1（P2-14 清单）+ h1c（H1c 契约测试登记的清理范畴，唯一前缀可枚举），
     且必须 sale_status='off_sale'（回收站态）才删；级联删其班次
     （order_item/consultation/review/attendance/cart/student_rel/compensation/
     category_rel/coupon_series_rel/favorite/visit/exposure/search 引用面先核验为 0）。
  ④ 视频 VID-20260912-2916ECA4（task06 3MB 真链路测试视频）：session_video 行 +
     session_asset 行 + DATA_DIR/media 下媒体文件。
  ⑤ 红线：不动 user000001 的 sys_user/student_profile 资料；不动非测试前缀真实系列。

用法（默认 dry-run，只打印清单不动数据）：
  .venv/Scripts/python.exe scripts/cleanup_demo_residues.py            # dry-run
  .venv/Scripts/python.exe scripts/cleanup_demo_residues.py --execute  # 真执行

连接参数读 edu-agent/.env（MYSQL_HOST/PORT/USER/PASSWORD/DATABASE）。
执行后复跑 dry-run 应全 0（幂等）。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pymysql

BASE_DIR = Path(__file__).resolve().parent.parent  # edu-agent/
ENV_PATH = BASE_DIR / ".env"
DATA_DIR = BASE_DIR / "data"

TEST_POST_IDS = (88, 89, 90, 97)
TEST_POST_TITLE_PREFIX = ("task08", "task118")  # 特征签名：title 必须以此开头
ORDER_NO = "6-260906172441-86dcaa"
COUPON_RECEIVE_RECORD_ID = 51122
VIDEO_CODE = "VID-20260912-2916ECA4"
SERIES_CODE_PREFIXES = ("rst17886141", "jsnn17886141", "jsn17886141", "t13w1", "h1c")

# 测试班次引用面（级联前必须全 0 才允许删班次/系列）
COHORT_REF_TABLES = [
    "order_item", "consultation_record", "cohort_review", "risk_alert_event",
    "session_attendance", "shopping_cart_item", "student_cohort_rel",
    "teacher_compensation_item",
]
SERIES_REF_TABLES = [
    "series_category_rel", "coupon_series_rel", "series_favorite",
    "series_visit_log", "series_exposure_log",
]


def load_env() -> dict:
    env = dict(os.environ)
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    return env


def connect(env: dict):
    return pymysql.connect(
        host=env.get("MYSQL_HOST", "localhost"),
        port=int(env.get("MYSQL_PORT", "3306")),
        user=env.get("MYSQL_USER", "root"),
        password=env.get("MYSQL_PASSWORD", ""),
        database=env.get("MYSQL_DATABASE", "edu"),
        charset=env.get("MYSQL_CHARSET", "utf8mb4"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


class Plan:
    """收集 (步骤名, 说明, SQL, 参数, 预期签名核验函数) 的执行计划。"""

    def __init__(self):
        self.steps: list[dict] = []

    def add(self, group: str, desc: str, sql: str, args: tuple, verify_fn=None):
        self.steps.append({"group": group, "desc": desc, "sql": sql,
                           "args": args, "verify": verify_fn, "ids": [], "skips": []})


# 同类 epoch 测试系列家族前缀（仅 --extend-test-family 时纳入，且必须过名称签名）
EXTENDED_FAMILY_PREFIXES = ("rst17", "jsn17", "jsnn17", "jsnu17")
import re as _re
_TEST_NAME_SIG = _re.compile(r"测试|JSON|C5|H1c")


def _series_like_sql(extended: bool = False) -> str:
    """series_code 前缀 OR 链（每项都带完整 'series_code LIKE'，防裸占位符退化）。"""
    prefixes = list(SERIES_CODE_PREFIXES) + (list(EXTENDED_FAMILY_PREFIXES) if extended else [])
    return " OR ".join(["series_code LIKE %s"] * len(prefixes))


def _series_args(extended: bool = False) -> tuple:
    prefixes = list(SERIES_CODE_PREFIXES) + (list(EXTENDED_FAMILY_PREFIXES) if extended else [])
    return tuple(p + "%" for p in prefixes)


def build_plan(cur, plan: Plan, extended: bool = False) -> None:
    # ── ① 测试帖连带评论/反应（签名：title 前缀 task08/task118） ──
    cur.execute(
        "SELECT id, title FROM community_post WHERE id IN %s",
        (TEST_POST_IDS,),
    )
    ok_posts = []
    for r in cur.fetchall():
        if any(str(r["title"]).startswith(p) for p in TEST_POST_TITLE_PREFIX):
            ok_posts.append(int(r["id"]))
            plan.add("①测试帖", f"community_post id={r['id']} title={r['title']!r}",
                     "DELETE FROM community_post WHERE id=%s AND title LIKE %s",
                     (r["id"], str(r["title"])[:20] + "%"))
        else:
            plan.steps.append({"group": "①测试帖", "desc": f"post {r['id']} 签名不符（title={r['title']!r}）→ SKIP",
                               "sql": None, "args": None, "verify": None, "ids": [], "skips": [r["id"]]})
    if ok_posts:
        fmt = ",".join(["%s"] * len(ok_posts))
        # 顺序关键：community_react 的 COMMENT 目标子查询依赖 community_comment 行，
        # 必须先删 react（POST/COMMENT 两路）→ 再删评论 → 帖子行删除挪到计划尾部最后执行。
        plan.add("①测试帖", f"community_react（POST 目标 {ok_posts}）",
                 f"DELETE FROM community_react WHERE target_type='POST' AND target_id IN ({fmt})",
                 tuple(ok_posts))
        plan.add("①测试帖", f"community_react（COMMENT 目标 of {ok_posts}，先于评论删除）",
                 f"DELETE FROM community_react WHERE target_type='COMMENT' AND target_id IN "
                 f"(SELECT id FROM (SELECT id FROM community_comment WHERE post_id IN ({fmt})) t)",
                 tuple(ok_posts))
        plan.add("①测试帖", f"community_comment（post_id in {ok_posts}）",
                 f"DELETE FROM community_comment WHERE post_id IN ({fmt})", tuple(ok_posts))
        # 帖子行删除移到计划尾部（react/评论清完后执行）
        post_steps = [x for x in plan.steps
                      if x["group"] == "①测试帖" and x["sql"] and x["sql"].startswith("DELETE FROM community_post")]
        for s in post_steps:
            plan.steps.remove(s)
            plan.steps.append(s)

    # ── ② 订单 + 关联 + 券领取记录（签名：pending） ──
    cur.execute("SELECT id, order_no, order_status, coupon_receive_record_id FROM `order` WHERE order_no=%s",
                (ORDER_NO,))
    order = cur.fetchone()
    receipt_ids = set()
    if order:
        if order["order_status"] == "pending":
            oid = int(order["id"])
            plan.add("②订单", f"order_item（order_id={oid}）",
                     "DELETE FROM order_item WHERE order_id=%s", (oid,))
            plan.add("②订单", f"`order` id={oid} order_no={order['order_no']}（pending）",
                     "DELETE FROM `order` WHERE id=%s AND order_status='pending'", (oid,))
            if order["coupon_receive_record_id"]:
                receipt_ids.add(int(order["coupon_receive_record_id"]))
        else:
            plan.steps.append({"group": "②订单", "desc": f"订单状态非 pending（{order['order_status']}）→ SKIP",
                               "sql": None, "args": None, "verify": None, "ids": [], "skips": [order["id"]]})
    if COUPON_RECEIVE_RECORD_ID:
        cur.execute("SELECT id, coupon_id, user_id, receive_status FROM coupon_receive_record WHERE id=%s",
                    (COUPON_RECEIVE_RECORD_ID,))
        rr = cur.fetchone()
        if rr and rr["receive_status"] == "unused":
            receipt_ids.add(int(rr["id"]))
        elif rr:
            plan.steps.append({"group": "②订单", "desc": f"领取记录 {rr['id']} 状态非 unused（{rr['receive_status']}）→ SKIP",
                               "sql": None, "args": None, "verify": None, "ids": [], "skips": [rr["id"]]})
    if receipt_ids:
        # 只删领取记录行，不动 coupon 种子行（receive_count/used_count 聚合保持原样=cosmetic）
        fmt = ",".join(["%s"] * len(receipt_ids))
        plan.add("②订单", f"coupon_receive_record（{sorted(receipt_ids)}；coupon 种子行不动，聚合列保持原样）",
                 f"DELETE FROM coupon_receive_record WHERE id IN ({fmt})", tuple(receipt_ids))

    # ── ③ 软删测试系列级联（签名：code 前缀 + sale_status='off_sale' + 引用面全 0） ──
    cur.execute(
        f"SELECT id, series_code, series_name, sale_status FROM series WHERE ({_series_like_sql(extended)})",
        _series_args(extended),
    )
    ok_series = []
    for r in cur.fetchall():
        code = str(r["series_code"])
        base_hit = any(code.startswith(p) for p in SERIES_CODE_PREFIXES)
        fam_hit = (not base_hit and extended
                   and any(code.startswith(p) for p in EXTENDED_FAMILY_PREFIXES)
                   and _TEST_NAME_SIG.search(str(r["series_name"] or "")))
        if not (base_hit or fam_hit):
            continue  # SQL LIKE 命中但签名不符（双保险）
        if r["sale_status"] != "off_sale":
            plan.steps.append({"group": "③测试系列", "desc": f"series {r['id']}({code}) 非 off_sale（{r['sale_status']}）→ SKIP（不动真实系列）",
                               "sql": None, "args": None, "verify": None, "ids": [], "skips": [r["id"]]})
            continue
        ok_series.append(int(r["id"]))
    if ok_series:
        sf = ",".join(["%s"] * len(ok_series))
        cur.execute(f"SELECT id, series_id, cohort_code, yn FROM series_cohort WHERE series_id IN ({sf})",
                    tuple(ok_series))
        cohorts = cur.fetchall()
        cohort_ids = [int(c["id"]) for c in cohorts]
        # 引用面核验：任一非 0 → 中止该系列删除
        ref_total = 0
        if cohort_ids:
            cf = ",".join(["%s"] * len(cohort_ids))
            for t in COHORT_REF_TABLES:
                cur.execute(f"SELECT COUNT(*) c FROM `{t}` WHERE cohort_id IN ({cf})", tuple(cohort_ids))
                ref_total += int(cur.fetchone()["c"])
        for t in SERIES_REF_TABLES:
            cur.execute(f"SELECT COUNT(*) c FROM `{t}` WHERE series_id IN ({sf})", tuple(ok_series))
            ref_total += int(cur.fetchone()["c"])
        cur.execute(f"SELECT COUNT(*) c FROM series_search_log WHERE clicked_series_id IN ({sf})", tuple(ok_series))
        ref_total += int(cur.fetchone()["c"])
        plan.steps.append({"group": "③测试系列",
                           "desc": f"引用面核验 order_item/consultation/review/risk/attendance/cart/student_rel/"
                                   f"compensation/category_rel/coupon_series_rel/favorite/visit/exposure/search = {ref_total}",
                           "sql": None, "args": None, "verify": None, "ids": [], "skips": []})
        if ref_total > 0:
            plan.steps.append({"group": "③测试系列", "desc": "引用面非 0 → 全部系列 SKIP（绝不级联破坏）",
                               "sql": None, "args": None, "verify": None, "ids": [], "skips": ok_series})
        else:
            if cohort_ids:
                cf = ",".join(["%s"] * len(cohort_ids))
                plan.add("③测试系列", f"series_cohort（{cohort_ids}，含 yn=0）",
                         f"DELETE FROM series_cohort WHERE id IN ({cf})", tuple(cohort_ids))
            plan.add("③测试系列", f"series（{ok_series}，off_sale 回收站测试系列）",
                     f"DELETE FROM series WHERE id IN ({sf}) AND sale_status='off_sale'", tuple(ok_series))

    # ── ④ 测试视频行 + 媒体文件（签名：video_code 精确匹配） ──
    cur.execute("SELECT id, asset_id, video_code FROM session_video WHERE video_code=%s", (VIDEO_CODE,))
    vids = cur.fetchall()
    for v in vids:
        plan.add("④测试视频", f"session_video id={v['id']} video_code={v['video_code']}",
                 "DELETE FROM session_video WHERE id=%s AND video_code=%s", (v["id"], VIDEO_CODE))
        cur.execute("SELECT id, session_id, asset_code, file_url, file_size FROM session_asset WHERE id=%s",
                    (v["asset_id"],))
        a = cur.fetchone()
        if a and str(a["file_url"] or "").endswith(VIDEO_CODE + ".mp4"):
            media_file = DATA_DIR / "media" / str(a["file_url"]).lstrip("/").replace("media/", "", 1) \
                if str(a["file_url"]).startswith("/media/") else None
            plan.add("④测试视频", f"session_asset id={a['id']} asset_code={a['asset_code']} file_url={a['file_url']}",
                     "DELETE FROM session_asset WHERE id=%s AND asset_code=%s", (a["id"], a["asset_code"]))
            plan.steps.append({"group": "④测试视频",
                               "desc": f"媒体文件 {media_file}（存在={bool(media_file and media_file.exists())}，"
                                       f"{(media_file.stat().st_size if media_file and media_file.exists() else 0)} bytes）→ {'删除' if media_file else '路径解析失败 SKIP'}",
                               "sql": None, "args": None, "verify": None, "ids": [], "skips": [],
                               "file": media_file})


def verify_zero(cur, extended: bool = False) -> list[str]:
    """复验：全部目标应清零，返回残留描述列表（空=干净）。"""
    residues = []
    cur.execute("SELECT COUNT(*) c FROM community_post WHERE id IN %s", (TEST_POST_IDS,))
    n = int(cur.fetchone()["c"])
    if n:
        residues.append(f"community_post 残留 {n}")
    cur.execute("SELECT COUNT(*) c FROM community_comment WHERE post_id IN %s", (TEST_POST_IDS,))
    if int(cur.fetchone()["c"]):
        residues.append("community_comment 残留")
    cur.execute("SELECT COUNT(*) c FROM `order` WHERE order_no=%s", (ORDER_NO,))
    if int(cur.fetchone()["c"]):
        residues.append("order 残留")
    cur.execute("SELECT COUNT(*) c FROM coupon_receive_record WHERE id IN (51001,51122)")
    if int(cur.fetchone()["c"]):
        residues.append("coupon_receive_record 残留")
    cur.execute(
        f"SELECT COUNT(*) c FROM series WHERE ({_series_like_sql(extended)}) AND sale_status='off_sale'",
        _series_args(extended),
    )
    if int(cur.fetchone()["c"]):
        residues.append("series 回收站测试系列残留")
    cur.execute("SELECT COUNT(*) c FROM session_video WHERE video_code=%s", (VIDEO_CODE,))
    if int(cur.fetchone()["c"]):
        residues.append("session_video 残留")
    cur.execute("SELECT COUNT(*) c FROM session_asset WHERE file_url LIKE %s", (f"%{VIDEO_CODE}%",))
    if int(cur.fetchone()["c"]):
        residues.append("session_asset 残留")
    media = DATA_DIR / "media" / "videos" / f"{VIDEO_CODE}.mp4"
    if media.exists():
        residues.append(f"媒体文件残留 {media}")
    return residues


def main() -> int:
    ap = argparse.ArgumentParser(description="EduAgent 演示库残留清理（默认 dry-run）")
    ap.add_argument("--execute", action="store_true", help="真执行（默认仅 dry-run 打印清单）")
    ap.add_argument("--extend-test-family", action="store_true",
                    help="扩展口径：除任务清单前缀外，另纳入机器签名可证的同类 epoch 测试系列"
                         "（rst17*/jsn17*/jsnn17*/jsnu17* + off_sale + 名称含 测试/JSON/C5/H1c 签名）。"
                         "默认仅任务清单前缀（rst17886141/jsnn17886141/jsn17886141/t13w1）+ h1c（H1c 测试登记）。")
    args = ap.parse_args()

    env = load_env()
    conn = connect(env)
    cur = conn.cursor()
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"== cleanup_demo_residues [{mode}] db={env.get('MYSQL_DATABASE', 'edu')} ==")

    plan = Plan()
    build_plan(cur, plan, extended=args.extend_test_family)

    total_rows = 0
    for s in plan.steps:
        tag = "SKIP" if s.get("sql") is None and s.get("skips") else ("INFO" if s.get("sql") is None else "DEL ")
        print(f"[{tag}] {s['group']} | {s['desc']}")
        if s.get("sql") and args.execute:
            affected = cur.execute(s["sql"], s["args"])
            total_rows += affected
            print(f"        -> affected {affected}")
        elif s.get("sql"):
            print(f"        -> SQL: {s['sql']} | args={s['args']}")
        if s.get("file") and args.execute and s["file"].exists():
            s["file"].unlink()
            print(f"        -> 文件已删除")

    print(f"\n-- 计划步骤 {len(plan.steps)} 项 --")
    if args.execute:
        conn.commit()
        print(f"-- 已提交，数据行删除合计 {total_rows} --")
        residues = verify_zero(cur, extended=args.extend_test_family)
        if residues:
            print("!! 复验存在残留：")
            for r in residues:
                print("   - " + r)
            return 1
        print("-- 复验：全部目标清零 PASS --")
    else:
        conn.rollback()
        residues = verify_zero(cur, extended=args.extend_test_family)
        print(f"-- dry-run 未动数据。当前残留项 {len(residues)} 个 --")
        for r in residues:
            print("   - " + r)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
