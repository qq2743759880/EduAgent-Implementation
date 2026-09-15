// EduAgent 一键部署三件套(taskC1):start / stop / status
// 用法: node scripts/deploy/deploy.mjs start|stop|status [--all]
// 零新依赖:Node >= 18(net / fetch / child_process 均内置),与 check-demo.mjs 同栈。
//
// start : ①前置检查(MySQL/VM Milvus+Mongo socket、Redis docker ping——只报告不阻塞硬启,
//           与 check-demo 同口径) ②后端 .venv uvicorn app.main:app --port 8000(读 .env 的
//           DEBUG/ENV_NAME 形态原样,不做替换;.env 须用户自行按 .env.example 配置)
//         ③前端 build+start 生产形态(C2 结论:NEXT_PROD_DIST_DIR=.next-prod,缺产物先 build)
//         ④拉起后自动跑 check-demo.mjs 断言 9/9(exit code 透传)
// stop  : 按端口清 8000/3000(--all 附加提示 Redis 容器处置,容器本身不停)
// status: 透传执行 scripts/check-demo.mjs(exit code 透传)
//
// 日志: edu-agent/logs/deploy-backend.log / deploy-frontend.log / deploy-frontend-build.log
// 幂等: 端口已在监听则跳过对应服务并提示。
// 注意: 生产形态(DEBUG=false)下 lifespan 对存储不可达即拒启(config.py _security_guard /
//       lifespan 硬校验)——本脚本只前置报告,不代替 .env 生产段配置(见 .env.example 双形态对照)。
import net from "node:net";
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, openSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { execSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

// ---------- 路径 ----------
const HERE = path.dirname(fileURLToPath(import.meta.url)); // edu-agent/scripts/deploy
const BACKEND_DIR = path.resolve(HERE, "..", ".."); // edu-agent
const FRONTEND_DIR = path.resolve(BACKEND_DIR, "..", "edu-frontend"); // 工作区同级前端
const LOG_DIR = path.join(BACKEND_DIR, "logs");
const CHECK_DEMO = path.join(BACKEND_DIR, "scripts", "check-demo.mjs");
const PIDS_FILE = path.join(LOG_DIR, "deploy.pids.json");
const BACKEND_LOG = path.join(LOG_DIR, "deploy-backend.log");
const FRONTEND_LOG = path.join(LOG_DIR, "deploy-frontend.log");
const FRONTEND_BUILD_LOG = path.join(LOG_DIR, "deploy-frontend-build.log");

// ---------- 常量(与 check-demo 同口径) ----------
const BACKEND_PORT = 8000;
const FRONTEND_PORT = 3000;
const REDIS_CONTAINER = "edu-redis-standalone";
const MYSQL_DEFAULT = { host: "127.0.0.1", port: 3306 };
const PROD_DIST_DIR = ".next-prod"; // C2 结论:NEXT_PROD_DIST_DIR 隔离 dev .next,build/start 两侧一致
const BACKEND_HEALTH_TIMEOUT_MS = 120_000; // CUDA 模型加载可能较慢
const FRONTEND_READY_TIMEOUT_MS = 90_000;
const SOCKET_TIMEOUT_MS = 3000;

const NOCOLOR = !process.stdout.isTTY;
const C = NOCOLOR
  ? { g: "", r: "", y: "", b: "", dim: "", x: "" }
  : { g: "\x1b[32m", r: "\x1b[31m", y: "\x1b[33m", b: "\x1b[36m", dim: "\x1b[2m", x: "\x1b[0m" };

const args = process.argv.slice(2);
const CMD = args[0];
const ALL = args.includes("--all");

// ---------- 工具 ----------
function log(msg = "") { console.log(msg); }
function info(msg) { log(`${C.b}[deploy]${C.x} ${msg}`); }
function ok(msg) { log(`${C.g}[ OK ]${C.x} ${msg}`); }
function warn(msg) { log(`${C.y}[WARN]${C.x} ${msg}`); }
function fail(msg) { log(`${C.r}[FAIL]${C.x} ${msg}`); }

function socketProbe(host, port, timeoutMs = SOCKET_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const s = net.connect({ host, port });
    let done = false;
    const finish = (err) => { if (done) return; done = true; s.destroy(); err ? reject(err) : resolve(); };
    s.setTimeout(timeoutMs, () => finish(new Error(`连接超时(>${timeoutMs}ms)`)));
    s.on("connect", () => finish(null));
    s.on("error", (e) => {
      const m = { ECONNREFUSED: "连接被拒绝", EHOSTUNREACH: "主机不可达", ENETUNREACH: "网络不可达" }[e.code] || e.message;
      finish(new Error(m));
    });
  });
}

