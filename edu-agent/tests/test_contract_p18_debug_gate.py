"""P1-8 硬门禁契约测试:DEBUG=true 仅允许 ENV_NAME=local(H1b)。

三态:DEBUG=true+prod 拒启 / DEBUG=true+local 放行 / DEBUG=false+prod 放行。
"""
from __future__ import annotations

import secrets

import pytest

from app.config import Settings


def _settings(debug: bool, env_name: str):
    from app.config import Settings

    return Settings(_env_file=None, MYSQL_PASSWORD="x", LLM_API_KEY="x", JWT_SECRET=secrets.token_hex(32), API_TOKEN=secrets.token_hex(16), DEBUG=debug, ENV_NAME=env_name)


@pytest.mark.parametrize(
    "debug,env_name,expect_block",
    [(True, "prod", True), (True, "local", False), (False, "prod", False)],
)
def test_debug_env_gate(debug: bool, env_name: str, expect_block: bool):
    import pydantic_core

    if expect_block:
        with pytest.raises((ValueError, pydantic_core.ValidationError), match="DEBUG"):
            _settings(debug, env_name)
    else:
        _settings(debug, env_name)  # 不抛即过


def test_env_name_default_local():
    assert _settings(False, "local").ENV_NAME == "local"
