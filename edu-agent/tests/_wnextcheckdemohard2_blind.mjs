// _wnextcheckdemohard2_blind.mjs — W-NEXT-CHECKDEMO-HARD-002 盲测 harness（接手新增）
// 位置说明:锚点注释原写 scripts/_wnextcheckdemohard2_blind.mjs;为守文件归属红线
// (本批只准动 check-demo.mjs / hitl_realness_probe.py / tests/ / 报告),移至 tests/ 下,函数名不变。
//
// 三组盲测,全部从 check-demo.mjs **原文截取真代码**执行(非复刻实现):
//   组 A ⑧ debugCheck 双探点 10 态(DEBUG-DOC-001 P0-3a)——stub globalThis.fetch + readDevEnv,
//        按「分支 0/A/B/C(+prod-gate 升级)/D/跳过/二探点异常」逐态断言 kind+关键文案。
//   组 B ⑯ .env 变更感知附注 2 态(DEBUG-DOC-001 P0-3b)——真 statSync 路径:.env 在→打印附注;
//        .env 缺→静默跳过。截取 try{...}catch 原文,靠 harness 落点控制 import.meta.url 解析。
//   组 C ② detectRedisContainer 3 态(PROBE-001 P0-1/P0-4)——stub runCmd 不碰真 docker:
//        filter 双 0→全表救回 / 全 0→干净报错 / 并存 5 连跑确定性+running 优先。
// 用法: node tests/_wnextcheckdemohard2_blind.mjs   → 全绿输出 BLIND-ALL-OK 并 exit 0
// 零新依赖:node >= 18(fetch/Response/fs 内置)。
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const EDU_ROOT = path.resolve(HERE, ".."); // edu-agent/
const CHECK_DEMO = path.join(EDU_ROOT, "scripts", "check-demo.mjs");
const SRC = readFileSync(CHECK_DEMO, "utf8");
const results = [];

function cut(startMark, endMark) {
  const i = SRC.indexOf(startMark);
  if (i === -1) throw new Error(`截取起点未找到: ${startMark}`);
  const j = SRC.indexOf(endMark, i);
  if (j === -1) throw new Error(`截取终点未找到: ${endMark}`);
  return SRC.slice(i, j);
}

function record(group, name, ok, detail) {
  results.push({ group, name, ok, detail: String(detail).slice(0, 220) });
  console.log(`${ok ? "PASS" : "FAIL"} [${group}] ${name}${ok ? "" : "  -> " + detail}`);
}

// ---------- 组 A:⑧ debugCheck 双探点 10 态 ----------
const DEBUG_CHECK_SRC = cut("const debugCheck = Object.assign(", 'await check("⑧"');

function makeDebugHarness() {
  return `// 自动生成:_wnextcheckdemohard2_blind.mjs ⑧ debugCheck 盲测态(勿手改)
const HTTP_TIMEOUT_MS = 5000;
const PROD_GATE = process.env.BLIND_PROD_GATE === "1";
const BACKEND = "http://blind-mock";
const FIX = { debug: (d) => "FIX.debug(" + d + ")" };
function readDevEnv() {
  try { return JSON.parse(process.env.BLIND_DEV_ENV); } catch { return { DEBUG: null, ENV_NAME: null }; }
}
globalThis.fetch = async (url) => {
  const plan = JSON.parse(process.env.BLIND_FETCH_PLAN || "[]");
  const key = String(url);
  for (const p of plan) {
    if (key.indexOf(p.path) !== -1) {
      if (p.err) throw new TypeError(p.err);
      return new Response(p.body || "", { status: p.status || 401 });
    }
  }
  throw new TypeError("unexpected fetch " + key);
};
${DEBUG_CHECK_SRC}
const want = JSON.parse(process.env.BLIND_WANT);
const out = { state: want.name };
try {
  const detail = await debugCheck();
  out.kind = "pass";
  out.text = String(detail || "");
} catch (e) {
  out.kind = e && e.__warn === true ? "warn" : "fail";
  out.text = String((e && e.message) || e);
}
process.stdout.write("__BLIND8__" + JSON.stringify(out));
`;
}

