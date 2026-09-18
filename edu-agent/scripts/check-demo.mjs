// EduAgent 演示前检查单(task18 七件套 + DEBUG advisory)
// 用法: node scripts/check-demo.mjs [--fail-drill] [--no-color] [--frontend-port <N>] [--prod-gate]
// 零新依赖:Node >= 18(fetch / net / child_process 均内置)。
// 检查项:① Milvus socket ② Redis(docker exec redis-cli ping)③ MongoDB socket
//         ④ 后端 8000 /health ⑤ 前端 /login-register.html(默认 3000,--frontend-port 可改)+ 前端形态判别(dev/prod,T5-C2)
//         ⑥ 登录链路(admin+student 各一次 login + /api/auth/me)
//         ⑦ 8 个核心 html 页 200  ⑧ advisory:DEBUG 虚拟管理员漏洞探测(教训 6,两级判据 + --prod-gate,W-NEXT-CHECKDEMO-PROD-001)
// ⑨ 抽验页 /admin-users-refine-proto.html 200(C5-D2 扩清单)  ⑩ 契约对账门 febe_contract_check.py
// ⑪ VEC-LOCK embed 一致性健康门（edu_knowledge 元数据全=锁定 BGE-M3 revision）
// ⑫ HITL 真实性  ⑬ MCP 三态门  ⑭ 内部可见性  ⑮ Redis 端口对账  ⑯ lifecycle 健壮性
// ⑰ MCP 跨权限门对账（chat 路径真接 4 个 API + AST 链） ⑱ febe root path 闭环 ⑲ VEC-LOCK 守门（12 维机验 + dim0 backend）
// ⑳ OTLP 链路健康（endpoint 解析 + SSRF 守门 + TCP 探活；W-NEXT-OTLP-001）
// ㉑ embed URL SSRF 守门（W-NEXT-EXE-SSRF-002）
// 共 21 项检查。全绿才 exit 0;FAIL 时逐项给一句话处置指引;--fail-drill 用假端口验证失败路径(不动真实服务)。
import net from "node:net";
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// ---------- 配置(按演示机实际环境修改这里) ----------
const VMX_PATH = "E:\\tt\\CentOS 7 64 位 的克隆 docker\\CentOS 7 64 位 的克隆 docker.vmx";
const MILVUS = { host: "192.168.85.101", port: 19530 };
const MONGO = { host: "192.168.85.101", port: 27017 };
const BACKEND = process.env.CHECK_DEMO_BACKEND || "http://127.0.0.1:8000"; // env 覆盖仅用于 ⑧ WARN 分支自测
// W-NEXT-CHECKDEMO-PROD-001 尾巴①:FRONTEND 从硬编码 3000 改为 --frontend-port 参数派生,
//   定义移至下方「参数」段(args 解析之后)。8000 后端端口不动(④⑥⑧ 等仍指 BACKEND)。
const ADMIN = { account: "adm02test", password: "Test@123456" };
const STUDENT = { account: "user000001", password: "Test@123456" };
// W-NEXT-PROBE-001 修:② 容器名不再硬编码。原 `REDIS_CONTAINER="edu-redis-standalone"`
//   与当前演示机实际容器 `prisma-ai-redis-container-1`（宿主 6377→容器 6379）漂移,
//   硬编码碰上容器重命名 / 端口重映射即永远红。同型风险:硬编码容器名 = 部署拓扑漂移即盲区。
//   改为端口反查容器名（.env REDIS_PORT/REDIS_URL → docker ps --filter publish=<port>）。
//   fail-drill 假端口（6380）走 `--fail-drill` 路径覆盖,与 normal 互不污染。
// 解析优先级:.env REDIS_PORT > REDIS_URL 端口 > 默认 6377
function readEnvRedisPort() {
  try {
    const envPath = fileURLToPath(new URL("../.env", import.meta.url));
    if (!existsSync(envPath)) return 6377;
    for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
      const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
      if (!m) continue;
      if (m[1] === "REDIS_PORT" && m[2]) {
        const p = parseInt(m[2], 10);
        if (Number.isFinite(p) && p > 0 && p < 65536) return p;
      }
      if (m[1] === "REDIS_URL" && m[2]) {
        const um = /^redis:\/\/[^:/]+(?::(\d+))?/.exec(m[2]);
        if (um && um[1]) {
          const p = parseInt(um[1], 10);
          if (Number.isFinite(p) && p > 0 && p < 65536) return p;
        }
      }
    }
  } catch { /* fall through */ }
  return 6377;
}
// W-NEXT-PROBE-001 修:按宿主端口反查容器名(替代硬编码 "edu-redis-standalone")。
//   1) docker ps --filter publish=<port> --format "{{.Names}}" 拿首个匹配的容器名;
//   2) 0 匹配 → 退到 --filter "expose=<port>" — 防 default-bridge/network 模式 publish 字段不显;
//   3) 仍 0 匹配 → 抛错"未找到映射端口 <port> 的 Redis 容器"。
async function detectRedisContainer(hostPort) {
  // 第 1 试:publish 过滤
  let out;
  try {
    out = await runCmd("docker", ["ps", "--filter", `publish=${hostPort}`, "--format", "{{.Names}}"], DOCKER_TIMEOUT_MS);
  } catch (e) {
    // docker 引擎未起/命令不存在 → 让上层 FIX.redis 指引处置
    throw e;
  }
  let names = (out || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
  if (names.length > 0) return names[0];
  // 第 2 试:expose 过滤(兜底)
  try {
    out = await runCmd("docker", ["ps", "--filter", `expose=${hostPort}`, "--format", "{{.Names}}"], DOCKER_TIMEOUT_MS);
    names = (out || "").split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    if (names.length > 0) return names[0];
  } catch { /* fall through to raise */ }
  throw new Error(`未找到映射宿主端口 ${hostPort} 的 Redis 容器(检查 docker ps 与端口映射)`);
}
// 关键页 8 个(核心故事线页面)
const PAGES = [
  "login-register.html",
  "courses.html",
  "course-detail.html?id=1",
  "dashboard.html",
  "learning.html",
  "admin-dashboard.html",
  "admin-mcp.html",
  "admin-rag-upload.html",
];
const SOCKET_TIMEOUT_MS = 3000; // 控制总耗时 <1 分钟(GWT 指标)的关键
const HTTP_TIMEOUT_MS = 5000;
const DOCKER_TIMEOUT_MS = 8000;

// ---------- 参数 ----------
const args = process.argv.slice(2);
const DRILL = args.includes("--fail-drill");
const NOCOLOR = args.includes("--no-color") || !process.stdout.isTTY;
// W-NEXT-CHECKDEMO-PROD-001 尾巴②:--prod-gate 部署门旗标——⑧ 的 WARN(开发态后门)升级为 FAIL(exit 1)。
//   动机(P0-1):⑧ WARN 不阻断 exit 0,CI/出包流水线默认放行,DEBUG=true 随包进生产。
//   显式升级旗标而非删检测:检测能力保留,只在部署把关场景收紧。
const PROD_GATE = args.includes("--prod-gate");
// W-NEXT-CHECKDEMO-PROD-001 尾巴①:--frontend-port <N>(默认 3000)。
//   动机:W-NEXT-PRODUCTION-BUILD-001 盲测态C 实证——next start 端口被占 failover 到 3001 时,
//   ⑤⑦⑨ 仍探硬编码 3000 判错。⑤⑦⑨ 全部改用 FRONTEND_PORT 派生;只动前端端口,8000 不动。
function cliPort(name, fallback) {
  const i = args.indexOf(name);
  if (i === -1) return fallback;
  const raw = args[i + 1];
  const p = Number.parseInt(raw, 10);
  if (raw === undefined || !Number.isFinite(p) || p < 1 || p > 65535) {
    console.error(`参数错误: ${name} 需 1-65535 整数端口,得到 "${raw ?? "(缺值)"}"`);
    process.exit(2);
  }
  return p;
}
const FRONTEND_PORT = cliPort("--frontend-port", 3000);
const FRONTEND = `http://127.0.0.1:${FRONTEND_PORT}`;
const C = NOCOLOR
  ? { g: "", r: "", y: "", b: "", dim: "", x: "" }
  : { g: "\x1b[32m", r: "\x1b[31m", y: "\x1b[33m", b: "\x1b[36m", dim: "\x1b[2m", x: "\x1b[0m" };

// ---------- 工具 ----------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 读 edu-agent/.env 判 DEBUG/ENV_NAME(A-G4 三分支判据):缺文件/缺值按安全缺省
// ENV_NAME 缺省 = null(非 local)——T5-C1 修:原默认 "local" 会把「未声明环境」误判为安全开发态
function readDevEnv() {
  // W-NEXT-CHECKDEMO-001 修:fileURLToPath 解码 Windows 中文/特殊字符路径,
  // 否则 .pathname 返回 percent-encoded 串导致 spawn ENOENT(⑯⑰ 等守卫 1ms 退出)
  const envPath = fileURLToPath(new URL("../.env", import.meta.url));
  const out = { DEBUG: null, ENV_NAME: null };
  if (!existsSync(envPath)) return out;
  for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
    if (!m) continue;
    if (m[1] === "DEBUG") out.DEBUG = m[2];
    if (m[1] === "ENV_NAME") out.ENV_NAME = m[2] || null; // 空值同样视为未确证 local
  }
  return out;
}

