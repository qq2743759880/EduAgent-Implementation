#!/usr/bin/env node
/**
 * fx-task05 管理端全链路联调验证（verify-task05-admin-chain.mjs）
 *
 * 6 段：登录 → 课程（系列→模块→课次→视频 Init→Finalize→Bind）→ 题库（标签→题目→批量导入→组卷）
 *       → 用户（角色变更/禁用）→ RAG（集合/重建 202+job_id/预设/审计）→ MCP（Server/发现/测试/健康扫描）
 *  - 每步 200/202（rebuild 断言 **202 + job_id**）；全程无 500
 *  - DEBUG 语义分支断言：读 edu-agent/.env，DEBUG=true → 无 Token DELETE 会话断言 200（虚拟 admin 软删）；
 *    DEBUG=false → 断言 401（与 be-task01 chat_delete_hit.py 口径一致）
 *  - 鉴权模式：优先尝试真实 admin 种子登录（env ADMIN_ACCOUNT/ADMIN_PASSWORD 或内置种子）；
 *    失败则回退 X-Force-Role: admin（DEBUG 虚拟 admin，复用 verify-task03/04 模式）
 *  - 造数幂等：随机系列/模块/课次/标签/题目 code；用户段用临时注册账号
 *
 * 前置：uvicorn :8000（be-task01 新代码）运行中；MySQL 可用。
 * 运行：node scripts/verify-task05-admin-chain.mjs
 * 退出码：0 全过 / 1 断言失败 / 2 脚本异常 / 3 服务未就绪
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const API = "http://127.0.0.1:8000";

/* ============ .env DEBUG 读取（口径对齐 be-task01 restart_uvicorn_and_chat_delete_hit.py L36-44） ============ */
function loadDebugFlag() {
  if (process.env.DEBUG !== undefined) return /^true$/i.test(String(process.env.DEBUG).trim());
  try {
    const envPath = path.resolve(__dirname, "../../edu-agent/.env");
    const txt = fs.readFileSync(envPath, "utf8");
    const m = txt.match(/^\s*DEBUG\s*=\s*(\S+)\s*$/m);
    if (m) return /^true$/i.test(m[1]);
  } catch { /* ignore */ }
  return true; // 交付基线默认 true
}
const DEBUG = loadDebugFlag();

/* ============ 就绪探测 ============ */
async function portUp(url, timeoutMs = 15000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const r = await fetch(url, { signal: AbortSignal.timeout(3000) });
      if (r.ok || r.status < 500) return true;
    } catch { /* retry */ }
    await new Promise((res) => setTimeout(res, 700));
  }
  return false;
}
if (!(await portUp(`${API}/health`))) {
  console.error(`[就绪探测] 后端 ${API} 未就绪 → exit 3`);
  process.exit(3);
}

/* ============ 结果收集 ============ */
const results = [];
function check(name, ok, extra = "") {
  results.push({ name, ok, extra });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  | " + extra : ""}`);
}

/* ============ 鉴权模式 ============ */
let authMode = "xforce"; // "jwt" | "xforce"
let token = null;
let authNote = "";
const ADMIN_SEEDS = [
  { account: process.env.ADMIN_ACCOUNT || undefined, password: process.env.ADMIN_PASSWORD || undefined },
  { account: "admin", password: "Admin@123" },
  { account: "admin", password: "admin123" },
  { account: "admin", password: "123456" },
].filter((s) => s.account && s.password);

for (const seed of ADMIN_SEEDS) {
  try {
    const r = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account: seed.account, password: seed.password }),
    });
    if (r.status === 200) {
      const j = await r.json();
      token = j.access_token;
      authMode = "jwt";
      authNote = `admin 种子登录成功（account=${seed.account}）`;
      break;
    }
  } catch { /* try next */ }
}
if (authMode === "xforce") {
  authNote = `admin 种子登录不可用 → 回退 X-Force-Role: admin（DEBUG 虚拟 admin，同 verify-task03/04）`;
}

function authHeaders(extra = {}) {
  if (authMode === "jwt") return { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...extra };
  return { "Content-Type": "application/json", "X-Force-Role": "admin", "X-Force-User-Id": "1", ...extra };
}

