#!/usr/bin/env node
/*
 * task110 — 全站死链扫描器（一次性工具，可留作回归）
 * 用法: node test-reports/scan-deadlinks.mjs
 * 遍历 edu-frontend/public/*.html，提取：
 *   a) href="..."
 *   b) location.href / location.replace / window.open = "..."
 *      （含 onclick="location.href='xxx.html'" 内联）
 *   c) ${...} 模板串（按 ? / ${ 前缀匹配文件名）
 * 判定目标文件是否存在于 public 目录；query 参数名与目标页取参不强制在此解析（人工对照）。
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const DIR = path.resolve(__dirname, "../edu-frontend/public");
const files = fs.readdirSync(DIR).filter((f) => f.endsWith(".html")).sort();

// 目标文件名集合（不含扩展名，便于前缀匹配）
const targets = new Set(files.map((f) => f.replace(/\.html$/, "")));

// 过滤：外链/锚点/mailto/javascript:/data:
function isExternalOrSpecial(u) {
  return /^(https?:|mailto:|tel:|javascript:|data:|#|about:)/.test(u);
}
// 归一化：去引号、去 ${...}、去 query、去 hash、去 /index 尾巴、去首尾空白
function normalize(u) {
  u = String(u).trim().replace(/^["'\s`]+|["'\s`]+$/g, "");
  if (u.includes("${")) u = u.replace(/\$\{[^}]*\}/g, ""); // 去模板占位
  u = u.split("?")[0].split("#")[0]; // 去 query / hash
  u = u.replace(/^\.\//, "").replace(/^\/+/, "").replace(/\/+$/g, "").replace(/\/index$/, "");
  return u;
}

const rows = [];
for (const f of files) {
  const html = fs.readFileSync(path.join(DIR, f), "utf8");
  const cand = [];

  // a) href 属性
  for (const m of html.matchAll(/href=["']([^"']+)["']/g)) cand.push(m[1]);
  // b) location / window.open 跳转（含内联 onclick）
  for (const m of html.matchAll(/(?:location\.(?:href|replace)|window\.open)\s*=\s*["']([^"']+)["']/g)) cand.push(m[1]);
  // c) 直接匹配 href="*.html?..." 模板已含于 a)；这里补充去掉引号的裸跳转（极少见）
  // 注：${...} 模板串已在 a) 中被捕获，normalize 会去占位。

  for (const raw of cand) {
    if (isExternalOrSpecial(raw)) continue;
    const norm = normalize(raw);
    if (!norm) continue;
    const isHtml = /\.html$/i.test(norm);
    const base = isHtml ? norm.replace(/\.html$/i, "") : norm;
    let ok;
    if (isHtml) {
      ok = files.includes(base + ".html");
    } else if (/\.(css|js|ico|png|jpe?g|gif|svg|webp|json|map|woff2?|ttf|mp4|webm|pdf|txt|xml)$/i.test(norm)) {
      ok = fs.existsSync(path.join(DIR, norm)) || fs.existsSync(path.join(DIR, base));
    } else {
      ok = false; // 裸路径 / 无扩展名 → 视为死链
    }
    rows.push({ file: f, raw: raw.trim(), norm, ok, isHtml });
  }
}

// 分组输出
const dead = rows.filter((r) => !r.ok);
const okRows = rows.filter((r) => r.ok);

console.log("=== 扫描: " + files.length + " 个 html ===");
console.log("\n--- [修复前] 死链 / 可疑项 (ok=false) ---");
dead.forEach((r) => console.log(`  ${r.file}: ${JSON.stringify(r.raw)}  => norm="${r.norm}"`));
console.log("\n--- 正常链接统计 (ok=true): " + okRows.length + " 条 ---");
console.log("\n--- 按文件统计 ---");
const byFile = {};
rows.forEach((r) => { (byFile[r.file] = byFile[r.file] || { dead: 0, ok: 0 }); r.ok ? byFile[r.file].ok++ : byFile[r.file].dead++; });
for (const f of files) { if (byFile[f]) console.log(`  ${f}: dead=${byFile[f].dead} ok=${byFile[f].ok}`); }

console.log("\n=== 死链总数: " + dead.length + " ===");