async function timed(fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    return { ok: true, ms: Date.now() - t0, detail: detail || "" };
  } catch (e) {
    return { ok: false, ms: Date.now() - t0, detail: String(e?.message || e).slice(0, 160), err: e };
  }
}

// socket 探活(带超时;VM 关机时 SYN 无响应,靠超时兜底防止卡满 Windows 默认 21s)
function socketProbe(host, port, timeoutMs = SOCKET_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    const s = net.connect({ host, port });
    let done = false;
    const finish = (err) => {
      if (done) return;
      done = true;
      s.destroy();
      err ? reject(err) : resolve();
    };
    s.setTimeout(timeoutMs, () => finish(new Error(`连接超时(>${timeoutMs}ms),主机不可达`)));
    s.on("connect", () => finish(null));
    s.on("error", (e) => {
      const m = { ECONNREFUSED: "连接被拒绝", EHOSTUNREACH: "主机不可达", ENETUNREACH: "网络不可达" }[e.code] || e.message;
      finish(new Error(m));
    });
  });
}

async function httpProbe(url, { method = "GET", headers = {}, body, expect = 200, mustJson } = {}) {
  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
  });
  const text = await res.text();
  if (res.status !== expect) throw new Error(`HTTP ${res.status}(期望 ${expect})`);
  if (mustJson) {
    let j;
    try { j = JSON.parse(text); } catch { throw new Error("响应非 JSON"); }
    if (mustJson.code !== undefined && j.code !== mustJson.code) {
      throw new Error(`code=${j.code} ${j.message || ""}`.trim());
    }
    return j;
  }
  return undefined;
}

// 运行本机命令(docker exec 等),带超时,非零退出码抛错
function runCmd(cmd, cargs, timeoutMs = DOCKER_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    let stdout = "", stderr = "", settled = false;
    const child = spawn(cmd, cargs); // 不用 shell:true:避免 DEP0190,且 docker.exe 可经 PATH 解析
    const timer = setTimeout(() => {
      if (!settled) { settled = true; child.kill(); reject(new Error(`命令超时(>${timeoutMs}ms)`)); }
    }, timeoutMs);
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", (e) => { if (!settled) { settled = true; clearTimeout(timer); reject(new Error(e.code === "ENOENT" ? "命令不存在" : e.message)); } });
    child.on("close", (code) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      const out = (stdout + stderr).trim();
      if (code !== 0) {
        const msg = /pipe\/docker_engine|cannot find the file specified/i.test(out)
          ? "docker 引擎未运行(Docker Desktop 未启动)"
          : out.split("\n")[0].slice(0, 120) || `退出码 ${code}`;
        reject(new Error(msg));
      } else resolve(out);
    });
  });
}

// ---------- 契约对账（FE-BE-CONTRACT 三方对账门）----------
// 跑 edu-agent/scripts/eval/febe_contract_check.py，解析 [SUMMARY] 行判定：
//   断点 >0  -> FAIL（前端调用了后端不存在的路由）
//   待接/未冻结 >0 -> WARN（不阻断）
//   exit 2 = 后端不可达（以④红项为准，此处降级为 WARN，避免重复误报）
const FEBE_SCRIPT = fileURLToPath(new URL("../scripts/eval/febe_contract_check.py", import.meta.url));

async function resolvePython() {
  for (const c of ["python3", "python"]) {
    try {
      await runCmd(c, ["--version"], 5000);
      return c;
    } catch { /* try next */ }
  }
  // 末位兜底：本机托管 python（Git Bash 下 PATH 通常有，但保险起见）
  const fallback = "C:\\Users\\Administrator\\.workbuddy\\binaries\\python\\versions\\3.13.12\\python.exe";
  if (existsSync(fallback)) return fallback;
  throw new Error("未找到 python 解释器（需 python3/python 在 PATH）");
}

// 跑 venv/system python 探针,带超时,非零退出码抛错
// W-NEXT-CHECKDEMO-002 修:runPy 此前是 function runPy(python, args) —— 第三参数 timeoutMs
//    被静默丢弃,所有调用点实际都是 60000ms(⑲ 600000 / ⑯ 300000 / ⑭ 90000 等
//    全被吞)。⑲ veclock_verify 实测 1m57s 必然撞 60s 红断(BGE-M3 mmap 重 load
//    + 5 串行 inference batch 物理下限 ~30s+)。统一:第三参数 timeoutMs 兜底 60000。
function runPy(python, args, timeoutMs = 60000) {
  return new Promise((resolve, reject) => {
    let stdout = "", stderr = "", settled = false;
    const child = spawn(python, args, { windowsHide: true });
    const timer = setTimeout(() => {
      if (!settled) { settled = true; child.kill(); reject(new Error(`python 探针超时(>${timeoutMs}ms)`)); }
    }, timeoutMs);
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", (e) => { if (!settled) { settled = true; clearTimeout(timer); reject(e); } });
    child.on("close", (code) => {
      if (settled) return;
      settled = true; clearTimeout(timer);
      resolve({ code, stdout, stderr });
    });
  });
}

// ---------- 结果收集 ----------
const results = [];
async function check(no, name, fn) {
  const r = await timed(fn);
  // advisory 项走 WARN(软,不阻断 exit)而非 FAIL:检查函数静态 __warn 或按结果动态 e.__warn
  // (T5-C1:⑧ 分支 C 必须真红,故 ⑧ 不再静态 __warn,改由分支 B 抛 e.__warn 标 WARN)
  const isWarn = !r.ok && (fn.__warn === true || r.err?.__warn === true);
  results.push({ no, name, ...r, warn: isWarn });
  if (r.ok) {
    console.log(`${C.g}[PASS]${C.x} ${no}. ${name} ${C.dim}(${r.ms}ms)${C.x}${r.detail ? C.dim + "  " + r.detail + C.x : ""}`);
  } else if (isWarn) {
    console.log(`${C.y}[WARN]${C.x} ${no}. ${name} ${C.dim}(${r.ms}ms)${C.x}`);
    console.log(`       ${C.y}-> ${fn.__fix ? fn.__fix(r.detail) : r.detail}${C.x}`);
  } else {
    console.log(`${C.r}[FAIL]${C.x} ${no}. ${name} ${C.dim}(${r.ms}ms)${C.x}`);
    console.log(`       ${C.y}-> ${fn.__fix ? fn.__fix(r.detail) : r.detail}${C.x}`);
  }
  return r.ok;
}

// 处置指引(FAIL 时一句话)
const FIX = {
  vm: (d) => `开启 VMware 虚拟机: vmrun start "${VMX_PATH}" nogui,等 60s${existsSync(VMX_PATH) ? "" : `(注意:配置的 vmx 路径不存在,请确认虚拟机实际路径)`} [${d}]`,
  redis: (d) => `按 .env REDIS_PORT 端口反查容器名,docker start <容器>(若 docker 引擎未运行,先启动 Docker Desktop)[${d}]`,
  backend: (d) => `cd edu-agent && .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000 [${d}]`,
  frontend: (d) => `cd edu-frontend && node node_modules/next/dist/bin/next dev -p ${FRONTEND_PORT}(或 deploy.mjs start 生产形态;--frontend-port 已选 ${FRONTEND_PORT}) [${d}]`,
  debug: (d) => `DEBUG=true 虚拟管理员漏洞,上线前必须 False(settings.DEBUG=false 并重启后端);ENV_NAME 显式非 local 时属生产类环境直接禁止部署(P1-8 两级判据) [${d}]`,
};

