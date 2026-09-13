// task119 全链 curl 等价实证（node fetch，输出返回 JSON）
const fs = require("fs");
const path = require("path");

const BASE = "http://127.0.0.1:8000";
const TOKEN = fs.readFileSync(path.resolve(__dirname, "_t119_token.txt"), "utf8").trim();
const SERIES = 1, SESSION = 5;
const PLAY = 525478;

const H = { "Content-Type": "application/json", "Authorization": "Bearer " + TOKEN };
const out = {};
async function call(name, method, url, body) {
  try {
    const r = await fetch(BASE + url, { method, headers: H, body: body ? JSON.stringify(body) : undefined });
    const text = await r.text();
    out[name] = { status: r.status, body: safe(text) };
  } catch (e) { out[name] = { error: e.message }; }
}
function safe(t) { try { return JSON.parse(t); } catch (e) { return t; } }

async function main() {
  await call("login", "GET", "/api/auth/me");
  await call("access", "GET", "/api/study/courses/" + SERIES + "/access");
  await call("outline", "GET", "/api/study/courses/" + SERIES + "/outline");

  // session 详情（含 transcode_status / video / assets）
  await call("session", "GET", "/api/study/sessions/" + SESSION);

  // tick-batch：3 条打点（含 PLAY + TICK）
  const ticks = [
    { event_type: "PLAY", position_seconds: 0, playback_rate: 1.0, network_type: "WIFI", event_time: "2026-09-02T23:35:00" },
    { event_type: "TICK", position_seconds: 33, playback_rate: 1.0, network_type: "WIFI", event_time: "2026-09-02T23:35:30" },
    { event_type: "TICK", position_seconds: 66, playback_rate: 1.0, network_type: "WIFI", event_time: "2026-09-02T23:36:00" },
  ];
  await call("tickBatch", "POST", "/api/progress/video/tick-batch",
    { play_session_id: PLAY, session_id: SESSION, ticks });

  // complete
  await call("complete", "POST", "/api/study/sessions/" + SESSION + "/complete");

  fs.writeFileSync(path.resolve(__dirname, "_t119_chain.json"), JSON.stringify(out, null, 2), "utf8");
  console.log("=== Java 证据已写入 _t119_chain.json ===");
  for (const k of Object.keys(out)) {
    const v = out[k];
    console.log(k + " [status=" + (v.status || "ERR") + "] " + JSON.stringify(v.body).slice(0, 400));
  }
}
main();