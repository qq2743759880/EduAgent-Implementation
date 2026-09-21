/* FEAT-WIRE-V2 #5：MCP 测试数据三核闸软删（Node 版）。
 * ① 备份：删前逐 server 全量详情落 JSON；② 行数一致：删后活跃面恰=保留面+被删者 yn=0；
 * ③ 幂等：重发 DELETE 须 4xx/幂等语义。软删走官方 API（关联工具同步 yn=0），禁 DB 直写。 */
import { writeFileSync } from "node:fs";

const API = "http://127.0.0.1:9988";
const HERE = new URL(".", import.meta.url).pathname.replace(/^\/([A-Za-z]):/, "$1:");
const KEEP = { 1: "stdio-echodemo", 2: "sse-demo-localhost" };
const DELETE_IDS = [4, 5, 6, 8, 10, 12, 14, 16, 17, 19, 21, 23];

async function jfetch(path, opts = {}) {
  const r = await fetch(API + path, {
    ...opts,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${TOKEN}`, ...(opts.headers || {}) },
  });
  let body = null;
  try { body = await r.json(); } catch {}
  return { status: r.status, body };
}

const login = await fetch(API + "/api/auth/login", {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: "adm02test", password: "Test@123456" }),
}).then((r) => r.json());
const TOKEN = login.data.access_token;

// ① 备份
const backup = {};
for (const sid of [...DELETE_IDS, ...Object.keys(KEEP).map(Number)]) {
  const r = await jfetch(`/api/mcp/servers/${sid}`);
  backup[sid] = r.body?.data ?? null;
}
writeFileSync(new URL("./d05-mcp-backup.json", import.meta.url), JSON.stringify(backup, null, 2), "utf8");
console.log(`① 备份完成：${Object.keys(backup).length} server 详情 -> d05-mcp-backup.json`);

// 删前活跃面
const before = await jfetch("/api/mcp/servers?page=1&page_size=100");
const beforeItems = before.body?.data?.items || [];
console.log(`② 删前活跃 server：${beforeItems.length} 个 = [${beforeItems.map((s) => s.id).sort((a, b) => a - b)}]`);

// 软删
const results = {};
for (const sid of DELETE_IDS) {
  const r = await jfetch(`/api/mcp/servers/${sid}`, { method: "DELETE" });
  results[sid] = { status: r.status, body: r.body };
  console.log(`   DELETE ${sid}: HTTP ${r.status} ${JSON.stringify(r.body)?.slice(0, 80)}`);
}

// 行数对账
const after = await jfetch("/api/mcp/servers?page=1&page_size=100");
const afterItems = after.body?.data?.items || [];
const afterIds = afterItems.map((s) => s.id).sort((a, b) => a - b);
const keepIds = Object.keys(KEEP).map(Number).sort((a, b) => a - b);
if (JSON.stringify(afterIds) !== JSON.stringify(keepIds)) throw new Error(`删后活跃面不符: ${afterIds}`);
console.log(`② 行数对账通过：删后活跃=${afterIds}（恰为保留面）`);

// 被删者读回：404/yn=0
for (const sid of DELETE_IDS) {
  const r = await jfetch(`/api/mcp/servers/${sid}`);
  const ok = r.status === 404 || r.body?.data == null || Number(r.body?.data?.yn ?? 1) === 0;
  if (!ok) throw new Error(`server ${sid} 删后状态异常: ${JSON.stringify(r).slice(0, 120)}`);
}
console.log("② 被删 12 server 读回全部 yn=0/404 ✓");

// ③ 幂等重删
for (const sid of DELETE_IDS.slice(0, 3)) {
  const r = await jfetch(`/api/mcp/servers/${sid}`, { method: "DELETE" });
  const ok = r.status >= 400 || r.body?.code !== 0 || r.body?.data?.ok;
  if (!ok) throw new Error(`幂等重删异常: ${JSON.stringify(r).slice(0, 120)}`);
  console.log(`③ 幂等重删 ${sid}: HTTP ${r.status} ${JSON.stringify(r.body)?.slice(0, 60)}`);
}

// 保留面详情完好 + 工具面
for (const sid of keepIds) {
  const r = await jfetch(`/api/mcp/servers/${sid}`);
  if (!r.body?.data) throw new Error(`保留 server ${sid} 详情缺失`);
}
const tools = await jfetch("/api/mcp/tools?page=1&page_size=100");
const toolItems = tools.body?.data?.items || tools.body?.data || [];
const toolServers = [...new Set((Array.isArray(toolItems) ? toolItems : []).map((t) => t.server_id))];
console.log(`③ 现役工具面 server_id：[${toolServers}]`);
writeFileSync(new URL("./d05-mcp-cleanup-result.json", import.meta.url),
  JSON.stringify({ deleted: results, afterIds, toolServers }, null, 2), "utf8");
console.log("三核闸全部通过");
