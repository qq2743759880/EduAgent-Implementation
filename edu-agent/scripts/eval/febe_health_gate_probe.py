#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
febe_health_gate_probe.py — check-demo.mjs ⑱ 守卫探针（W-NEXT-CHECKDEMO-001 / W-NEXT-FE-003）
============================================================================

封装 febe_contract_check.run(quiet=True)，解析 [SUMMARY] 行，输出
[FEBE_HEALTH] {json} 供 check-demo ⑱ 守卫解析。

退出码：
  0 = PASS（unfrozen_only == 0；env_blocked 视具体场景）
  2 = env_blocked（后端不可达 → check-demo ⑱ 走 WARN 不阻断）
  1 = FAIL（unfrozen_only > 0 或 解析失败）

安全约束（Mimosa）：
  - host 写死 127.0.0.1:8000（仅本地后端；非 loopback 立即 SystemExit）
  - 无 DB 写入（仅读 OpenAPI + 本地 JSON / HTML）
  - 不读密钥

用法：
  python febe_health_gate_probe.py
"""
import json
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import febe_contract_check as F  # noqa: E402


def _emit(j: dict) -> None:
    print("[FEBE_HEALTH] " + json.dumps(j, ensure_ascii=False))


def main() -> int:
    try:
        code = F.run(quiet=True)
    except SystemExit as e:
        # febe_contract_check 在 host 校验失败时 SystemExit
        _emit({"unfrozen_only": -1, "env_blocked": True, "detail": str(e)[:160]})
        return 2
    except Exception as e:
        # 后端不可达等：febe_contract_check.run 内部已经 print [SUMMARY]，但为了
        # ⑱ 守卫解析一致性，仍发一行 [FEBE_HEALTH] env_blocked
        _emit({"unfrozen_only": -1, "env_blocked": True, "detail": str(e)[:160]})
        return 2

    # code 1 = 断点>0 或 在用未冻结>0 —— ⑱ 不阻断断点/在用（那是 ⑩ 的事），
    # ⑱ 只看 unfrozen_only。code 0 = 契约无漂移；code 2 = 后端不可达。
    # 由于 run() 是 quiet 模式，我们从 contracts/fe_calls/be_routes 重新算 unfrozen_only。
    fe_calls = F.scan_frontend()
    try:
        spec = F.fetch_openapi()
    except Exception as e:
        _emit({"unfrozen_only": -1, "env_blocked": True, "detail": str(e)[:160]})
        return 2
    be_routes = F.backend_routes(spec)
    contracts, _malformed = F.load_contracts(be_routes)

    unfrozen_mp = sorted(be_routes - contracts)
    in_use_unfrozen = sorted((fe_calls & be_routes) - contracts)
    unfrozen_only = sorted(set(unfrozen_mp) - set(in_use_unfrozen))

    uo = len(unfrozen_only)
    bp = len(fe_calls - be_routes)
    iu = len(in_use_unfrozen)
    tc = len(be_routes - fe_calls)

    j = {
        "unfrozen_only": uo,
        "breakpoints": bp,
        "in_use_unfrozen": iu,
        "to_connect": tc,
        "env_blocked": False,
        "detail": "",
    }
    _emit(j)
    return 0 if uo == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
