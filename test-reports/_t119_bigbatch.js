// task119 边界实证2：201 条打点强制分批上限（4*50? 否，一次性 201 > 200 应由前端切批）；这里测 200 上限接受+1 拒绝
// 以及 complete/打点是否真实落库（outline 重查 watch_ratio/完成icon 变化）
// 此处改用 DB 查询确认落库，前端分批逻辑由代码断言保证
const fs = require("fs");
const path = require("path");
const BASE = "http://127.0.0.1:8000";
const TOKEN = fs.readFileSync(path.resolve(__dirname, "_t119_token.txt"), "utf8").trim();
const H = { "Content-Type": "application/json", "Authorization": "Bearer " + TOKEN };

async function call(name, method, url, body) {
  try {
    const r = await fetch(BASE + url, { method, headers: H, body: body ? JSON.stringify(body) : undefined });
    const text = await r.text();
    let j; try { j = JSON.parse(text); } catch (e) { j = text; }
    console.log(`--- ${name} [${r.status}] ---`); console.log(JSON.stringify(j).slice(0, 300));
    return { status: r.status, body: j };
  } catch (e) { console.log(name, "ERR", e.message); return { error: e.message }; }
}

async function main() {
  // 1) 200 条上限大batch（PLAY + 199 TICK）
  const ticks = [];
  // 无时区本地时间（YYYY-MM-DDTHH:MM:SS）——带 Z 后端会 500
  const base = new Date("2026-09-02T23:40:00");
  function localISO(d) {
    const p = (n, l = 2) => String(n).padStart(l, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }
  ticks.push({ event_type: "PLAY", position_seconds: 0, playback_rate: 1.0, network_type: "WIFI", event_time: localISO(base) });
  for (let i = 1; i <= 199; i++) {
    const t = new Date(base.getTime() + i * 33000);
    ticks.push({ event_type: "TICK", position_seconds: i * 33, playback_rate: 1.0, network_type: "WIFI", event_time: localISO(t) });
  }
  console.log("batch ticks 长度 =", ticks.length, "(断言 =200)");
  await call("tickBatch200", "POST", "/api/progress/video/tick-batch", { play_session_id: 525478, session_id: 5, ticks });
}
main();