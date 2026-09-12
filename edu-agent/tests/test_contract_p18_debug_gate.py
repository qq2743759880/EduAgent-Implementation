"""P1-8 硬门禁契约测试:DEBUG=true 仅允许 ENV_NAME=local(H1b)。

三态:DEBUG=true+prod 拒启 / DEBUG=true+local 放行 / DEBUG=false+prod 放行。
"""
from __future__ import annotations

import pytest

from app.config import Settings


def _settings(monkeypatch: pytest.MonkeyPatch, *, debug: bool, env_name: str):
    from app.config import settings

    monkeypatch.setattr(settings, "DEBUG", debug)
    monkeypatch.setattr(settings, "ENV_NAME", env_name)
    return settings


@pytest.mark.parametrize(
    "debug,env_name,expect_block",
    [(True, "prod", True), (True, "local", False), (False, "prod", False)],
)
def test_debug_env_gate(monkeypatch: pytest.MonkeyPatch, debug: bool, env_name: str, expect_block: bool):
    s = _settings(monkeypatch, debug=debug, env_name=env_name)
    if expect_block:
        with pytest.raises(RuntimeError, match="P1-8"):
            s.enforce_debug_env_gate()
    else:
        s.enforce_debug_env_gate()  # 不抛即过


def test_env_name_default_local():
    from app.config import settings

    assert settings.ENV_NAME == "local"
