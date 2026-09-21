const API = "http://127.0.0.1:9988";
const NAME = "探针员" + Date.now().toString().slice(-4);
const login = await fetch(API + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ account: "user000001", password: "Test@123456" }) }).then(r => r.json());
const tok = login.data.access_token;
const r = await fetch(API + "/api/chat/stream", { method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${tok}` },
  body: JSON.stringify({ query: `我叫${NAME}，请记住我的名字`, stream: true }) });
const reader = r.body.getReader();
const dec = new TextDecoder();
let buf = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buf += dec.decode(value, { stream: true });
}
const doneLine = buf.split("\n").filter(l => l.startsWith("data:")).pop();
console.log("NAME:", NAME);
console.log("DONE frame:", doneLine ? doneLine.slice(0, 500) : "none");
