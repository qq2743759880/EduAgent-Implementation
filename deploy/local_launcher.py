"""Bounded Windows launcher for the existing Bili-Study local environment.

Does not install dependencies, migrate databases, stop processes or edit proxies.
The existing worker manager and video drain protocol retain lifecycle ownership.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

import psutil
import requests

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'bili-study-agent'
FRONTEND = ROOT / 'bili-study-frontend'
PYTHON = BACKEND / '.venv/Scripts/python.exe'
LOGS = BACKEND / 'logs'
STATE = BACKEND / 'data/runtime-launcher'
PORTS = {'backend': 9988, 'frontend': 3322}
CONTAINER = 'prisma-ai-redis-container-1'
CLIENT = requests.Session()
CLIENT.trust_env = False


class StartupError(RuntimeError):
    pass


def hidden_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def run_command(command, *, timeout, cwd=None):
    try:
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=timeout,
                                env={**os.environ, 'DEBUG': 'false', 'PYTHONUTF8': '1'},
                                **hidden_options())
    except subprocess.TimeoutExpired as exc:
        raise StartupError(f'{Path(command[0]).name} timed out after {timeout}s') from exc
    except OSError as exc:
        raise StartupError(f'Cannot run {Path(command[0]).name}: {exc}') from exc
    if result.returncode:
        raise StartupError(f'{Path(command[0]).name} exit={result.returncode}: '
                           f'{(result.stderr or result.stdout)[-600:].strip()}')
    return result.stdout.strip()


@contextmanager
def start_lock(path):
    import msvcrt
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise StartupError('another startup is already running; retry when it finishes') from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def tcp_online(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def listener_pids(port):
    return sorted({c.pid for c in psutil.net_connections(kind='tcp')
                   if c.status == psutil.CONN_LISTEN and c.laddr.port == port and c.pid})


def owns_process(pid, service):
    try:
        process = psutil.Process(pid)
        chain = [process, *process.parents()[:3]]
        if service == 'backend':
            # Windows venv redirects to base Python; verify its venv ancestor too.
            command = process.cmdline()
            return (Path(process.cwd()).resolve() == BACKEND
                    and 'app.main:app' in command and 'uvicorn' in command
                    and any(p.cmdline() and Path(p.cmdline()[0]).resolve() == PYTHON
                            for p in chain))
        return any(Path(p.cwd()).resolve() == FRONTEND
                   and Path(p.exe()).name.lower() == 'node.exe'
                   and any('node_modules/next/dist/bin/next' in arg.replace('\\', '/')
                           for arg in p.cmdline())
                   and '3322' in p.cmdline() for p in chain)
    except (psutil.Error, OSError, ValueError):
        return False


def process_debug_enabled(pid):
    try:
        value = psutil.Process(pid).environ().get('DEBUG', '')
        return value.lower() in {'true', '1', 'yes', 'on'}
    except psutil.Error as exc:
        raise StartupError('Cannot verify existing backend DEBUG environment') from exc


def ensure_process(service):
    pids = listener_pids(PORTS[service])
    if pids:
        if not all(owns_process(pid, service) for pid in pids):
            raise StartupError(f'{service} port {PORTS[service]} occupied by unverified PID(s) {pids}; '
                               'no process was stopped')
        if service == 'backend' and any(process_debug_enabled(pid) for pid in pids):
            raise StartupError('Existing backend has DEBUG enabled; drain/stop it safely before restart')
        print(f'[REUSE] {service} verified pid={pids}', flush=True)
        return pids[0]
    LOGS.mkdir(parents=True, exist_ok=True)
    if service == 'backend':
        command = [str(PYTHON), '-X', 'utf8', '-B', '-m', 'uvicorn', 'app.main:app',
                   '--host', '127.0.0.1', '--port', '9988']
        cwd = BACKEND
    else:
        node = shutil.which('node')
        if not node:
            raise StartupError('Node.js missing from PATH; dependencies are not installed automatically')
        command = [node, str(FRONTEND / 'node_modules/next/dist/bin/next'), 'dev', '-p', '3322']
        cwd = FRONTEND
    log = LOGS / f'launcher-{service}.log'
    with log.open('ab') as handle:
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=handle, stderr=subprocess.STDOUT,
                                   env={**os.environ, 'DEBUG': 'false', 'PYTHONUTF8': '1'},
                                   **hidden_options())
    print(f'[SPAWN] {service} pid={process.pid}; waiting for readiness; log={log}', flush=True)
    return process.pid


def docker_command():
    bundled = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Docker/Docker/resources/bin/docker.exe'
    executable = str(bundled) if bundled.is_file() else shutil.which('docker')
    if not executable:
        raise StartupError('Redis offline and Docker CLI missing; restore existing Redis first')
    # This is the existing Linux container, not a new store or Windows engine.
    return [executable, '--context', 'desktop-linux']


def ensure_docker(timeout):
    docker = docker_command()
    try:
        if not run_command([*docker, 'info', '--format', '{{.ServerVersion}}'], timeout=5):
            raise StartupError('Docker server version is missing')
    except StartupError:
        desktop = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Docker/Docker/Docker Desktop.exe'
        if not desktop.is_file():
            raise StartupError('Docker daemon offline and Docker Desktop executable missing')
        if not any(p.info['name'] == 'com.docker.backend.exe'
                   for p in psutil.process_iter(['name'])):
            subprocess.Popen([str(desktop)], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             **hidden_options())
        print('[WAIT] Docker Linux engine; no proxy/TUN settings will be changed', flush=True)
        deadline = time.monotonic() + timeout
        while True:
            try:
                if not run_command([*docker, 'info', '--format', '{{.ServerVersion}}'],
                                   timeout=max(.1, min(5, deadline - time.monotonic()))):
                    raise StartupError('Docker server version is missing')
                break
            except StartupError:
                if time.monotonic() >= deadline:
                    raise StartupError('Docker engine not ready. Check Docker Desktop internal proxy/network '
                                       'logs; no containers, proxies or data were reset')
                time.sleep(1)
    return docker


def ensure_redis(timeout):
    if tcp_online(6377):
        print('[OK] Redis port 6377 reachable; backend readiness will verify protocol', flush=True)
        return
    docker = ensure_docker(timeout)
    run_command([*docker, 'start', CONTAINER], timeout=20)
    deadline = time.monotonic() + 15
    while not tcp_online(6377):
        if time.monotonic() >= deadline:
            raise StartupError(f'{CONTAINER} started but Redis port 6377 is unavailable')
        time.sleep(1)
    print(f'[OK] Original Redis container {CONTAINER}', flush=True)


def http_state(url, timeout=3):
    try:
        response = CLIENT.get(url, timeout=timeout)
        try:
            body = response.json()
        except ValueError:
            body = {}
        if not isinstance(body, dict):
            body = {'reason': 'invalid health response shape'}
        return response.status_code, body
    except requests.RequestException as exc:
        return None, {'reason': type(exc).__name__}


def demo_configuration():
    # Read the same private settings as the backend; never return credentials.
    code = "from app.config import settings as s; import json; print('EDU_STACK='+json.dumps(dict(mineru_enabled=s.MINERU_ENABLED,mineru_executable=s.MINERU_EXECUTABLE,neo4j_enabled=s.NEO4J_ENABLED,neo4j_host=__import__('urllib.parse',fromlist=['urlsplit']).urlsplit(s.NEO4J_URI).hostname,jaeger_url=s.JAEGER_UI_URL,otel_endpoint=s.OTEL_EXPORTER_OTLP_ENDPOINT)))"
    output = run_command([str(PYTHON), '-c', code], timeout=20, cwd=BACKEND)
    return json.loads(output.split('EDU_STACK=', 1)[1])


def document_worker_snapshot():
    code = """import asyncio,json
