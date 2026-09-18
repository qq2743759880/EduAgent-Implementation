// W-NEXT-CHECKDEMO-PROD-001 尾巴②:deploy_env_gate.mjs 自测试(纯 Node,零依赖,CI 可跑)
// 用法: node scripts/eval/test_deploy_env_gate.mjs
// 覆盖 deploy 门全部决策分支(临时 fixture 写入 os.tmpdir,finally 清理):
//   1 DEBUG=false + ENV_NAME=prod        → exit 0 allow
//   2 DEBUG=true  + ENV_NAME=prod        → exit 1 deny_prod_env_debug_true(P1-8 同口径)
//   3 DEBUG=true  + ENV_NAME 缺省        → exit 1 deny_debug_true(P0-2 从严)
//   4 DEBUG=true  + ENV_NAME=local       → exit 1 deny_debug_true(部署门不认开发态)
//   5 DEBUG 缺省 + ENV_NAME=prod         → exit 0 allow_debug_undeclared(config.py 默认 False)
//   6 DEBUG=true  + ENV_NAME=PROD(大写)  → exit 1(大小写不敏感,P1-8 strip+lower 同口径)
//   7 DEBUG=TRUE  + ENV_NAME=staging     → exit 1(bool 词表大小写不敏感)
//   8 DEBUG=maybe(不可解析)             → exit 1 deny_debug_unparsable(fail-closed)
//   9 真实 edu-agent/.env.example(CI 同路径)→ exit 0(防示例带 DEBUG=true 误导部署)
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const GATE = fileURLToPath(new URL("./deploy_env_gate.mjs", import.meta.url));
const REAL_ENV_EXAMPLE = path.resolve(path.dirname(GATE), "..", "..", ".env.example");

const dir = mkdtempSync(path.join(tmpdir(), "deploy-gate-test-"));
const fixture = (name, content) => {
  const p = path.join(dir, name);
  writeFileSync(p, content, "utf8");
  return p;
};

const cases = [
  { name: "1 DEBUG=false+prod", file: fixture("c1.env", "DEBUG=false\nENV_NAME=prod\n"), code: 0, decision: "allow" },
  { name: "2 DEBUG=true+prod", file: fixture("c2.env", "DEBUG=true\nENV_NAME=prod\n"), code: 1, decision: "deny_prod_env_debug_true" },
  { name: "3 DEBUG=true+缺省ENV_NAME", file: fixture("c3.env", "DEBUG=true\n"), code: 1, decision: "deny_debug_true" },
  { name: "4 DEBUG=true+ENV_NAME=local", file: fixture("c4.env", "DEBUG=true\nENV_NAME=local\n"), code: 1, decision: "deny_debug_true" },
  { name: "5 DEBUG缺省+prod", file: fixture("c5.env", "ENV_NAME=prod\n"), code: 0, decision: "allow_debug_undeclared" },
  { name: "6 大写ENV_NAME=PROD", file: fixture("c6.env", "DEBUG=true\nENV_NAME=PROD\n"), code: 1, decision: "deny_prod_env_debug_true" },
  { name: "7 大写DEBUG=TRUE+staging", file: fixture("c7.env", "DEBUG=TRUE\nENV_NAME=staging\n"), code: 1, decision: "deny_prod_env_debug_true" },
  { name: "8 DEBUG不可解析", file: fixture("c8.env", "DEBUG=maybe\n"), code: 1, decision: "deny_debug_unparsable" },
  { name: "9 真实.env.example(CI对齐)", file: REAL_ENV_EXAMPLE, code: 0, decision: null /* 以 exit 0 为准 */ },
];

let failed = 0;
try {
  for (const c of cases) {
    const r = spawnSync(process.execPath, [GATE, c.file], { encoding: "utf8" });
    const out = (r.stdout || "") + (r.stderr || "");
    const m = /\[DEPLOY_GATE\]\s*(\{.*\})/.exec(out);
    let j = null;
    try { j = m ? JSON.parse(m[1]) : null; } catch { /* fallthrough */ }
    const codeOk = (r.status === c.code);
    const decisionOk = c.decision === null || (j && j.decision === c.decision);
    if (codeOk && decisionOk) {
      console.log(`PASS ${c.name}: exit=${r.status}${j ? ` decision=${j.decision}` : ""}`);
    } else {
      failed++;
      console.error(`FAIL ${c.name}: exit=${r.status}(期望 ${c.code}) decision=${j?.decision}(期望 ${c.decision})\n  output=${out.slice(0, 300)}`);
    }
  }
  // 文件缺失分支(路径指向不存在文件)
  const miss = spawnSync(process.execPath, [GATE, path.join(dir, "no-such.env")], { encoding: "utf8" });
  const missOut = (miss.stdout || "") + (miss.stderr || "");
  if (miss.status === 1 && /file_missing/.test(missOut)) {
    console.log("PASS 10 env 文件缺失 → exit 1 file_missing");
  } else {
    failed++;
    console.error(`FAIL 10 env 文件缺失: exit=${miss.status} output=${missOut.slice(0, 200)}`);
  }
} finally {
  try { rmSync(dir, { recursive: true, force: true }); } catch { /* 清理失败不掩盖结果 */ }
}
console.log(`=== deploy_env_gate 自测试: ${cases.length + 1 - failed}/${cases.length + 1} PASS ===`);
process.exit(failed === 0 ? 0 : 1);
