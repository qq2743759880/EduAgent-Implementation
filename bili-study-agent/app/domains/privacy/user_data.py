"""Pilot-scoped user export/delete across reviewed MySQL and Mongo stores."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Mapping


# Order is child-first where an explicit relation exists. Do not add tables
# based only on name: first confirm ownership and retention obligations.
USER_DATA_TABLES: tuple[str, ...] = (
    "session_video_play_event",
    "session_video_play",
    "session_attendance",
    "quiz_wrong_book",
    "learning_next_action",
    "quiz_answer_session",
    "learning_loop",
    "session_homework_submission",
    "session_exam_submission",
    "learning_daily_summary",
    "learning_path_instance",
    "user_kp_mastery",
    "user_vocab_card",
    "chat_message",
    "chat_session",
    "user_profile",
    "user_memory_event",
    "user_memory",
    # User-scoped conversation audit and course/student personal records.
    # Keep student_profile last: allowlisted rows that reference its id are
    # removed first. Other business-domain references still fail closed via
    # the surrounding MySQL transaction rather than being cascaded here.
    "rag_audit_log",
    "course_review",
    "student_profile",
)

USER_DATA_COLLECTIONS: tuple[str, ...] = ("learning_event",)

# The event has no user_id column. Its FK points to the user-owned play
# session; deleting the parent first would fail FK checks or lose its scope.
INDIRECT_PLAY_EVENT = "session_video_play_event"


async def _assert_user_scope(cursor: Any, table: str) -> None:
    if table == INDIRECT_PLAY_EVENT:
        event_columns = await _fetch_all(cursor, "SHOW COLUMNS FROM `session_video_play_event`")
        parent_columns = await _fetch_all(cursor, "SHOW COLUMNS FROM `session_video_play`")
        if "play_session_id" not in {str(row.get("Field", "")) for row in event_columns} or not {"id", "user_id"}.issubset(
            {str(row.get("Field", "")) for row in parent_columns}
        ):
            raise RuntimeError("required playback event/parent ownership schema is missing")
        return
    columns = await _fetch_all(cursor, f"SHOW COLUMNS FROM `{table}`")
    if not columns or "user_id" not in {str(row.get("Field", "")) for row in columns}:
        raise RuntimeError(f"required table/schema is missing direct user_id scope: {table}")


def _user_rows_sql(table: str, *, for_update: bool = False) -> str:
    lock = " FOR UPDATE" if for_update else ""
    if table == INDIRECT_PLAY_EVENT:
        return (
            "SELECT e.* FROM `session_video_play_event` e "
            "JOIN `session_video_play` p ON e.play_session_id=p.id "
            f"WHERE p.user_id=%s ORDER BY e.id{lock}"
        )
    return f"SELECT * FROM `{table}` WHERE user_id=%s ORDER BY 1{lock}"


def _delete_user_sql(table: str) -> str:
    if table == INDIRECT_PLAY_EVENT:
        return (
            "DELETE e FROM `session_video_play_event` e "
            "JOIN `session_video_play` p ON e.play_session_id=p.id WHERE p.user_id=%s"
        )
    return f"DELETE FROM `{table}` WHERE user_id=%s"

EXCLUDED_STORES: tuple[str, ...] = (
    "Milvus user vectors and Neo4j graph memory",
    "sys_user/authentication credentials, non-user-scoped operational audit, and billing records",
    "shared course, lesson, question-bank, and Content Pack rows",
)


def validate_user_id(user_id: int) -> int:
    if isinstance(user_id, bool) or int(user_id) <= 0:
        raise ValueError("user_id must be a positive integer")
    return int(user_id)


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value.__class__.__name__ == "ObjectId" and value.__class__.__module__.startswith("bson"):
        return {"$objectid": str(value)}
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=json_default).encode("utf-8")


def payload_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def make_export(
    user_id: int,
    tables: Mapping[str, list[dict[str, Any]]],
    collections: Mapping[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    uid = validate_user_id(user_id)
    unknown = set(tables) - set(USER_DATA_TABLES)
    if unknown:
        raise ValueError(f"unreviewed table(s) in export: {', '.join(sorted(unknown))}")
    collection_data = dict(collections or {})
    unknown_collections = set(collection_data) - set(USER_DATA_COLLECTIONS)
    if unknown_collections:
        raise ValueError(f"unreviewed collection(s) in export: {', '.join(sorted(unknown_collections))}")
    return {
        "format": "eduagent-user-data-export-v3",
        "scope": "reviewed-mysql-and-mongo-user-id-stores",
        "user_id": uid,
        "tables": {name: list(tables.get(name, [])) for name in USER_DATA_TABLES},
        "collections": {name: list(collection_data.get(name, [])) for name in USER_DATA_COLLECTIONS},
        "excluded_stores": list(EXCLUDED_STORES),
    }


def validate_backup(backup: Any, user_id: int, expected_payload: Mapping[str, Any]) -> None:
    uid = validate_user_id(user_id)
    if not isinstance(backup, dict) or backup.get("format") != "eduagent-user-data-export-v3":
        raise ValueError("backup format is invalid")
    if backup.get("user_id") != uid:
        raise ValueError("backup user_id does not match the requested target")
    if payload_sha256(backup) != payload_sha256(expected_payload):
        raise ValueError("backup is not an exact current export for this user and table scope")


async def _fetch_all(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    await cursor.execute(sql, params)
    rows = await cursor.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], Mapping):
        return [dict(row) for row in rows]
    columns = [item[0] for item in (cursor.description or ())]
    if not columns:
        raise RuntimeError("database cursor did not expose result column names")
    return [dict(zip(columns, row)) for row in rows]


async def _mysql_user_rows(cursor: Any, user_id: int) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in USER_DATA_TABLES:
        await _assert_user_scope(cursor, table)
        tables[table] = await _fetch_all(cursor, _user_rows_sql(table), (user_id,))
    return tables


def _mongo_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _mongo_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_mongo_json_value(v) for v in value]
    if value.__class__.__name__ == "ObjectId" and value.__class__.__module__.startswith("bson"):
        return {"$objectid": str(value)}
    if isinstance(value, (datetime, date, Decimal, bytes)):
        return json.loads(json.dumps(value, default=json_default))
    return value


async def _mongo_user_rows(mongo_db: Any, user_id: int) -> dict[str, list[dict[str, Any]]]:
    if mongo_db is None:
        raise RuntimeError("MongoDB handle is required for complete Pilot privacy scope")
    out: dict[str, list[dict[str, Any]]] = {}
    for name in USER_DATA_COLLECTIONS:
        cursor = mongo_db[name].find({"user_id": user_id}).sort("_id", 1)
        docs = await cursor.to_list(length=None)
        out[name] = [_mongo_json_value(doc) for doc in docs]
    return out


async def inspect_user_data(conn: Any, user_id: int, mongo_db: Any) -> dict[str, Any]:
    """Count allowlisted rows/docs. Missing MySQL tables fail closed."""
    uid = validate_user_id(user_id)
    counts: dict[str, int] = {}
    async with conn.cursor() as cursor:
        user = await _fetch_all(cursor, "SELECT id FROM sys_user WHERE id=%s LIMIT 2", (uid,))
        if len(user) != 1:
            raise ValueError("target user must resolve to exactly one sys_user row")
        for table in USER_DATA_TABLES:
            await _assert_user_scope(cursor, table)
            if table == INDIRECT_PLAY_EVENT:
                rows = await _fetch_all(cursor, _user_rows_sql(table), (uid,))
                counts[table] = len(rows)
            else:
                rows = await _fetch_all(cursor, f"SELECT COUNT(*) AS row_count FROM `{table}` WHERE user_id=%s", (uid,))
                counts[table] = int(rows[0]["row_count"])
    collections = {name: len(rows) for name, rows in (await _mongo_user_rows(mongo_db, uid)).items()}
    return {"mysql": counts, "mongo": collections}


async def export_user_data(conn: Any, user_id: int, mongo_db: Any) -> dict[str, Any]:
    """Read exact user-owned rows/docs from reviewed MySQL and Mongo allowlists."""
    uid = validate_user_id(user_id)
    async with conn.cursor() as cursor:
        user = await _fetch_all(cursor, "SELECT id FROM sys_user WHERE id=%s LIMIT 2", (uid,))
        if len(user) != 1:
            raise ValueError("target user must resolve to exactly one sys_user row")
        tables = await _mysql_user_rows(cursor, uid)
    collections = await _mongo_user_rows(mongo_db, uid)
    return make_export(uid, tables, collections)


async def delete_user_data(
    conn: Any, user_id: int, expected_backup: Mapping[str, Any], mongo_db: Any
) -> dict[str, Any]:
    """Delete exact backed-up user rows; Mongo failures report resumable partial state.

    The stores cannot share a transaction. MySQL commits first; Mongo is then
    deleted by backed-up ``_id`` only. Re-running accepts stores already empty,
    but rejects changed/new rows so the operator must make a fresh backup.
    """
    uid = validate_user_id(user_id)
    deleted: dict[str, int] = {}
    try:
        async with conn.cursor() as cursor:
            # Re-check the target and each direct-scope column inside the same
            # transaction immediately before any mutation.
            user = await _fetch_all(cursor, "SELECT id FROM sys_user WHERE id=%s LIMIT 2 FOR UPDATE", (uid,))
            if len(user) != 1:
                raise ValueError("target user must resolve to exactly one sys_user row")
            locked_tables = {}
            for table in USER_DATA_TABLES:
                await _assert_user_scope(cursor, table)
                locked_tables[table] = await _fetch_all(cursor, _user_rows_sql(table, for_update=True), (uid,))
            mongo_rows = await _mongo_user_rows(mongo_db, uid)
            validate_backup_header(expected_backup, uid)
            mysql_status = _validate_retryable_store(expected_backup["tables"], locked_tables, "mysql")
            mongo_status = _validate_retryable_store(expected_backup["collections"], mongo_rows, "mongo")
            for table in USER_DATA_TABLES:
                await cursor.execute(_delete_user_sql(table), (uid,))
                deleted[table] = int(cursor.rowcount)
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    result: dict[str, Any] = {
        "status": "APPLIED",
        "mysql": {"status": mysql_status, "deleted": deleted},
        "mongo": {"status": mongo_status, "deleted": {}},
    }
    try:
        for name, docs in expected_backup["collections"].items():
            if not docs:
                result["mongo"]["deleted"][name] = 0
                continue
            ids = [_decode_object_ids(doc["_id"]) for doc in docs]
            deleted_result = await mongo_db[name].delete_many({"user_id": uid, "_id": {"$in": ids}})
            remaining = await _mongo_user_rows(mongo_db, uid)
            if remaining.get(name):
                result["status"] = "PARTIAL"
                result["mongo"]["status"] = "PARTIAL"
                result["mongo"]["deleted"][name] = int(deleted_result.deleted_count)
                result["mongo"]["remaining"] = {key: len(value) for key, value in remaining.items()}
                return result
            result["mongo"]["deleted"][name] = int(deleted_result.deleted_count)
        if all(v == "ALREADY_EMPTY" for v in (mysql_status, mongo_status)):
            result["status"] = "ALREADY_DELETED"
        return result
    except Exception as exc:
        result["status"] = "PARTIAL"
        result["mongo"]["status"] = "FAILED"
        result["mongo"]["error"] = type(exc).__name__
        return result


def _validate_restore_rows(backup: Mapping[str, Any], user_id: int) -> None:
    """Reject foreign-user rows and orphan play events before any insertion."""
    for table in USER_DATA_TABLES:
        rows = backup["tables"][table]
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError(f"backup rows are invalid: {table}")
        if table != INDIRECT_PLAY_EVENT and any(row.get("user_id") != user_id for row in rows):
            raise ValueError(f"backup contains another user's row: {table}")
    owned_plays = {row.get("id") for row in backup["tables"]["session_video_play"]}
    if any(row.get("play_session_id") not in owned_plays for row in backup["tables"][INDIRECT_PLAY_EVENT]):
        raise ValueError("backup playback event does not belong to a backed-up play session")
    owned_chat_sessions = {row.get("session_id") for row in backup["tables"]["chat_session"]}
    if any(row.get("session_id") not in owned_chat_sessions for row in backup["tables"]["chat_message"]):
        raise ValueError("backup chat message does not belong to a backed-up chat session")
    owned_student_profiles = {row.get("id") for row in backup["tables"]["student_profile"]}
    for table in ("session_video_play", "session_attendance", "session_homework_submission", "session_exam_submission"):
        if any(row.get("student_id") is not None and row["student_id"] not in owned_student_profiles for row in backup["tables"][table]):
            raise ValueError(f"backup references another user's student profile: {table}")
    owned_loops = {row.get("id") for row in backup["tables"]["learning_loop"]}
    owned_answers = {row.get("id") for row in backup["tables"]["quiz_answer_session"]}
    if any(row.get("learning_loop_id") is not None and row["learning_loop_id"] not in owned_loops
           for row in backup["tables"]["quiz_answer_session"]):
        raise ValueError("backup quiz answer references another user's learning loop")
    if any(row.get("learning_loop_id") not in owned_loops or row.get("quiz_answer_session_id") not in owned_answers
           for row in backup["tables"]["learning_next_action"]):
        raise ValueError("backup next action references another user's learning evidence")
    for name in USER_DATA_COLLECTIONS:
        docs = backup["collections"][name]
        if not isinstance(docs, list) or not all(isinstance(doc, dict) and doc.get("user_id") == user_id and "_id" in doc for doc in docs):
            raise ValueError(f"backup Mongo ownership or identity is invalid: {name}")


def _mongo_restore_missing(expected: list[dict[str, Any]], current: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    expected_by_id = {canonical_json_bytes(doc["_id"]): doc for doc in expected}
    if len(expected_by_id) != len(expected):
        raise ValueError(f"duplicate Mongo document id in backup: {name}")
    current_by_id = {canonical_json_bytes(doc["_id"]): doc for doc in current}
    if len(current_by_id) != len(current):
        raise ValueError(f"duplicate Mongo document id in current store: {name}")
    for key, doc in current_by_id.items():
        if key not in expected_by_id or canonical_json_bytes(doc) != canonical_json_bytes(expected_by_id[key]):
            raise ValueError(f"Mongo target has changed or foreign data: {name}")
    return [doc for key, doc in expected_by_id.items() if key not in current_by_id]


async def restore_user_data(conn: Any, user_id: int, backup: Mapping[str, Any], mongo_db: Any) -> dict[str, Any]:
    """Restore an exact v3 user export to empty stores; retry a partial Mongo replay.

    Caller must stop both writers and verify the backup hash. MySQL rows are
    inserted in one FK-safe transaction. A Mongo failure leaves a reported
    PARTIAL state; retry accepts only already restored exact documents.
    """
    uid = validate_user_id(user_id)
    validate_backup_header(backup, uid)
    _validate_restore_rows(backup, uid)
    if mongo_db is None:
        raise RuntimeError("MongoDB handle is required for complete Pilot privacy restore")
    inserted: dict[str, int] = {}
    try:
        async with conn.cursor() as cursor:
            user = await _fetch_all(cursor, "SELECT id FROM sys_user WHERE id=%s LIMIT 2 FOR UPDATE", (uid,))
            if len(user) != 1:
                raise ValueError("target user must resolve to exactly one sys_user row")
            current_tables: dict[str, list[dict[str, Any]]] = {}
            schema_columns: dict[str, set[str]] = {}
            for table in USER_DATA_TABLES:
                await _assert_user_scope(cursor, table)
                schema_columns[table] = {str(row["Field"]) for row in await _fetch_all(cursor, f"SHOW COLUMNS FROM `{table}`")}
                current_tables[table] = await _fetch_all(cursor, _user_rows_sql(table, for_update=True), (uid,))
                for row in backup["tables"][table]:
                    if set(row) != schema_columns[table]:
                        raise ValueError(f"backup columns differ from current schema: {table}")
            mysql_exact = all(canonical_json_bytes(current_tables[name]) == canonical_json_bytes(backup["tables"][name]) for name in USER_DATA_TABLES)
            mysql_empty = all(not rows for rows in current_tables.values())
            if not mysql_exact and not mysql_empty:
                raise ValueError("MySQL target contains changed or unbacked user rows")
            current_mongo = await _mongo_user_rows(mongo_db, uid)
            missing_mongo = {name: _mongo_restore_missing(backup["collections"][name], current_mongo[name], name)
                             for name in USER_DATA_COLLECTIONS}
            if mysql_empty and not mysql_exact:
                for table in reversed(USER_DATA_TABLES):
                    rows = backup["tables"][table]
                    for row in rows:
                        columns = list(row)
                        names = ",".join(f"`{name}`" for name in columns)
                        placeholders = ",".join(["%s"] * len(columns))
                        values = tuple(json.dumps(row[name], ensure_ascii=False) if isinstance(row[name], (dict, list)) else row[name] for name in columns)
                        await cursor.execute(f"INSERT INTO `{table}` ({names}) VALUES ({placeholders})", values)
                    inserted[table] = len(rows)
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    result: dict[str, Any] = {"status": "APPLIED", "mysql": {"status": "ALREADY_PRESENT" if mysql_exact else "RESTORED", "inserted": inserted},
                              "mongo": {"status": "RESTORED", "inserted": {}}}
    try:
        for name, docs in missing_mongo.items():
            for doc in docs:
                await mongo_db[name].insert_one(_decode_object_ids(doc))
            result["mongo"]["inserted"][name] = len(docs)
        final_mongo = await _mongo_user_rows(mongo_db, uid)
        for name in USER_DATA_COLLECTIONS:
            if _mongo_restore_missing(backup["collections"][name], final_mongo[name], name):
                raise RuntimeError(f"Mongo restore remains incomplete: {name}")
        if mysql_exact and not any(missing_mongo.values()):
            result["status"] = "ALREADY_RESTORED"
            result["mongo"]["status"] = "ALREADY_PRESENT"
        return result
    except Exception as exc:
        result["status"] = "PARTIAL"
        result["mongo"]["status"] = "FAILED"
        result["mongo"]["error"] = type(exc).__name__
        return result


def validate_backup_header(backup: Any, user_id: int) -> None:
    uid = validate_user_id(user_id)
    if not isinstance(backup, dict) or backup.get("format") != "eduagent-user-data-export-v3":
        raise ValueError("backup format is invalid")
    if backup.get("user_id") != uid:
        raise ValueError("backup user_id does not match the requested target")
    if set(backup.get("tables", {})) != set(USER_DATA_TABLES):
        raise ValueError("backup MySQL table scope is incomplete or unknown")
    if set(backup.get("collections", {})) != set(USER_DATA_COLLECTIONS):
        raise ValueError("backup Mongo collection scope is incomplete or unknown")


def _validate_retryable_store(expected: Mapping[str, list[dict[str, Any]]], current: Mapping[str, list[dict[str, Any]]], label: str) -> str:
    exact = all(canonical_json_bytes(current[name]) == canonical_json_bytes(expected[name]) for name in expected)
    if exact:
        return "MATCHED_BACKUP"
    empty = all(not rows for rows in current.values())
    if empty:
        return "ALREADY_EMPTY"
    raise ValueError(f"{label} user data changed since backup; make a new export and re-approve")


def _decode_object_ids(value: Any) -> Any:
    if isinstance(value, Mapping) and set(value) == {"$objectid"}:
        from bson import ObjectId
        return ObjectId(str(value["$objectid"]))
    if isinstance(value, Mapping):
        return {k: _decode_object_ids(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode_object_ids(v) for v in value]
    return value
