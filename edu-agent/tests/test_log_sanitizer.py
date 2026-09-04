# -*- coding: utf-8 -*-
"""测试日志脱敏工具（Phase 3 可观测性）。"""
from __future__ import annotations

import pytest
from app.common.log_sanitizer import sanitize_for_log, sanitize_dict_for_log, is_sensitive_key


class TestSanitizeForLog:
    """sanitize_for_log 单元测试。"""

    def test_none_returns_none_string(self):
        assert sanitize_for_log(None) == "None"

    def test_int_unchanged(self):
        assert sanitize_for_log(42) == "42"

    def test_phone_masked(self):
        assert sanitize_for_log("13812345678") == "138****5678"

    def test_phone_in_text(self):
        result = sanitize_for_log("用户手机 13900001111 已注册")
        assert "139****1111" in result
        assert "13900001111" not in result

    def test_email_masked(self):
        result = sanitize_for_log("user@example.com")
        assert "use***@example.com" == result

    def test_long_string_truncated(self):
        long_str = "a" * 500
        result = sanitize_for_log(long_str, max_length=200)
        assert len(result) <= 220  # 200 + truncation suffix
        assert "truncated" in result

    def test_normal_text_unchanged(self):
        text = "这是一段普通文本，没有任何敏感信息"
        assert sanitize_for_log(text) == text


class TestSanitizeDictForLog:
    """sanitize_dict_for_log 单元测试。"""

    def test_password_key_redacted(self):
        data = {"username": "admin", "password": "secret123"}
        result = sanitize_dict_for_log(data)
        assert result["username"] == "admin"
        assert result["password"] == "***"

    def test_token_key_redacted(self):
        data = {"access_token": "eyJhbGciOiJIUzI1NiJ9.xxx"}
        result = sanitize_dict_for_log(data)
        assert result["access_token"] == "***"

    def test_api_key_redacted(self):
        data = {"api_key": "sk-1234567890abcdef"}
        result = sanitize_dict_for_log(data)
        assert result["api_key"] == "***"

    def test_nested_dict_redacted(self):
        data = {"user": {"name": "test", "password": "nested_secret"}}
        result = sanitize_dict_for_log(data)
        assert result["user"]["name"] == "test"
        assert result["user"]["password"] == "***"

    def test_normal_dict_unchanged(self):
        data = {"name": "张三", "age": 25, "city": "北京"}
        result = sanitize_dict_for_log(data)
        assert result == data

    def test_phone_in_dict_value_masked(self):
        data = {"contact": "手机号 13812345678"}
        result = sanitize_dict_for_log(data)
        assert "138****5678" in result["contact"]


class TestIsSensitiveKey:
    """is_sensitive_key 单元测试。"""

    def test_password_is_sensitive(self):
        assert is_sensitive_key("password") is True

    def test_token_is_sensitive(self):
        assert is_sensitive_key("access_token") is True

    def test_secret_is_sensitive(self):
        assert is_sensitive_key("client_secret") is True

    def test_api_key_is_sensitive(self):
        assert is_sensitive_key("api_key") is True

    def test_username_not_sensitive(self):
        assert is_sensitive_key("username") is False

    def test_email_not_sensitive(self):
        assert is_sensitive_key("email") is False

    def test_case_insensitive(self):
        assert is_sensitive_key("Password") is True
        assert is_sensitive_key("API_KEY") is True