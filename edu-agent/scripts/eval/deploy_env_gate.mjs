// W-NEXT-CHECKDEMO-PROD-001 尾巴②(P0-1/P0-2 自批判收口):部署环境门(deploy env gate)
// 用法: node scripts/eval/deploy_env_gate.mjs [env文件路径]
//   env 文件路径缺省 = 脚本定位的 edu-agent/.env;也可显式传,如 CI 传 edu-agent/.env.example
// 退出码: 0 = 可部署(DEBUG=false 或缺省);1 = 禁止部署(DEBUG=true / DEBUG 值不可解析 / env 文件缺失)
// 末行输出: [DEPLOY_GATE] {"file":...,"debug":...,"env_name":...,"decision":...,"reason":...}
//
// 语义(两级判据,与 check-demo ⑧ / 后端 P1-8 `_debug_env_gate`(app/config.py:763)同口径):
//   - DEBUG=false 或缺省(config.py 默认 False)→ exit 0(生产唯一合法形态)
//   - DEBUG=true + ENV_NAME 显式非 local(strip+lower ≠ ""/"local",如 prod/production/staging/dev/qa)
//       → exit 1:生产类环境 DEBUG=true 真后门(P1-8 同口径最严判)
//   - DEBUG=true + ENV_NAME 缺省/空/local → exit 1:deploy 门从严判(P0-2 根因正是
//       「生产忘设 ENV_NAME 时 DEBUG=true 被当开发态放行」;部署语境下 DEBUG=true 一律不可出包。
//       本地开发形态请勿运行部署门——本地把关用 check-demo.mjs ⑧,其对本机 dev 态为 WARN 不阻断)
//   - DEBUG 值不可解析(非 bool 词表)→ exit 1(fail-closed,宁红不漏)
//   - env 文件缺失 → exit 1(部署门无法验证 = 不放行;CI 场景 .env.example 缺失也该红)
// CI 接线:.github/workflows/ci.yml `deploy-env-gate` job 对 edu-agent/.env.example 跑本门(必须 exit 0,
//   防示例文件带 DEBUG=true 误导部署);deploy/README.md task123 检查单要求部署前对真实 .env 跑本门。
// 零新依赖:Node >= 18(仅 fs/path/child_process 内置)。
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_ENV = path.resolve(SCRIPT_DIR, "..", "..", ".env"); // edu-agent/.env

function fail(msg) {
  console.error(msg);
  process.exit(1);
}

function parseBool(v) {
  if (v === undefined) return null; // 键缺省
  const s = String(v).trim().toLowerCase();
  if (s === "") return null; // 空值按未声明
  if (["true", "1", "yes", "on", "t", "y"].includes(s)) return true;
  if (["false", "0", "no", "off", "f", "n"].includes(s)) return false;
  return undefined; // 不可解析 → fail-closed
}

function parseEnvFile(p) {
  const out = { DEBUG: undefined, ENV_NAME: undefined };
  const lines = readFileSync(p, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
    if (!m) continue;
    let val = m[2];
    // 去包裹引号(单/双),防 DEBUG="true" 误判
    if (val.length >= 2 && ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'")))) {
      val = val.slice(1, -1);
    }
    if (m[1] === "DEBUG") out.DEBUG = val;
    if (m[1] === "ENV_NAME") out.ENV_NAME = val;
  }
  return out;
}

// ---------- 入口 ----------
const argv = process.argv.slice(2).filter((a) => !a.startsWith("-"));
const envPath = argv[0] ? path.resolve(process.cwd(), argv[0]) : DEFAULT_ENV;

if (!existsSync(envPath)) {
  console.log(`[DEPLOY_GATE] ${JSON.stringify({ file: envPath, decision: "file_missing", reason: "env 文件不存在——部署门无法验证即不放行(fail-closed)" })}`);
  fail(`部署门 FAIL:env 文件不存在: ${envPath}`);
}
let raw;
try {
  raw = parseEnvFile(envPath);
} catch (e) {
  console.log(`[DEPLOY_GATE] ${JSON.stringify({ file: envPath, decision: "parse_error", reason: String(e?.message || e) })}`);
  fail(`部署门 FAIL:env 文件读取/解析失败: ${envPath}`);
}
const debug = parseBool(raw.DEBUG);
const envNameRaw = raw.ENV_NAME === undefined ? null : String(raw.ENV_NAME);
// P1-8 同口径归一化:strip + lower;""/"local" = 本机开发态
const envName = envNameRaw === null ? "" : envNameRaw.trim().toLowerCase();
const envNonLocal = envName !== "" && envName !== "local";
// 文案显示用:缺省 vs 显式值(显式 local 标注本机开发态)
const envNameDisp = envNameRaw === null ? "缺省" : `'${envNameRaw}'${envNonLocal ? "(显式非 local,生产类)" : "(本机开发态)"}`;

function emit(decision, reason, code) {
  console.log(`[DEPLOY_GATE] ${JSON.stringify({ file: envPath, debug: debug === null ? "undeclared" : debug, env_name: envNameRaw, decision, reason })}`);
  if (code === 0) {
    console.log(`部署门 PASS: ${reason}`);
    process.exit(0);
  }
  console.error(`部署门 FAIL: ${reason}`);
  process.exit(1);
}

if (debug === undefined) {
  emit("deny_debug_unparsable", `DEBUG=${raw.DEBUG} 无法解析为 bool(词表 true/1/yes/on/t/y, false/0/no/off/f/n)——fail-closed 拒绝部署`, 1);
}
if (debug === true) {
  if (envNonLocal) {
    emit("deny_prod_env_debug_true",
      `DEBUG=true 且 ENV_NAME='${envNameRaw}' 为显式非 local(P1-8 同口径,生产类环境)——虚拟管理员后门(未登录可读用户数据)禁止随包进生产;改 .env DEBUG=false 并重启后端`, 1);
  }
  emit("deny_debug_true",
    `DEBUG=true 且 ENV_NAME=${envNameDisp}——部署门从严:DEBUG=true 一律不可出包(P0-2:生产忘设 ENV_NAME 时该形态即真后门);生产 .env 必须 DEBUG=false`, 1);
}
// debug === false 或缺省(后端 config.py 默认 False,同口径)
if (debug === null) {
  emit("allow_debug_undeclared", `DEBUG 未显式声明(按 config.py 默认 False 处理);ENV_NAME=${envNameDisp}——建议显式写 DEBUG=false 消除歧义`, 0);
}
emit("allow", `DEBUG=false 且 ENV_NAME=${envNameDisp}——部署安全缺省成立`, 0);
