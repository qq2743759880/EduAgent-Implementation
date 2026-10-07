"""Exact per-user Redis revocation for the isolated Pilot namespace."""
from __future__ import annotations

import re
from typing import Any

from .user_data import validate_user_id


_CONTEXT_DELETE_IF_OWNER = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local ok, document = pcall(cjson.decode, raw)
if not ok or type(document) ~= 'table' or document.user_id == nil then
  return -2
end
if tostring(document.user_id) ~= ARGV[1] then return -1 end
return redis.call('DEL', KEYS[1])
"""


async def purge_user_redis_ephemera(redis: Any, user_id: int) -> dict[str, Any]:
    """Revoke this user's indexed and legacy contexts plus refresh JTIs.

    The Pilot deployment reserves Redis DB 14. The key scan is limited to the
    StudyContext prefix and Lua checks the stored owner before deleting, so
    legacy keys created before the reverse index was introduced are covered
    without touching another user's contexts.
    """
    uid = validate_user_id(user_id)
    db = getattr(getattr(redis, "connection_pool", None), "connection_kwargs", {}).get("db")
    if db != 14:
        raise RuntimeError("privacy Redis purge requires isolated Pilot DB 14")
    owner_index = f"study_context:owner:{uid}"
    context_ids = await redis.smembers(owner_index)
    context_ids = {value.decode() if isinstance(value, bytes) else str(value) for value in context_ids}
    if any(not re.fullmatch(r"sc_[A-Za-z0-9_-]{20,90}", value) for value in context_ids):
        raise RuntimeError("invalid context ID in user reverse index")
    refresh_keys = []
    async for key in redis.scan_iter(match=f"rt:{uid}:*", count=100):
        name = key.decode() if isinstance(key, bytes) else str(key)
        if not re.fullmatch(rf"rt:{uid}:[0-9a-f]{{32}}", name):
            raise RuntimeError("unexpected refresh key in user-scoped scan")
        refresh_keys.append(name)
    deleted_contexts = 0
    for context_id in sorted(context_ids):
        result = int(await redis.eval(_CONTEXT_DELETE_IF_OWNER, 1, "study_context:v1:" + context_id, str(uid)))
        if result == -1:
            raise RuntimeError("context reverse index points to a different user")
        if result == -2:
            raise RuntimeError("context reverse index points to malformed data")
        deleted_contexts += result

    # Older contexts predate the per-user reverse index. Restrict the scan to
    # the exact context prefix, validate key shape, then let Lua atomically
    # compare ownership and delete; unrelated owners remain untouched.
    legacy_deleted = 0
    async for key in redis.scan_iter(match="study_context:v1:*", count=100):
        name = key.decode() if isinstance(key, bytes) else str(key)
        match = re.fullmatch(r"study_context:v1:(sc_[A-Za-z0-9_-]{20,90})", name)
        if not match:
            raise RuntimeError("unexpected key in StudyContext namespace")
        result = int(await redis.eval(_CONTEXT_DELETE_IF_OWNER, 1, name, str(uid)))
        if result == -2:
            raise RuntimeError("unindexed StudyContext contains malformed data")
        if result == 1:
            legacy_deleted += 1

    await redis.delete(owner_index)
    deleted_refresh = int(await redis.delete(*refresh_keys)) if refresh_keys else 0
    return {
        "indexed_study_contexts_deleted": deleted_contexts,
        "legacy_study_contexts_deleted": legacy_deleted,
        "refresh_allowlist_keys_deleted": deleted_refresh,
        "unindexed_study_contexts": "SCANNED_OWNER_CHECKED",
    }
