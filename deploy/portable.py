"""Portable installation and reviewed source export; standard library only.

Never reads local production data or changes the existing Git index/services.
The private Compose environment belongs to the independent portable deployment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {'.py', '.js', '.ts', '.tsx', '.html', '.css', '.json', '.yaml', '.yml',
                 '.toml', '.lock', '.md', '.sql', '.ini', '.svg', '.txt', '.example', '.cmd', '.mjs'}
ASSET_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.ico', '.woff', '.woff2', '.ttf'}
SOURCE_TREES = ('bili-study-agent/app', 'bili-study-agent/alembic', 'bili-study-agent/vendor',
                'bili-study-frontend/src', 'bili-study-frontend/public', 'bili-study-frontend/refine-layer/src')
SOURCE_FILES = (
    '.gitignore', '.dockerignore', 'start-bili-study.cmd', 'stop-bili-study.cmd',
    'deploy/local_launcher.py', 'docs/HISTORY.md', 'docs/ARCHITECTURE.md',
    'docs/VIDEO-KNOWLEDGE-COMPILER.md', 'bili-study-agent/pyproject.toml', 'bili-study-agent/uv.lock',
    'bili-study-frontend/package.json', 'bili-study-frontend/package-lock.json', 'bili-study-frontend/next.config.ts',
    'bili-study-frontend/tsconfig.json', 'bili-study-frontend/postcss.config.mjs', 'bili-study-frontend/eslint.config.mjs',
    'bili-study-frontend/next-env.d.ts', 'deploy/portable.py', 'deploy/bootstrap.py',
    'deploy/schema.sql', 'deploy/schema-manifest.json', 'deploy/.env.portable.example',
    'deploy/docker-compose.yml', 'deploy/backend.Dockerfile', 'deploy/frontend.Dockerfile',
    'deploy/minio.Dockerfile',
    'bili-study-agent/scripts/run_parser_worker.py', 'bili-study-agent/scripts/run_ingest_worker.py',
    'bili-study-agent/scripts/run_reconciler.py', 'bili-study-agent/scripts/manage_workers.py',
    'bili-study-agent/scripts/download_models.py', 'bili-study-agent/scripts/video_knowledge.py',
    'deploy/tests/test_portability.py', '.github/workflows/portable.yml',
    'docs/PORTABILITY.md',
    'THIRD-PARTY-NOTICES.md', 'start-bili-study-portable.cmd', 'start-bili-study-portable.sh',
    'bili-study-frontend/public/samples/cache-knowledge-demo.pdf',
    'bili-study-frontend/public/samples/cache-scanned-demo.pdf',
    'bili-study-frontend/public/samples/bili-study-cache-lab-20261007.pdf',
)


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if line.strip() and not line.lstrip().startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def initialize(root: Path, models: Path) -> Path:
    target = root / 'deploy/.env.portable'
    if target.exists():
        raise FileExistsError('Private configuration already exists; edit it instead of overwriting')
    template = (root / 'deploy/.env.portable.example').read_text(encoding='utf-8')
    lines = []
    for line in template.splitlines():
        if line.endswith('=GENERATE_ME'):
            line = line.split('=', 1)[0] + '=' + secrets.token_hex(24)
        elif line.startswith('EDU_MODEL_DIR='):
            line = 'EDU_MODEL_DIR=' + models.resolve().as_posix()
        elif line.startswith('EDU_SECRETS_DIR='):
            line = 'EDU_SECRETS_DIR=' + (root / 'private').resolve().as_posix()
        lines.append(line)
    with target.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write('\n'.join(lines) + '\n')
    if os.name != 'nt':
        target.chmod(0o600)
    (root / 'private').mkdir(exist_ok=True)
    return target


def release_files(root: Path) -> list[Path]:
    found = set()
    for tree in SOURCE_TREES:
        folder = root / tree
        if not folder.exists():
            continue
        for path in folder.rglob('*'):
            relative = path.relative_to(root)
            if any(part in {'__pycache__', '.git', 'node_modules', '.venv', 'data', 'logs',
                            'test-reports', 'test-results', '.next', '.next-prod', 'private', '.mimosa', '.archify'} for part in relative.parts):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('External/symbolic source links are not exportable: ' + relative.as_posix())
            if not path.is_file() or (path.suffix not in TEXT_SUFFIXES | ASSET_SUFFIXES
                                       and path.name not in {'LICENSE', 'NOTICE'}):
                continue
            # Historical live responses and private runtime identity are not source assets.
            if path.name in {'verification.json', 'release-manifest.json'} or path.name.startswith('.env'):
                continue
            found.add(path)
    for name in SOURCE_FILES:
        path = root / name
        if path.is_file():
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('External source link: ' + name)
            found.add(path)
    return sorted(found, key=lambda p: p.relative_to(root).as_posix())


def credential_findings(root: Path, files: list[Path]) -> list[str]:
    # Known private values supplement token patterns; reports expose paths only.
    private_values = set()
    instructions = root / 'AGENTS.md'
    if instructions.is_file():
        match = re.search(r'当前本地测试密码\s*`([^`]+)`', instructions.read_text(encoding='utf-8'))
        if match:
            private_values.add(match[1].encode())
    for env_path in (root / 'bili-study-agent/.env', root / 'bili-study-frontend/.env.local', root / 'deploy/.env.portable'):
        if env_path.is_file():
            for key, value in read_env(env_path).items():
                if re.search(r'(PASSWORD|SECRET|TOKEN|API_KEY|COOKIE)', key, re.I) and len(value) >= 8:
                    if not value.startswith(('REPLACE_', 'GENERATE_', 'ci-', 'test-')):
                        private_values.add(value.encode())
    patterns = [rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                rb'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,}|AKIA[A-Z0-9]{16})\b',
                rb'(?:https?|mysql(?:\+\w+)?|mongodb)://[^\s/"\']+:[^\s/"\']+@']
    findings = []
    for path in files:
        body = path.read_bytes()
        if any(value in body for value in private_values) or any(re.search(p, body) for p in patterns):
            findings.append(path.relative_to(root).as_posix())
    return findings


def export_release(root: Path, destination: Path) -> dict:
    if destination.exists():
        raise FileExistsError('Release destination exists; choose a fresh directory')
    if destination.resolve().is_relative_to(root.resolve()):
        raise ValueError('Export must be outside the working repository')
    files = release_files(root)
    findings = credential_findings(root, files)
    if findings:
        raise ValueError('Potential credential in export source; refusing export: ' + ', '.join(findings))
    destination.mkdir(parents=True)
    manifest = {'scope': 'source-only snapshot, no original Git history or runtime data', 'files': []}
    for source in files:
        relative = source.relative_to(root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest['files'].append({'path': relative.as_posix(),
                                  'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    guide = root / 'README.md'
    if guide.is_file():
        shutil.copy2(guide, destination / 'README.md')
        manifest['files'].append({'path': 'README.md', 'sha256': hashlib.sha256(guide.read_bytes()).hexdigest()})
    (destination / 'release-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def compose(root: Path, env_file: Path, arguments: list[str]) -> int:
    return subprocess.call(['docker', 'compose', '--project-name', 'eduagent-portable',
                            '--env-file', str(env_file.resolve()), '-f', str(root / 'deploy/docker-compose.yml'),
                            *arguments], env={**os.environ, 'EDU_ENV_FILE': str(env_file.resolve())})


def runtime_status(env_file: Path) -> dict:
    values = read_env(env_file)
    backend = 'http://127.0.0.1:' + values.get('BACKEND_PORT', '9988')
    frontend = 'http://127.0.0.1:' + values.get('FRONTEND_PORT', '3322')
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(url):
        with client.open(url, timeout=5) as response:
            return json.loads(response.read())

    result = {}
    try:
        health = get(backend + '/health/ready')
        result['backend_ready'] = health.get('status') == 'ready' and all(health.get('stores', {}).values())
        result['backend'] = health
    except Exception:
        result['backend_ready'] = False
    try:
        with client.open(frontend + '/login-register.html', timeout=5) as response:
            result['frontend_ready'] = response.status == 200
    except Exception:
        result['frontend_ready'] = False
    try:
        result['jaeger_query_ready'] = isinstance(get(values['JAEGER_UI_URL'].rstrip('/') + '/api/services').get('data'), list)
    except Exception:
        result['jaeger_query_ready'] = False
    try:
        with client.open(values['NEO4J_BROWSER_URL'], timeout=5) as response:
            result['neo4j_browser_ready'] = response.status == 200
    except Exception:
        result['neo4j_browser_ready'] = False
    try:
        credentials = json.dumps({'account': values['ADMIN_ACCOUNT'], 'password': values['ADMIN_PASSWORD']}).encode()
        request = urllib.request.Request(backend + '/api/auth/login', data=credentials, headers={'Content-Type': 'application/json'})
        with client.open(request, timeout=10) as response:
            token = json.loads(response.read())['data']['access_token']
        request = urllib.request.Request(backend + '/api/knowledge/admin/document-capabilities', headers={'Authorization': 'Bearer ' + token})
        with client.open(request, timeout=10) as response:
            capabilities = json.loads(response.read())['data']
        workers = capabilities['mineru']['workers']
        result['document_workers_ready'] = all(workers.get(name) is True for name in ('parser-worker', 'ingest-worker', 'reconciler'))
        result['mineru_configured'] = capabilities['mineru']['configured']
    except Exception:
        result['document_workers_ready'] = False
        result['mineru_configured'] = False
    result['ready'] = all(result.get(key) for key in ('backend_ready', 'frontend_ready', 'jaeger_query_ready',
                                                     'neo4j_browser_ready', 'document_workers_ready'))
    if values.get('MINERU_ENABLED', 'true').lower() == 'true':
        result['ready'] = result['ready'] and result['mineru_configured']
    return result


def preflight(root: Path, env_file: Path) -> None:
    values = read_env(env_file)
    for key in ('LLM_API_KEY', 'LLM_MODEL_FAST', 'LLM_MODEL_STRONG', 'ADMIN_PASSWORD',
                'MYSQL_PASSWORD', 'MINIO_SECRET_KEY', 'NEO4J_PASSWORD', 'JWT_SECRET', 'API_TOKEN'):
        if not values.get(key) or values[key].startswith(('REPLACE_', 'GENERATE_')):
            raise ValueError('Fill private configuration: ' + key)
    if values.get('DEBUG') != 'false':
        raise ValueError('Portable deployment requires DEBUG=false')
    models = Path(values['EDU_MODEL_DIR'])
    if not models.is_absolute():
        models = env_file.parent / models
    for filename in ('bge-m3/config.json', 'faster-whisper-base/model.bin'):
        if not (models / filename).is_file():
            raise ValueError('Missing model: ' + filename + '; see download_models.py --help')
    if not any((models / 'bge-m3' / name).is_file() for name in ('model.safetensors', 'pytorch_model.bin', 'model.safetensors.index.json')):
        raise ValueError('BGE-M3 weights are missing')
    docker = subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], check=True, capture_output=True, text=True, timeout=15)
    if not docker.stdout.strip():
        raise ValueError('Docker engine did not report a server version; proxy/CLI availability is not readiness')
    print('Private configuration and required models verified; no existing services changed')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'check', 'up', 'status', 'export'))
    parser.add_argument('--models-dir', type=Path, default=ROOT / 'models')
    parser.add_argument('--env-file', type=Path, default=ROOT / 'deploy/.env.portable')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.action == 'init':
            print('Created private configuration:', initialize(ROOT, args.models_dir))
            print('Edit LLM credentials/model names before up. Never commit this file.')
        elif args.action == 'export':
            if not args.output:
                parser.error('--output is required for export')
            receipt = export_release(ROOT, args.output)
            print(f'Exported {len(receipt["files"])} reviewed source files to {args.output}; no push performed')
        elif args.action == 'status':
            compose(ROOT, args.env_file, ['ps', '--all'])
            status = runtime_status(args.env_file)
            print(json.dumps(status, ensure_ascii=False, indent=2))
            return 0 if status['ready'] else 1
        else:
            preflight(ROOT, args.env_file)
            if args.action == 'up':
                code = compose(ROOT, args.env_file, ['up', '--build', '--detach', '--wait', '--wait-timeout', '600'])
                if code:
                    return code
                status = runtime_status(args.env_file)
                print(json.dumps(status, ensure_ascii=False, indent=2))
                return 0 if status['ready'] else 1
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print('FAIL:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