async function runDebugState(st) {
  const harness = makeDebugHarness();
  const f = path.join(mkdtempSync(path.join(tmpdir(), "h2blind8-")), "state.mjs");
  writeFileSync(f, harness, "utf8");
  try {
    const out = await new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [f], {
        env: {
          ...process.env,
          BLIND_DEV_ENV: JSON.stringify(st.devEnv),
          BLIND_FETCH_PLAN: JSON.stringify(st.plan),
          BLIND_PROD_GATE: st.prodGate ? "1" : "0",
          BLIND_WANT: JSON.stringify({ name: st.name }),
        },
      });
      let stdout = "", stderr = "";
      child.stdout.on("data", (d) => (stdout += d));
      child.stderr.on("data", (d) => (stderr += d));
      child.on("error", reject);
      child.on("close", (code) => {
        const m = /__BLIND8__(\{.*\})/.exec(stdout || "");
        if (!m) return reject(new Error(`态 ${st.name} 未输出契约 JSON(exit=${code}): ${(stdout + stderr).slice(0, 300)}`));
        resolve(JSON.parse(m[1]));
      });
    });
    const kindOk = out.kind === st.expect;
    const textOk = st.contains.every((s) => out.text.includes(s));
    record("A:⑧双探点", st.name, kindOk && textOk,
      kindOk ? `文案缺项: 期望含[${st.contains.join("|")}] 实得「${out.text.slice(0, 160)}」` : `kind=${out.kind} 期望 ${st.expect}:「${out.text.slice(0, 160)}」`);
  } finally {
    rmSync(path.dirname(f), { recursive: true, force: true });
  }
}

const DENY401 = { status: 401, body: '{"code":40100,"message":"unauthorized"}' };
const OPEN200 = { status: 200, body: '{"code":0,"data":[]}' };
const DEBUG_STATES = [
  { name: "S01_管理端护栏失效_任意环境直红", devEnv: { DEBUG: "true", ENV_NAME: null },
    plan: [{ path: "/api/users/me", ...OPEN200 }, { path: "/api/admin/users", ...OPEN200 }],
    expect: "fail", contains: ["管理端点无 token 可达", "/api/admin/users 返回 HTTP 200", "护栏失效", "另 /api/users/me HTTP 200 可达"] },
  { name: "S01b_管理端破_users_me被拒_仍直红", devEnv: { DEBUG: "true", ENV_NAME: null },
    plan: [{ path: "/api/users/me", ...DENY401 }, { path: "/api/admin/users", ...OPEN200 }],
    expect: "fail", contains: ["管理端点无 token 可达", "另 /api/users/me 被 401 拒"] },
  { name: "S02_双探点均拒_DEBUG=true_开关仍开", devEnv: { DEBUG: "true", ENV_NAME: null },
    plan: [{ path: "/api/users/me", ...DENY401 }, { path: "/api/admin/users", ...DENY401 }],
    expect: "pass", contains: ["双探点被拒", "后门开关仍开启", "admin Bearer 护栏在"] },
  { name: "S03_双探点均拒_DEBUG=false_生产态正确", devEnv: { DEBUG: "false", ENV_NAME: null },
    plan: [{ path: "/api/users/me", ...DENY401 }, { path: "/api/admin/users", ...DENY401 }],
    expect: "pass", contains: ["双探点被拒", "DEBUG 安全,生产态正确"] },
  { name: "S04_开发态后门_WARN", devEnv: { DEBUG: "true", ENV_NAME: null },
    plan: [{ path: "/api/users/me", ...OPEN200 }, { path: "/api/admin/users", ...DENY401 }],
    expect: "warn", contains: ["WARN 开发态虚拟管理员后门存在", "admin Bearer 护栏在"] },
  { name: "S05_生产类环境_ENV_NAME非local_直红", devEnv: { DEBUG: "true", ENV_NAME: "prod" },
    plan: [{ path: "/api/users/me", ...OPEN200 }, { path: "/api/admin/users", ...DENY401 }],
    expect: "fail", contains: ["生产类环境虚拟管理员后门", "管理面:"] },
  { name: "S06_prod_gate_WARN升级FAIL", devEnv: { DEBUG: "true", ENV_NAME: null }, prodGate: true,
    plan: [{ path: "/api/users/me", ...OPEN200 }, { path: "/api/admin/users", ...DENY401 }],
    expect: "fail", contains: ["--prod-gate 部署门", "WARN 已升级为 FAIL"] },
  { name: "S07_DEBUG=false_真后门_直红", devEnv: { DEBUG: "false", ENV_NAME: null },
    plan: [{ path: "/api/users/me", ...OPEN200 }, { path: "/api/admin/users", ...DENY401 }],
    expect: "fail", contains: ["真后门", "生产态/DEBUG=false 模式下绝不应出现"] },
  { name: "S08_后端不可达_跳过不重复误报", devEnv: { DEBUG: "true", ENV_NAME: null },
    plan: [{ path: "/api/users/me", err: "boom connect refused" }],
    expect: "pass", contains: ["跳过:后端不可达", "DEBUG 漏洞未探测"] },
  { name: "S09_二探点网络异常_不另立红项", devEnv: { DEBUG: "true", ENV_NAME: null },
    plan: [{ path: "/api/users/me", ...OPEN200 }, { path: "/api/admin/users", err: "boom admin reset" }],
    expect: "warn", contains: ["WARN 开发态虚拟管理员后门存在", "探测异常(boom admin reset)"] },
];

