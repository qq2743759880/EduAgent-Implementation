const API = "http://127.0.0.1:9988";
const login = await fetch(API + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: "user000001", password: "Test@123456" }) }).then(r => r.json());
const tok = login.data.access_token;
const r = await fetch(API + "/api/mcp/tools/test", { method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` },
  body: JSON.stringify({ tool_name: "recall_memory", args: { query: "我叫什么名字", top_k: 3 } }),
}).then(x => x.json());
console.log(JSON.stringify(r, null, 2).slice(0, 700));