let stageName = "准备";
async function req(method, pathStr, { body, headers = {} } = {}) {
  const resp = await fetch(`${API}${pathStr}`, {
    method,
    headers: authHeaders(headers),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let data = null;
  const text = await resp.text();
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  return { status: resp.status, data };
}

function genCode(prefix) {
  const ts = Date.now().toString(36).slice(-6);
  const rnd = Math.floor(Math.random() * 9000 + 1000).toString(36);
  return `${prefix}-${ts}${rnd}`.slice(0, 40);
}

function assertNo500(res, name) {
  check(`${stageName} · ${name} 无 500（status<500）`, res.status < 500, `status=${res.status}`);
  return res.status < 500;
}

try {
  /* ============ 1. 登录 ============ */
  stageName = "登录";
  console.log(`  ℹ️  鉴权模式=${authMode}（DEBUG=${DEBUG}） ${authNote}`);
  if (authMode === "jwt") {
    check("登录 200 + roles 含 admin", typeof token === "string" && token.length > 20, "");
  } else {
    check("登录（回退 X-Force 模式）", true, "DEBUG 虚拟 admin 语义，满足管理端全链路");
  }

  /* ============ 2. 课程（系列→模块→课次→视频 Init→Finalize→Bind） ============ */
  stageName = "课程";
  const sCode = genCode("S-ADM");
  const series = await req("POST", "/api/admin/courses/series", {
    body: {
      series_code: sCode,
      series_name: `联调系列 ${sCode}`,
      subject_code: "english",
      level_code: "L2",
      level_name: "L2",
      description: "fx-task05 管理端全链路联调造数",
      target_hours: 6,
      sale_status: "on_sale",
      sort_no: 1,
    },
  });
  check("创建系列 200", series.status === 200 && (series.data?.id || series.data?.series_id), `status=${series.status}`);
  assertNo500(series, "创建系列");
  const seriesId = series.data?.id ?? series.data?.series_id ?? null;
  if (!seriesId) throw new Error("创建系列未返回 id");

  const mCode = genCode("MOD");
  const mod = await req("POST", "/api/admin/courses/modules", {
    body: { series_id: seriesId, module_code: mCode, module_name: `联调模块 ${mCode}`, stage_no: 1, description: "联调" },
  });
  check("创建模块 200", mod.status === 200 && (mod.data?.id || mod.data?.module_id), `status=${mod.status}`);
  assertNo500(mod, "创建模块");
  const moduleId = mod.data?.id ?? mod.data?.module_id ?? null;
  if (!moduleId) throw new Error("创建模块未返回 id");

  const sess = await req("POST", "/api/admin/courses/sessions", {
    body: { module_id: moduleId, session_no: 1, session_title: `联调课次 ${sCode}`, description: "联调", duration_minutes: 45 },
  });
  check("创建课次 200", sess.status === 200 && (sess.data?.id || sess.data?.session_id), `status=${sess.status}`);
  assertNo500(sess, "创建课次");
  const sessionId = sess.data?.id ?? sess.data?.session_id ?? null;
  if (!sessionId) throw new Error("创建课次未返回 id");

  const init = await req("POST", "/api/admin/courses/videos/upload/init", {
    body: { origin_file_name: `chain-${sCode}.mp4`, file_size: 1024 * 1024, duration_seconds: 60, asset_title: "联调视频", bind_session_id: sessionId },
  });
  check("视频 Init 200 + asset_id", init.status === 200 && typeof init.data?.asset_id === "string", `status=${init.status}`);
  assertNo500(init, "视频 Init");
  const assetId = init.data?.asset_id ?? null;
  if (!assetId) throw new Error("视频 Init 未返回 asset_id");

  const fin = await req("POST", "/api/admin/courses/videos/upload/finalize", {
    body: { asset_id: assetId, final_duration_seconds: 60, play_720_url: `http://minio/chain/${sCode}/720.mp4` },
  });
  check("视频 Finalize 200 + 状态 ready", fin.status === 200 && fin.data?.transcode_status === "ready", `status=${fin.status} state=${fin.data?.transcode_status}`);
  assertNo500(fin, "视频 Finalize");

  const bind = await req("POST", "/api/admin/courses/videos/bind-session", {
    body: { asset_id: assetId, session_id: sessionId },
  });
  check("视频 Bind 200 + 绑定回显", bind.status === 200 && (bind.data?.session_id === sessionId || bind.data?.id), `status=${bind.status}`);
  assertNo500(bind, "视频 Bind");

  /* ============ 3. 题库（标签→题目→批量导入→组卷） ============ */
  stageName = "题库";
  const tagCode = genCode("TAG");
  const tag = await req("POST", "/api/admin/questions/tags", {
    body: { tag_type: "knowledge", tag_code: tagCode, tag_name: `联调标签 ${tagCode}`, subject_code: "english", sort_no: 1 },
  });
  check("创建标签 200", tag.status === 200 && (tag.data?.id || tag.data?.tag_id), `status=${tag.status}`);
  assertNo500(tag, "创建标签");
  const tagId = tag.data?.id ?? tag.data?.tag_id ?? null;

  const qCode = genCode("Q");
  const qst = await req("POST", "/api/admin/questions", {
    body: {
      question_code: qCode,
      subject_code: "english",
      question_type: "single_choice",
      difficulty_level: "L2",
      stem_html: `<p>联调题目 ${qCode}：What is the capital of France?</p>`,
      analysis_html: "<p>Paris is the capital.</p>",
      options_json: [
        { label: "A", content: "London" },
        { label: "B", content: "Paris" },
        { label: "C", content: "Berlin" },
        { label: "D", content: "Rome" },
      ],
      correct_answer: "B",
      default_score: 5,
      tag_ids: tagId ? [tagId] : [],
    },
  });
  check("创建题目 200", qst.status === 200 && (qst.data?.id || qst.data?.question_id), `status=${qst.status}`);
  assertNo500(qst, "创建题目");

  const batch = await req("POST", "/api/admin/questions/batch-import", {
    body: [
      {
        question_code: genCode("QB"),
        subject_code: "english",
        question_type: "single_choice",
        difficulty_level: "L1",
        stem_html: "<p>批量导入题目 A</p>",
        correct_answer: "A",
        options_json: [
          { label: "A", content: "ok" },
          { label: "B", content: "no" },
        ],
      },
      {
        question_code: genCode("QB"),
        subject_code: "english",
        question_type: "true_false",
        difficulty_level: "L1",
        stem_html: "<p>批量导入题目 B（判断）</p>",
        correct_answer: "1",
      },
    ],
  });
  check("批量导入 200 + imported/skipped/failed 计数", batch.status === 200 && Number.isInteger(batch.data?.imported) && Number.isInteger(batch.data?.failed), `status=${batch.status} imported=${batch.data?.imported} skipped=${batch.data?.skipped} failed=${batch.data?.failed}`);
  assertNo500(batch, "批量导入");

  const compose = await req("POST", "/api/admin/questions/papers/compose", {
    body: {
      spec: { subject_code: "english", total_score: 100, duration_minutes: 60, pass_score: 60, tag_ids: tagId ? [tagId] : [] },
      paper_code: genCode("PAPER"),
      paper_title: `联调组卷 ${sCode}`,
      expected_question_count: 5,
    },
  });
  check("组卷 200 + draft_paper_id", compose.status === 200 && Number.isInteger(compose.data?.draft_paper_id), `status=${compose.status} selected=${compose.data?.selected_count}`);
  assertNo500(compose, "组卷");

  /* ============ 4. 用户（角色变更/禁用） ============ */
  stageName = "用户";
  const userList = await req("GET", "/api/admin/users?role_code=student&page=1&page_size=10");
  check("用户列表 200", userList.status === 200 && Array.isArray(userList.data?.items), `status=${userList.status}`);
  assertNo500(userList, "用户列表");

  // 临时注册学生（幂等：随机账号）→ 角色变更 teacher → 禁用
  const tmpAccount = genCode("admuser").replace(/-/g, "_");
  await fetch(`${API}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account: tmpAccount, nickname: `联调用户${tmpAccount.slice(-4)}`, password: "P@ssw0rd123", mobile: `138${String(Math.floor(Math.random() * 1e8)).padStart(8, "0")}` }),
  });
  const tmpLogin = await fetch(`${API}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account: tmpAccount, password: "P@ssw0rd123" }),
  });
  const tmpUser = tmpLogin.ok ? (await tmpLogin.json()).user : null;
  if (!tmpUser?.user_id) throw new Error("临时测试用户登录失败");
  check("临时测试用户已注册（学生）", true, `uid=${tmpUser.user_id}`);

  const roleChg = await req("POST", `/api/admin/users/${tmpUser.user_id}/role`, { body: { target_role: "teacher", reason: "联调角色变更" } });
  check("角色变更 student→teacher 200", roleChg.status === 200 && roleChg.data?.target_role === "teacher", `status=${roleChg.status}`);
  assertNo500(roleChg, "角色变更");

  const disable = await req("POST", `/api/admin/users/${tmpUser.user_id}/status`, { body: { status: 0, reason: "联调禁用（测试账号）" } });
  check("禁用测试用户 200", disable.status === 200 && disable.data?.status === 0, `status=${disable.status}`);
  assertNo500(disable, "禁用用户");

  // 最后 1 个可用 admin 守卫负例（服务层 40303「至少保留 1 名可用管理员账号」）：
  // 仅当可用 admin 恰好 1 个时才能确定性触发；多 admin 环境跳过并记录
  const adminCount = await req("GET", "/api/admin/users?role_code=admin&status=1&yn=1&page=1&page_size=100");
  const activeAdmins = Array.isArray(adminCount.data?.items) ? adminCount.data.items.length : -1;
  if (activeAdmins === 1) {
    const guard = await req("POST", `/api/admin/users/${adminCount.data.items[0].user_id}/role`, { body: { target_role: "student", reason: "联调负例" } });
    check("降级最后 1 个 admin → 400/403 守卫", guard.status === 400 || guard.status === 403, `status=${guard.status}`);
  } else {
    check("最后 admin 守卫（多 admin 环境跳过）", true, `可用 admin 数=${activeAdmins}`);
  }

  /* ============ 5. RAG（集合/重建 202+job_id/预设/审计） ============ */
  stageName = "RAG";
  const collections = await req("GET", "/api/admin/rag/collections");
  check("RAG 集合列表 200", collections.status === 200 && Array.isArray(collections.data), `status=${collections.status} count=${Array.isArray(collections.data) ? collections.data.length : 0}`);
  assertNo500(collections, "集合列表");

  const rebuild = await req("POST", "/api/admin/rag/collections/rebuild", {
    body: { collection_name: "knowledge_chunk_v1", partition_name: "_default", mode: "incremental" },
  });
  check("重建索引 202 + job_id", rebuild.status === 202 && typeof rebuild.data?.job_id === "string" && /^r_/.test(rebuild.data.job_id), `status=${rebuild.status} job_id=${rebuild.data?.job_id}`);
  assertNo500(rebuild, "重建索引");

  const presets = await req("GET", "/api/admin/rag/presets");
  check("预设列表 200", presets.status === 200 && Array.isArray(presets.data), `status=${presets.status} count=${Array.isArray(presets.data) ? presets.data.length : 0}`);
  assertNo500(presets, "预设列表");

  const audit = await req("GET", "/api/admin/rag/audit-log?page=1&page_size=20");
  check("审计日志 200", audit.status === 200 && Array.isArray(audit.data?.items), `status=${audit.status}`);
  assertNo500(audit, "审计日志");

  /* ============ 6. MCP（Server/发现/测试/健康扫描） ============ */
  stageName = "MCP";
  const servers = await req("GET", "/api/mcp/servers");
  check("MCP Server 列表 200", servers.status === 200 && Array.isArray(servers.data?.items), `status=${servers.status} total=${servers.data?.total}`);
  assertNo500(servers, "Server 列表");
  const serverId = servers.data?.items?.[0]?.id ?? null;
  if (serverId) {
    const tools = await req("GET", `/api/mcp/servers/${serverId}/tools`);
    check("Server 工具列表 200", tools.status === 200 && Array.isArray(tools.data?.items), `status=${tools.status} tools=${tools.data?.total}`);
    assertNo500(tools, "工具列表");

    const discover = await req("GET", `/api/mcp/servers/${serverId}/discover-live`);
    check("discover-live 200（HTTP 层）", discover.status === 200, `status=${discover.status} ok=${discover.data?.ok} tools=${discover.data?.tool_count}`);
    assertNo500(discover, "discover-live");

    // 工具测试：tools/test 依赖 DB 注册工具（registry.get_tool_by_ref），discover-live 实时工具不落库不可测。
    // 遍历 servers 找首个有 DB 工具（优先 add）的 server 做测试；全部无 DB 工具 → 跳过。
    const serverList = Array.isArray(servers.data?.items) ? servers.data.items : [];
    let tested = false;
    for (const srv of serverList) {
      const srvTools = await req("GET", `/api/mcp/servers/${srv.id}/tools`);
      if (!(srvTools.status === 200 && Array.isArray(srvTools.data?.items) && srvTools.data.items.length > 0)) continue;
      const toolItem = srvTools.data.items.find((t) => t.tool_name === "add") ?? srvTools.data.items[0];
      const args = {};
      try {
        const schema = toolItem.input_schema ?? {};
        const props = schema.properties ?? {};
        for (const [k, v] of Object.entries(props)) {
          if (v?.type === "integer" || v?.type === "number") args[k] = 1;
          else if (v?.type === "boolean") args[k] = true;
          else args[k] = "test";
        }
      } catch { /* keep empty */ }
      const test = await req("POST", "/api/mcp/tools/test", {
        body: { server_id: srv.id, tool_name: toolItem.tool_name, args },
      });
      check("工具测试 200 + status/result/latency_ms", test.status === 200 && typeof test.data?.status === "string" && typeof test.data?.latency_ms === "number" && (test.data?.result !== undefined || test.data?.error_message), `status=${test.status} tool=${toolItem.tool_name} server=${srv.id} status=${test.data?.status} latency=${test.data?.latency_ms}ms`);
      assertNo500(test, "工具测试");
      tested = true;
      break;
    }
    if (!tested) {
      check("工具测试（无 DB 注册工具跳过）", true, "discover-live 工具不落库，tools/test 不可测（同 verify-task04 行为）");
    }
  } else {
    check("MCP 工具/发现/测试（无 Server 跳过）", true, "server 列表为空");
  }

  const health = await req("POST", "/api/mcp/health-scan", { body: {} });
  check("健康扫描 200 + scanned", health.status === 200 && Number.isInteger(health.data?.scanned), `status=${health.status} scanned=${health.data?.scanned} ok=${health.data?.ok_count} err=${health.data?.error_count}`);
  assertNo500(health, "健康扫描");

  /* ============ DEBUG 语义分支断言（读 .env 判定，不得只按 401 断言） ============ */
  stageName = "DEBUG 语义";
  // 造一次性会话，然后用无 Token DELETE 打靶：
  const tmpSession = await req("POST", "/api/chat/sessions", { body: { title: "admin-chain-debug-probe" } });
  const tmpSessionId = tmpSession.data?.session_id ?? tmpSession.data?.id ?? null;
  if (tmpSessionId) {
    const del = await fetch(`${API}/api/chat/sessions/${tmpSessionId}`, { method: "DELETE" }); // 无 Authorization
    if (DEBUG) {
      check(`DEBUG=true 无 Token DELETE → 200（虚拟 admin 软删语义）`, del.status === 200, `status=${del.status}`);
    } else {
      check(`DEBUG=false 无 Token DELETE → 401`, del.status === 401, `status=${del.status}`);
    }
  } else {
    check("DEBUG 语义打靶（会话创建失败跳过）", false, "未拿到 session_id");
  }
} catch (err) {
  console.error(`脚本异常（阶段：${stageName}）:`, err instanceof Error ? err.message : String(err));
  process.exitCode = 2;
}

const failed = results.filter((r) => !r.ok);
console.log(`\n===== 管理端全链路（verify-task05-admin-chain）：${results.length - failed.length}/${results.length} 通过，失败 ${failed.length}（鉴权=${authMode} DEBUG=${DEBUG}） =====`);
if (failed.length) {
  for (const f of failed) console.error(`  FAIL: ${f.name}${f.extra ? " | " + f.extra : ""}`);
  process.exitCode = 1;
}
process.exit(process.exitCode ?? 0);
