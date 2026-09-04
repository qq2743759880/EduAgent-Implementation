# -*- coding: utf-8 -*-
"""测试密码强度校验（Phase 1 安全加固）。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.auth.schemas import UserRegister


class TestPasswordStrength:
    """UserRegister._validate_password_strength 单元测试。"""

    def test_valid_password(self):
        """满足所有复杂度要求的密码应通过校验。"""
        reg = UserRegister(
            account="testuser",
            nickname="测试用户",
            password="Abc1234!",
            mobile="13800000001",
        )
        assert reg.password == "Abc1234!"

    def test_too_short(self):
        """少于 8 位应被 Pydantic min_length 拒绝。"""
        with pytest.raises(PydanticValidationError):
            UserRegister(
                account="testuser",
                nickname="test",
                password="Ab1!",
                mobile="13800000001",
            )

    def test_no_uppercase(self):
        """缺少大写字母应被拒绝。"""
        with pytest.raises(PydanticValidationError, match="大写字母"):
            UserRegister(
                account="testuser",
                nickname="test",
                password="abc1234!",
                mobile="13800000001",
            )

    def test_no_lowercase(self):
        """缺少小写字母应被拒绝。"""
        with pytest.raises(PydanticValidationError, match="小写字母"):
            UserRegister(
                account="testuser",
                nickname="test",
                password="ABC1234!",
                mobile="13800000001",
            )

    def test_no_digit(self):
        """缺少数字应被拒绝。"""
        with pytest.raises(PydanticValidationError, match="数字"):
            UserRegister(
                account="testuser",
                nickname="test",
                password="Abcdefg!",
                mobile="13800000001",
            )

    def test_no_special_char(self):
        """缺少特殊字符应被拒绝。"""
        with pytest.raises(PydanticValidationError, match="特殊字符"):
            UserRegister(
                account="testuser",
                nickname="test",
                password="Abc12345",
                mobile="13800000001",
            )

    def test_all_special_chars_accepted(self):
        """各种特殊字符都应被接受。"""
        for ch in "!@#$%^&*()_+-=[]{}|;:',.<>?/`~":
            reg = UserRegister(
                account="testuser",
                nickname="test",
                password=f"Abc1234{ch}",
                mobile="13800000001",
            )
            assert reg.password == f"Abc1234{ch}"


class TestAccountSanitization:
    """UserRegister._sanitize_account 单元测试。"""

    def test_valid_account(self):
        reg = UserRegister(
            account="test_user-123",
            nickname="test",
            password="Abc1234!",
            mobile="13800000001",
        )
        assert reg.account == "test_user-123"

    def test_account_with_special_chars(self):
        """账号含特殊字符应被拒绝。"""
        with pytest.raises(PydanticValidationError):
            UserRegister(
                account="test@user",
                nickname="test",
                password="Abc1234!",
                mobile="13800000001",
            )

    def test_account_with_spaces(self):
        with pytest.raises(PydanticValidationError):
            UserRegister(
                account="test user",
                nickname="test",
                password="Abc1234!",
                mobile="13800000001",
            )


class TestNicknameSanitization:
    """UserRegister._sanitize_nickname 单元测试。"""

    def test_valid_nickname(self):
        reg = UserRegister(
            account="testuser",
            nickname="正常的昵称",
            password="Abc1234!",
            mobile="13800000001",
        )
        assert reg.nickname == "正常的昵称"

    def test_html_tag_rejected(self):
        """昵称含 HTML 标签应被拒绝。"""
        with pytest.raises(PydanticValidationError, match="HTML"):
            UserRegister(
                account="testuser",
                nickname="<script>alert('xss')</script>",
                password="Abc1234!",
                mobile="13800000001",
            )

    def test_angle_bracket_rejected(self):
        with pytest.raises(PydanticValidationError, match="非法字符"):
            UserRegister(
                account="testuser",
                nickname="test;nick\"",
                password="Abc1234!",
                mobile="13800000001",
            )