async function httpOk(url, timeoutMs = 5000) {
  const res = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
  await res.text();
  if (res.status !== 200) throw new Error(`HTTP ${res.status}`);
  return true;
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

// 读 .env 的指定键(原样读取,不做任何替换——形态归用户所有,脚本只报告)
function readEnvKeys(keys) {
  const out = {};
  const p = path.join(BACKEND_DIR, ".env");
  if (!existsSync(p)) return out;
  for (const line of readFileSync(p, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m && keys.includes(m[1])) out[m[1]] = m[2].trim();
  }
  return out;
}

// 端口 → 监听 PID 列表(Windows netstat -ano)
function pidsOnPort(port) {
  let out = "";
  try { out = execSync(`netstat -ano -p tcp`, { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }); }
  catch { return []; }
  const pids = new Set();
  for (const line of out.split(/\r?\n/)) {
    const cols = line.trim().split(/\s+/);
    if (cols.length >= 5 && cols[3] === "LISTENING" && cols[1].endsWith(`:${port}`)) {
      const pid = Number(cols[4]);
      if (Number.isFinite(pid) && pid > 0) pids.add(pid);
    }
  }
  return [...pids];
}

function portBusy(port) { return pidsOnPort(port).length > 0; }

// 追加式日志 fd
function openLog(p) { mkdirSync(LOG_DIR, { recursive: true }); return openSync(p, "a"); }

// ---------- 前置检查(只报告不阻塞,与 check-demo 同口径) ----------
function parseUriHostPort(uri, fallbackPort) {
  // 支持 http://host:port / mongodb://host:port / redis://host:port/db
  try {
    const u = new URL(uri);
    return { host: u.hostname, port: Number(u.port) || fallbackPort };
  } catch { return null; }
}

async function preflight() {
  const env = readEnvKeys(["DEBUG", "ENV_NAME", "MYSQL_HOST", "MYSQL_PORT", "MILVUS_URI", "MONGO_URI"]);
  log(`\n${C.b}=== ① 前置检查(报告口径,不阻塞硬启——与 check-demo 同口径)===${C.x}`);

  // 形态报告(部署形态要求用户 .env 已按 .env.example 生产段配置;脚本只检查并报告)
  const dbg = (env.DEBUG || "(未设置→config.py 默认 False)").toLowerCase();
  const envName = env.ENV_NAME || "(未设置→config.py 默认 local)";
  info(`.env 形态原样: DEBUG=${dbg}  ENV_NAME=${envName}  (脚本不做替换)`);
  if (dbg === "true") {
    warn(`当前为 dev 形态(DEBUG=true):存在虚拟管理员后门风险面(P1-8 门禁要求 DEBUG=true+ENV_NAME=local;生产交付前必须改 false,taskC3 硬验收)`);
  } else if (dbg === "false") {
    warn(`生产形态(DEBUG=false):lifespan 对 MySQL/Milvus/Mongo/MinIO/Neo4j/Redis 任一不可达即拒启;JWT_SECRET/API_TOKEN 默认值亦拒启(_security_guard)`);
  } else {
    warn(`DEBUG 值非 true/false 字面量(${dbg}),以 config.py 解析结果为准`);
  }

  const mysql = { host: env.MYSQL_HOST === "localhost" || !env.MYSQL_HOST ? MYSQL_DEFAULT.host : env.MYSQL_HOST, port: Number(env.MYSQL_PORT) || MYSQL_DEFAULT.port };
  const milvus = parseUriHostPort(env.MILVUS_URI || "http://192.168.85.101:19530", 19530);
  const mongo = parseUriHostPort(env.MONGO_URI || "mongodb://192.168.85.101:27017", 27017);

  const checks = [
    ["MySQL", socketProbe(mysql.host, mysql.port), `宿主 MySQL ${mysql.host}:${mysql.port}`, `启动 MySQL 服务(本机同构环境为 Windows 服务)`],
    ["Milvus", socketProbe(milvus.host, milvus.port), `VM Milvus ${milvus.host}:${milvus.port}`, `开启 VMware 虚拟机并确认 milvus 容器在跑(docker ps)`],
    ["MongoDB", socketProbe(mongo.host, mongo.port), `VM MongoDB ${mongo.host}:${mongo.port}`, `开启 VMware 虚拟机并确认 mongo 容器在跑(docker ps)`],
  ];
  for (const [name, p, desc, fix] of checks) {
    try { await p; ok(`${name} 可达 — ${desc}`); }
    catch (e) { fail(`${name} 不可达 — ${desc} [${e.message}]`); warn(`  -> 处置: ${fix}`); }
  }

  // Redis:docker exec ping,失败给指引但不阻塞(与 check-demo 同口径)
  try {
    const r = spawnSync("docker", ["exec", REDIS_CONTAINER, "redis-cli", "ping"], { encoding: "utf8", timeout: 8000 });
    if (r.status === 0 && /PONG/i.test(r.stdout || "")) ok(`Redis 可达 — docker exec ${REDIS_CONTAINER} redis-cli ping = PONG`);
    else throw new Error((r.stderr || r.stdout || `退出码 ${r.status}`).split("\n")[0].slice(0, 120));
  } catch (e) {
    fail(`Redis 不可达 — docker exec ${REDIS_CONTAINER} redis-cli ping [${e.message}]`);
    warn(`  -> 处置: docker start ${REDIS_CONTAINER}(若 docker 引擎未运行,先启动 Docker Desktop)`);
  }
  return env;
}

// ---------- 服务拉起 ----------
function spawnDetached(cmd, cargs, cwd, logPath, extraEnv = {}) {
  mkdirSync(LOG_DIR, { recursive: true });
  const fd = openSync(logPath, "a");
  const child = spawn(cmd, cargs, {
    cwd,
    detached: true,
    windowsHide: true,
    env: { ...process.env, ...extraEnv },
    stdio: ["ignore", fd, fd],
  });
  child.unref();
  return child.pid;
}

async function waitHttp(url, timeoutMs, what) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try { await httpOk(url); return Date.now() - t0; } catch { /* 未就绪 */ }
    await sleep(1000);
  }
  throw new Error(`${what} 在 ${Math.round(timeoutMs / 1000)}s 内未就绪(查看 logs/deploy-*.log)`);
}

