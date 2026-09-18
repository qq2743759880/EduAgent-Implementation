// EduAgent 一键部署(start / stop / status / stop-prod-and-restart-dev;taskC1 + W-NEXT-DEPLOY-HARD-001)
// 用法: node scripts/deploy/deploy.mjs start|stop|status|stop-prod-and-restart-dev
//                 [--all] [--frontend-port <N>] [--prod-gate] [--env <env文件路径>]
// 零新依赖:Node >= 18(net / fetch / child_process 均内置),与 check-demo.mjs 同栈。
//
// start : ①[--prod-gate 时]部署环境门 scripts/eval/deploy_env_gate.mjs(exit!=0 立即中止,不拉起任何服务)
//         ②前置检查(MySQL/VM Milvus+Mongo socket、Redis docker ping——只报告不阻塞硬启,
//           与 check-demo 同口径) ③后端 .venv uvicorn app.main:app --port 8000(读 .env 的
//           DEBUG/ENV_NAME 形态原样,不做替换;.env 须用户自行按 .env.example 配置)
//         ④前端 build+start 生产形态(C2 结论:NEXT_PROD_DIST_DIR=.next-prod,缺产物先 build)
//         ⑤拉起后自动跑 check-demo.mjs 断言(透传 --frontend-port;--prod-gate 时加 --prod-gate 严格门)
// stop  : 按端口清 8000/<FRONTEND_PORT>(--all 附加提示 Redis 容器处置,容器本身不停)
// status: 前端 dev/prod 形态判别(_buildManifest 探针,404=生产判据)→ 透传 scripts/check-demo.mjs
// stop-prod-and-restart-dev: 停 <FRONTEND_PORT> 生产实例(端口反查 PID→taskkill)→ 删 .next dev 缓存
//         (AGENTS.md 教训 1:dev 重启须删 .next;不动 .next-prod 生产产物)→ 起 next dev → 健康探测 200
//
// W-NEXT-DEPLOY-HARD-001 改造(2026-09-18),承接两份上游批判资产:
//   ① --frontend-port <N>(默认 3000):FRONTEND_PORT 从硬编码改为 CLI 参数派生,start/stop/status/
//      stop-prod-and-restart-dev 全链路生效并透传 check-demo(承接 W-NEXT-CHECKDEMO-PROD-001 P0-4:
//      此前 deploy 侧拉起/停止/记录不跟随 failover 端口,check-demo 探测侧单方跟随会判错端口)。
//   ② --prod-gate:start 前先跑部署环境门 deploy_env_gate.mjs(默认对 edu-agent/.env,--env 可指他文件;
//      exit!=0 中止),check-demo 断言段以 --prod-gate 严格模式跑(承接 W-NEXT-CHECKDEMO-PROD-001 P0-1:
//      deploy 出包路径接部署环境门,runCheckDemoAssert 不再裸跑 check-demo)。
//   ③ stop-prod-and-restart-dev(承接 W-NEXT-PRODUCTION-BUILD-001 P0-5:生产→dev 可逆性子命令封装)。
//   ④ status 形态判别(复用 check-demo ⑤ 同款 _buildManifest 探针;404=生产判据,200=dev)。
//
// 日志: edu-agent/logs/deploy-backend.log / deploy-frontend.log / deploy-frontend-build.log /
//       deploy-frontend-dev.log(stop-prod-and-restart-dev 专用)
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
const DEPLOY_ENV_GATE = path.join(BACKEND_DIR, "scripts", "eval", "deploy_env_gate.mjs"); // W-NEXT-DEPLOY-HARD-001 ②(只调用不改)
const PIDS_FILE = path.join(LOG_DIR, "deploy.pids.json");
const BACKEND_LOG = path.join(LOG_DIR, "deploy-backend.log");
const FRONTEND_LOG = path.join(LOG_DIR, "deploy-frontend.log");
const FRONTEND_BUILD_LOG = path.join(LOG_DIR, "deploy-frontend-build.log");
const FRONTEND_DEV_LOG = path.join(LOG_DIR, "deploy-frontend-dev.log"); // W-NEXT-DEPLOY-HARD-001 ③

