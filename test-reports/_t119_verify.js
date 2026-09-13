// task119 机验：grep 归零 + JS 语法 + ≤200 断言
const fs = require("fs");
const path = require("path");

const file = path.resolve(__dirname, "../edu-frontend/public/learning.html");
const src = fs.readFileSync(file, "utf8");

let fail = 0;
function check(name, ok, detail) {
  console.log((ok ? "PASS" : "FAIL") + " | " + name + (ok ? "" : " | " + detail));
  if (!ok) fail++;
}

// ① api/learning/ 归零 —— 逐处看上下文，只允许出现在"说明弃用的注释"
const re = /\/api\/learning\//g;
let m, hits = [];
while ((m = re.exec(src))) hits.push({ idx: m.index, ctx: src.slice(Math.max(0, m.index - 45), m.index + 20) });
check("api/learning/ 出现次数为 0", hits.length === 0, JSON.stringify(hits.map(h => h.ctx.trim().replace(/\s+/g, " ")), null, 0));
hits.forEach(h => console.log("   ctx: ..." + h.ctx.trim().replace(/\s+/g, " ") + "..."));

// ③ 打点批量 ≤200：找出所有 Math.min(200, ...) 之类批量上限
check("存在 ≤200 批量上限常量", /Math\.min\(200|>= 200|length >= 200/.test(src));

// 打点字段断言（VideoTickBatchIn ticks 结构字段）
["event_type", "position_seconds", "playback_rate"].forEach(f => {
  check("tick 字段包含 " + f, src.includes(f));
});

// ④ beforeunload flush
check("beforeunload 触发 flush", /beforeunload/.test(src));
// 失败静默重试 ≤2
check("重试上限 ≤2", /tries <= 2|<= 2 次/.test(src));

// ES 语法粗查：未闭合的大括号平衡（仅对注入块做粗略校验）
const open = (src.match(/\{/g) || []).length;
const close = (src.match(/\}/g) || []).length;
check("花括号配平 " + open + "/" + close, open === close);

// 入口参数必须用 EAPI.pageId
check("用 EAPI.pageId 读参", /E\.pageId\("series_id"\)/.test(src) && /E\.pageId\("cohort_id"\)/.test(src) && /E\.pageId\("session_id"\)/.test(src));

// 不重定义全局 $ / renderSides
check("不重定义全局 renderSides", !/function\s+renderSides\b/.test(src));
// 不出现 var $ = 顶层全局（仅在 IIFE 内局部定义）
check("$ 仅在 IIFE 内局部定义", !/^var \$ =/m.test(src) && /\$ = function \(s\)/.test(src));

// 关键端点路径已接
["/api/study/courses/", "/api/study/sessions/", "/api/progress/video/tick-batch", '"/api/study/sessions/" +'].forEach(k => {
  check("接入 " + k, src.includes(k));
});

console.log("\n" + (fail === 0 ? "=== 全部通过 ===" : "=== 存在 " + fail + " 项失败 ==="));
process.exit(fail === 0 ? 0 : 1);