function recordPid(kind, pid, extra = {}) {
  let j = {};
  try { j = JSON.parse(readFileSync(PIDS_FILE, "utf8")); } catch { /* 首次 */ }
  j[kind] = { pid, startedAt: new Date().toISOString(), ...extra };
  writeFileSync(PIDS_FILE, JSON.stringify(j, null, 2));
}

async function startBackend() {
  log(`\n${C.b}=== ② 后端(uvicorn 生产形态,读 .env 形态原样)===${C.x}`);
  if (portBusy(BACKEND_PORT)) {
    const pid = pidsOnPort(BACKEND_PORT)[0];
    warn(`端口 ${BACKEND_PORT} 已有监听(PID ${pid})——幂等跳过后端拉起`);
    return { skipped: true, pid };
  }
  const py = path.join(BACKEND_DIR, ".venv", "Scripts", "python.exe");
  if (!existsSync(py)) throw new Error(`未找到虚拟解释器: ${py}`);
  const pid = spawnDetached(py, ["-m", "uvicorn", "app.main:app", "--port", String(BACKEND_PORT)], BACKEND_DIR, BACKEND_LOG);
  recordPid("backend", pid, { cmd: `uvicorn app.main:app --port ${BACKEND_PORT}`, form: "uvicorn(生产形态)" });
  info(`后端拉起中(PID ${pid},日志 logs/deploy-backend.log),等待 /health ...`);
  const ms = await waitHttp(`http://127.0.0.1:${BACKEND_PORT}/health`, BACKEND_HEALTH_TIMEOUT_MS, "后端");
  ok(`后端就绪 http://127.0.0.1:${BACKEND_PORT}/health(${ms}ms)`);
  return { skipped: false, pid };
}

