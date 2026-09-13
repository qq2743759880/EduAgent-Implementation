// 抽取 learning.html 中 task119 注入 IIFE 段并用 vm.Script 编译验语法
const fs = require("fs");
const vm = require("vm");
const src = fs.readFileSync(require("path").resolve(__dirname, "../edu-frontend/public/learning.html"), "utf8");

// 定位注入块：从特有注释到文件最后一个 "})();"
const marker = "task119：learning 学习动线真实接入";
const idx = src.indexOf(marker);
if (idx < 0) { console.error("FAIL | 未找到 task119 注入块标记"); process.exit(1); }

// 从该注释前的函数体起点找真正脚本起点：回溯到上一个 "<script"
const scriptStart = src.lastIndexOf("<script", idx);
const scriptEnd = src.lastIndexOf("</script>", src.length);
const block = src.slice(scriptStart, scriptEnd);

// 去掉 <script ...> 头,保留纯 JS
const jsbody = block.replace(/^\s*<script[^>]*>/, "").replace(/\s*$/, "");

try {
  new vm.Script(jsbody, { filename: "learning-task119-inline.js" });
  console.log("PASS | task119 注入块 JS 语法编译通过，代码长度 " + jsbody.length + " 字符 / " + jsbody.split("\n").length + " 行");
} catch (e) {
  console.error("FAIL | 语法错误: " + e.message);
  process.exit(1);
}