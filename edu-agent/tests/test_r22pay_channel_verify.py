# -*- coding: utf-8 -*-
"""W-NEXT-PAYGATE-001 测试：真实支付渠道回调验签闸门（承接 tracker 346）。

覆盖（全部离线单测，无真实后端依赖；RSA 密钥对测试内嵌生成，不入 env/.env）：
- verify_signature：正确签名过 / payload 篡改拒 / 签名篡改拒 / 缺 key 50301 /
  公钥损坏 50301 / 未知渠道拒 / 缺签名拒 / PEM 与 base64-DER 两种公钥格式
- verify_amount：相等过 / 差 1 分拒 / 浮点尾差（0.1+0.05 vs 0.15）过 /
  非法格式拒 / 负数拒 / 0 元单过
- verify_merchant：匹配过 / 不匹配拒 / 未配置 50301 / 缺失拒
- run_channel_gates：确定性顺序（商户→签名→金额）+ 每次拒绝均有 [PAY-GATE-AUDIT] 审计
- service.channel_notify 分派：mock/未知渠道拒 / 渠道与记录不一致拒 /
  闸门全过才 settle（篡改不落账）/ 幂等 duplicate 兜底
- service.mock_notify 兼容回归：提取 _settle_once 后行为不变（mock 过/非 mock 拒/40420）
"""
from __future__ import annotations

import base64
import asyncio

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.common.exceptions import AppException, DependencyUnavailableError
from app.config import settings
from app.domains.trade import channel_verify as cv
from app.domains.trade.payment import service as svc


# ════════════════════════════════════════════════════════════
# fixture：测试内嵌生成 RSA 密钥对（绝不出现在 env / .env / 配置）
# ════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def rsa_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = private_key.public_key()
    pem = pub.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    der_b64 = base64.b64encode(pub.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo,
    )).decode("ascii")
    return private_key, pem, der_b64