async function ensureFrontendBuild() {
  const dist = path.join(FRONTEND_DIR, PROD_DIST_DIR);
  if (existsSync(path.join(dist, "BUILD_ID"))) {
    ok(`前端生产产物已存在 ${PROD_DIST_DIR}/BUILD_ID=${readFileSync(path.join(dist, "BUILD_ID"), "utf8").trim()}(跳过 build)`);
    return;
  }
  warn(`${PROD_DIST_DIR} 不存在,先执行生产 build(C2 结论:NEXT_PROD_DIST_DIR=${PROD_DIST_DIR} npx next build,约 1-2 分钟)...`);
  mkdirSync(LOG_DIR, { recursive: true });
  const fd = openSync(FRONTEND_BUILD_LOG, "a");
  const r = spawnSync("cmd", ["/c", "npx", "next", "build"], {
    cwd: FRONTEND_DIR,
    env: { ...process.env, NEXT_PROD_DIST_DIR: PROD_DIST_DIR },
    stdio: ["ignore", fd, fd],
  });
  if (r.status !== 0) {
    fail(`next build 失败(退出码 ${r.status}),完整输出见 logs/deploy-frontend-build.log`);
    throw new Error("前端生产 build 失败,中止 start(C4 降级出口不适用于运行期;请先在 edu-frontend 下排查 build)");
  }
  ok(`next build 完成(日志 logs/deploy-frontend-build.log)`);
}

async function startFrontend() {
  log(`\n${C.b}=== ③ 前端(build+start 生产形态,C2 结论)===${C.x}`);
  if (portBusy(FRONTEND_PORT)) {
    const pid = pidsOnPort(FRONTEND_PORT)[0];
    warn(`端口 ${FRONTEND_PORT} 已有监听(PID ${pid})——幂等跳过前端拉起(注意:可能是 dev 形态,如需生产形态请先 stop)`);
    return { skipped: true, pid };
  }
  await ensureFrontendBuild();
  const pid = spawnDetached("cmd", ["/c", "npx", "next", "start", "-p", String(FRONTEND_PORT)], FRONTEND_DIR, FRONTEND_LOG, { NEXT_PROD_DIST_DIR: PROD_DIST_DIR });
  recordPid("frontend", pid, { cmd: `next start -p ${FRONTEND_PORT}`, form: `build+start(${PROD_DIST_DIR})` });
  info(`前端拉起中(PID ${pid},日志 logs/deploy-frontend.log),等待 /login-register.html ...`);
  const ms = await waitHttp(`http://127.0.0.1:${FRONTEND_PORT}/login-register.html`, FRONTEND_READY_TIMEOUT_MS, "前端");
  ok(`前端就绪 http://127.0.0.1:${FRONTEND_PORT}/login-register.html(${ms}ms)`);
  return { skipped: false, pid };
}

async function runCheckDemoAssert() {
  log(`\n${C.b}=== ④ check-demo 断言(期望 9/9)===${C.x}`);
  const r = spawnSync(process.execPath, [CHECK_DEMO], { stdio: "inherit", cwd: BACKEND_DIR });
  const code = r.status ?? 1;
  if (code === 0) ok("check-demo 9/9 全绿——演示环境就绪");
  else {
    fail(`check-demo 存在红项(exit=${code})——按上方逐项指引处置;环境前提类红项(VM/Redis)如实记录不阻塞交付`);
    if (readEnvKeys(["DEBUG"]).DEBUG?.toLowerCase() === "true") {
      warn(`当前 .env 为 DEBUG=true(dev 形态):生产交付需按 .env.example 生产段配置 .env(DEBUG=false+强密钥,taskC3 硬验收范围)`);
    }
  }
  return code;
}

