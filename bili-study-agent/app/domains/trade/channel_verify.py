# -*- coding: utf-8 -*-
"""真实支付渠道回调验签闸门（W-NEXT-PAYGATE-001，承接 tracker 346 登记缺口）。

背景：`settle_payment` 原先用记录内金额直接入账，`mock_notify` 仅校验 mock 渠道；
真实渠道（alipay/wechat_pay）回调此前未接线。本模块把「接入前置闸门」先建好——
真实渠道一接入即生效，不接真实渠道时闸门因缺 key 全量拒绝（fail closed）。

闸门四关（确定性策略：任何一关不过 = 拒绝 + 审计日志，无旁路）：
  ① 渠道白名单：channel ∈ {alipay, wechat_pay}；mock/未知/线下渠道拒绝
  ② 验商户：verify_merchant —— 回调 merchant_id vs settings.PAY_MERCHANT_ID（分单位精确串比较）
  ③ 验签：verify_signature —— RSA2（SHA256withRSA，PKCS1v15），待签串按支付宝官方
     规则规范化（排除 sign/sign_type/空值，key ASCII 升序，k=v 用 & 连接）；
     公钥从 settings.PAY_ALIPAY_PUBLIC_KEY / PAY_WECHAT_API_V3_KEY 读取，
     缺 key / 公钥损坏 → 50301 DEPENDENCY_UNAVAILABLE（依赖未配置），绝不放行
  ④ 验金额：verify_amount —— 回调金额 vs 订单 payable_amount，分单位整数比较
     （Decimal(str()) 规避二进制浮点尾差，对齐对账 _cents 口径）

审计：所有拒绝经 `audit_reject` 输出单行结构化 JSON（[PAY-GATE-AUDIT] 前缀），
供日志采集/告警；DB 级审计表为后续项（见完成报告自批判）。

红线遵守：不碰 settle_payment 本体、不改既有契约（响应壳/错误码表零新增）；
config.py 仅追加 PAY_* 字段（默认空=闸门全拒）。
"""
from __future__ import annotations

import base64
import json
import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.common.error_codes import FORBIDDEN, VALIDATION
from app.common.exceptions import AppException, DependencyUnavailableError
from app.config import settings

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────
# 渠道白名单（闸门①）：真实在线回调渠道；mock/线下渠道不走本闸门
# ────────────────────────────────────────────────────────────
GATE_CHANNELS = {"alipay", "wechat_pay"}

# 渠道 → 公钥配置字段（settings；缺 key = 依赖未配置 → 50301 拒绝）
_CHANNEL_KEY_FIELD = {
    "alipay": "PAY_ALIPAY_PUBLIC_KEY",
    "wechat_pay": "PAY_WECHAT_API_V3_KEY",
}

# 参与签名的参数排除项（对齐支付宝 RSA2 官方规则：sign/sign_type 不参与签名）
_SIGN_EXCLUDED_KEYS = {"sign", "sign_type"}

# 拒绝审计日志前缀（采集/告警锚点）
_AUDIT_PREFIX = "[PAY-GATE-AUDIT]"


def audit_reject(reason: str, channel: str | None = None, **ctx: object) -> None:
    """闸门拒绝审计：单行结构化 JSON，绝不出抛异常阻断主流程（审计失败仅告警）。
    供 service 分派点（渠道/记录不匹配、入口渠道白名单）与闸门内部共同使用——
    确保所有拒绝路径都有 [PAY-GATE-AUDIT] 落日志。"""
    rec: dict = {"event": "PAY_NOTIFY_REJECT", "reason": reason}
    if channel is not None:
        rec["channel"] = channel
    rec.update(ctx)
    try:
        logger.warning("%s %s", _AUDIT_PREFIX, json.dumps(rec, ensure_ascii=False, default=str))
    except Exception:  # pragma: no cover - 审计序列化失败不阻断拒绝主流程
        logger.warning("%s %s reason=%s ctx=%r", _AUDIT_PREFIX, reason, reason, ctx)


def _canonical_string(payload: dict) -> str:
    """RSA2 待签串规范化（支付宝官方规则）：排除 sign/sign_type 与空值，
    按 key ASCII 升序 `k=v` 用 `&` 连接。值一律 str()（渠道回调均为字符串语义）。"""
    items = []
    for k in sorted(payload.keys()):
        if k in _SIGN_EXCLUDED_KEYS:
            continue
        v = payload[k]
        if v is None or (isinstance(v, str) and v == ""):
            continue
        items.append(f"{k}={v}")
    return "&".join(items)


def _load_public_key(channel: str):
    """渠道公钥加载：支持 PEM（-----BEGIN PUBLIC KEY-----）或 base64 DER 裸文。
    缺 key / 解析失败 → DependencyUnavailableError（50301，fail closed 绝不放行）。"""
    field = _CHANNEL_KEY_FIELD.get(channel)
    if field is None:
        raise AppException(VALIDATION, f"非法支付渠道：{channel}")
    key_text = (str(getattr(settings, field, "") or "")).strip()
    if not key_text:
        raise DependencyUnavailableError("支付渠道依赖未配置，请稍后重试")
    try:
        if "-----BEGIN" in key_text:
            return serialization.load_pem_public_key(key_text.encode("utf-8"))
        return serialization.load_der_public_key(base64.b64decode(key_text))
    except Exception as exc:
        # 公钥损坏同样是依赖配置问题：fail closed，原始异常仅入日志（50301 脱敏契约）
        logger.error("[PAY-GATE] 渠道 %s 公钥解析失败（%s）：%s", channel, field, exc)
        raise DependencyUnavailableError("支付渠道依赖未配置，请稍后重试") from exc