// ---------- 常量(与 check-demo 同口径) ----------
const BACKEND_PORT = 8000;
// Redis 容器名不再硬编码(0f566ef 半成品=edu-redis-standalone 已漂移;W-NEXT-PROBE-001 同款按 .env
// REDIS_PORT 宿主端口反查运行中容器,见 preflight/detectRedisContainer)
const MYSQL_DEFAULT = { host: "127.0.0.1", port: 3306 };
const PROD_DIST_DIR = ".next-prod"; // C2 结论:NEXT_PROD_DIST_DIR 隔离 dev .next,build/start 两侧一致
const BACKEND_HEALTH_TIMEOUT_MS = 120_000; // CUDA 模型加载可能较慢
const FRONTEND_READY_TIMEOUT_MS = 90_000;
const SOCKET_TIMEOUT_MS = 3000;

const NOCOLOR = !process.stdout.isTTY;
const C = NOCOLOR
  ? { g: "", r: "", y: "", b: "", dim: "", x: "" }
  : { g: "\x1b[32m", r: "\x1b[31m", y: "\x1b[33m", b: "\x1b[36m", dim: "\x1b[2m", x: "\x1b[0m" };

// ---------- 工具 ----------
function log(msg = "") { console.log(msg); }
function info(msg) { log(`${C.b}[deploy]${C.x} ${msg}`); }
function ok(msg) { log(`${C.g}[ OK ]${C.x} ${msg}`); }
function warn(msg) { log(`${C.y}[WARN]${C.x} ${msg}`); }
function fail(msg) { log(`${C.r}[FAIL]${C.x} ${msg}`); }

// ---------- CLI 参数(W-NEXT-DEPLOY-HARD-001 ①②) ----------
const args = process.argv.slice(2);
const CMD = args[0];
const ALL = args.includes("--all");
// W-NEXT-DEPLOY-HARD-001 ①:--frontend-port <N>(默认 3000),校验口径与 check-demo cliPort 一致
function cliFlagValue(name) {
  const i = args.indexOf(name);
  if (i === -1) return undefined;
  return args[i + 1];
}
function cliPort(name, fallback) {
  if (!args.includes(name)) return fallback;
  const raw = args[args.indexOf(name) + 1];
  const p = Number.parseInt(raw, 10);
  if (raw === undefined || !Number.isFinite(p) || p < 1 || p > 65535) {
    fail(`参数错误: ${name} 需 1-65535 整数端口,得到 "${raw ?? "(缺值)"}"`);
    process.exit(2);
  }
  return p;
}
const FRONTEND_PORT = cliPort("--frontend-port", 3000);
// W-NEXT-DEPLOY-HARD-001 ②:--prod-gate 部署门总开关(start 前跑 deploy_env_gate + check-demo 严格模式)
const PROD_GATE = args.includes("--prod-gate");
const ENV_FLAG = args.includes("--env");
// --env <路径>:部署环境门读取的 env 文件(默认 edu-agent/.env;仅与 --prod-gate 搭配生效)
const GATE_ENV_PATH = (() => {
  const v = cliFlagValue("--env");
  if (v === undefined) return path.join(BACKEND_DIR, ".env");
  if (!v || v.startsWith("--")) { fail(`参数错误: --env 需要一个 env 文件路径,得到 "${v ?? "(缺值)"}"`); process.exit(2); }
  return path.resolve(process.cwd(), v);
})();

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

// ---------- 形态判别(W-NEXT-DEPLOY-HARD-001 ④,复用 check-demo ⑤ 同款探针) ----------
// 判据与 check-demo ⑤ 同源:next dev 会暴露 /_next/static/development/_buildManifest.js(200),
// 生产 build 无此路径(404)→ 404=生产判据,200=dev 形态。
async function detectFrontendForm() {
  const base = `http://127.0.0.1:${FRONTEND_PORT}`;
  const TMO = SOCKET_TIMEOUT_MS + 2000;
  try {
    const login = await fetch(`${base}/login-register.html`, { signal: AbortSignal.timeout(TMO) });
    await login.text().catch(() => {});
    if (login.status !== 200) return { form: "abnormal", detail: `login-register.html HTTP ${login.status}` };
    let probe;
    try {
      const bm = await fetch(`${base}/_next/static/development/_buildManifest.js`, { signal: AbortSignal.timeout(TMO) });
      await bm.text().catch(() => {});
      probe = String(bm.status);
    } catch (e) { probe = `err(${String(e?.message || e).slice(0, 40)})`; }
    return { form: probe === "200" ? "dev" : "prod", detail: `_buildManifest dev 探针=${probe}` };
  } catch (e) {
    return { form: "down", detail: String(e?.message || e).slice(0, 80) };
  }
}