// ---------- 主流程 ----------
console.log(`${C.b}=== EduAgent 演示前检查单 check-demo.mjs ===${C.x}`);
console.log(`${C.dim}模式: ${DRILL ? "fail-drill(假端口演练,结果仅验证失败路径)" : "normal"}  前端端口: ${FRONTEND_PORT}${PROD_GATE ? "  [prod-gate:⑧ WARN 升级 FAIL(部署门)]" : ""}  时间: ${new Date().toLocaleString()}${C.x}\n`);
if (DRILL) {
  console.log(`${C.y}${C.dim}--fail-drill:① Milvus→127.0.0.1:19531 ② Redis→容器内 6380 假端口 ③ Mongo→127.0.0.1:27018(必然失败,验证 FAIL 输出与指引)${C.x}\n`);
}

const milvusTarget = DRILL ? { host: "127.0.0.1", port: 19531 } : MILVUS;
const mongoTarget = DRILL ? { host: "127.0.0.1", port: 27018 } : MONGO;
// W-NEXT-PROBE-001 修:② 容器名从硬编码改为运行时按端口反查(detectRedisContainer)。
//   fail-drill 模式:端口 6380 → 必然 0 容器命中,验证「未找到映射宿主端口 <port> 的 Redis 容器」失败路径。
const redisHostPort = DRILL ? 6380 : readEnvRedisPort();

// ① Milvus
await check("①", `Milvus 连通 ${milvusTarget.host}:${milvusTarget.port}`, Object.assign(
  () => socketProbe(milvusTarget.host, milvusTarget.port),
  { __fix: FIX.vm }));

// ② Redis
// W-NEXT-PROBE-001 修:容器名从硬编码 `edu-redis-standalone` 改为端口反查。
//   顺序:① 端口取自 .env(REDIS_PORT 或 REDIS_URL);② docker ps --filter publish=<port>
//   拿首个容器名;③ 0 匹配再退到 --filter expose=<port>;④ 仍 0 匹配报"未找到映射宿主端口"。
//   拿到容器名后才发起 docker exec redis-cli ping —— 实测可达才算 PASS。
await check("②", `Redis(按 .env REDIS_PORT=${redisHostPort} 反查容器 docker exec redis-cli ping)`, Object.assign(
  async () => {
    const container = await detectRedisContainer(redisHostPort);
    const out = await runCmd("docker", ["exec", container, "redis-cli", "ping"]);
    if (!/PONG/i.test(out)) throw new Error(`ping 返回异常: ${out.slice(0, 80)}`);
    return `PONG(容器 ${container})`;
  },
  { __fix: FIX.redis }));

// ③ MongoDB
await check("③", `MongoDB 连通 ${mongoTarget.host}:${mongoTarget.port}`, Object.assign(
  () => socketProbe(mongoTarget.host, mongoTarget.port),
  { __fix: FIX.vm }));

// ④ 后端 /health
await check("④", `后端 8000 /health`, Object.assign(
  async () => {
    const j = await httpProbe(`${BACKEND}/health`, { mustJson: {} });
    if (j?.status !== "ok") throw new Error(`status=${j?.status}`);
    return `status=ok v${j.version || "?"}`;
  },
  { __fix: FIX.backend }));

// ⑤ 前端登录页 + 前端形态判别(T5-C2:dev 开发形态从未被验收门覆盖的假绿)
// 判别法:next dev 会暴露 /_next/static/development/_buildManifest.js(200),生产 build 无此路径(404)
await check("⑤", `前端 ${FRONTEND_PORT} /login-register.html(+生产形态判别)`, Object.assign(
  async () => {
    await httpProbe(`${FRONTEND}/login-register.html`);
    let devForm = false;
    try {
      await httpProbe(`${FRONTEND}/_next/static/development/_buildManifest.js`);
      devForm = true;
    } catch {
      devForm = false; // 404 = 生产 build 形态
    }
    if (devForm) {
      const e = new Error("前端为 next dev 开发形态(_buildManifest dev 探针 200),非生产 build,生产形态未验收");
      e.__warn = true;
      throw e;
    }
    return "生产 build 形态(_buildManifest dev 探针 404)";
  },
  { __fix: (d) => `cd edu-frontend && node node_modules/next/dist/bin/next dev -p ${FRONTEND_PORT}(验生产形态:deploy.mjs stop 后 start,先 build 再起)[${d}]` }));

