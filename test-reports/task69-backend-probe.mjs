/* task69 后端契约探针：验证 admin 能拉取题型枚举 / 题目详情 / 我的班次 */
const BASE = "http://127.0.0.1:8000";
const accounts = {
  admin: { account: "adm02test", password: "Test@123456" },
  student: { account: "stu01test", password: "Test@123456" },
};

async function login(acc) {
  const r = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(acc),
  });
  const j = await r.json();
  const tok = j?.data?.access_token ?? j?.data?.token ?? null;
  return { status: r.status, code: j?.code, token: tok, data: j?.data };
}

async function probe(name, path, token, extra = {}) {
  const headers = { ...(token ? { authorization: `Bearer ${token}` } : {}) };
  const r = await fetch(`${BASE}${path}`, { headers, ...extra });
  const text = await r.text().catch(() => "");
  let j = null;
  try { j = JSON.parse(text); } catch {}
  console.log(`\n[${name}] GET ${path} -> HTTP ${r.status}`);
  if (j) console.log("  shell:", JSON.stringify({ code: j?.code, message: j?.message, hasData: "data" in j, data: j?.data === null ? null : typeof j?.data }));
  else console.log("  body(非JSON):", text.slice(0, 200));
  return { status: r.status, j };
}

const adminLogin = await login(accounts.admin);
console.log("[admin login]", adminLogin.status, "code=", adminLogin.code, "tokenLen=", adminLogin.token ? adminLogin.token.length : 0);
if (adminLogin.token) {
  const t = await probe("题型枚举", "/api/admin/questions/types", adminLogin.token);
  if (t.j?.data) {
    const d = t.j.data;
    console.log("  题型data类型:", Array.isArray(d) ? "array" : "object", "keys=", Array.isArray(d) ? `len=${d.length}` : Object.keys(d).join(","));
    const items = Array.isArray(d) ? d : d.items;
    console.log("  items 样例:", JSON.stringify((items || []).slice(0,2)));
  }
  await probe("题目详情 id=1", "/api/admin/questions/questions/1", adminLogin.token);
  const d1 = await fetch(`${BASE}/api/admin/questions/questions/1`, { headers: { authorization: `Bearer ${adminLogin.token}` } }).then(r=>r.json());
  const q = d1?.data;
  if (q) console.log("\n  题目id=1: stem=", JSON.stringify(q.stem?.slice?.(0,120)), " type_id=", q.question_type_id, " opts=", JSON.stringify(q.options_json?.slice?.(0,4)), " answer=", JSON.stringify(q.answer_text));
  await probe("题库列表", "/api/admin/questions/banks", adminLogin.token);
}

const stuLogin = await login(accounts.student);
console.log("\n[student login]", stuLogin.status, "code=", stuLogin.code, "tokenLen=", stuLogin.token ? stuLogin.token.length : 0);
if (stuLogin.token) {
  await probe("我的班次", "/api/me/cohorts", stuLogin.token);
}

/* 经前端代理（3000）验证 /api 转发 */
console.log("\n=== 经前端 3000 代理 ===");
if (adminLogin.token) {
  const headers = { authorization: `Bearer ${adminLogin.token}` };
  for (const p of ["/api/admin/questions/types", "/api/admin/questions/questions/1", "/api/admin/dashboard/metrics"]) {
    try {
      const r = await fetch(`http://127.0.0.1:3000${p}`, { headers });
      const text = await r.text().catch(() => "");
      let j = null; try { j = JSON.parse(text); } catch {}
      console.log(`[proxy] ${p} -> ${r.status}`, j ? `code=${j?.code}` : `body=${text.slice(0,80)}`);
    } catch (e) { console.log(`[proxy] ${p} -> FETCH_ERR ${e.message}`); }
  }
}