async function backendHealthQuick() {
  try {
    const r = await fetch(`http://127.0.0.1:${BACKEND_PORT}/health`, { signal: AbortSignal.timeout(5000) });
    const t = await r.text().catch(() => "");
    if (r.status !== 200) return `http ${r.status}`;
    return /"status"\s*:\s*"ok"/.test(t) ? "ok" : "non-ok";
  } catch { return "down"; }
}

// ---------- 前置检查(只报告不阻塞,与 check-demo 同口径) ----------
function parseUriHostPort(uri, fallbackPort) {
  // 支持 http://host:port / mongodb://host:port / redis://host:port/db
  try {
    const u = new URL(uri);
    return { host: u.hostname, port: Number(u.port) || fallbackPort };
  } catch { return null; }
}

// 按宿主发布端口反查运行中容器名(docker ps --filter publish=<port>;W-NEXT-PROBE-001 同款)
function detectRedisContainer(port) {
  const r = spawnSync("docker", ["ps", "--filter", `publish=${port}`, "--format", "{{.Names}}"], { encoding: "utf8", timeout: 8000 });
  if (r.status !== 0) throw new Error((r.stderr || r.stdout || `docker ps 退出码 ${r.status}`).split("\n")[0].slice(0, 120));
  const name = (r.stdout || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean)[0];
  if (!name) throw new Error(`未找到映射宿主端口 ${port} 的运行中容器`);
  return name;
}

