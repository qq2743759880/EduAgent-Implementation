// 抽取 courses.html / admin-courses.html 的每个内联 <script> 块并用 vm.Script 编译验语法
//（外部 <script src> 跳过）。与 _t119_syntax.js 同一风格。
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const targets = [
  "../edu-frontend/public/courses.html",
  "../edu-frontend/public/admin-courses.html",
];

let allOk = true;

for (const rel of targets) {
  const file = path.resolve(__dirname, rel);
  const src = fs.readFileSync(file, "utf8");
  const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
  let m, idx = 0, inlineCount = 0, fail = false;
  while ((m = re.exec(src)) !== null) {
    const attrs = m[1] || "";
    if (/\bsrc\s*=/.test(attrs)) continue; // 外部脚本，跳过
    inlineCount++;
    idx++;
    const jsbody = m[2];
    try {
      new vm.Script(jsbody, { filename: path.basename(file) + "#inline" + idx });
    } catch (e) {
      fail = true;
      allOk = false;
      console.error("FAIL | " + rel + " #inline" + idx + " 语法错误: " + e.message);
    }
  }
  console.log((fail ? "FAIL | " : "PASS | ") + rel + " 内联脚本 " + inlineCount + " 块");
}

process.exit(allOk ? 0 : 1);