// ⑥ 登录链路(admin + student 各一次 login + /api/auth/me)
await check("⑥", `登录链路 login×2 + /api/auth/me×2`, Object.assign(
  async () => {
    const who = async (acc, expectRole) => {
      const j = await httpProbe(`${BACKEND}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: { account: acc.account, password: acc.password },
        mustJson: { code: 0 },
      });
      const tok = j?.data?.access_token;
      if (!tok) throw new Error(`${acc.account}: 无 access_token`);
      const me = await httpProbe(`${BACKEND}/api/auth/me`, {
        headers: { Authorization: `Bearer ${tok}` },
        mustJson: { code: 0 },
      });
      const role = me?.data?.role;
      if (role !== expectRole) throw new Error(`${acc.account}: role=${role} 期望 ${expectRole}`);
      return `${acc.account}(role=${role},user_id=${me?.data?.user_id})`;
    };
    const a = await who(ADMIN, "admin");
    const s = await who(STUDENT, "student");
    return `${a} + ${s}`;
  },
  { __fix: (d) => `先过 ④ 后端: cd edu-agent && .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000(若账号失效查 DB 种子) [${d}]` }));

// ⑦ 关键页 200(8 个核心 html)
await check("⑦", `关键页 200 × ${PAGES.length}`, Object.assign(
  async () => {
    const bad = [];
    for (const p of PAGES) {
      try { await httpProbe(`${FRONTEND}/${p}`); } catch (e) { bad.push(`${p}(${e.message})`); }
    }
    if (bad.length) throw new Error(`${bad.length}/${PAGES.length} 页异常: ${bad.join(", ")}`);
    return `${PAGES.length}/${PAGES.length} 全 200`;
  },
  { __fix: FIX.frontend }));

// ⑧ advisory:DEBUG 虚拟管理员漏洞(教训 6;W-NEXT-CHECKDEMO-PROD-001:恢复 ENV_NAME 二次判据 + --prod-gate 部署门)
// 两级判据(W-NEXT-CHECKDEMO-PROD-001 修,P0-2):
//   W-NEXT-DEBUG-DOC-001 曾把判据简化为「DEBUG=true 即开发态 WARN」并删除 T5-C1 的 ENV_NAME 二次判据——
//   后果:生产忘设 ENV_NAME 时 DEBUG=true 真后门被当开发态 WARN 不阻断。现恢复,且与后端 P1-8
//   `_debug_env_gate`(app/config.py:763)同口径:ENV_NAME.strip().lower() ∈ {"", "local"} 视为本机开发态,
//   其余(prod/production/staging/dev/qa 等,大小写不敏感)为显式生产类环境。
//   .env 缺 ENV_NAME 键 = config.py 默认 "local"(本机 dev 态,后端实际运行口径一致)→ WARN 不变。
// 四分支语义:
//   A) 无 token 被 401/403 拒绝 → PASS(文案按 DEBUG 动态:DEBUG=true 时不自称「安全」)
//   B) 后门存在 + DEBUG=true + ENV_NAME 显式非 local → FAIL 阻断(生产类环境 DEBUG=true 真后门,不再 WARN)
//   C) 后门存在 + DEBUG=true + ENV_NAME 缺省/local(本机 dev 态) → WARN 不阻断;--prod-gate 时升级 FAIL(P0-1)
//   D) 后门存在 + DEBUG≠true(生产态/DEBUG=false 模式) → FAIL 阻断(真后门,原分支 C 语义不变)
// fail-drill 行为不变(①②③红,④-⑨按假端口语义)。
const debugCheck = Object.assign(
  async () => {
    const env = readDevEnv();
    // P1-8 同口径归一化:strip + lower;缺键/空值 = 本机开发态(config.py 默认 "local")
    const envName = (env.ENV_NAME || "").trim().toLowerCase();
    const envDeclaredNonLocal = envName !== "" && envName !== "local";
    let res;
    try {
      res = await fetch(`${BACKEND}/api/users/me`, { signal: AbortSignal.timeout(HTTP_TIMEOUT_MS) });
    } catch (e) {
      // 后端不可达:本项无法探测,④ 已红,不重复误报 DEBUG 漏洞
      return `跳过:后端不可达(以④红项为准),DEBUG 漏洞未探测`;
    }
    const text = await res.text();
    const vuln = res.status === 200 || /"code":\s*0/.test(text);
    if (!vuln) {
      // 分支 A:被拒即 PASS;DEBUG=true 时只说明「.env 后门开关仍开启」,不得自称 DEBUG 安全
      return env.DEBUG === "true"
        ? `无 token 被 ${res.status} 拒绝(DEBUG=true:.env 后门开关仍开启,生产部署前请 DEBUG=false)`
        : `无 token 被 ${res.status} 拒绝(DEBUG 安全,生产态正确)`;
    }
    if (env.DEBUG === "true") {
      if (envDeclaredNonLocal) {
        // 分支 B:两级判据第 2 级命中——ENV_NAME 显式非 local(P1-8 同口径)= 生产类环境,直接红
        throw new Error(`生产类环境虚拟管理员后门:DEBUG=true 且 ENV_NAME=${env.ENV_NAME.trim()}(显式非 local,P1-8 同口径)——生产/预发绝不允许 DEBUG=true(未登录可读用户数据),立即 .env DEBUG=false 并重启后端;后端 P1-8 门禁下该形态本不应能启动`);
      }
      if (PROD_GATE) {
        // 分支 C 升级:--prod-gate 部署门开启,WARN 升级 FAIL(P0-1:开发态后门不随包出生产)
        throw new Error(`--prod-gate 部署门:虚拟管理员后门存在(DEBUG=true, ENV_NAME=${env.ENV_NAME === null ? "缺省(=config.py 默认 local)" : env.ENV_NAME})——WARN 已升级为 FAIL 阻断出包;生产 .env 必须 DEBUG=false`);
      }
      // 分支 C:本机开发态已知后门 → WARN(软)不阻断,避免永久红=狼来了;
      // 明示设计意图:本地开发态保留有意,生产环境 DEBUG=False 才 PASS;两级判据见上
      const e = new Error(`WARN 开发态虚拟管理员后门存在(DEBUG=true, ENV_NAME=${env.ENV_NAME === null ? "缺省(=config.py 默认 local)" : env.ENV_NAME});两级判据:ENV_NAME 显式非 local 时直接 FAIL,当前判为本机开发态故 WARN 不阻断;生产部署前必须 DEBUG=false(--prod-gate 旗标可将本 WARN 升级为 FAIL),见 P1-8 ENV_NAME 门 / AGENTS.md 教训 6`);
      e.__warn = true;
      throw e;
    }
    // 分支 D:DEBUG 未开却 200(真后门),即生产态或 DEBUG=false 模式下绝不应允许 → 红,阻断 exit 1
    throw new Error(`无 token 返回 HTTP ${res.status} 有数据(DEBUG=${env.DEBUG === null ? "缺省(≠true)" : env.DEBUG});生产态/DEBUG=false 模式下绝不应出现——真后门,部署前必须 DEBUG=false`);
  },
  { __fix: FIX.debug });
await check("⑧", `advisory: DEBUG 虚拟管理员探测(无 token /api/users/me,两级判据+--prod-gate,W-NEXT-CHECKDEMO-PROD-001)`, debugCheck);

// ⑨ 抽验页 /admin-users-refine-proto.html 200(C5-D2 扩清单)
await check("⑨", `抽验页 200 /admin-users-refine-proto.html(C5-D2)`, Object.assign(
  () => httpProbe(`${FRONTEND}/admin-users-refine-proto.html`),
  { __fix: FIX.frontend }));

// ⑩ 契约对账（FE-BE-CONTRACT 四方对账门）：跑 febe_contract_check.py（W-NEXT-FE-001 四档）
//   断点(bp) >0                         -> FAIL 红（前端调用了后端不存在的路由）
//   在用未冻结(in_use_unfrozen) >0        -> FAIL 红（前端实际在用但无冻结契约 = 治理压力核心，CI 阻断）
//   未冻结仅后端(unfrozen_only) >0        -> WARN（后端有、前端未用、无契约，不阻断）
//   待接(to_connect) >0                  -> WARN（后端有、前端未接，不阻断）
//   后端不可达(exit 2)                   -> WARN（以④为准）
const contractGate = Object.assign(
  async () => {
    const py = await resolvePython();
    const { code, stdout, stderr } = await runPy(py, [FEBE_SCRIPT]);
    const summary = /\[SUMMARY\]\s*breakpoints=(\d+)\s+in_use_unfrozen=(\d+)\s+unfrozen_only=(\d+)\s+to_connect=(\d+)/
      .exec(stdout || "");
    if (!summary) {
      throw new Error(`未解析到 [SUMMARY]（exit=${code}）；stderr=${(stderr || "").slice(0, 200)}`);
    }
    const bp = +summary[1], iu = +summary[2], uo = +summary[3], tc = +summary[4];
    if (code === 2) {
      const e = new Error(`后端不可达，契约对账跳过（以④红项为准）：断点=${bp} 在用未冻结=${iu} 未冻结仅后端=${uo} 待接=${tc}`);
      e.__warn = true;
      throw e;
    }
    // 红/阻断：断点>0 或 前端在用却无契约>0
    if (bp > 0) {
      throw new Error(`断点 ${bp} 条（前端调用了后端不存在的路由），见 febe_contract_check.py ① 段`);
    }
    if (iu > 0) {
      throw new Error(`在用未冻结 ${iu} 条（前端实际在用的接口无冻结契约，CI 红/阻断；详见 febe_contract_check.py ② 段，清单移交 W-NEXT-CONTRACT-001）`);
    }
    // WARN，不阻断：后端有前端未接 / 后端有契约无（前端未用）
    if (tc > 0 || uo > 0) {
      const e = new Error(`待接 ${tc} / 未冻结仅后端 ${uo} 条（WARN，不阻断；详见 febe_contract_check.py ③④ 段）`);
      e.__warn = true;
      throw e;
    }
    return `断点0 在用未冻结0 未冻结仅后端0 待接0`;
  },
  { __fix: (d) => `python edu-agent/scripts/eval/febe_contract_check.py 查看四方差异清单（断点·在用未冻结 红 / 待接·未冻结 WARN） [${d}]` });
await check("⑩", `契约对账门 febe_contract_check.py（断点·在用未冻结 红 / 待接·未冻结 WARN）`, contractGate);

// ⑪ VEC-LOCK：embed 一致性健康门（VEC-G5）——edu_knowledge 元数据全 = 锁定 BGE-M3 revision，
//    无 fallback 混写/未归一化/空文本。走 venv python 探针（查 Milvus），PASS 才算绿。
// W-NEXT-CHECKDEMO-004 修:../veclock_health_probe.py 解析到 edu-agent/veclock_health_probe.py
//     (错误,少了一层 scripts/)——探针实际在 edu-agent/scripts/。改用绝对 ../scripts/veclock_health_probe.py。
const VECLOCK_PROBE = fileURLToPath(new URL("../scripts/veclock_health_probe.py", import.meta.url));
const EDU_PY = fileURLToPath(new URL("../.venv/Scripts/python.exe", import.meta.url));
await check("⑪", `VEC-LOCK embed 一致性(edu_knowledge 元数据)`, Object.assign(
  async () => {
    // W-NEXT-CHECKDEMO-004 修:runCmd 没有 windowsHide:true,WINDOWS 探针长 UTF-8
    //     argv 在非 hide 模式下偶发路径截断(Python 报「can't open file 'E:\\stu\\」):
    //     probe 路径 'E:\stu\project\stu\EduAgent实施手册\edu-agent\scripts\...py'
    //     含中文 + 反斜杠,windowsHide:true 后稳定。改用 runPy 拿 stdout/stderr 并做
    //     pydantic 友好报(stderr 含 Field required 即说明 cwd 没 .env)。
    const { code, stdout, stderr } = await runPy(EDU_PY, [VECLOCK_PROBE], 60000);
    if (stderr && /Field\s+required\s+\[type=missing/i.test(stderr)) {
      const m = /(\w+)\s+Field required/i.exec(stderr);
      const field = m ? m[1] : "unknown";
      throw new Error(`pydantic Field required: ${field} —— 子进程未加载 edu-agent/.env（stderr=${stderr.slice(0, 120)}）`);
    }
    const text = (stdout || "").trim();
    // 末行格式:"edu_knowledge N 行 ... => PASS|FAIL"
    if (!text.includes("=> PASS")) {
      throw new Error(`exit=${code}; 探针未输出 PASS: ${text.slice(0, 200)}`);
    }
    return text.split("\n").pop().trim();
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\veclock_health_probe.py 排查 embed 元数据/索引状态 [${d}]` }));

// ⑬ W-NEXT-MCP-001「MCP 三态」健康门（能力对账 + 内置工具落审计 + 字段级脱敏）
//   打 live 8000 + MySQL，真实调 calculator（内置）验证审计落库(server_id=0)与字段脱敏；
//   探针末行输出 [TRISTATE] <json>，env_blocked→WARN（不阻断，仅环境未就绪），其余失败→红。
const TRISTATE_PROBE = fileURLToPath(new URL("../scripts/eval/mcp_tristate_probe.py", import.meta.url));
await check("⑬", `MCP 三态门（能力对账+内置落审计+脱敏）`, Object.assign(
  async () => {
    const { code, stdout } = await runPy(EDU_PY, [TRISTATE_PROBE], 60000);
    const m = /\[TRISTATE\]\s*(\{.*\})/.exec(stdout || "");
    if (!m) {
      if (code === 2) {
        const e = new Error(`环境阻塞（后端/DB 不可达，以④红项为准）: ${(stdout || "").slice(0, 200)}`);
        e.__warn = true; throw e;
      }
      throw new Error(`探针未输出 [TRISTATE]（exit=${code}）: ${(stdout || "").slice(0, 200)}`);
    }
    const j = JSON.parse(m[1]);
    if (j.env_blocked) {
      const e = new Error(`环境阻塞（后端/DB 不可达，跳过）: ${j.detail || ""}`);
      e.__warn = true; throw e;
    }
    if (!j.audit_ok) throw new Error(`能力对账未通过: ${j.detail || ""}`);
    if (!j.builtin_logged) throw new Error(`内置工具未落审计: ${j.detail || ""}`);
    if (!j.redacted) throw new Error(`字段脱敏未生效: ${j.detail || ""}`);
    return `审计checked=${j.audit_checked} 内置落库✔ 脱敏✔`;
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\eval\\mcp_tristate_probe.py 排查（需 8000 在线 + MySQL 可达） [${d}]` }));

// ⑫ HITL 真实性健康门（SURFACED-1 闭环实证，P0）：/health 200 + chat 流式 knowledge_import
//    HITL confirm → 续流执行，**不再出现** 42200「必须提供 tool_id」症状（回归红线 =
//    HITL-FIX 后 admin confirm 写类工具零落库的根因）。走 venv python 探针（真实 HTTP + 只读
//    SQL 取证），PASS 才算绿；模型本轮未触发 knowledge_import 时观测返回（单测已覆盖 tool_name 修复），不阻断 exit。
// W-NEXT-CHECKDEMO-004 修:同 ⑪,../hitl_realness_probe.py 错指 edu-agent/ 根,改用 ../scripts/hitl_realness_probe.py
const HITL_PROBE = fileURLToPath(new URL("../scripts/hitl_realness_probe.py", import.meta.url));
await check("⑫", `HITL 真实性(confirm 续流不再 42200)`, Object.assign(
  async () => {
    // W-NEXT-CHECKDEMO-004 修:同 ⑪,改用 runPy (windowsHide:true) 防长 UTF-8 argv
    //     截断;同时加 pydantic Field required 友好报。
    const { code, stdout, stderr } = await runPy(EDU_PY, [HITL_PROBE], 90000);
    if (stderr && /Field\s+required\s+\[type=missing/i.test(stderr)) {
      const m = /(\w+)\s+Field required/i.exec(stderr);
      const field = m ? m[1] : "unknown";
      throw new Error(`pydantic Field required: ${field} —— 子进程未加载 edu-agent/.env（stderr=${stderr.slice(0, 120)}）`);
    }
    const text = (stdout || "").trim();
    let j;
    try { j = JSON.parse(text); } catch { throw new Error(`探针输出非 JSON: ${text.slice(0, 200)}`); }
    if (j.error) throw new Error(j.error);
    if (j.regression) throw new Error(j.regression);
    if (!j.health_ok) throw new Error("后端 /health 非 ok");
    if (j.pending_confirm_seen && j.confirm_resumed && !j.symptom_in_confirm_pass)
      return `pending_confirm→confirm 真可达,42200 症状消失(task ${j.task_before}→${j.task_after})`;
    if (!j.pending_confirm_seen) return `模型未触发 knowledge_import,跳过(单测已覆盖): ${j.note || ""}`;
    return `confirm 续流无 42200 症状`;
  },
  { __fix: (d) => `确认 HITL_ENABLED=True 且后端可达;SURFACED-1 修复见 tests/test_chat_tool_calling.py [${d}]` }));

// ⑭ W-NEXT-INT-001A 内部可见性健康门：student 检索内部关键词 0 命中 + admin 命中 > 0（T14 S6 修复）
//    走 wnextint1a_visibility_probe.py 探针（真实 HTTP login + /api/chat/search + format_docs=False），
//    末行输出 [WINT1A] {student_hits:0, admin_hits:>0, ...}；env_blocked→WARN（不阻断，仅环境未就绪）。
const WINT1A_PROBE = fileURLToPath(new URL("../scripts/eval/wnextint1a_visibility_probe.py", import.meta.url));
await check("⑭", `内部可见性(student 0 内部命中 / admin >0)`, Object.assign(
  async () => {
    const { code, stdout } = await runPy(EDU_PY, [WINT1A_PROBE, "--base", BACKEND], 90000);
    const m = /\[WINT1A\]\s*(\{.*\})/.exec(stdout || "");
    if (!m) {
      if (code === 2) {
        const e = new Error(`环境阻塞（后端不可达，以④红项为准）: ${(stdout || "").slice(0, 200)}`);
        e.__warn = true; throw e;
      }
      throw new Error(`探针未输出 [WINT1A]（exit=${code}）: ${(stdout || "").slice(0, 200)}`);
    }
    const j = JSON.parse(m[1]);
    if (j.env_blocked) {
      const e = new Error(`环境阻塞（后端/DB 不可达，跳过）: ${j.detail || ""}`);
      e.__warn = true; throw e;
    }
    if (!j.student_hits_zero) throw new Error(`student 内部关键词命中 ${j.student_hits_total} 条（S6 回归保护 FAIL）`);
    if (!(j.admin_hits_total > 0)) throw new Error(`admin 内部关键词 0 命中（admin 不被 internal 过滤失效）`);
    return `student=${j.student_hits_total} admin=${j.admin_hits_total}（5 query 全过）`;
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\eval\\wnextint1a_visibility_probe.py --base ${BACKEND} 排查 [${d}]` }));

// ⑮ W-NEXT-REDIS-FIX「Redis 部署对账」门——.env REDIS_PORT vs docker 宿主端口一致性。
//    探针：edu-agent/scripts/eval/redis_port_check.py（纯 docker + .env 探测，不依赖后端）。
//    四态：PASS（红/绿）/ WARN（红/绿，不阻断仅提示）/ FAIL_ENV_MISSING（红/绿）/ ENV_BLOCKED（红/绿）。
//    退出码语义：0=PASS/WARN(配置漂移)，1=FAIL_ENV_MISSING，2=ENV_BLOCKED。
//    ⑮ 阻断规则：PASS → PASS；WARN → 红阻断（部署脱节 = 盲区再现）；FAIL_ENV_MISSING → 红阻断；ENV_BLOCKED → WARN 不阻断。
const REDIS_PORT_CHECK = fileURLToPath(new URL("../scripts/eval/redis_port_check.py", import.meta.url));
await check("⑮", `Redis 部署对账(.env REDIS_PORT vs docker 宿主端口)`, Object.assign(
  async () => {
    const py = await resolvePython();
    const { code, stdout, stderr } = await runPy(py, [REDIS_PORT_CHECK], 30000);
    const m = /\[PORT_CHECK\]\s*(\{.*\})/.exec(stdout || "");
    if (!m) {
      throw new Error(`探针未输出 [PORT_CHECK]（exit=${code}）: ${(stdout || "").slice(0, 200)}${stderr ? " | stderr=" + stderr.slice(0, 120) : ""}`);
    }
    const j = JSON.parse(m[1]);
    if (j.env_blocked === undefined && j.status === "ENV_BLOCKED") {
      // 兼容字段命名（脚本里 status="ENV_BLOCKED"，无独立 env_blocked 字段）
      j.env_blocked = true;
    }
    if (j.status === "ENV_BLOCKED") {
      const e = new Error(`docker 不可用（以②红项为准）: ${j.docker_error || "无容器"}`);
      e.__warn = true; throw e;
    }
    if (j.status === "FAIL_ENV_MISSING") {
      throw new Error(`.env 缺 REDIS_PORT/REDIS_URL: ${j.env_error || ""}——按 deploy/README.md §1.1 补齐`);
    }
    if (j.status === "WARN") {
      throw new Error(`.env REDIS_PORT=${j.env_port} ≠ docker 宿主端口=${j.docker_port}（容器 ${j.container || "?"}）——部署脱节，需改 .env`);
    }
    return `.env=${j.env_port} docker=${j.docker_port}（容器 ${j.container}, 容器内 ${j.container_internal_port}）`;
  },
  { __fix: (d) => `cd edu-agent && python scripts\\eval\\redis_port_check.py 排查；详见 deploy/README.md §1.1 [${d}]` }));

// ⑯ W-NEXT-LIFECYCLE-001「8000 lifecycle 健壮性」门 —— 修复了 uvicorn shutdown 阶段
//    asyncio.CancelledError 在 queue._fetch_one/stop_consumer 的竞态透传（uvicorn 0.52 已知
//    行为：报 "Application shutdown failed" + 完整 traceback，进程 exit 3）。
//    探针：edu-agent/scripts/_lifecycle_real_verify.py（Python subprocess + CTRL_BREAK_EVENT
//    /SIGTERM 模拟 SIGTERM），跑 5 轮：每轮 start < 30s + /health 200 + 优雅 stop < 10s + 
//    日志 0 Traceback / 0 CancelledError / 0 "Application shutdown failed"。
//    退出码：0=PASS，1=FAIL。env_blocked（后端/DB 不可达）→ WARN 不阻断。
const LIFECYCLE_PROBE = fileURLToPath(new URL("../scripts/_lifecycle_real_verify.py", import.meta.url));
await check("⑯", `8000 lifecycle 健壮性(start+stop×5,无 CancelledError traceback)`, Object.assign(
  async () => {
    const { code, stdout, stderr } = await runPy(EDU_PY, [LIFECYCLE_PROBE, "5"], 300000);
    const m = /\[LIFECYCLE\]\s*(\{.*\})/.exec(stdout || "");
    if (!m) {
      throw new Error(`探针未输出 [LIFECYCLE]（exit=${code}）: ${(stdout || "").slice(0, 200)}${stderr ? " | stderr=" + stderr.slice(0, 120) : ""}`);
    }
    const j = JSON.parse(m[1]);
    if (j.env_blocked) {
      const e = new Error(`环境阻塞（后端/依赖不可达）: ${j.detail || ""}`);
      e.__warn = true; throw e;
    }
    if (!j.pass) {
      throw new Error(`lifecycle 失败: ${j.detail || "5 轮中存在 start>30s / stop>10s / traceback>0 / CancelledError>0 / 'shutdown failed'>0"}`);
    }
    return `5 轮 start ${j.avg_start_ms}ms / stop ${j.avg_stop_ms}ms / 0 traceback / 0 CancelledError`;
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\_lifecycle_real_verify.py 5 复跑；如失败查 logs/lifecycle_real_*.log [${d}]` }));

// ⑰ W-NEXT-MCP-003「MCP 跨权限门对账」健康门——audit_mcp_capability checked=17 +
//    5 个新对账行 + chat 路径真接 permission_gate 4 个 API + JSON serializable + AST 真接模式 ≥4。
//    纯离线探针，不依赖 8000/DB——只走 audit 函数与 AST 解析源码；FAIL 时阻断 exit。
//    退出码：0=PASS（全绿）；1=FAIL（代码缺陷：行缺失/未真接/返回值形态异常）。
//    W-NEXT-CHECKDEMO-002 改:BGE-M3 mmap 在 Windows 内存压力下偶发 1455,
//    cross_perm 探针若首跑 5 个 AST 解析 + JSON 序列化 + 17 行 audit 对账超过
//    30s 会被误杀。统一抬到 60s 与 ⑬⑱ 看齐（防 BGE-慢 类同型误杀）。
const CROSSPERM_PROBE = fileURLToPath(new URL("../scripts/eval/mcp_cross_perm_gate_probe.py", import.meta.url));
await check("⑰", `MCP 跨权限门对账(audit checked=17 + 5 新对账行 + chat AST 链 + JSON serializable)`, Object.assign(
  async () => {
    const { code, stdout } = await runPy(EDU_PY, [CROSSPERM_PROBE], 60000);
    const m = /\[CROSSPERM\]\s*(\{.*\})/.exec(stdout || "");
    if (!m) {
      throw new Error(`探针未输出 [CROSSPERM]（exit=${code}）: ${(stdout || "").slice(0, 200)}`);
    }
    const j = JSON.parse(m[1]);
    if (!j.audit_ok) throw new Error(`审计未通过: ${j.detail || ""}`);
    if (j.audit_checked < 17) throw new Error(`审计 checked 不足 17，实测 ${j.audit_checked}`);
    if (!j.five_rows_present) throw new Error(`5 个新对账行缺失: ${j.detail || ""}`);
    if (!j.chat_path_connected) throw new Error(`chat 路径 AST 链不全: ${j.detail || ""}`);
    if (!j.json_serializable) throw new Error(`audit 返回非 JSON serializable: ${j.detail || ""}`);
    if ((j.ast_modes_count || 0) < 4) throw new Error(`AST 真接模式不足 ${j.ast_modes_count}/5（≥4）`);
    return `checked=${j.audit_checked} 5行✔ chat链✔ JSON✔ AST真接${j.ast_modes_count}/5`;
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\eval\\mcp_cross_perm_gate_probe.py 排查 [${d}]` }));

// ⑱ W-NEXT-CHECKDEMO-001 / W-NEXT-FE-003「febe root path 闭环」门——验收
//    parser 根路径扩展（KNOWN_ROOT_PATHS 白名单）后 unfrozen_only 必须 == 0。
//    探针：纯离线，跑 febe_contract_check.py --quiet，解析 [SUMMARY] 行
//    unfrozen_only=N 数字。unfrozen_only==0 → PASS；>0 → 红（仍有 root path
//    落不进冻结集合，回退为治理 backlog）。env_blocked（后端 8000 不可达）
//    → WARN 不阻断（与 ⑩ 同语义）。
const FEBE_HEALTH = fileURLToPath(new URL("../scripts/eval/febe_health_gate_probe.py", import.meta.url));
await check("⑱", `febe root path 闭环(febe_contract_check --quiet unfrozen_only=0)`, Object.assign(
  async () => {
    // 末位兜底：FEBE_HEALTH 探针若不存在，降级到直接跑 febe_contract_check.py
    //   parse [SUMMARY]；二者契约同构。W-NEXT-FE-003 仅交付 parser 改造，未
    //   强制要求独立探针，本任务加 ⑱ 门时一并探针化以便未来扩展 dim 门。
    let probe = FEBE_HEALTH;
    const py = await resolvePython();
    const { code, stdout, stderr } = await runPy(py, [probe], 60000);
    const m = /\[FEBE_HEALTH\]\s*(\{.*\})/.exec(stdout || "");
    let j = null;
    if (m) {
      j = JSON.parse(m[1]);
    } else {
      // 探针不存在/未输出 → 降级为解析 [SUMMARY]
      const summary = /\[SUMMARY\]\s*breakpoints=(\d+)\s+in_use_unfrozen=(\d+)\s+unfrozen_only=(\d+)\s+to_connect=(\d+)/
        .exec(stdout || "");
      if (!summary) {
        if (code === 2) {
          const e = new Error(`环境阻塞（后端不可达，以④红项为准）: ${(stdout || "").slice(0, 200)}`);
          e.__warn = true; throw e;
        }
        throw new Error(`探针未输出 [FEBE_HEALTH]/[SUMMARY]（exit=${code}）: ${(stdout || "").slice(0, 200)}${stderr ? " | stderr=" + stderr.slice(0, 120) : ""}`);
      }
      j = {
        unfrozen_only: +summary[3],
        breakpoints: +summary[1],
        in_use_unfrozen: +summary[2],
        to_connect: +summary[4],
        detail: "",
      };
    }
    if (j.env_blocked) {
      const e = new Error(`环境阻塞（后端/DB 不可达）: ${j.detail || ""}`);
      e.__warn = true; throw e;
    }
    if ((j.unfrozen_only || 0) > 0) {
      throw new Error(`unfrozen_only=${j.unfrozen_only} > 0：仍有后端路由未被冻结契约吸收（parser root path 兜底不足或新加白名单）`);
    }
    return `unfrozen_only=0 断点=${j.breakpoints || 0} 在用未冻结=${j.in_use_unfrozen || 0}`;
  },
  { __fix: (d) => `cd edu-agent && python scripts/eval/febe_contract_check.py 看 ③ 段未冻结仅后端清单；如含 root/运维端点，扩 KNOWN_ROOT_PATHS [${d}]` }));

// ⑲ W-NEXT-VEC-003「VEC-LOCK 守门」门 —— VEC-LOCK 核心代码改动必经 veclock_verify.py 12 维机验
//    + dim0 backend 探测（锁定 revision）。该门是 pre-commit hook 的同源 CI 收口：
//      hook 在 commit 时阻断; ⑲ 在演示前再跑一次守门（覆盖「已 commit 但环境漂移」「多人共改」盲区）。
//    探针：edu-agent/scripts/eval/veclock_verify.py（v2 确定性版，12 维）。
//    阻断规则：passed == 12/12 + dim0 backend == "bge_m3" → PASS；
//             否则红阻断。任何 EXIT ≠0 或 12/12 失败 → 红（12 维是 VEC-LOCK 不可协商基线）。
const VECLOCK_VERIFY = fileURLToPath(new URL("../scripts/eval/veclock_verify.py", import.meta.url));
await check("⑲", `VEC-LOCK 守门(veclock_verify.py 12 维 + dim0 backend=bge_m3)`, Object.assign(
  async () => {
    // 1) 跑 12 维机验,捕获 stdout 解析「汇总:N/12 PASS」
    const { code, stdout, stderr } = await runPy(EDU_PY, [VECLOCK_VERIFY], 600000);
    // W-NEXT-CHECKDEMO-003 修:cwd=仓库根时 pydantic-settings 找不到 .env 会抛
    //    ValidationError(Field required),exit=1,stderr 含 "Field required"。
    //    单独跑能 PASS 是因为 cwd=edu-agent/.env 在 cwd。
    //    友好报:stderr 看到 pydantic Field required → 报「配置缺失」而非含糊的「未解析汇总行」。
    if (stderr && /Field\s+required\s+\[type=missing/i.test(stderr)) {
      const m = /(\w+)\s+Field required/i.exec(stderr);
      const field = m ? m[1] : "unknown";
      throw new Error(`pydantic Field required: ${field} —— 子进程未加载 edu-agent/.env。请确认 cwd 或检查 .env 中 ${field}=...（stderr=${stderr.slice(0, 200)}）`);
    }
    // 探针末行格式:[veclock] 汇总：12/12 PASS  / [veclock] 汇总：N/12 PASS（提早退出，backend 探测失败）
    const summary = /\[veclock\]\s*汇总[：:]\s*(\d+)\s*\/\s*(\d+)\s*PASS/.exec(stdout || "");
    if (!summary) {
      throw new Error(`未解析到 [veclock] 汇总行（exit=${code}）: ${(stdout || "").slice(0, 200)}${stderr ? " | stderr=" + stderr.slice(0, 120) : ""}`);
    }
    const passed = +summary[1], total = +summary[2];
    // 2) dim0 backend 探测:必须 PASS + backend=bge_m3 + model 锁定 revision
    const dim0Line = /\[veclock\]\s*PASS\s+0\s+backend\s*探测[^\n]*backend=(\S+)\(须=(\S+)\)\s+model=(\S+)\(须=(\S+)\)/.exec(stdout || "");
    const dim0FailLine = /\[veclock\]\s*FAIL\s+0\s+backend\s*探测[^\n]*backend=(\S+)/.exec(stdout || "");
    if (dim0FailLine) {
      throw new Error(`dim0 backend 探测 FAIL: ${(dim0FailLine[1] || "").slice(0, 60)}（须=bge_m3）—— BGE-M3 mmap 失败或 backend 假阳，提早退出`);
    }
    if (!dim0Line) {
      throw new Error(`未解析到 dim0 backend 探测行: ${(stdout || "").slice(0, 200)}`);
    }
    const backend = dim0Line[1].replace(/[),]/g, "");
    const wantBackend = dim0Line[2].replace(/[),]/g, "");
    if (backend !== wantBackend) {
      throw new Error(`dim0 backend=${backend} ≠ 锁定 ${wantBackend}（BGE-M3 锁定已破）`);
    }
    if (passed !== total) {
      throw new Error(`12 维机验失败: passed=${passed} ≠ total=${total}（必有 dim FAIL，请看上方 PASS/FAIL 行）`);
    }
    return `${passed}/${total} PASS + dim0 backend=${backend}（锁定）`;
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\eval\\veclock_verify.py 看 PASS/FAIL 行定位 dim；dim0 backend 失败时清内存释放 BGE-M3 mmap [${d}]` }));

// ⑳ W-NEXT-OTLP-001「OTLP exporter 链路健康」门——OTLP collector 探针：
//    endpoint 解析 + SSRF 白名单守门 + 一次性 TCP 探活。探针读 settings.OTEL_EXPORTER_OTLP_ENDPOINT：
//      空 → state=disabled，PASS（默认 disabled 安全缺省）；
//      非空 → state=healthy/probe_failed/ssrf_rejected/probe_skipped，按 PASS/WARN/FAIL 分级。
//    不依赖 8000/DB，只走 venv python + app.observability.otlp.OtlpExporter + ssrf_guard.validate_url。
//    阻断规则：state=disabled → PASS（默认安全缺省）；
//             state=healthy → PASS（链路绿，OTel collector 实达）；
//             state=probe_skipped → PASS（跳过启动探活 = 运维显式 false）；
//             state=probe_failed → WARN（探活失败不阻断；配置后首启 collector 未就绪常见）；
//             state=ssrf_rejected → FAIL 红（host 不在白名单 = 误配置 / 安全违规）。
//    退出码 0=PASS/WARN；1=FAIL（ssrf_rejected）。env_blocked（缺 .env / OtlpExporter 抛兜底异常）→ WARN。
const OTLP_PROBE = fileURLToPath(new URL("../scripts/eval/otlp_health_probe.py", import.meta.url));
await check("⑳", `OTLP 链路健康(endpoint 解析 + 探活 + SSRF 守门)`, Object.assign(
  async () => {
    const { code, stdout, stderr } = await runPy(EDU_PY, [OTLP_PROBE], 30000);
    if (stderr && /Field\s+required\s+\[type=missing/i.test(stderr)) {
      const m = /(\w+)\s+Field required/i.exec(stderr);
      const field = m ? m[1] : "unknown";
      throw new Error(`pydantic Field required: ${field} —— 子进程未加载 edu-agent/.env。请确认 cwd 或检查 .env 中 ${field}=...（stderr=${stderr.slice(0, 200)}）`);
    }
    const m = /\[OTLP\]\s*(\{.*\})/.exec(stdout || "");
    if (!m) {
      throw new Error(`探针未输出 [OTLP] JSON（exit=${code}）: ${(stdout || "").slice(0, 200)}${stderr ? " | stderr=" + stderr.slice(0, 120) : ""}`);
    }
    let j;
    try { j = JSON.parse(m[1]); } catch { throw new Error(`[OTLP] JSON 解析失败: ${m[1].slice(0, 200)}`); }
    if (j.env_blocked) {
      const e = new Error(`环境阻塞（OtlpExporter 不可用 / .env 缺字段）: ${j.env_blocked_reason || ""}`);
      e.__warn = true; throw e;
    }
    // ssrf_rejected 阻断（红）：host 不在白名单 = 误配置 / 安全违规
    if (j.state === "ssrf_rejected") {
      throw new Error(`endpoint host 不在 SSRF 白名单（ssrf_ok=false）：${j.endpoint} — ${(j.last_error || j.ssrf_reason || "").slice(0, 160)}`);
    }
    // probe_failed 仅 WARN（探活失败不阻断；配置后首启 collector 未就绪常见）
    if (j.state === "probe_failed") {
      const e = new Error(`OTLP 端点 TCP 探活失败（${j.endpoint}，${j.last_error || ""}）—— WARN 不阻断，配置已就位但 collector 未启`);
      e.__warn = true; throw e;
    }
    // healthy / disabled / probe_skipped → PASS
    return `state=${j.state} endpoint=${j.endpoint || "(empty/disabled)"} probe=${j.probe_ms}ms`;
  },
  { __fix: (d) => `cd edu-agent && .venv\\Scripts\\python.exe scripts\\eval\\otlp_health_probe.py 看 [OTLP] state；ssrf_rejected 改 .env OTEL_EXPORTER_OTLP_ENDPOINT 至白名单 host [${d}]` }));

// ㉒ W-NEXT-MINIO-002 「object_key 复用历史审计」健康门——只读探针
//    wnextminio2_audit_history.py：扫 knowledge_import_task.source_files，
//    统计「跨多 task 复用 object_key」「同名覆盖（size drift）」两项历史指标。
//    退出码：0=PASS（无复用，无 size drift）；1=WARN（有复用或 size drift，
//    但不阻断 exit 0 ——历史无法回填，仅记录）；2=FAIL（DB/IO 不可达）。
//    与 ㉑ 配套：㉑ 管「未来不覆盖」（新上传派生 {hash8}_{rand6}_{safe_name}）；
//    ㉒ 管「历史已发生覆盖事件」留痕（只读，不修复）。
const WNEXTMINIO2_AUDIT = fileURLToPath(new URL("../scripts/eval/wnextminio2_audit_history.py", import.meta.url));
// W-NEXT-MINIO-002: 探针必须在 cwd=edu-agent 下跑（app.config.settings 才能
//    加载 .env；从仓库根跑会 Field required 抛错）。EDU_PY 已固定为 venv python。
const EDU_CWD = fileURLToPath(new URL("..", import.meta.url));
await check("㉒", `object_key 复用历史审计(多少 key 跨多 task、最大复用次数)`, Object.assign(
  async () => {
    // 用 cwd=edu-agent 启 venv python，确保 .env 可被 pydantic-settings 加载。
    const child = spawn(EDU_PY, [WNEXTMINIO2_AUDIT], { windowsHide: true, cwd: EDU_CWD });
    const timer = setTimeout(() => {
      try { child.kill(); } catch {}
    }, 60000);
    let stdout = "", stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    const code = await new Promise((resolve) => child.on("close", resolve));
    clearTimeout(timer);
    if (stderr && /Field\s+required\s+\[type=missing/i.test(stderr)) {
      const m = /(\w+)\s+Field required/i.exec(stderr);
      const field = m ? m[1] : "unknown";
      throw new Error(`pydantic Field required: ${field} —— 子进程未加载 edu-agent/.env（cwd=${EDU_CWD}）。请确认 .env 中 ${field}=...（stderr=${stderr.slice(0, 200)}）`);
    }
    // W-NEXT-MINIO-002 探针默认输出单行 [WM2] JSON；stdout 可能含 INFO 日志，
    // 用正则末位兜底取最后一条 [WM2] 行（容错）。
    const matches = stdout ? stdout.match(/\[WM2\]\s*(\{[\s\S]*?\})\s*$/m) : null;
    if (!matches) {
      // 探针 DB 不可达（exit=2）→ 视为环境阻塞，WARN 不阻断（与 ㉑ 同语义）
      if (code === 2) {
        const e = new Error(`环境阻塞（DB 不可达，以 ④ 红项为准）: ${(stdout || "").slice(0, 200)}${stderr ? " | stderr=" + stderr.slice(0, 120) : ""}`);
        e.__warn = true; throw e;
      }
      throw new Error(`探针未输出 [WM2]（exit=${code}）: ${(stdout || "").slice(0, 200)}${stderr ? " | stderr=" + stderr.slice(0, 120) : ""}`);
    }
    let j;
    try {
      j = JSON.parse(matches[1]);
    } catch (err) {
      throw new Error(`[WM2] JSON 解析失败: ${err.message} raw=${matches[1].slice(0, 120)}`);
    }
    if (j.status === "FAIL") {
      throw new Error(`audit 探针 FAIL: ${j.reason || ""}`);
    }
    // WARN 语义：复用 key 跨多 task 或 size drift。历史已发生，无法回填 —— 软告警。
    // 但仍需保证返回关键字段存在；强校验数字格式与类型。
    const dup = Number(j.cross_task_reused_key_count);
    const max = Number(j.max_reuse_count);
    const rows = Number(j.affected_task_rows);
    const drift = Number(j.has_size_drift_count);
    if (!Number.isFinite(dup) || dup < 0) throw new Error(`cross_task_reused_key_count 非法: ${j.cross_task_reused_key_count}`);
    if (!Number.isFinite(max) || max < 0) throw new Error(`max_reuse_count 非法: ${j.max_reuse_count}`);
    if (!Number.isFinite(rows) || rows < 0) throw new Error(`affected_task_rows 非法: ${j.affected_task_rows}`);
    if (!Number.isFinite(drift) || drift < 0) throw new Error(`has_size_drift_count 非法: ${j.has_size_drift_count}`);
    // 数组字段类型
    if (!Array.isArray(j.duplicate_object_keys)) throw new Error(`duplicate_object_keys 非数组`);
    if (j.status === "PASS") {
      return `PASS 复用=0 / max=0 / 涉及行=0 / size_drift=0`;
    }
    // WARN：标 __warn 让汇总显示 WARN，但 exit code 不受影响（绿）
    const e = new Error(`WARN: 跨多 task 复用 ${dup} key（最大 ${max} 次 / 涉及 ${rows} 行 / size_drift=${drift}）——历史已发生覆盖，无法回填`);
    e.__warn = true; throw e;
  },
  { __fix: (d) => `cd edu-agent && PYTHONPATH=. .venv\\Scripts\\python.exe scripts\\eval\\wnextminio2_audit_history.py 排查；如 WARN:历史覆盖无法修复，需新上传路径走 ㉑ 守卫(${d})` }));

// ---------- 汇总 ----------
// warn 条目(软)不阻断:绿 = ok 或 warn;仅真正 FAIL(非 ok 且非 warn)计入红项、触发 exit 1
const pass = results.filter((r) => r.ok).length;
const warn = results.filter((r) => !r.ok && r.warn).map((r) => r.no);
const red = results.filter((r) => !r.ok && !r.warn).map((r) => r.no);
const totalMs = results.reduce((a, r) => a + r.ms, 0);
console.log("");
if (red.length === 0) {
  const warnNote = warn.length ? `,WARN ${warn.join("、")}` : "";
  console.log(`${C.g}汇总: 绿 ${pass + warn.length}/${results.length}${warnNote} —— 演示环境就绪${C.x} ${C.dim}(检查耗时 ${totalMs}ms)${C.x}`);
} else {
  const warnNote = warn.length ? `,WARN ${warn.join("、")}` : "";
  console.log(`${C.r}汇总: 绿 ${pass}/${results.length},红项 ${red.join("、")}${warnNote} —— 请按上方指引处置后重跑${C.x} ${C.dim}(检查耗时 ${totalMs}ms)${C.x}`);
}
process.exit(red.length === 0 ? 0 : 1);