async function preflight() {
  const env = readEnvKeys(["DEBUG", "ENV_NAME", "MYSQL_HOST", "MYSQL_PORT", "MILVUS_URI", "MONGO_URI", "REDIS_URL", "REDIS_PORT"]);
  log(`\n${C.b}=== ① 前置检查(报告口径,不阻塞硬启——与 check-demo 同口径)===${C.x}`);

  // 形态报告(部署形态要求用户 .env 已按 .env.example 生产段配置;脚本只检查并报告)
  const dbg = (env.DEBUG || "(未设置→config.py 默认 False)").toLowerCase();
  const envName = env.ENV_NAME || "(未设置→config.py 默认 local)";
  info(`.env 形态原样: DEBUG=${dbg}  ENV_NAME=${envName}  (脚本不做替换)`);
  if (dbg === "true") {
    warn(`当前为 dev 形态(DEBUG=true):存在虚拟管理员后门风险面(P1-8 门禁要求 DEBUG=true+ENV_NAME=local;生产交付前必须改 false,taskC3 硬验收;出包请加 --prod-gate 走部署环境门)`);
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

  // Redis:按 .env REDIS_PORT(缺省回退 REDIS_URL 端口/6379)反查容器名后 docker exec ping,
  //   失败给指引但不阻塞(W-NEXT-PROBE-001 同款端口反查——0f566ef 半成品硬编码 edu-redis-standalone,
  //   而本机活容器已漂移为按 REDIS_PORT=6377 映射的容器,硬编码会假红,2026-09-18 实测修正)
  const redisPort = Number(env.REDIS_PORT) || parseUriHostPort(env.REDIS_URL || "", 6379)?.port || 6379;
  try {
    const container = detectRedisContainer(redisPort);
    const r = spawnSync("docker", ["exec", container, "redis-cli", "ping"], { encoding: "utf8", timeout: 8000 });
    if (r.status === 0 && /PONG/i.test(r.stdout || "")) ok(`Redis 可达 — docker exec ${container} redis-cli ping = PONG(宿主端口 ${redisPort})`);
    else throw new Error((r.stderr || r.stdout || `退出码 ${r.status}`).split("\n")[0].slice(0, 120));
  } catch (e) {
    fail(`Redis 不可达 — 宿主端口 ${redisPort} 反查容器 docker exec redis-cli ping [${e.message}]`);
    warn(`  -> 处置: 按 .env REDIS_PORT=${redisPort} 反查容器名,docker start <容器名>(若 docker 引擎未运行,先启动 Docker Desktop)`);
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

// ---------- 部署环境门(W-NEXT-DEPLOY-HARD-001 ②;只调用不改 scripts/eval/deploy_env_gate.mjs) ----------
function runDeployEnvGate() {
  info(`部署环境门: node scripts/eval/deploy_env_gate.mjs ${GATE_ENV_PATH}`);
  const r = spawnSync(process.execPath, [DEPLOY_ENV_GATE, GATE_ENV_PATH], { stdio: "inherit", cwd: BACKEND_DIR });
  return r.status ?? 1;
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
  log(`\n${C.b}=== ③ 前端(build+start 生产形态,C2 结论;端口 ${FRONTEND_PORT})===${C.x}`);
  if (portBusy(FRONTEND_PORT)) {
    const pid = pidsOnPort(FRONTEND_PORT)[0];
    warn(`端口 ${FRONTEND_PORT} 已有监听(PID ${pid})——幂等跳过前端拉起(注意:可能是 dev 形态,形态判别用 deploy.mjs status;如需生产形态请先 stop)`);
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
  log(`\n${C.b}=== ④ check-demo 断言(期望 9/9;--frontend-port ${FRONTEND_PORT}${PROD_GATE ? " + --prod-gate 严格门" : ""})===${C.x}`);
  // W-NEXT-DEPLOY-HARD-001 ①②:透传 --frontend-port(探测侧跟随部署端口,CHECKDEMO-PROD-001 P0-4);
  //   --prod-gate 时透传严格门旗标(承接 CHECKDEMO-PROD-001 P0-1:deploy 出包路径不再裸跑 check-demo)
  const cdArgs = [CHECK_DEMO, "--frontend-port", String(FRONTEND_PORT)];
  if (PROD_GATE) cdArgs.push("--prod-gate");
  const r = spawnSync(process.execPath, cdArgs, { stdio: "inherit", cwd: BACKEND_DIR });
  const code = r.status ?? 1;
  if (code === 0) ok("check-demo 9/9 全绿——演示环境就绪");
  else {
    fail(`check-demo 存在红项(exit=${code})——按上方逐项指引处置;环境前提类红项(VM/Redis)如实记录不阻塞交付`);
    if (readEnvKeys(["DEBUG"]).DEBUG?.toLowerCase() === "true") {
      warn(`当前 .env 为 DEBUG=true(dev 形态):生产交付需按 .env.example 生产段配置 .env(DEBUG=false+强密钥,taskC3 硬验收范围;出包请加 --prod-gate)`);
    }
  }
  return code;
}

async function cmdStart() {
  log(`${C.b}=== EduAgent deploy start(build+start 生产形态;幂等;前端端口 ${FRONTEND_PORT})===${C.x}`);
  log(`${C.dim}后端目录: ${BACKEND_DIR}\n前端目录: ${FRONTEND_DIR}${C.x}`);
  if (!existsSync(CHECK_DEMO)) { fail(`缺少复用件: ${CHECK_DEMO}`); process.exit(2); }
  // ⓪ 部署环境门(W-NEXT-DEPLOY-HARD-001 ②;--prod-gate 时启用,exit!=0 即中止,不拉起任何服务)
  if (PROD_GATE) {
    if (!existsSync(DEPLOY_ENV_GATE)) { fail(`缺少复用件: ${DEPLOY_ENV_GATE}`); process.exit(2); }
    log(`\n${C.b}=== ⓪ 部署环境门(deploy_env_gate.mjs;exit!=0 即中止)===${C.x}`);
    const g = runDeployEnvGate();
    if (g !== 0) {
      fail(`部署环境门未通过(exit=${g})——已中止部署,未拉起任何服务`);
      warn(`  -> 处置: 改 ${GATE_ENV_PATH} 为 DEBUG=false(生产唯一合法形态,参照 .env.example 生产段;JWT_SECRET/API_TOKEN 同步改非默认值)后重试`);
      warn(`  -> 说明: 部署门从严判——DEBUG=true 一律不可出包(含 ENV_NAME 缺省/local 的本机 dev 形态);本地开发日常把关用 check-demo.mjs ⑧(WARN 不阻断)`);
      process.exit(2);
    }
    ok(`部署环境门 PASS——继续部署`);
  } else {
    info(`${C.dim}未启用 --prod-gate:跳过部署环境门(生产出包请加 --prod-gate;check-demo 断言段也将以常规模式跑)${C.x}`);
    if (ENV_FLAG) warn(`--env 已传但未搭配 --prod-gate,本次不生效(部署环境门仅在 --prod-gate 下运行)`);
  }
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
  log(`\n${C.dim}PID 记录: ${PIDS_FILE};停止: node scripts/deploy/deploy.mjs stop --frontend-port ${FRONTEND_PORT};回退 dev: node scripts/deploy/deploy.mjs stop-prod-and-restart-dev --frontend-port ${FRONTEND_PORT}${C.x}`);
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
  log(`${C.b}=== EduAgent deploy stop(清 8000/${FRONTEND_PORT})===${C.x}`);
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
    log(`\n${C.dim}[--all] Redis 容器(按 .env REDIS_PORT 宿主端口反查)保留运行(不停)——缓存/限流/会话依赖它,一般无需停止;` +
      `如确需停止: docker stop <按 REDIS_PORT 反查的容器名>(重启: docker start <同容器名>;docker 引擎未运行先启动 Docker Desktop)${C.x}`);
  }
  const cleared = (b.killed.length || b.none) && (f.killed.length || f.none);
  log(cleared ? `\n${C.g}stop 完成:8000/${FRONTEND_PORT} 已清零或原本无监听${C.x}` : `\n${C.r}stop 部分失败,请复核 netstat -ano | findstr ":8000 :${FRONTEND_PORT}"${C.x}`);
  process.exit(cleared ? 0 : 1);
}

// ---------- stop-prod-and-restart-dev(W-NEXT-DEPLOY-HARD-001 ③;承接 PRODUCTION-BUILD-001 P0-5) ----------
async function cmdStopProdAndRestartDev() {
  log(`${C.b}=== EduAgent deploy stop-prod-and-restart-dev(生产→dev 可逆;端口 ${FRONTEND_PORT})===${C.x}`);
  // ① 停前形态如实记录(_buildManifest 探针)
  const before = await detectFrontendForm();
  info(`停前前端 ${FRONTEND_PORT} 形态: ${before.form}(${before.detail})`);
  // ② 按端口反查 PID → taskkill /F /T(与 stop 同机制)
  const r = killPort(FRONTEND_PORT, "前端");
  if (!r.none && !r.killed.length) { fail(`端口 ${FRONTEND_PORT} 存在监听但终止失败——中止(防止 next dev failover 到错误端口)`); process.exit(1); }
  // ②b 等待端口释放(有界 10s;盲测③实测:taskkill 报成功后进程 teardown/套接字关闭有秒级窗口,
  //     0f566ef 半成品立即 portBusy 曾误判"仍被占用"而中止——轮询到 LISTENING 消失再放行)
  let released = false;
  for (let i = 0; i < 20; i++) {
    if (!portBusy(FRONTEND_PORT)) { released = true; break; }
    await sleep(500);
  }
  if (!released) { fail(`端口 ${FRONTEND_PORT} 在 10s 内仍未释放——中止(防止 next dev failover 到错误端口)`); process.exit(1); }
  ok(`端口 ${FRONTEND_PORT} 已释放`);
  // ③ 删 .next dev 缓存(AGENTS.md 教训 1:dev server 不热重载入口跳转,重启须删 .next;
  //    只删 .next,不动 .next-prod 生产产物——C2 结论两侧隔离)
  const devCache = path.join(FRONTEND_DIR, ".next");
  if (existsSync(devCache)) {
    try { rmSync(devCache, { recursive: true, force: true }); ok(`已删 dev 缓存 ${devCache}(生产产物 ${PROD_DIST_DIR} 未动)`); }
    catch (e) { fail(`删 ${devCache} 失败: ${e.message}(可能有进程占用,请复核后重试)`); process.exit(1); }
  } else {
    info(`无 .next dev 缓存,跳过删除`);
  }
  // ④ 起 next dev(实证 2026-09-18:活生产实例命令行 = `node node_modules/next/dist/bin/next start -p 3000`,
  //    vendored next 真实入口在 node_modules/next/dist/bin/next——0f566ef 半成品误写 FRONTEND_DIR/next/... 已修)
  const nextBin = path.join(FRONTEND_DIR, "node_modules", "next", "dist", "bin", "next");
  if (!existsSync(nextBin)) { fail(`未找到 next 可执行入口: ${nextBin}`); process.exit(2); }
  const pid = spawnDetached(process.execPath, [nextBin, "dev", "-p", String(FRONTEND_PORT)], FRONTEND_DIR, FRONTEND_DEV_LOG);
  recordPid("frontend", pid, { cmd: `next dev -p ${FRONTEND_PORT}`, form: "next dev(stop-prod-and-restart-dev)" });
  info(`next dev 拉起中(PID ${pid},日志 logs/deploy-frontend-dev.log),等待 /login-register.html ...`);
  // ⑤ 健康探测 200
  const ms = await waitHttp(`http://127.0.0.1:${FRONTEND_PORT}/login-register.html`, FRONTEND_READY_TIMEOUT_MS, "前端 dev");
  ok(`前端 dev 就绪 http://127.0.0.1:${FRONTEND_PORT}/login-register.html 200(${ms}ms)`);
  // ⑥ 形态复核(_buildManifest 探针期望 200=dev)
  const after = await detectFrontendForm();
  if (after.form === "dev") ok(`形态复核: dev(${after.detail})——已从生产切回开发形态`);
  else warn(`形态复核异常: ${after.form}(${after.detail})——健康探测已 200,请人工复核`);
  log(`\n${C.dim}回到生产形态: node scripts/deploy/deploy.mjs start --frontend-port ${FRONTEND_PORT}${C.x}`);
}

// ---------- status(W-NEXT-DEPLOY-HARD-001 ④:形态判别 + 原有 check-demo 透传) ----------
async function cmdStatus() {
  log(`${C.b}=== EduAgent deploy status(形态判别 + check-demo 透传)===${C.x}`);
  const fe = await detectFrontendForm();
  const be = await backendHealthQuick();
  const formLine = `前端 ${FRONTEND_PORT} 形态: ${fe.form}(${fe.detail})`;
  if (fe.form === "prod") ok(`${formLine} —— 生产 build 形态(_buildManifest dev 探针 404=生产判据)`);
  else warn(formLine + (fe.form === "dev" ? " —— next dev 开发形态,生产交付请 deploy.mjs start(build+start .next-prod)" : fe.form === "down" ? " —— 未监听/不可达,拉起用 deploy.mjs start" : ""));
  const beLine = `后端 ${BACKEND_PORT} /health: ${be}`;
  if (be === "ok") ok(beLine); else warn(`${beLine} —— 拉起用 deploy.mjs start(或查 logs/deploy-backend.log)`);
  log(`[STATUS] ${JSON.stringify({ frontend_port: FRONTEND_PORT, frontend_form: fe.form, frontend_detail: fe.detail, backend_health: be })}`);
  info(`透传执行 scripts/check-demo.mjs(status=check-demo 原样;--frontend-port ${FRONTEND_PORT}${PROD_GATE ? " --prod-gate" : ""})...\n`);
  const cdArgs = [CHECK_DEMO, "--frontend-port", String(FRONTEND_PORT)];
  if (PROD_GATE) cdArgs.push("--prod-gate");
  const r = spawnSync(process.execPath, cdArgs, { stdio: "inherit", cwd: BACKEND_DIR });
  process.exit(r.status ?? 1);
}

// ---------- 入口 ----------
(async () => {
  if (CMD === "start") return cmdStart();
  if (CMD === "stop") return cmdStop();
  if (CMD === "status") return cmdStatus();
  if (CMD === "stop-prod-and-restart-dev") return cmdStopProdAndRestartDev();
  log("EduAgent 一键部署(taskC1 三件套 + W-NEXT-DEPLOY-HARD-001 可逆性/端口/部署门扩展)");
  log("用法: node scripts/deploy/deploy.mjs start|stop|status|stop-prod-and-restart-dev [--all] [--frontend-port <N>] [--prod-gate] [--env <env文件>]");
  log("  start                      前置检查(报告口径)→[--prod-gate: 部署环境门,exit!=0 中止]→ 后端 uvicorn(读 .env 形态原样)→ 前端 build+start(.next-prod)→ check-demo 断言");
  log(`  stop                       按端口清 8000/${FRONTEND_PORT};--all 附加 Redis 容器处置提示(容器本身不停)`);
  log(`  status                     前端 dev/prod 形态判别(_buildManifest 探针,404=生产判据)→ 透传 check-demo.mjs`);
  log(`  stop-prod-and-restart-dev  停 ${FRONTEND_PORT} 生产实例(端口反查 PID→taskkill)→ 删 .next dev 缓存(AGENTS.md 教训1,不动 .next-prod)→ 起 next dev → 健康探测 200`);
  log(`  --frontend-port <N>        前端端口(默认 3000;start/stop/status/stop-prod-and-restart-dev 全链路生效,并透传 check-demo --frontend-port)`);
  log(`  --prod-gate                start 前跑 scripts/eval/deploy_env_gate.mjs(exit!=0 中止部署)+ check-demo 断言段以 --prod-gate 严格模式跑`);
  log(`  --env <env文件>            部署环境门读取的 env 文件路径(默认 edu-agent/.env;仅与 --prod-gate 搭配生效)`);
  process.exit(CMD ? 2 : 0);
})();