// ---------- 组 B:⑯ .env 变更感知附注 2 态 ----------
const NOTE_BLOCK = (() => {
  const key = "const envMtime = statSync";
  const i = SRC.indexOf(key);
  if (i === -1) throw new Error("⑯ 附注截取起点未找到");
  const tryStart = SRC.lastIndexOf("try {", i);
  const endMark = "按缺文件安全缺省处理) */ }";
  const j = SRC.indexOf(endMark, i);
  if (j === -1) throw new Error("⑯ 附注截取终点未找到");
  return SRC.slice(tryStart, j + endMark.length);
})();

function makeNoteHarness() {
  return `// 自动生成:_wnextcheckdemohard2_blind.mjs ⑯ 附注盲测态(勿手改)
import { statSync } from "node:fs";
import { fileURLToPath } from "node:url";
const C = { dim: "", x: "" };
let NOTE_PRINTED = false;
const _origLog = console.log;
console.log = (...a) => { NOTE_PRINTED = true; _origLog("[NOTE] " + a.join(" ")); };
${NOTE_BLOCK}
console.log = _origLog;
process.stdout.write("__BLIND16__" + JSON.stringify({ printed: NOTE_PRINTED }));
`;
}

async function runNoteState(name, harnessDir, expectPrinted) {
  const f = path.join(harnessDir, "note_state.mjs");
  writeFileSync(f, makeNoteHarness(), "utf8");
  const stdout = await new Promise((resolve, reject) => {
    const child = spawn(process.execPath, [f]);
    let so = "", se = "";
    child.stdout.on("data", (d) => (so += d));
    child.stderr.on("data", (d) => (se += d));
    child.on("error", reject);
    child.on("close", (code) => {
      const m = /__BLIND16__(\{.*\})/.exec(so || "");
      if (!m) return reject(new Error(`态 ${name} 未输出契约 JSON(exit=${code}): ${(so + se).slice(0, 300)}`));
      resolve(so);
    });
  });
  const printed = /__BLIND16__(\{.*\})/.exec(stdout);
  const j = JSON.parse(printed[1]);
  const noteLine = (stdout.match(/\[NOTE\][^\n]*/) || [""])[0];
  const ok = j.printed === expectPrinted
    && (!expectPrinted || (noteLine.includes("[⑯ 附注]") && noteLine.includes(".env 变更感知") && noteLine.includes("最近修改")));
  record("B:⑯附注", name, ok, `printed=${j.printed} 期望 ${expectPrinted} note=「${noteLine.slice(0, 120)}」`);
}

// ---------- 组 C:② detectRedisContainer 3 态 ----------
const FNS_SRC = cut("function parseDockerPortTableMatches", "[HARD2:FNSPLIT-END]");

