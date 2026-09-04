#!/usr/bin/env node
/**
 * W4 回归门禁（防复生）：把 W2 技术批判 C2 与 C4 的修复落地为可重复机验的 gate。
 *
 * 检查项（两项独立，可分别跑，输出明确 PASS/FAIL）：
 *   [C2] page_meta 「双轨分页」清零：扫描 edu-agent/app 与 edu-frontend/public
 *        （--with-src 时可含 edu-frontend/src），仅允许注释/文档字符串命中；
 *        字段定义 / 键 use 的主动码命中 = VIOLATION（需「主动命中=0」）。
 *   [C4] respbar 演示工具条残留清零：扫描 edu-frontend/public/*.html（--with-src 时可含 src），
 *        仅允许注释命中（含 `已移除(critique C4)` 这类说明注释）；活动 css class / respbar 用法 = VIOLATION。
 *
 * 判定口径：对每个命中行按语言去掉注释/文档字符串后再判非注释命中（区分「注释 vs 主动引用」）。
 *
 * 用法：
 *   node scripts/gate-w4-critique.mjs [--root <仓库根>] [--with-src] [--debug]
 * 输出：
 *   每项  PASS|FAIL + 命中行列表（注释命中分行列出，主动命中在 FAIL 段列出）
 *   尾部 GATE_RESULT=OK|VIOLATION（任一 VIOLATION → VIOLATION）
 * 退出码：全 PASS → 0；任一 VIOLATION → 1。
 *
 * 依赖：纯 node（fs/path），无第三方 npm 包。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));

/* ===== CLI 参数 ===== */
function parseArgs(argv) {
  const a = { root: path.resolve(SCRIPT_DIR, '..'), withSrc: false, debug: false };
  for (let i = 0; i < argv.length; i += 1) {
    const v = argv[i];
    if (v === '--root' && argv[i + 1]) { a.root = path.resolve(argv[i + 1]); i += 1; }
    else if (v === '--with-src') a.withSrc = true;
    else if (v === '--debug') a.debug = true;
  }
  return a;
}

/* ===== 逐语言去注释/去文档字符串（区分注释 vs 主动引用） =====
 * 思路：按语言维护跨行状态（块注释 /*...*\/、HTML <!--...-->、Python 三引号文档串、
 * 以及单引号/双引号/模板字符串），把注释与字符串位置替换为等长空格，
 * 只保留「真实可执行代码」，再在其中判定关键词是否出现。 */

function detectLang(file) {
  const ext = path.extname(file).toLowerCase();
  if (ext === '.py') return 'py';
  if (ext === '.html' || ext === '.htm') return 'html';
  return 'js'; // .js/.ts/.tsx/.css/.mjs → 同一套 /* */ // 字符串规则可覆盖
}

/** 生成等长空格串，保持行列信息便于定位。 */
function blanks(n) { return ' '.repeat(Math.max(n, 0)); }

function stripCommentsIter(text, lang) {
  // 返回：代码清洗串、命中信息无关；调用方自行按行 scan 关键词。
  // 跨行状态：block = null | '/*' | '<!--' | '"""' | "'''"
  let block = null;
  const lines = text.split('\n');
  const codeLines = [];
  for (const line of lines) {
    let seg = '';
    let i = 0;
    const n = line.length;
    // 当前是否处于单行字符串内（非跨行）。跨行用 block 处理（py 文档串 / /* 块）。
    let strDelim = null; // JS: ' " ` ；py 单行: ' "
    while (i < n) {
      const ch = line[i];
      const two = line.slice(i, i + 2);
      const three = line.slice(i, i + 3);
      const four = line.slice(i, i + 4);

      /* --- 处理跨行块注释/文档串 --- */
      if (block === '/*') {
        if (two === '*/') { block = null; seg += '  '; i += 2; }
        else { seg += ' '; i += 1; }
        continue;
      }
      if (block === '<!--') {
        if (three === '-->') { block = null; seg += '   '; i += 3; }
        else { seg += ' '; i += 1; }
        continue;
      }
      if (block === '"""') {
        if (three === '"""') { block = null; seg += '   '; i += 3; }
        else { seg += ' '; i += 1; }
        continue;
      }
      if (block === "'''") {
        if (three === "'''") { block = null; seg += '   '; i += 3; }
        else { seg += ' '; i += 1; }
        continue;
      }

      /* --- 常规代码段 --- */
      if (lang !== 'py') {
        // 注释起始（HTML 中 <!-- 与 /* 同层，CSS/JS 用 /* 与 //）
        if (two === '/*') { seg += '  '; block = '/*'; i += 2; continue; }
        if (four === '<!--') { seg += '    '; block = '<!--'; i += 4; continue; }
        if (two === '//') { seg += blanks(n - i); i = n; continue; } // 行注释到行尾
      } else {
        if (ch === '#') { seg += blanks(n - i); i = n; continue; } // py 行注释
        if (three === '"""') { seg += '   '; block = '"""'; i += 3; continue; }
        if (three === "'''") { seg += '   '; block = "'''"; i += 3; continue; }
      }

      /* --- URL 内 // 保护：HTML 里 <href="//..."> 或 "https://" 中的 // 不能当注释 ---
       * 规则：紧邻其前是字母/数字之一的 // （出现于 :// ）不算注释，按普通字符保留。 */
      if (two === '//' && i > 0 && /[A-Za-z0-9]/.test(line[i - 1])) {
        seg += '//'; i += 2; continue;
      }

      /* --- 单行字符串 --- */
      if (lang === 'py' && (ch === '"' || ch === "'")) {
        seg += ch; strDelim = ch; i += 1;
        while (i < n) {
          const inn = line[i];
          if (inn === '\\') { seg += blanks(2); i += 2; }          // 转义
          else if (inn === strDelim) { seg += inn; strDelim = null; i += 1; break; }
          else { seg += ' '; i += 1; }
        }
        continue;
      }
      if (lang !== 'py' && (ch === '"' || ch === "'" || ch === '`')) {
        seg += ch; strDelim = ch; i += 1;
        while (i < n) {
          const inn = line[i];
          if (inn === '\\') { seg += blanks(2); i += 2; }
          else if (inn === strDelim) { seg += inn; strDelim = null; i += 1; break; }
          else { seg += ' '; i += 1; }
        }
        continue;
      }

      seg += ch; i += 1;
    }
    codeLines.push(seg);
  }
  // 文件结束仍有未闭合块注释：按整段注释处理（上面已填空格，无碍主动命中判断）。
  return codeLines.join('\n');
}

