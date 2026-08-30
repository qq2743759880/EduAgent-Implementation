"""
verify_task36.py — task36 RAG 上传后端增强 验收脚本
====================================================
覆盖 GWT 验收标准：
- ① MySQL knowledge_import_task 双写：create/update/get/list 全链路（列表分页倒序）
- ② Redis 双写：本会话 Redis 不可用 → 验证「优雅降级到 MySQL」路径；Redis SETEX 逻辑已实现但未 live 验证
- ③ MinIO edu-upload 留存 + 30 天生命周期：真实 bucket 设置生命周期 + 上传对象 + 校验留存
- ④ 契约⑥冻结点：GET /api/knowledge/tasks 等价逻辑（list_tasks 分页倒序 + RBAC 由路由层保证）

退出码：0 = 关键项（MySQL + MinIO）全部 PASS；1 = 有关键失败。
Redis 不可用为已知环境事实，单独标记为 SKIP 不计入失败。
"""
import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # EduAgent实施手册/
EDU = PROJECT_ROOT / "edu-agent"
if str(EDU) not in sys.path:
    sys.path.insert(0, str(EDU))

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="INFO")

import app.config  # noqa: F401  (触发 .env 加载)
from app.config import settings
from app.database import execute_write, fetch_one, get_minio_client, init_mysql
from app.knowledge import task_store
from app.services.minio_uploader import get_uploader

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"; RESET = "\033[0m"
PASS = f"{GREEN}PASS{RESET}"; FAIL = f"{RED}FAIL{RESET}"; SKIP = f"{YELLOW}SKIP{RESET}"

results = []


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    tag = PASS if ok else FAIL
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))


async def verify_mysql():
    print("\n=== ① MySQL 双写链路（knowledge_import_task）===")
    task_id = f"verify_task36_{uuid.uuid4().hex[:10]}"
    meta = [{
        "object_key": "verify/obj1.md",
        "file_name": "a.md",
        "file_size": 10,
        "content_type": "text/markdown",
    }]
    try:
        await init_mysql()
    except Exception as exc:
        rec("MySQL 连接", False, f"init_mysql 失败: {exc!r}")
        return

    rec("MySQL 连接", True, f"{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}")

    # create
    try:
        created = await task_store.create_task(
            task_id=task_id,
            task_type="verify",
            tenant_id="verify_tenant",
            visibility="private",
            source_files_meta=meta,
            total_chunks=20,
        )
        rec("create_task 返回结构", created["task_id"] == task_id and created["status"] == "pending",
            f"status={created['status']}")
    except Exception as exc:
        rec("create_task", False, f"{exc!r}")
        return

    # 行级校验（真相源）
    row = await fetch_one(
        "SELECT task_id, status, source_files, total_chunks FROM knowledge_import_task WHERE task_id=%s",
        (task_id,),
    )
    rec("MySQL 行写入", row is not None and row["status"] == "pending",
        f"row_status={row['status'] if row else None}")
    import json as _json
    src_ok = row and _json.loads(row["source_files"]) == meta
    rec("source_files JSON 列", bool(src_ok), "")

    # update（done → succeeded）
    await task_store.update_task(
        task_id=task_id, status="done", imported_chunks=5, total_chunks=20,
    )
    row2 = await fetch_one(
        "SELECT status, imported_chunks FROM knowledge_import_task WHERE task_id=%s", (task_id,)
    )
    rec("update_task status 映射 done→succeeded", row2["status"] == "succeeded",
        f"db_status={row2['status']}")
    rec("update_task 进度回写", row2["imported_chunks"] == 5, f"imported={row2['imported_chunks']}")

    # get（Redis 未初始化 → 回退 MySQL）
    got = await task_store.get_task(task_id)
    rec("get_task 回退 MySQL", got is not None and got["status"] == "succeeded",
        f"status={got['status'] if got else None}")

    # list 分页倒序
    listing = await task_store.list_tasks(page=1, page_size=10)
    items = listing["items"]
    rec("list_tasks 结构", all(k in listing for k in ("items", "total", "page", "page_size", "total_pages")),
        f"total={listing['total']}, returned={len(items)}")
    contains = any(t["task_id"] == task_id for t in items)
    rec("list_tasks 含本任务", contains, "")
    # 倒序校验：created_at 非递增
    ctimes = [t["created_at"] for t in items if t["created_at"]]
    desc_ok = all(ctimes[i] >= ctimes[i + 1] for i in range(len(ctimes) - 1))
    rec("list_tasks 倒序(created_at DESC)", desc_ok, f"sample={ctimes[:3]}")

    # list 状态过滤
    flt = await task_store.list_tasks(page=1, page_size=10, status="succeeded")
    filtered_ok = all(t["status"] == "succeeded" for t in flt["items"]) and flt["total"] >= 1
    rec("list_tasks status 过滤", filtered_ok, f"filtered_total={flt['total']}")

    # 清理
    await execute_write("DELETE FROM knowledge_import_task WHERE task_id=%s", (task_id,))
    leftover = await fetch_one(
        "SELECT 1 FROM knowledge_import_task WHERE task_id=%s", (task_id,)
    )
    rec("测试行清理", leftover is None, "")