from app.config import settings
from redis.asyncio import Redis
async def check():
 r=Redis.from_url(settings.REDIS_URL,socket_timeout=3,decode_responses=True)
 try: print('EDU_WORKERS='+json.dumps({name:bool(await r.exists('worker:alive:'+name)) for name in ('parser-worker','ingest-worker','reconciler')}))
 finally: await r.aclose()
asyncio.run(check())
"""
    output=run_command([str(PYTHON),'-c',code],cwd=BACKEND,timeout=15)
    return json.loads(output.split('EDU_WORKERS=',1)[1])


def wait_document_workers(timeout):
    deadline=time.monotonic()+timeout
    while True:
        states=document_worker_snapshot()
        if all(states.values()):return states
        missing=[name for name,ready in states.items() if not ready]
        if time.monotonic()>=deadline:raise StartupError('Document workers have no live heartbeat: '+', '.join(missing))
        print('[WAIT] document workers: '+', '.join(missing),flush=True)
        time.sleep(2)


def demo_stack_status(config):
    result = {}
    if config.get('mineru_enabled'):
        result['mineru'] = {'ready': Path(config.get('mineru_executable', '')).is_file(), 'mode': 'local subprocess, PDF'}
    if config.get('neo4j_enabled'):
        host = config['neo4j_host']; host = f'[{host}]' if ':' in host else host
        url = f'http://{host}:7474/browser/'
        result['neo4j'] = {'ready': http_state(url)[0] == 200, 'browser_url': url}
    if config.get('otel_endpoint'):
        url = config['jaeger_url'].rstrip('/')
        status, body = http_state(url + '/api/services')
        result['jaeger'] = {'ready': status == 200 and isinstance(body.get('data'), list), 'ui_url': url}
        result['otlp'] = {'ready': http_state(config['otel_endpoint'])[0] == 405,
                          'route': config['otel_endpoint'], 'check': 'HTTP GET rejected with POST-only contract; real spans verified separately'}
    return result


def ensure_demo_stack(config, timeout):
    if config.get('mineru_enabled'):
        executable = config.get('mineru_executable', '')
        if not Path(executable).is_file():
            raise StartupError('MinerU configured but runtime executable is missing; no automatic installation')
        version = run_command([executable, '--version'], timeout=20)
        if 'MinerU' not in version:
            raise StartupError('MinerU runtime did not identify its version')
        print('[OK] ' + version.splitlines()[0], flush=True)
    if config.get('otel_endpoint'):
        url = config['jaeger_url'].rstrip('/')
        status, body = http_state(url + '/api/services')
        if status != 200 or not isinstance(body.get('data'), list):
            if urlsplit(url).hostname not in {'localhost', '127.0.0.1', '::1'}:
                raise StartupError('Configured remote Jaeger unavailable; local launcher cannot own it')
            docker = ensure_docker(timeout)
            identity = run_command([*docker, 'inspect', 'eduagent-jaeger', '--format', '{{.Config.Image}}'], timeout=10)
            if 'jaegertracing/all-in-one:' not in identity:
                raise StartupError('Jaeger container identity is unverified; no container changed')
            run_command([*docker, 'start', 'eduagent-jaeger'], timeout=20)
            deadline = time.monotonic() + timeout
            while True:
                status, body = http_state(url + '/api/services')
                if status == 200 and isinstance(body.get('data'), list): break
                if time.monotonic() >= deadline:
                    raise StartupError('Jaeger container started but UI/query API unavailable; check its logs')
                time.sleep(1)
    # Reuse the probe result rather than sampling Jaeger a second time.
    result = {}
    if config.get('otel_endpoint'):
        result['jaeger'] = {'ready': True, 'ui_url': config['jaeger_url']}
        if http_state(config['otel_endpoint'])[0] != 405:
            raise StartupError('Jaeger UI is online but configured OTLP HTTP POST route is unavailable')
        result['otlp'] = {'ready': True, 'route': config['otel_endpoint']}
    for name, state in demo_stack_status({**config, 'otel_endpoint': ''}).items():
        result[name] = state
        if not state['ready']: raise StartupError(name + ' configured but unavailable')
    return result


def is_ready(status, body):
    if not isinstance(body, dict):
        return False
    stores = body.get('stores')
    return (status == 200 and body.get('status') == 'ready'
            and isinstance(stores, dict) and bool(stores)
            and all(value is True for value in stores.values()))


def wait_ready(probe, *, timeout, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    last = None
    while clock() < deadline:
        status, body = probe()
        if is_ready(status, body):
            return body
        message = f'HTTP={status}; {body.get("reason") or body.get("status") or "not ready"}'
        stores = body.get('stores')
        if isinstance(stores, dict):
            failed = [name for name, healthy in stores.items() if healthy is not True]
            if failed:
                message += f'; unavailable stores={failed}'
        if message != last:
            print(f'[WAIT] backend {message}', flush=True)
            last = message
        sleep(min(2, max(0, deadline - clock())))
    raise StartupError(f'Backend readiness timed out: {last}; check backend logs under {LOGS} '
                       'and /health/warmup. '
                       'Processes left running; use the existing drain-safe stop script')


def start(backend_timeout, docker_timeout):
    if not PYTHON.is_file() or not (FRONTEND / 'node_modules/next/dist/bin/next').is_file():
        raise StartupError('Project venv or frontend dependencies missing; no automatic installation')
    # Validate ownership before changing paused state or starting either service.
    for service in PORTS:
        for pid in listener_pids(PORTS[service]):
            if not owns_process(pid, service):
                raise StartupError(f'{service} port occupied by unverified PID {pid}')
            if service == 'backend' and process_debug_enabled(pid):
                raise StartupError('Existing backend DEBUG must be false')
    ensure_redis(docker_timeout)
    demo = ensure_demo_stack(demo_configuration(), docker_timeout)
    print(run_command([str(PYTHON), '-m', 'app.domains.video_learning.task_worker', '--unpause'],
                      cwd=BACKEND, timeout=20), flush=True)
    backend_pid = ensure_process('backend')
    frontend_pid = ensure_process('frontend')
    ready = wait_ready(lambda: http_state('http://127.0.0.1:9988/health/ready'), timeout=backend_timeout)
    deadline = time.monotonic() + 60
    while http_state('http://127.0.0.1:3322/login-register.html')[0] != 200:
        if time.monotonic() >= deadline:
            raise StartupError(f'Frontend did not return HTTP 200; check {LOGS / "launcher-frontend.log"}')
        time.sleep(2)
    print(run_command([str(PYTHON), 'scripts/manage_workers.py', 'start'],
                      cwd=BACKEND, timeout=30), flush=True)
    demo['document_workers']=wait_document_workers(min(backend_timeout,120))
    for pid in listener_pids(9988):
        if not owns_process(pid, 'backend'):
            raise StartupError('Backend listener identity changed during startup')
    degraded = ready.get('optional_degraded') or []
    print(f'[READY] backend 9988; frontend 3322; optional_degraded={degraded}', flush=True)
    print('Open: http://127.0.0.1:3322/login-register.html', flush=True)
    return {'backend_pid': backend_pid, 'frontend_pid': frontend_pid,
            'backend': ready, 'frontend_http': 200, 'demo_stack': demo}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'status'], nargs='?', default='start')
    parser.add_argument('--backend-timeout', type=int, default=180)
    parser.add_argument('--docker-timeout', type=int, default=90)
    args = parser.parse_args()
    if args.backend_timeout < 1 or args.docker_timeout < 1:
        parser.error('timeouts must be positive seconds')
    if args.action == 'status':
        demo = demo_stack_status(demo_configuration())
        workers=document_worker_snapshot()
        status, body = http_state('http://127.0.0.1:9988/health/ready')
        front = http_state('http://127.0.0.1:3322/login-register.html')[0]
        owned = all(listener_pids(PORTS[name]) and all(owns_process(pid, name)
                    for pid in listener_pids(PORTS[name])) for name in PORTS)
        print(json.dumps({'backend_http': status, 'backend': body, 'frontend_http': front,
                          'listeners_owned': owned, 'demo_stack': demo, 'document_workers':workers}, ensure_ascii=False, indent=2))
        return 0 if owned and is_ready(status, body) and front == 200 and all(s['ready'] for s in demo.values()) and all(workers.values()) else 1
    try:
        with start_lock(STATE / 'start.lock'):
            result = start(args.backend_timeout, args.docker_timeout)
            result['checked_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
            result['status'] = 'ready'
            (STATE / 'last-start.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0
    except (StartupError, OSError, psutil.Error) as exc:
        print(f'[FAIL] {exc}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