async function cmdStart() {
  log(`${C.b}=== EduAgent deploy start(build+start 生产形态;幂等)===${C.x}`);
  log(`${C.dim}后端目录: ${BACKEND_DIR}\n前端目录: ${FRONTEND_DIR}${C.x}`);
  if (!existsSync(CHECK_DEMO)) { fail(`缺少复用件: ${CHECK_DEMO}`); process.exit(2); }
  try { await preflight(); } catch (e) { warn(`前置检查异常(不阻塞): ${e.message}`); }

  let backend, frontend;
  try {
    backend = await startBackend();
    frontend = await startFrontend();
  } catch (e) {
    fail(e.message);
    process.exit(2);
  }
  const code = await runCheckDemoAssert();
  log(`\n${C.dim}PID 记录: ${PIDS_FILE};停止: node scripts/deploy/deploy.mjs stop${C.x}`);
  process.exit(code);
}

// ---------- stop ----------
function killPort(port, label) {
  const pids = pidsOnPort(port);
  if (!pids.length) { info(`${label} 端口 ${port} 无监听进程,跳过`); return { killed: [], none: true }; }
  const killed = [];
  for (const pid of pids) {
    const r = spawnSync("taskkill", ["/F", "/T", "/PID", String(pid)], { encoding: "utf8" });
    if (r.status === 0) { ok(`${label} 端口 ${port} PID ${pid} 已终止`); killed.push(pid); }
    else fail(`${label} 端口 ${port} PID ${pid} 终止失败: ${(r.stderr || r.stdout || "").split("\n")[0].slice(0, 120)}`);
  }
  return { killed, none: false };
}

function cmdStop() {
  log(`${C.b}=== EduAgent deploy stop(清 8000/3000)===${C.x}`);
  const b = killPort(BACKEND_PORT, "后端");
  const f = killPort(FRONTEND_PORT, "前端");
  // 清理陈旧 PID 记录(端口已无监听即视为陈旧)
  try {
    const j = JSON.parse(readFileSync(PIDS_FILE, "utf8"));
    if (b.none || b.killed.length) delete j.backend;
    if (f.none || f.killed.length) delete j.frontend;
    if (Object.keys(j).length) writeFileSync(PIDS_FILE, JSON.stringify(j, null, 2)); else rmSync(PIDS_FILE, { force: true });
  } catch { /* 无记录 */ }
  if (ALL) {
    log(`\n${C.dim}[--all] Redis 容器 ${REDIS_CONTAINER} 保留运行(不停)——缓存/限流/会话依赖它,一般无需停止;` +
      `如确需停止: docker stop ${REDIS_CONTAINER}(重启: docker start ${REDIS_CONTAINER};docker 引擎未运行先启动 Docker Desktop)${C.x}`);
  }
  const cleared = (b.killed.length || b.none) && (f.killed.length || f.none);
  log(cleared ? `\n${C.g}stop 完成:8000/3000 已清零或原本无监听${C.x}` : `\n${C.r}stop 部分失败,请复核 netstat -ano | findstr ":8000 :3000"${C.x}`);
  process.exit(cleared ? 0 : 1);
}

// ---------- status ----------
function cmdStatus() {
  info(`透传执行 scripts/check-demo.mjs(status=check-demo 原样)...\n`);
  const r = spawnSync(process.execPath, [CHECK_DEMO], { stdio: "inherit", cwd: BACKEND_DIR });
  process.exit(r.status ?? 1);
}

// ---------- 入口 ----------
(async () => {
  if (CMD === "start") return cmdStart();
  if (CMD === "stop") return cmdStop();
  if (CMD === "status") return cmdStatus();
  log("EduAgent 一键部署三件套(taskC1)");
  log("用法: node scripts/deploy/deploy.mjs start|stop|status [--all]");
  log("  start  前置检查(报告口径)→ 后端 uvicorn(读 .env 形态原样)→ 前端 build+start(.next-prod)→ check-demo 9/9 断言");
  log("  stop   按端口清 8000/3000;--all 附加 Redis 容器处置提示(容器本身不停)");
  log("  status 透传 check-demo.mjs");
  process.exit(CMD ? 2 : 0);
})();
