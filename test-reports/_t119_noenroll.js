// task119 无报名边界态实证：access / outline / session 403 行为
const fs = require("fs");
const path = require("path");
const BASE = "http://127.0.0.1:8000";
const TOKEN = fs.readFileSync(path.resolve(__dirname, "_t119_token.txt"), "utf8").trim();
const H = { "Content-Type": "application/json", "Authorization": "Bearer " + TOKEN };
async function call(name, method, url) {
  const r = await fetch(BASE + url, { method, headers: H });
  let j; try { j = JSON.parse(await r.text()); } catch (e) { j = (await r.text()); }
  console.log(`--- ${name} [${r.status}] ---`); console.log(JSON.stringify(j).slice(0, 260));
  return { status: r.status, body: j };
}
async function main() {
  await call("access-noEnroll", "GET", "/api/study/courses/1/access");
  await call("session-noEnroll", "GET", "/api/study/sessions/5");
  await call("outline-noEnroll", "GET", "/api/study/courses/1/outline");
}
main();