def verify_merchant(merchant_id: str | None, channel: str | None = None) -> bool:
    """闸门② 验商户：回调 merchant_id 与 settings.PAY_MERCHANT_ID 精确匹配。
    - 期望商户号未配置 → 50301（依赖未配置，fail closed）
    - 不匹配 / 缺失 → 40300 拒绝 + 审计
    """
    expected = (str(getattr(settings, "PAY_MERCHANT_ID", "") or "")).strip()
    if not expected:
        audit_reject("MERCHANT_NOT_CONFIGURED", channel=channel)
        raise DependencyUnavailableError("支付渠道依赖未配置，请稍后重试")
    got = (str(merchant_id).strip()) if merchant_id is not None else ""
    if got != expected:
        audit_reject("MERCHANT_MISMATCH", channel=channel,
                      merchant_id=got, expected_len=len(expected))
        raise AppException(FORBIDDEN, "支付回调商户校验失败")
    return True


def verify_signature(channel: str, payload: dict, signature: str | None) -> bool:
    """闸门③ 验签：RSA2（SHA256withRSA，PKCS1v15）。
    - 渠道不在白名单 → 42200
    - payload/signature 缺失 → 40300
    - 缺 key / 公钥损坏 → 50301（绝不放行）
    - 签名 base64 非法 / 验签不过 / 任何意外 → 40300（全路径拒绝 + 审计，无旁路）
    """
    if channel not in GATE_CHANNELS:
        audit_reject("UNKNOWN_CHANNEL", channel=channel)
        raise AppException(VALIDATION, f"非法支付渠道：{channel}")
    if not isinstance(payload, dict) or not payload or not signature:
        audit_reject("SIGNATURE_MISSING", channel=channel,
                      has_payload=bool(payload), has_signature=bool(signature))
        raise AppException(FORBIDDEN, "支付回调验签失败")

    try:
        public_key = _load_public_key(channel)  # 缺 key/坏 key → 50301（fail closed）
    except DependencyUnavailableError:
        audit_reject("KEY_NOT_CONFIGURED", channel=channel)
        raise
    if not getattr(public_key, "public_bytes", None):  # 非预期密钥对象类型兜底
        audit_reject("KEY_TYPE_INVALID", channel=channel)
        raise DependencyUnavailableError("支付渠道依赖未配置，请稍后重试")

    canonical = _canonical_string(payload)
    try:
        sig_bytes = base64.b64decode(signature, validate=True)
    except Exception:
        audit_reject("SIGNATURE_MALFORMED", channel=channel)
        raise AppException(FORBIDDEN, "支付回调验签失败") from None
    try:
        public_key.verify(sig_bytes, canonical.encode("utf-8"),
                          padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature:
        audit_reject("SIGNATURE_TAMPERED", channel=channel, canonical_head=canonical[:200])
        raise AppException(FORBIDDEN, "支付回调验签失败") from None
    except Exception as exc:  # 密钥类型/填充不匹配等任何意外 → 一律拒绝，无旁路
        audit_reject("SIGNATURE_ERROR", channel=channel, error=type(exc).__name__)
        raise AppException(FORBIDDEN, "支付回调验签失败") from exc
    return True


def _to_cents(value: object, field: str) -> int:
    """金额 → 分（整数）：Decimal(str()) 规避二进制浮点尾差（0.1+0.05≠0.15），
    ROUND_HALF_UP 取整与对账 _cents（round(float*100)）口径一致（四舍五入只影响
    亚分级表示尾差，真实渠道金额均为两位小数，整分级差异永不跨舍入边界）。
    非法/负数 → 42200 拒绝（资金口径绝不猜测）。"""
    try:
        q = (Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        audit_reject("AMOUNT_MALFORMED", field=field, got=repr(value))
        raise AppException(VALIDATION, f"回调金额格式非法：{field}") from None
    cents = int(q)
    if cents < 0:
        audit_reject("AMOUNT_NEGATIVE", field=field, got=str(value))
        raise AppException(VALIDATION, f"回调金额非法（负数）：{field}")
    return cents


def verify_amount(notify_amount: object, payable_amount: object, channel: str | None = None) -> bool:
    """闸门④ 验金额：回调金额 vs 应付金额，分单位整数比较（对齐对账 _cents 口径）。
    任何格式非法 / 差 1 分 → 42200 拒绝 + 审计。0 元单（全额券）允许 0==0 通过。"""
    notify_cents = _to_cents(notify_amount, "notify_amount")
    payable_cents = _to_cents(payable_amount, "payable_amount")
    if notify_cents != payable_cents:
        audit_reject("AMOUNT_MISMATCH", channel=channel,
                      notify_cents=notify_cents, payable_cents=payable_cents)
        raise AppException(VALIDATION, "回调金额与应付金额不一致")
    return True


def run_channel_gates(
    *, channel: str, payload: dict, signature: str | None,
    merchant_id: str | None, notify_amount: object, payable_amount: object,
) -> bool:
    """闸门编排（确定性顺序：②商户 → ③签名 → ④金额）。
    三关全过返回 True；任何一关不过直接抛 AppException（闸门内部已审计），无旁路。"""
    verify_merchant(merchant_id, channel=channel)
    verify_signature(channel, payload, signature)
    verify_amount(notify_amount, payable_amount, channel=channel)
    logger.info("[PAY-GATE] 渠道 %s 回调闸门三关全过（merchant/signature/amount）", channel)
    return True