async function runDetectStates() {
  const TABLE = [
    "mysql-c\t0.0.0.0:3308->3306/tcp\trunning",
    "exited-redis\t0.0.0.0:6377->6379/tcp\texited",
    "running-redis\t:::6377->6379/tcp\trunning",
    "ipv6-redis\t[::]:6379->6379/tcp\trunning",
    "expose-only\t6379/tcp\tcreated",
  ].join("\n");
  const harness = `// 自动生成:_wnextcheckdemohard2_blind.mjs ② 盲测态(勿手改)
const MODE = process.env.BLIND_MODE;
const TABLE = ${JSON.stringify(TABLE)};
async function runCmd(cmd, cargs, timeoutMs) {
  if (MODE === "filters_zero") {
    if (cargs[1] === "--filter") return "";
    if (cargs[1] === "-a") return TABLE;
  }
  if (MODE === "all_zero") {
    if (cargs[1] === "--filter") return "";
    if (cargs[1] === "-a") return "";
  }
  throw new Error("unexpected runCmd " + JSON.stringify(cargs));
}
const DOCKER_TIMEOUT_MS = 8000;
${FNS_SRC}
const out = { mode: MODE };
try { out.detect = await detectRedisContainer(6377); } catch (e) { out.detect = "THREW: " + e.message; }
out.five = [];
for (let i = 0; i < 5; i++) out.five.push(JSON.stringify(parseDockerPortTableMatches(6377, TABLE)));
out.coexist = parseDockerPortTableMatches(6377, TABLE);
process.stdout.write("__BLIND2__" + JSON.stringify(out));
`;
  const f = path.join(mkdtempSync(path.join(tmpdir(), "h2blind2-")), "detect.mjs");
  writeFileSync(f, harness, "utf8");
  try {
    const run = (mode) => new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [f], { env: { ...process.env, BLIND_MODE: mode } });
      let so = "", se = "";
      child.stdout.on("data", (d) => (so += d));
      child.stderr.on("data", (d) => (se += d));
      child.on("error", reject);
      child.on("close", (code) => {
        const m = /__BLIND2__(\{.*\})/.exec(so || "");
        if (!m) return reject(new Error(`态 ${mode} 未输出契约 JSON(exit=${code}): ${(so + se).slice(0, 300)}`));
        resolve(JSON.parse(m[1]));
      });
    });
    const r1 = await run("filters_zero");
    record("C:②兜底", "filter双0_全表救回running-redis", r1.detect === "running-redis", `detect=${r1.detect}`);
    const r2 = await run("all_zero");
    record("C:②兜底", "全0_干净报错含端口", String(r2.detect).startsWith("THREW: 未找到映射宿主端口 6377"), `detect=${r2.detect}`);
    const r3 = await run("filters_zero");
    const det = r3.five.every((s) => s === r3.five[0]) && r3.coexist[0] === "running-redis" && r3.coexist[1] === "exited-redis" && !r3.coexist.includes("mysql-c");
    record("C:②兜底", "同宿主端口并存_5连跑全等_running优先", det, `five唯一=${r3.five.every((s) => s === r3.five[0])} order=${JSON.stringify(r3.coexist)}`);
  } finally {
    rmSync(path.dirname(f), { recursive: true, force: true });
  }
}

// ---------- 主流程 ----------
try {
  for (const st of DEBUG_STATES) await runDebugState(st);

  // 组 B:.env 存在/缺失两态。harness 落点决定 import.meta.url 的 ../.env 解析:
  //   态1 d1/h.mjs → ../.env = edu-agent/.env(真存在,DEBUG=true);态2 d1/deeper-*/h.mjs → ../.env = d1/.env(缺)
  const d1 = mkdtempSync(path.join(EDU_ROOT, "_h2blind16-"));
  const d2 = mkdtempSync(path.join(d1, "deeper-"));
  try {
    await runNoteState("env存在_附注打印含mtime", d1, true);
    // 态 2:.env 缺 → 静默跳过(harness 放 deeper/ → ../.env = d1/.env,不存在)
    rmSync(path.join(d1, ".env"), { force: true });
    await runNoteState("env缺失_静默跳过", d2, false);
  } finally {
    rmSync(d1, { recursive: true, force: true });
  }

  await runDetectStates();
} catch (e) {
  console.error("盲测 harness 异常中断:", e);
  process.exit(2);
}

const fails = results.filter((r) => !r.ok);
console.log(`\n盲测汇总: ${results.length - fails.length}/${results.length} 绿${fails.length ? `,红项 ${fails.map((r) => r.name).join("、")}` : ""}`);
console.log(fails.length === 0 ? "BLIND-ALL-OK" : "BLIND-HAS-RED");
process.exit(fails.length === 0 ? 0 : 1);
