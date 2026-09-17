# -*- coding: utf-8 -*-
"""W-NEXT-EXE-SSRF-002：embedder 出站 HTTP 守门单测。

任务定义（编排者 kickoff）：
- embed URL 入口必经 ssrf_guard.validate_url（白名单 host + 禁 IMDS 元数据 endpoint）
- settings.EMBEDDING_API_URL 走白名单 → OK
- settings.EMBEDDING_API_URL=http://169.254.169.254 → 拒 + log WARN
- settings.EMBEDDING_API_URL=http://10.0.0.1（不在白名单且非 loopback）→ 拒

实现：embedder._api_embed_batch 在 `httpx.Client(... )` 之前调 `_gate_embed_url(url)`，
由 _gate_embed_url 调 ssrf_guard.validate_url（白名单 = ssrf_guard.DEFAULT_ALLOWED_HOSTS
+ EMBEDDING_API_URL 字面 host + EMBEDDING_API_URL_ALLOWED_HOSTS 设置）。

注意：pydantic-settings 模型不允许运行时 setattr 非声明字段（extra != "allow"），
故 monkeypatch 不能直接对 `settings.EMBEDDING_API_URL_ALLOWED_HOSTS = ...`；本批单测
改用两类实证：
  A) 直接调 _gate_embed_url(URL) 验守门放行/拒绝；
  B) monkeypatch 环境变量（DOTENV-style），让 pydantic 重新读；
  C) 改 model 内已有的声明字段（EMBEDDING_API_URL / LLM_BASE_URL）→ 走 getattr 链。

GWT (≥3 例)：
1. test_embed_url_default_whitelisted（默认 ark.cn-beijing.volces.com 在白名单内放行）
2. test_embed_url_imds_rejected（169.254.169.254 被 BLOCKED_HOSTS 拒绝）
3. test_embed_url_rfc1918_not_whitelisted_rejected（10.0.0.5 等非白名单私网被拒）
4. test_embed_url_explicit_untrusted_rejected（evil.example.com / google.com 等外网被拒）
5. test_gate_embed_url_logs_warning_on_reject（拒绝路径必 log WARN 含 [W-NEXT-EXE-SSRF-002] 标签）
6. test_api_embed_batch_skipped_when_url_blocked（_api_embed_batch 真 HTTP 短路：拒绝时 RuntimeError + 0 网络调用）
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.knowledge.importer import embedder


# ============================================================
# 工具：pydantic-settings 不允许 setattr 非声明字段。
# 本批验证 EMBEDDING_API_URL 字面 → 只需改已声明字段（monkeypatch OK）；
# 测试 EMBEDDING_API_URL_ALLOWED_HOSTS 路径用独立 reload path（见 test_5b）。
# ============================================================
def _set_declared(monkeypatch: pytest.MonkeyPatch, attr: str, value: object) -> None:
    """monkeypatch.setattr 到已声明字段；pydantic-settings Model 必须 hasattr."""
    assert hasattr(embedder.settings, attr), f"settings.{attr} 必须声明，否则改环境变量再 reload"
    monkeypatch.setattr(embedder.settings, attr, value, raising=True)


# ============================================================
# 1. 默认 EMBEDDING_API_URL 走 ark.cn-beijing.volces.com 字面 → 放行
# ============================================================
def test_embed_url_default_whitelisted() -> None:
    """GWT EXESSRF2-G1/PASS：默认 EMBEDDING_API_URL=https://ark.cn-beijing.volces.com/api/plan/v3
    的 host（ark.cn-beijing.volces.com）→ 白名单字面 → 守门放行。"""
    from app.config import settings as _settings

    assert _settings.EMBEDDING_API_URL, (
        f"本测试期望 .env EMBEDDING_API_URL 非空（ark.cn-beijing.volces.com 默认值）；"
        f"如为开发变体请改本测试或恢复 .env 默认。"
    )
    assert _settings.EMBEDDING_API_URL.startswith("https://ark.cn-beijing.volces.com"), (
        f"默认 EMBEDDING_API_URL 应是 ark 字面；got {_settings.EMBEDDING_API_URL!r}"
    )
    # 1.1：构造 ark 字面 URL → _gate_embed_url 不抛
    embedder._gate_embed_url(_settings.EMBEDDING_API_URL.rstrip("/") + "/embeddings")
    # 1.2：白名单函数返回 ark.cn-beijing.volces.com
    allowed = embedder._embed_ssrf_allowed_hosts()
    assert "ark.cn-beijing.volces.com" in allowed, (
        f"默认 EMBEDDING_API_URL 字面 host 必须进白名单；got {sorted(allowed)}"
    )
    # 1.3：localhost/127.0.0.1 仍进默认（项目依赖本机回环）
    assert "127.0.0.1" in allowed
    assert "localhost" in allowed
    # 1.4：完整 url（含 /embeddings 路径）能过 ssrf_guard 白名单
    embedder._gate_embed_url(f"{_settings.EMBEDDING_API_URL.rstrip('/')}/embeddings")


# ============================================================
# 2. IMDS endpoint（169.254.169.254）必拒 + log WARN
# ============================================================
def test_embed_url_imds_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """GWT EXESSRF2-G1/REJECT：EMBEDDING_API_URL=http://169.254.169.254 → 守门必拒 + log WARN。"""
    # 临时把 EMBEDDING_API_URL 改成 IMDS —— 守门内置 BLOCKED_HOSTS 必拒绝，
    # 即使攻击者改 .env EMBEDDING_API_URL=IMDS 也无用（拒绝位先于白名单匹配）。
    _set_declared(monkeypatch, "EMBEDDING_API_URL", "http://169.254.169.254/")
    _set_declared(monkeypatch, "LLM_BASE_URL", "http://169.254.169.254/")

    captured: list[str] = []

    def _sink(message) -> None:
        rec = message.record
        captured.append(f"{rec['level'].name}: {rec['message']}")

    from loguru import logger as _loguru_logger
    sink_id = _loguru_logger.add(_sink, level="WARNING")
    try:
        with pytest.raises(embedder._SSRFBlockedError) as exc_info:
            embedder._gate_embed_url("http://169.254.169.254/latest/meta-data/")
    finally:
        _loguru_logger.remove(sink_id)

    err = exc_info.value
    reason = (err.reason or "")
    assert any(tok in reason for tok in ("IMDS", "封禁", "白名单", "SSRF")), (
        f"IMDS 拒绝 reason 必须含 IMDS/封禁/白名单；got: {err.reason!r}"
    )
    assert err.host == "169.254.169.254"

    # log WARN 必出现 [W-NEXT-EXE-SSRF-002] 标签 + "embed 出站 URL 拒绝" 文案
    log_text = "\n".join(captured)
    assert "[W-NEXT-EXE-SSRF-002]" in log_text, (
        f"WARN 日志必带 [W-NEXT-EXE-SSRF-002] 标签；got: {log_text[:300]!r}"
    )
    assert "embed 出站 URL 拒绝" in log_text
    assert "169.254.169.254" in log_text


