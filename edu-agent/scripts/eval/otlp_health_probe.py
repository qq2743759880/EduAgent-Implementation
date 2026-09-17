"""W-NEXT-OTLP-001 ⑳ 健康门探针 —— OTLP exporter 链路健康（endpoint 解析 + 探活 + SSRF 守门）。

走真实 settings + app.observability.otlp.OtlpExporter，不依赖 8000/DB：
1. 读取 settings.OTEL_EXPORTER_OTLP_ENDPOINT（空=disabled/PASS；非空=继续）
2. endpoint SSRF 白名单守门（app.security.ssrf_guard.validate_url）
3. 启动期 OtlpExporter.start() 跑一次（TCP 探活，host=白名单 127.0.0.1）
4. 解析 [OTLP] JSON 输出 state / endpoint / probe_ms / last_error

末行格式固定：`[OTLP] {endpoint, state, ssrf_ok, probe_ok, env_blocked, ...}`
check-demo ⑳ 守卫消费 JSON：
  - env_blocked=true → WARN（以④红项为准）
  - state="disabled" → PASS（默认配置）
  - state="healthy" + probe_ok=true → PASS
  - state="ssrf_rejected" → FAIL（host 不在白名单）
  - state="probe_failed" → WARN（探活失败不阻断；如需阻断改 ssrf_ok=false）

用法：
  python otlp_health_probe.py [--endpoint http://127.0.0.1:4318]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 入口处显式 load_dotenv(EDU_ROOT/.env)：与 check-demo ⑲⑭⑯ 同型兜底（防 cwd=
# 仓库根时 pydantic-settings 找不到 .env，参见 W-NEXT-CHECKDEMO-003 实证）。
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
_ENV_PATH = os.path.join(REPO, ".env")
if os.path.isfile(_ENV_PATH):
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(_ENV_PATH, override=False)
    except Exception:
        pass

sys.path.insert(0, REPO)
os.chdir(REPO)

# Mimosa host 写死本地
LOCAL_HOST = "127.0.0.1"
DEFAULT_PROBE_HOST_PORT = (LOCAL_HOST, 14318)  # 默认探测目标：本地假设的 OTel Collector 端口


def _endpoint_override(endpoint: str | None) -> str:
    """CLI 覆盖 endpoint 优先；否则回退 settings。"""
    if endpoint:
        return endpoint.strip()
    try:
        from app.config import settings
        return (settings.OTEL_EXPORTER_OTLP_ENDPOINT or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"[OTLP] WARN settings 读取失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=None,
                    help="覆盖 settings.OTEL_EXPORTER_OTLP_ENDPOINT；留空=读 settings")
    args = ap.parse_args()

    endpoint = _endpoint_override(args.endpoint)

    # 1) endpoint 空 → disabled（安全缺省 PASS）
    if not endpoint:
        out = {
            "env_blocked": False,
            "state": "disabled",
            "endpoint": "",
            "ssrf_ok": True,
            "probe_ok": True,
            "probe_ms": 0,
            "last_error": "",
            "detail": "OTEL_EXPORTER_OTLP_ENDPOINT 未配置（disabled 安全缺省）",
        }
        print(f"[OTLP] {json.dumps(out, ensure_ascii=False)}")
        return 0

    # 2) SSRF 白名单守门
    ssrf_ok = True
    ssrf_reason = ""
    try:
        from app.security.ssrf_guard import validate_url
        validate_url(endpoint)
    except Exception as exc:  # noqa: BLE001
        ssrf_ok = False
        ssrf_reason = str(exc)

    # 3) 构造 OtlpExporter 并跑一次 start（TCP 探活，host 必须在白名单）
    state = "ssrf_rejected"
    probe_ok = False
    probe_ms = 0
    last_error = ssrf_reason
    detail = ssrf_reason or "endpoint SSRF 白名单通过"

    if ssrf_ok:
        try:
            from app.observability.otlp import OtlpExporter, OTLP_DISABLED_PROBE
            exp = OtlpExporter(
                endpoint=endpoint,
                service_name="otlp_health_probe",
                timeout_s=2.0,
                headers={},
            )
            state = exp.start()
            probe_ms = exp._probe_ms
            last_error = exp._last_error
            # OTLP_HEALTHY 视为 probe_ok=true；其他（disabled_probe 等）视为 false
            probe_ok = (state == "healthy")
            detail = (f"endpoint={endpoint} state={state} probe_ms={probe_ms}ms "
                      f"last_error={last_error or 'none'}")
            # 探针是只读，不留 buffer 状态
            exp.shutdown()
        except Exception as exc:  # noqa: BLE001
            state = "probe_failed"
            last_error = f"{type(exc).__name__}: {exc}"
            detail = f"OtlpExporter.start() 异常: {last_error}"

    # 4) env_blocked 判据：探针运行所需 deps 不全 / 配置缺失
    env_blocked = False
    env_blocked_reason = ""

    # 5) 输出
    out = {
        "env_blocked": env_blocked,
        "env_blocked_reason": env_blocked_reason,
        "state": state,
        "endpoint": endpoint,
        "ssrf_ok": ssrf_ok,
        "ssrf_reason": ssrf_reason,
        "probe_ok": probe_ok,
        "probe_ms": probe_ms,
        "last_error": last_error,
        "detail": detail,
    }
    print(f"[OTLP] {json.dumps(out, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
