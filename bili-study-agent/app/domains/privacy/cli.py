"""Admin-operated privacy export/delete CLI. Delete is dry-run by default."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.domains.privacy.user_data import (
    canonical_json_bytes,
    delete_user_data,
    export_user_data,
    inspect_user_data,
    restore_user_data,
    validate_backup_header,
    validate_user_id,
    _validate_restore_rows,
)


def _require_private_path(path: Path) -> Path:
    """Reject user data artifacts inside the source checkout."""
    resolved = path.resolve()
    workspace = Path(__file__).resolve().parents[4]
    try:
        resolved.relative_to(workspace)
    except ValueError:
        return resolved
    raise ValueError("privacy export/backup path must be outside the repository workspace")


async def _with_connection(operation: Any) -> Any:
    from app.database import get_mysql_pool

    pool = get_mysql_pool()
    async with pool.acquire() as conn:
        return await operation(conn)


def _require_isolated_pilot_target(args: argparse.Namespace) -> None:
    """Refuse default/shared databases; operations require explicit isolated DB names."""
    from app.config import settings

    mysql_db = str(settings.MYSQL_DATABASE)
    mongo_db = str(settings.MONGO_DB)
    if str(settings.ENV_NAME).strip().lower() != "pilot" or bool(settings.DEBUG):
        raise RuntimeError("privacy CLI requires ENV_NAME=pilot and DEBUG=false")
    if not mysql_db.endswith("_pilot") or mysql_db == "edu":
        raise RuntimeError("privacy CLI requires a dedicated MySQL database ending in _pilot")
    if not mongo_db.endswith("_pilot") or mongo_db == "edu_agent":
        raise RuntimeError("privacy CLI requires a dedicated Mongo database ending in _pilot")
    if args.expected_mysql_db != mysql_db or args.expected_mongo_db != mongo_db:
        raise RuntimeError("explicit expected database names must exactly match configured Pilot databases")


def _require_writes_stopped(args: argparse.Namespace) -> None:
    if args.writes_stopped_confirmation != "PILOT_MYSQL_AND_MONGO_WRITES_STOPPED":
        raise RuntimeError(
            "apply requires confirmation that Pilot API/background writers for both MySQL and Mongo are stopped"
        )


async def _export(args: argparse.Namespace) -> int:
    from app.database import close_mongo, close_mysql, get_mongo_db, init_mongo, init_mysql

    _require_isolated_pilot_target(args)
    await init_mysql()
    try:
        await init_mongo()
        payload = await _with_connection(lambda conn: export_user_data(conn, args.user_id, get_mongo_db()))
    finally:
        await close_mongo()
        await close_mysql()
    raw = canonical_json_bytes(payload)
    output = _require_private_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    print(json.dumps({"result": "EXPORTED", "user_id": args.user_id, "file": str(output), "sha256": hashlib.sha256(raw).hexdigest(), "tables": {k: len(v) for k, v in payload["tables"].items()}, "excluded_stores": payload["excluded_stores"]}, ensure_ascii=False, indent=2))
    return 0


async def _delete(args: argparse.Namespace) -> int:
    from app.database import (close_mongo, close_mysql, close_redis, get_mongo_db, get_redis,
                              init_mongo, init_mysql, init_redis)

    uid = validate_user_id(args.user_id)
    _require_isolated_pilot_target(args)
    if args.apply:
        _require_writes_stopped(args)
        # Fail before MySQL mutation if the isolated Redis namespace is not
        # reachable. Its owner-scoped ephemera must be revoked with deletion.
        await init_redis()
    await init_mysql()
    try:
        await init_mongo()
        counts = await _with_connection(lambda conn: inspect_user_data(conn, uid, get_mongo_db()))
        summary = {"mode": "DRY_RUN", "user_id": uid, "row_counts": counts,
                   "mysql_db": args.expected_mysql_db, "mongo_db": args.expected_mongo_db}
        if not args.apply:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        if os.getenv("EDU_PRIVACY_APPLY") != "I_UNDERSTAND_USER_SCOPED_DELETE":
            raise RuntimeError("apply blocked: set EDU_PRIVACY_APPLY=I_UNDERSTAND_USER_SCOPED_DELETE only in an approved maintenance window")
        if args.confirm_user_id != uid:
            raise RuntimeError("apply blocked: --confirm-user-id must exactly match --user-id")
        if not args.backup or not args.backup_sha256:
            raise RuntimeError("apply blocked: --backup and --backup-sha256 are required")
        backup_path = _require_private_path(args.backup)
        raw_backup = backup_path.read_bytes()
        actual_sha = hashlib.sha256(raw_backup).hexdigest()
        if actual_sha.lower() != args.backup_sha256.lower():
            raise RuntimeError("apply blocked: backup SHA-256 mismatch")
        backup = json.loads(raw_backup)
        # The service re-reads/locks the exact rows and validates the backup
        # inside the deletion transaction, avoiding a read-delete race.
        deleted = await _with_connection(lambda conn: delete_user_data(conn, uid, backup, get_mongo_db()))
        if deleted["status"] in {"APPLIED", "ALREADY_DELETED"}:
            try:
                from app.domains.privacy.redis_user import purge_user_redis_ephemera
                deleted["redis"] = await purge_user_redis_ephemera(get_redis(), uid)
            except Exception as exc:
                deleted["status"] = "PARTIAL"
                deleted["redis"] = {"status": "FAILED", "error": type(exc).__name__}
        print(json.dumps({"mode": deleted["status"], "user_id": uid, "backup_sha256": actual_sha,
                          "stores": deleted, "mysql_db": args.expected_mysql_db,
                          "mongo_db": args.expected_mongo_db}, ensure_ascii=False, indent=2))
        return 0 if deleted["status"] in {"APPLIED", "ALREADY_DELETED"} else 3
    finally:
        await close_mongo()
        await close_mysql()
        if args.apply:
            await close_redis()


async def _restore(args: argparse.Namespace) -> int:
    from app.database import close_mongo, close_mysql, get_mongo_db, init_mongo, init_mysql

    uid = validate_user_id(args.user_id)
    _require_isolated_pilot_target(args)
    backup_path = _require_private_path(args.backup)
    raw_backup = backup_path.read_bytes()
    actual_sha = hashlib.sha256(raw_backup).hexdigest()
    if actual_sha.lower() != args.backup_sha256.lower():
        raise RuntimeError("restore blocked: backup SHA-256 mismatch")
    backup = json.loads(raw_backup)
    validate_backup_header(backup, uid)
    _validate_restore_rows(backup, uid)
    if args.apply:
        _require_writes_stopped(args)
        if os.getenv("EDU_PRIVACY_APPLY") != "I_UNDERSTAND_USER_SCOPED_DELETE":
            raise RuntimeError("restore apply blocked: explicit maintenance-window environment confirmation required")
        if args.confirm_user_id != uid:
            raise RuntimeError("restore apply blocked: --confirm-user-id must exactly match --user-id")
    await init_mysql()
    try:
        await init_mongo()
        counts = await _with_connection(lambda conn: inspect_user_data(conn, uid, get_mongo_db()))
        if not args.apply:
            print(json.dumps({"mode": "RESTORE_DRY_RUN", "user_id": uid, "backup_sha256": actual_sha,
                              "row_counts": counts, "mysql_db": args.expected_mysql_db,
                              "mongo_db": args.expected_mongo_db}, ensure_ascii=False, indent=2))
            return 0
        restored = await _with_connection(lambda conn: restore_user_data(conn, uid, backup, get_mongo_db()))
        print(json.dumps({"mode": restored["status"], "user_id": uid, "backup_sha256": actual_sha,
                          "stores": restored, "mysql_db": args.expected_mysql_db,
                          "mongo_db": args.expected_mongo_db}, ensure_ascii=False, indent=2))
        return 0 if restored["status"] in {"APPLIED", "ALREADY_RESTORED"} else 3
    finally:
        await close_mongo()
        await close_mysql()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="write an exact user-scoped MySQL export artifact")
    export.add_argument("--user-id", type=int, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--expected-mysql-db", required=True)
    export.add_argument("--expected-mongo-db", required=True)
    delete = sub.add_parser("delete", help="show row counts; requires extra safeguards to apply")
    delete.add_argument("--user-id", type=int, required=True)
    delete.add_argument("--apply", action="store_true", help="destructive; dry-run is default")
    delete.add_argument("--confirm-user-id", type=int)
    delete.add_argument("--backup", type=Path)
    delete.add_argument("--backup-sha256")
    delete.add_argument("--expected-mysql-db", required=True)
    delete.add_argument("--expected-mongo-db", required=True)
    delete.add_argument("--writes-stopped-confirmation")
    restore = sub.add_parser("restore", help="restore an exact v3 backup into empty isolated Pilot user stores")
    restore.add_argument("--user-id", type=int, required=True)
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--backup-sha256", required=True)
    restore.add_argument("--apply", action="store_true", help="write restore; dry-run is default")
    restore.add_argument("--confirm-user-id", type=int)
    restore.add_argument("--expected-mysql-db", required=True)
    restore.add_argument("--expected-mongo-db", required=True)
    restore.add_argument("--writes-stopped-confirmation")
    args = parser.parse_args(argv)
    validate_user_id(args.user_id)
    try:
        operation = {"export": _export, "delete": _delete, "restore": _restore}[args.command]
        return asyncio.run(operation(args))
    except Exception as exc:
        print(f"privacy operation refused/failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