# ============================================================
# 3. RFC1918 私网（10.0.0.5 / 192.168.1.1）——不在白名单字面时必拒
# ============================================================
@pytest.mark.parametrize("evil_host", [
    "http://10.0.0.5/",         # 10/8 私网，不在白名单（仅 10.0.0.1 允许）
    "http://192.168.1.1/",      # 192.168/16 不在白名单（仅 192.168.85.101）
    "http://172.20.5.5/",       # 172.16/12 私网
])
def test_embed_url_rfc1918_not_whitelisted_rejected(monkeypatch: pytest.MonkeyPatch, evil_host: str) -> None:
    """GWT EXESSRF2-G1/REJECT：RFC1918 私网段但不在白名单字面 → 必拒。"""
    _set_declared(monkeypatch, "EMBEDDING_API_URL", evil_host)
    _set_declared(monkeypatch, "LLM_BASE_URL", evil_host)

    with pytest.raises(embedder._SSRFBlockedError) as exc_info:
        embedder._gate_embed_url(evil_host + "v1/embeddings")
    reason = (exc_info.value.reason or "")
    assert "白名单" in reason or "高危段" in reason or "私网" in reason.lower(), (
        f"私网拒绝 reason 必须含「白名单」/「高危段」/「私网」；got: {reason!r}"
    )


