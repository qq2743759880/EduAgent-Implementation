"""Public portability contracts; no shared infrastructure or credentials."""
import importlib.util
from pathlib import Path

import pytest
import secrets


def load_tool():
    path = Path(__file__).parents[1] / 'portable.py'
    spec = importlib.util.spec_from_file_location('portable', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_private_config_is_unique_and_never_overwrites(tmp_path):
    tool = load_tool()
    (tmp_path / 'deploy').mkdir()
    template = Path(__file__).parents[1] / '.env.portable.example'
    (tmp_path / 'deploy/.env.portable.example').write_bytes(template.read_bytes())
    config = tool.initialize(tmp_path, tmp_path / 'models')
    values = tool.read_env(config)
    assert values['DEBUG'] == 'false'
    assert len(values['JWT_SECRET']) >= 32
    assert values['MYSQL_PASSWORD'] != values['MYSQL_ROOT_PASSWORD']
    first = config.read_bytes()
    with pytest.raises(FileExistsError):
        tool.initialize(tmp_path, tmp_path / 'models')
    assert config.read_bytes() == first


def test_release_omits_runtime_and_rejects_credentials_and_external_links(tmp_path):
    tool = load_tool()
    root = tmp_path / 'source'
    (root / 'bili-study-agent/app').mkdir(parents=True)
    (root / 'bili-study-agent/app/main.py').write_text('value = 1\n')
    (root / 'bili-study-agent/.env').write_text('LLM_API_KEY=private-secret-value-0123456789\n')
    (root / 'bili-study-agent/logs').mkdir()
    (root / 'bili-study-agent/logs/debug.log').write_text('private-secret-value-0123456789')
    assert [str(p.relative_to(root)).replace('\\', '/') for p in tool.release_files(root)] == ['bili-study-agent/app/main.py']
    (root / 'bili-study-agent/app/main.py').write_text('key = "private-secret-value-0123456789"\n')
    with pytest.raises(ValueError, match='credential'):
        tool.export_release(root, tmp_path / 'unsafe')
    assert not (tmp_path / 'unsafe').exists()
    fixture_password = secrets.token_hex(20)
    (root / 'AGENTS.md').write_text(f'当前本地测试密码 `{fixture_password}`', encoding='utf-8')
    (root / 'bili-study-agent/app/main.py').write_text(f'password = {fixture_password!r}\n')
    with pytest.raises(ValueError, match='credential'):
        tool.export_release(root, tmp_path / 'unsafe-test-password')
    (root / 'bili-study-agent/app/main.py').write_text('value = 1\n')
    tool.export_release(root, tmp_path / 'safe')
    assert not (tmp_path / 'safe/bili-study-agent/.env').exists()
    with pytest.raises(FileExistsError):
        tool.export_release(root, tmp_path / 'safe')


def test_bootstrap_refuses_existing_schema_and_requires_private_admin_password():
    path = Path(__file__).parents[1] / 'bootstrap.py'
    spec = importlib.util.spec_from_file_location('bootstrap', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match='empty'):
        module.require_empty_database(['sys_user'])
    module.require_empty_database([])
    with pytest.raises(ValueError, match='password'):
        module.validate_admin_password('123456')
    module.validate_admin_password('unique-local-example-123!')