def rsa2_sign(private_key, payload: dict) -> str:
    """按闸门同一规范化规则生成 RSA2 签名（base64）。"""
    canonical = cv._canonical_string(payload)
    sig = private_key.sign(canonical.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode("ascii")


PAYLOAD = {
    "app_id": "2026000000000001", "out_trade_no": "P-1-260918-abcdef",
    "total_amount": "12.30", "seller_id": "2026000000000001",
    "trade_status": "TRADE_SUCCESS", "trade_no": "ALI-TRD-1",
}


@pytest.fixture()
def with_keys(monkeypatch, rsa_pair):
    """给 settings 注入测试公钥与商户号（仅进程内 monkeypatch，不落 env）。"""
    _, pem, der_b64 = rsa_pair
    monkeypatch.setattr(settings, "PAY_ALIPAY_PUBLIC_KEY", pem)
    monkeypatch.setattr(settings, "PAY_WECHAT_API_V3_KEY", der_b64)
    monkeypatch.setattr(settings, "PAY_MERCHANT_ID", "2026000000000001")
    return rsa_pair


# ════════════════════════════════════════════════════════════
# 闸门③ 验签
# ════════════════════════════════════════════════════════════
class TestVerifySignature:
    def test_valid_signature_pass_alipay_pem(self, with_keys, rsa_pair, caplog):
        """正确 RSA2 签名（PEM 公钥）→ 通过。"""
        priv, _, _ = rsa_pair
        with caplog.at_level("WARNING"):
            assert cv.verify_signature("alipay", dict(PAYLOAD), rsa2_sign(priv, PAYLOAD)) is True
        assert not any("PAY-GATE-AUDIT" in r.message for r in caplog.records)

    def test_valid_signature_pass_wechat_der(self, with_keys, rsa_pair):
        """正确 RSA2 签名（base64-DER 公钥，wechat_pay）→ 通过。"""
        priv, _, _ = rsa_pair
        payload = dict(PAYLOAD, amount="1")
        assert cv.verify_signature("wechat_pay", payload, rsa2_sign(priv, payload)) is True

    def test_tampered_payload_rejected(self, with_keys, rsa_pair, caplog):
        """payload 篡改（金额 12.30→99.99，签名不变）→ 拒绝 + 审计。"""
        priv, _, _ = rsa_pair
        sig = rsa2_sign(priv, PAYLOAD)
        tampered = dict(PAYLOAD, total_amount="99.99")
        with caplog.at_level("WARNING"):
            with pytest.raises(AppException) as ei:
                cv.verify_signature("alipay", tampered, sig)
        assert ei.value.code == "40300"
        assert any("SIGNATURE_TAMPERED" in r.message for r in caplog.records)

    def test_tampered_signature_rejected(self, with_keys, rsa_pair, caplog):
        """签名篡改（合法签名换伪造值）→ 拒绝 + 审计。"""
        _, _, _ = rsa_pair
        forged = base64.b64encode(b"forged-signature-bytes-0000").decode()
        with caplog.at_level("WARNING"):
            with pytest.raises(AppException) as ei:
                cv.verify_signature("alipay", dict(PAYLOAD), forged)
        assert ei.value.code == "40300"
        assert any("SIGNATURE_TAMPERED" in r.message for r in caplog.records)

    def test_wrong_key_signature_rejected(self, with_keys):
        """用另一把私钥签发（密钥替换攻击）→ 拒绝。"""
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with pytest.raises(AppException) as ei:
            cv.verify_signature("alipay", dict(PAYLOAD), rsa2_sign(other, PAYLOAD))
        assert ei.value.code == "40300"

    def test_missing_key_50301_fail_closed(self, monkeypatch, rsa_pair, caplog):
        """缺 key：PAY_ALIPAY_PUBLIC_KEY 为空 → 50301（依赖未配置），绝不放行。"""
        priv, _, _ = rsa_pair
        monkeypatch.setattr(settings, "PAY_ALIPAY_PUBLIC_KEY", "")
        monkeypatch.setattr(settings, "PAY_MERCHANT_ID", "m1")
        with caplog.at_level("WARNING"):
            with pytest.raises(DependencyUnavailableError) as ei:
                cv.verify_signature("alipay", dict(PAYLOAD), rsa2_sign(priv, PAYLOAD))
        assert str(ei.value.code) == "50301"
        assert ei.value.http_status == 503
        assert any("KEY_NOT_CONFIGURED" in r.message for r in caplog.records)

    def test_corrupted_key_50301_fail_closed(self, monkeypatch, rsa_pair):
        """公钥损坏（非 PEM/DER 乱文）→ 50301 fail closed，绝不放行。"""
        priv, _, _ = rsa_pair
        monkeypatch.setattr(settings, "PAY_ALIPAY_PUBLIC_KEY", "not-a-valid-key!!")
        monkeypatch.setattr(settings, "PAY_MERCHANT_ID", "m1")
        with pytest.raises(DependencyUnavailableError) as ei:
            cv.verify_signature("alipay", dict(PAYLOAD), rsa2_sign(priv, PAYLOAD))
        assert str(ei.value.code) == "50301"

    def test_unknown_channel_rejected(self, with_keys):
        """未知渠道 → 42200 拒绝。"""
        with pytest.raises(AppException) as ei:
            cv.verify_signature("stripe", dict(PAYLOAD), "x")
        assert ei.value.code == "42200"

    def test_missing_signature_rejected(self, with_keys):
        """缺签名 → 40300 拒绝（不接受无签名回调）。"""
        with pytest.raises(AppException) as ei:
            cv.verify_signature("alipay", dict(PAYLOAD), None)
        assert ei.value.code == "40300"

    def test_non_base64_signature_rejected(self, with_keys):
        """签名非 base64 → 40300 拒绝。"""
        with pytest.raises(AppException) as ei:
            cv.verify_signature("alipay", dict(PAYLOAD), "!!!not-base64!!!")
        assert ei.value.code == "40300"


# ════════════════════════════════════════════════════════════
# 闸门④ 验金额（分单位整数比较）
# ════════════════════════════════════════════════════════════
class TestVerifyAmount:
    def test_equal_pass(self):
        assert cv.verify_amount("12.30", 12.30) is True

    def test_off_by_one_cent_rejected(self, caplog):
        """差 1 分：12.30 vs 12.31 → 拒绝 + 审计。"""
        with caplog.at_level("WARNING"):
            with pytest.raises(AppException) as ei:
                cv.verify_amount("12.30", "12.31")
        assert ei.value.code == "42200"
        assert any("AMOUNT_MISMATCH" in r.message for r in caplog.records)

    def test_float_tail_pass(self):
        """浮点尾差口径：0.1+0.05 vs 0.15 → 通过（与对账 _cents 一致）。"""
        assert cv.verify_amount(0.1 + 0.05, 0.15) is True

    def test_zero_amount_pass(self):
        """0 元单（全额券）0==0 → 通过。"""
        assert cv.verify_amount("0", "0.00") is True

    def test_malformed_amount_rejected(self):
        with pytest.raises(AppException) as ei:
            cv.verify_amount("abc", "1.00")
        assert ei.value.code == "42200"

    def test_negative_amount_rejected(self):
        with pytest.raises(AppException) as ei:
            cv.verify_amount("-1.00", "1.00")
        assert ei.value.code == "42200"

    def test_none_amount_rejected(self):
        with pytest.raises(AppException) as ei:
            cv.verify_amount(None, "1.00")
        assert ei.value.code == "42200"


# ════════════════════════════════════════════════════════════
# 闸门② 验商户
# ════════════════════════════════════════════════════════════
class TestVerifyMerchant:
    def test_match_pass(self, with_keys):
        assert cv.verify_merchant("2026000000000001") is True

    def test_mismatch_rejected(self, with_keys, caplog):
        """商户不匹配 → 40300 拒绝 + 审计。"""
        with caplog.at_level("WARNING"):
            with pytest.raises(AppException) as ei:
                cv.verify_merchant("9999000000000009")
        assert ei.value.code == "40300"
        assert any("MERCHANT_MISMATCH" in r.message for r in caplog.records)

    def test_missing_merchant_id_rejected(self, with_keys):
        with pytest.raises(AppException) as ei:
            cv.verify_merchant(None)
        assert ei.value.code == "40300"

    def test_expected_not_configured_50301(self, monkeypatch, caplog):
        """期望商户号未配置 → 50301 fail closed（与缺 key 同一确定性策略）。"""
        monkeypatch.setattr(settings, "PAY_MERCHANT_ID", "")
        with caplog.at_level("WARNING"):
            with pytest.raises(DependencyUnavailableError) as ei:
                cv.verify_merchant("2026000000000001")
        assert str(ei.value.code) == "50301"
        assert any("MERCHANT_NOT_CONFIGURED" in r.message for r in caplog.records)


# ════════════════════════════════════════════════════════════
# 闸门编排：确定性顺序 + 无旁路
# ════════════════════════════════════════════════════════════
class TestRunChannelGates:
    def test_all_pass(self, with_keys, rsa_pair):
        priv, _, _ = rsa_pair
        ok = cv.run_channel_gates(
            channel="alipay", payload=dict(PAYLOAD), signature=rsa2_sign(priv, PAYLOAD),
            merchant_id="2026000000000001", notify_amount="12.30", payable_amount=12.30,
        )
        assert ok is True

    def test_deterministic_order_merchant_first(self, with_keys, caplog):
        """商户错 + 签名错并发：确定性策略先拒商户（顺序可审计，非随机路径）。"""
        with caplog.at_level("WARNING"):
            with pytest.raises(AppException) as ei:
                cv.run_channel_gates(
                    channel="alipay", payload=dict(PAYLOAD), signature="bad",
                    merchant_id="wrong-merchant", notify_amount="12.30", payable_amount=12.30,
                )
        assert ei.value.code == "40300"
        reasons = [r.message for r in caplog.records if "PAY-GATE-AUDIT" in r.message]
        assert len(reasons) == 1 and "MERCHANT_MISMATCH" in reasons[0]

    def test_any_gate_failure_no_bypass(self, with_keys, rsa_pair, caplog):
        """商户/签名过、金额差 1 分 → 仍然拒绝（三关缺一不可）。"""
        priv, _, _ = rsa_pair
        with caplog.at_level("WARNING"):
            with pytest.raises(AppException) as ei:
                cv.run_channel_gates(
                    channel="alipay", payload=dict(PAYLOAD), signature=rsa2_sign(priv, PAYLOAD),
                    merchant_id="2026000000000001", notify_amount="12.29", payable_amount=12.30,
                )
        assert ei.value.code == "42200"
        assert any("AMOUNT_MISMATCH" in r.message for r in caplog.records)


# ════════════════════════════════════════════════════════════
# service.channel_notify 分派 + mock_notify 兼容（fake repo/transaction，无 DB）
# ════════════════════════════════════════════════════════════
class _FakeTx:
    async def __aenter__(self):
        return object(), object()

    async def __aexit__(self, *exc):
        return False


class _FakeRepo:
    def __init__(self, rows: dict):
        self._rows = rows

    async def get_payment(self, payment_no):
        return self._rows.get(payment_no)


class _FakeWrite:
    def __init__(self):
        self.calls: list[dict] = []

    async def settle_payment(self, **kw):
        self.calls.append(kw)
        return {"applied": True, "order_status_change": True}


def _row(channel="alipay", payment_no="P-1-TEST", payable=12.30):
    return {
        "id": 1, "institution_id": 1, "payment_no": payment_no, "order_id": 10,
        "payment_channel": channel, "payment_status": "pending", "amount": payable,
        "third_party_trade_no": None, "paid_at": None, "refund_at": None,
        "created_at": "2026-09-18 00:00:00", "updated_at": "2026-09-18 00:00:00",
        "order_no": "O-TEST", "order_status": "pending", "payable_amount": payable,
    }


@pytest.fixture()
def wired(monkeypatch):
    """替换 service 的 repo/write/transaction 为内存 fake（settle 语义由 fake 记录调用）。"""
    repo, write = _FakeRepo({}), _FakeWrite()
    monkeypatch.setattr(svc, "_payment_repo", repo)
    monkeypatch.setattr(svc, "_payment_write", write)
    monkeypatch.setattr(svc, "transaction", _FakeTx)
    return repo, write


def _notify(channel="alipay", payment_no="P-1-TEST", priv=None, payload=None,
            sign_payload=None, merchant="2026000000000001", amount="12.30"):
    payload = dict(payload or PAYLOAD)
    # sign_payload：模拟「签名对原报文计算、实际报文被篡改」的攻击形态
    sig = rsa2_sign(priv, dict(sign_payload) if sign_payload is not None else payload) if priv is not None else None
    return svc.channel_notify(
        channel, payment_no, payload=payload, signature=sig, merchant_id=merchant,
        notify_amount=amount, third_party_trade_no="TRD-X",
    )


class TestChannelNotifyDispatch:
    def test_gates_pass_then_settle_once(self, with_keys, wired, rsa_pair):
        """闸门三关全过 → 走与 mock 相同的单事务结算（幂等核心，settle 恰好一次）。"""
        priv, _, _ = rsa_pair
        repo, write = wired
        repo._rows["P-1-TEST"] = _row()
        r = asyncio.run(_notify(priv=priv))
        assert r.applied is True and r.order_no == "O-TEST" and r.message == "支付成功"
        assert len(write.calls) == 1
        assert write.calls[0]["payment_no"] == "P-1-TEST"
        assert write.calls[0]["third_party_trade_no"] == "TRD-X"

    def test_tampered_notify_never_settles(self, with_keys, wired, rsa_pair, caplog):
        """篡改回调（签名对原报文计算、金额字段被改）→ 拒绝且 settle 零调用（拒绝在落账之前）。"""
        priv, _, _ = rsa_pair
        repo, write = wired
        repo._rows["P-1-TEST"] = _row()
        with caplog.at_level("WARNING"):
            with pytest.raises(AppException):
                asyncio.run(_notify(payload=dict(PAYLOAD, total_amount="0.01"),
                                    sign_payload=PAYLOAD, priv=priv))
        assert write.calls == []
        assert any("SIGNATURE_TAMPERED" in r.message for r in caplog.records)

    def test_mock_channel_rejected_on_gate_entry(self, with_keys, wired):
        """mock 渠道不走渠道回调入口（走既有 mock-notify，鉴权语义零变化）。"""
        repo, write = wired
        repo._rows["P-1-TEST"] = _row(channel="mock")
        with pytest.raises(AppException) as ei:
            asyncio.run(_notify(channel="mock"))
        assert ei.value.code == "42200"
        assert write.calls == []

    def test_unknown_channel_rejected(self, with_keys, wired):
        repo, write = wired
        repo._rows["P-1-TEST"] = _row()
        with pytest.raises(AppException) as ei:
            asyncio.run(_notify(channel="crypto_pay"))
        assert ei.value.code == "42200"
        assert write.calls == []

    def test_channel_record_mismatch_rejected(self, with_keys, wired, rsa_pair, caplog):
        """回调渠道与支付记录渠道不一致（wechat 回调打在 alipay 单上）→ 拒绝 + 审计。"""
        priv, _, _ = rsa_pair
        repo, write = wired
        repo._rows["P-1-TEST"] = _row(channel="wechat_pay")
        with caplog.at_level("WARNING"):
            with pytest.raises(AppException) as ei:
                asyncio.run(_notify(channel="alipay", priv=priv))
        assert ei.value.code == "40300"
        assert any("CHANNEL_RECORD_MISMATCH" in r.message for r in caplog.records)
        assert write.calls == []

    def test_missing_payment_404(self, with_keys, wired):
        repo, _ = wired
        with pytest.raises(AppException) as ei:
            asyncio.run(_notify(payment_no="P-NOT-EXIST"))
        assert ei.value.code == "40420"


class TestMockNotifyCompat:
    """_settle_once 提取后 mock_notify 行为不变（回归红线：mock 不动）。"""

    def test_mock_channel_applies(self, wired):
        repo, write = wired
        repo._rows["P-MOCK"] = _row(channel="mock", payment_no="P-MOCK")
        r = asyncio.run(svc.mock_notify("P-MOCK", "TRD-MOCK"))
        assert r.applied is True and r.message == "支付成功"
        assert len(write.calls) == 1

    def test_non_mock_channel_rejected_40021(self, wired):
        """原红线保持：mock 回调仅限 mock 模拟渠道。"""
        repo, write = wired
        repo._rows["P-ALI"] = _row(channel="alipay", payment_no="P-ALI")
        with pytest.raises(AppException) as ei:
            asyncio.run(svc.mock_notify("P-ALI", None))
        assert ei.value.code == "40021"
        assert write.calls == []

    def test_missing_payment_404(self, wired):
        with pytest.raises(AppException) as ei:
            asyncio.run(svc.mock_notify("P-NONE", None))
        assert ei.value.code == "40420"

    def test_duplicate_key_idempotent(self, wired):
        """并发唯一键冲突 → applied=False（幂等兜底，与原实现一致）。"""
        repo, write = wired
        repo._rows["P-MOCK"] = _row(channel="mock", payment_no="P-MOCK")

        async def _dup(**kw):
            raise Exception("(1062, 'Duplicate entry')")

        write.settle_payment = _dup
        r = asyncio.run(svc.mock_notify("P-MOCK", None))
        assert r.applied is False and r.message == "已处理（幂等）"