# ============================================================
# 4. 任意未白名单公网域名 → 必拒（绝对白名单模型）
# ============================================================
@pytest.mark.parametrize("evil_url", [
    "https://evil.example.com/v1/embeddings",
    "https://www.google.com/v1/embeddings",
    "http://attacker.cn/v1/embeddings",
])
def test_embed_url_explicit_untrusted_rejected(monkeypatch: pytest.MonkeyPatch, evil_url: str) -> None:
    """GWT EXESSRF2-G1/REJECT：白名单外任意外网 → 必拒（绝对白名单模型，禁后缀通配）。"""
    # 把两路 URL 都设成 evil_url 排除合法 host 干扰
    _set_declared(monkeypatch, "EMBEDDING_API_URL", "")
    _set_declared(monkeypatch, "LLM_BASE_URL", evil_url)

    with pytest.raises(embedder._SSRFBlockedError) as exc_info:
        embedder._gate_embed_url(evil_url)
    assert "白名单" in exc_info.value.reason, (
        f"外网拒绝必须含「白名单」文案；got: {exc_info.value.reason!r}"
    )


# ============================================================
# 5. 拒绝路径必 log WARN（覆盖率：每个拒绝分支都被审计可见）
# ============================================================
def test_gate_embed_url_logs_warning_on_reject(monkeypatch: pytest.MonkeyPatch) -> None:
    """GWT EXESSRF2-G1/MONITOR：拒绝路径必 log WARN 供安全审计。"""
    _set_declared(monkeypatch, "EMBEDDING_API_URL", "")
    _set_declared(monkeypatch, "LLM_BASE_URL", "")

    captured: list[str] = []

    def _sink(message) -> None:
        rec = message.record
        captured.append(f"{rec['level'].name}: {rec['message']}")

    from loguru import logger as _loguru_logger
    sink_id = _loguru_logger.add(_sink, level="WARNING")
    try:
        with pytest.raises(embedder._SSRFBlockedError):
            embedder._gate_embed_url("https://evil.example.com/api/x")
    finally:
        _loguru_logger.remove(sink_id)

    log_text = "\n".join(captured)
    assert "[W-NEXT-EXE-SSRF-002]" in log_text, f"WARN 必带守卫标签；got {log_text!r}"
    assert re.search(r"embed 出站 URL 拒绝", log_text), f"WARN 必含拒绝文案；got {log_text!r}"


# ============================================================
# 6. _api_embed_batch 入口：URL 被拒时 HTTP **零外发**（不静默）
# ============================================================
def test_api_embed_batch_skipped_when_url_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """GWT EXESSRF2-G1/PROBE：白名单不通过 → _api_embed_batch 短路抛 SSRFBlockedError；
    httpx.Client.post **不被调用**（绝不静默外发）。"""
    # 把 EMBEDDING_API_URL 调到 IMDS，让 _gate_embed_url 必拒
    _set_declared(monkeypatch, "EMBEDDING_API_URL", "http://169.254.169.254/")
    _set_declared(monkeypatch, "LLM_BASE_URL", "http://169.254.169.254/")
    _set_declared(monkeypatch, "EMBEDDING_API_KEY", "test-key")

    # 直接调 _api_embed_batch 验证：抛 SSRFBlockedError（不是静默吞）
    with pytest.raises(embedder._SSRFBlockedError) as exc_info:
        embedder._api_embed_batch(["hello"])
    msg = str(exc_info.value)
    assert any(tok in msg.lower() for tok in ("imds", "白名单", "封禁", "ssrf")), (
        f"拒绝路径必须含 IMDS/白名单/封禁/SSRF 文案；got: {msg[:200]!r}"
    )

    # 关键：守门是 _api_embed_batch **第一句**网络前动作 ⇒ httpx 不可构造
    # 用 grep 源码静态验证 _gate_embed_url 在 httpx.Client 之前；
    src_path = Path(embedder.__file__)
    src = src_path.read_text(encoding="utf-8")
    func_body_start = src.index("def _api_embed_batch(")
    func_body_end = src.index("\ndef ", func_body_start + 1)
    body = src[func_body_start:func_body_end]
    pos_gate = body.index("_gate_embed_url(")
    pos_httpx = body.index("httpx.Client(")
    assert pos_gate < pos_httpx, (
        "_gate_embed_url 必须在 httpx.Client 之前执行（HTTP 零外发靠源码位序保证）"
        f"；pos_gate={pos_gate}, pos_httpx={pos_httpx}"
    )