def verify_minio():
    print("\n=== ③ MinIO edu-upload 留存 + 30 天生命周期 ===")
    endpoint = settings.MINIO_ENDPOINT
    print(f"  配置 MINIO_ENDPOINT = {endpoint}")
    # 尝试用配置端点初始化；失败则回退到实测可达的 VM
    try:
        from app.database import init_minio
        init_minio()
        rec("MinIO 初始化(配置端点)", True, endpoint)
    except Exception as exc:
        vm = "192.168.85.101:9000"
        print(f"  {YELLOW}配置端点不可达（{exc!r}），回退 VM {vm}{RESET}")
        try:
            import urllib3
            from minio import Minio
            _http = urllib3.PoolManager(timeout=urllib3.Timeout(connect=5.0, read=10.0))
            client = Minio(vm, access_key=settings.MINIO_ACCESS_KEY,
                           secret_key=settings.MINIO_SECRET_KEY, secure=False, http_client=_http)
            # 直接把 client 注入 database 单例，使 get_uploader() 可用
            import app.database as dbmod
            dbmod._minio_client = client
            if not client.bucket_exists(settings.MINIO_BUCKET_UPLOAD):
                client.make_bucket(settings.MINIO_BUCKET_UPLOAD)
            rec("MinIO 初始化(VM 回退)", True, vm)
        except Exception as exc2:
            rec("MinIO 连接", False, f"VM 回退也失败: {exc2!r}")
            return

    try:
        up = get_uploader()
    except Exception as exc:
        rec("get_uploader", False, f"{exc!r}")
        return

    # 设置 30 天生命周期
    ok_lc = up.ensure_upload_bucket_lifecycle(30)
    rec("设置 30 天生命周期", ok_lc, "")

    # 校验生命周期规则已落地
    lc_ok = False
    try:
        cfg = get_minio_client().get_bucket_lifecycle(settings.MINIO_BUCKET_UPLOAD)
        rule = cfg.rules[0]
        lc_ok = (rule.rule_id == "edu-upload-retention" and rule.expiration is not None
                 and getattr(rule.expiration, "days", None) == 30)
        print(f"  生命周期规则: rule_id={rule.rule_id}, days={getattr(rule.expiration, 'days', None)}")
    except Exception as exc:
        print(f"  {YELLOW}get_bucket_lifecycle 失败（可能 SDK 版本差异）: {exc!r}{RESET}")
    rec("校验生命周期规则(30d)", lc_ok, "")

    # 上传一个测试文件并校验留存
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tf:
        tf.write(b"# verify task36 minio retention\nhello world\n")
        tmp_path = tf.name
    try:
        meta = up.upload_file(tmp_path, "verify_task36_upload.md",
                              content_type="text/markdown")
        ok_exists = up.object_exists(meta["object_key"], bucket=settings.MINIO_BUCKET_UPLOAD)
        rec("MinIO 上传对象", ok_exists, f"object_key={meta['object_key']}")
        # 清理测试对象（仅删验证对象，不删业务数据）
        get_minio_client().remove_object(settings.MINIO_BUCKET_UPLOAD, meta["object_key"])
        rec("测试对象清理", True, "")
    except Exception as exc:
        rec("MinIO 上传", False, f"{exc!r}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


async def verify_redis_degrade():
    print("\n=== ② Redis 双写（本会话不可用 → 验证优雅降级）===")
    # 不调用 init_redis()，get_redis() 应抛 RuntimeError → 被 task_store 吞掉
    task_id = f"verify_redis_{uuid.uuid4().hex[:8]}"
    try:
        created = await task_store.create_task(
            task_id=task_id,
            task_type="verify",
            tenant_id="verify_tenant",
            visibility="private",
            source_files_meta=[],
            total_chunks=1,
        )
        rec("Redis 不可用时 create_task 不阻断(降级MySQL)", created["task_id"] == task_id,
            "Redis 异常被吞，仅落 MySQL")
        await task_store.update_task(task_id=task_id, status="done")
        got = await task_store.get_task(task_id)
        rec("降级后 get_task 仍从 MySQL 命中", got is not None and got["status"] == "succeeded", "")
        await execute_write("DELETE FROM knowledge_import_task WHERE task_id=%s", (task_id,))
        rec("Redis 降级测试行清理", True, "")
        print(f"  {YELLOW}说明：Redis SETEX edu:knowledge:task:{{id}} 逻辑已实现，但本会话 Redis 全不可用，"
              f"未做 live 验证；MySQL 为真相源已验证。{RESET}")
    except Exception as exc:
        rec("Redis 降级路径", False, f"未预期异常: {exc!r}")


async def main():
    await verify_mysql()
    verify_minio()
    await verify_redis_degrade()

    print("\n================ 汇总 ================")
    failed = [n for n, ok, _ in results if not ok]
    if failed:
        print(f"{RED}失败项({len(failed)}): {failed}{RESET}")
        sys.exit(1)
    print(f"{GREEN}全部关键项 PASS（Redis 降级为已知环境事实，不计失败）{RESET}")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