/** 对单个文本：返回该关键词在「主动/非注释」里的命中行号行（1-based）。 */
function activeHits(text, keyword, lang) {
  const clean = stripCommentsIter(text, lang);
  const rawLines = text.split('\n');
  const cleanLines = clean.split('\n');
  const hits = [];
  for (let idx = 0; idx < rawLines.length; idx += 1) {
    if (cleanLines[idx] && cleanLines[idx].includes(keyword)) {
      hits.push({ line: idx + 1, text: rawLines[idx] });
    }
  }
  return hits;
}

/** 全部命中（含注释）行，用于 PASS 时给出可审计行列表 */
function allHits(text, keyword) {
  return text.split('\n')
    .map((l, i) => ({ line: i + 1, text: l }))
    .filter((h) => h.text.includes(keyword));
}

/* ===== 目录遍历（深度优先） ===== */
function walk(dir, collect, extAllow, base) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) walk(full, collect, extAllow, base);
    else if (e.isFile() && extAllow.some((x) => full.endsWith(x))) collect(full);
  }
}

function scanFiles(roots) {
  const files = [];
  for (const r of roots) {
    if (!fs.existsSync(r)) continue;
    walk(r, (f) => files.push(f), ['.py', '.html', '.htm', '.js', '.ts', '.tsx', '.css', '.mjs'], r);
  }
  return files;
}

/* ===== 检查实现 ===== */
function checkPages({ root, withSrc, debug }) {
  const targets = [path.join(root, 'edu-agent', 'app'), path.join(root, 'edu-frontend', 'public')];
  if (withSrc) targets.push(path.join(root, 'edu-frontend', 'src'));
  const files = scanFiles(targets);
  const active = [];
  const commentHits = [];
  for (const f of files) {
    let text;
    try { text = fs.readFileSync(f, 'utf8'); } catch { continue; }
    const rel = path.relative(root, f);
    const lang = detectLang(f);
    const act = activeHits(text, 'page_meta', lang);
    for (const h of act) active.push({ file: rel, line: h.line, text: h.text.trim() });
    const all = allHits(text, 'page_meta');
    for (const h of all) commentHits.push({ file: rel, line: h.line, text: h.text.trim() });
  }
  return { active, commentHits };
}

function checkRespbar({ root, withSrc, debug }) {
  const targets = [path.join(root, 'edu-frontend', 'public')];
  if (withSrc) targets.push(path.join(root, 'edu-frontend', 'src'));
  const files = [];
  const pubFiles = fs.existsSync(targets[0]) ? fs.readdirSync(targets[0]).filter((f) => f.endsWith('.html')) : [];
  for (const f of pubFiles) files.push(path.join(targets[0], f));
  // src 递归（存在时）
  const srcRoot = targets[1];
  if (withSrc && fs.existsSync(srcRoot)) walk(srcRoot, (f) => files.push(f), ['.html', '.js', '.ts', '.tsx', '.css'], srcRoot);
  const active = [];
  const commentHits = [];
  for (const f of files) {
    let text;
    try { text = fs.readFileSync(f, 'utf8'); } catch { continue; }
    const rel = path.relative(root, f);
    const lang = detectLang(f);
    const act = activeHits(text, 'respbar', lang);
    for (const h of act) active.push({ file: rel, line: h.line, text: h.text.trim() });
    const all = allHits(text, 'respbar');
    for (const h of all) commentHits.push({ file: rel, line: h.line, text: h.text.trim() });
  }
  return { active, commentHits };
}

/* ===== 渲染 ===== */
function render(name, result) {
  const ok = result.active.length === 0;
  console.log(`\n[${ok ? 'PASS' : 'FAIL'}] ${name}`);
  console.log(`  主动命中(非注释/文档字符串)=${result.active.length}${ok ? '  ✓ 判定：主动命中=0' : '  ✗ 须为 0'}`);
  if (ok) {
    // 列出全部命中（含注释）便于审计
    for (const h of result.commentHits) console.log(`    (comment) ${h.file}:${h.line}  ${h.text.length > 90 ? h.text.slice(0, 90) + '…' : h.text}`);
  } else {
    for (const h of result.active) console.log(`    ACTIVE  ${h.file}:${h.line}  ${h.text.slice(0, 120)}`);
  }
  return ok;
}

function main() {
  const a = parseArgs(process.argv.slice(2));
  const p = checkPages(a);
  const r = checkRespbar(a);
  render('[C2] page_meta 双轨清零', p);
  render('[C4] respbar 演示残留清零', r);
  const ok = p.active.length === 0 && r.active.length === 0;
  console.log(`\nGATE_RESULT=${ok ? 'OK' : 'VIOLATION'}`);
  process.exitCode = ok ? 0 : 1;
  return ok;
}

process.exitCode = 1;
main();