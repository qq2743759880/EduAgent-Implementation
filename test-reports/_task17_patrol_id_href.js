// task17 巡检辅助：scripts 引用的 DOM id 是否都存在于 HTML（静态+动态拼接 id 全覆盖）
const fs = require('fs');
const path = require('path');
const dir = path.join(__dirname, '..', 'edu-frontend', 'public');
const pages = ['favorites.html', 'practice.html', 'my-cohorts.html', 'refund.html'];
let fail = 0;
for (const f of pages) {
  const html = fs.readFileSync(path.join(dir, f), 'utf8');
  const idSet = new Set();
  for (const m of html.matchAll(/id="([^"]+)"/g)) idSet.add(m[1]);
  const blocks = [...html.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
  const refs = new Set();
  for (const m of blocks.matchAll(/getElementById\(\s*['"]([\w-]+)['"]\s*\)/g)) refs.add(m[1]);
  for (const m of blocks.matchAll(/\$\$?\(\s*['"]([\w-]+)['"]\s*\)/g)) refs.add(m[1]);
  for (const m of blocks.matchAll(/querySelector(?:All)?\(\s*['"]#([\w-]+)/g)) refs.add(m[1]);
  // 动态拼接：'panel-'+p / 'tab-'+k / 'tabbtn-'+k / 'tab-empty-'+k
  const dynPrefix = [['panel-', ['success', 'loading', 'error', 'empty']], ['tab-', ['active', 'completed', 'refunded']], ['tabbtn-', ['active', 'completed', 'refunded']], ['tab-empty-', ['active', 'completed', 'refunded']]];
  const usesDyn = dynPrefix.some(([p]) => blocks.includes("'" + p + "'") || blocks.includes('"' + p + '"'));
  const missing = [...refs].filter(r => !idSet.has(r));
  const dynMissing = [];
  if (usesDyn) {
    for (const [p, suffixes] of dynPrefix) {
      if (!(blocks.includes("'" + p + "'") || blocks.includes('"' + p + '"'))) continue;
      for (const s of suffixes) if (!idSet.has(p + s)) dynMissing.push(p + s);
    }
  }
  if (missing.length || dynMissing.length) fail++;
  console.log(f, '| static missing:', missing.length ? missing : 'NONE', '| dynamic missing:', dynMissing.length ? dynMissing : 'NONE');
}
// href 死链核查：站内相对链接指向的页面是否存在
console.log('--- href targets ---');
for (const f of pages) {
  let html = fs.readFileSync(path.join(dir, f), 'utf8');
  html = html.replace(/<!--[\s\S]*?-->/g, ''); // 剥离 HTML 注释，避免审计日志中的 href="#" 样例误报
  const idSet = new Set();
  for (const m of html.matchAll(/id="([^"]+)"/g)) idSet.add(m[1]);
  const bad = [];
  for (const m of html.matchAll(/href="([^"#][^"]*)"/g)) {
    const h = m[1];
    if (/^(https?:|\/\/|mailto:|javascript:)/.test(h)) continue;
    const file = h.split(/[?#]/)[0].replace(/^\//, '');
    if (!file || !file.endsWith('.html')) continue;
    if (!fs.existsSync(path.join(dir, file))) bad.push(h);
  }
  const hashLinks = [...html.matchAll(/href="#([\w-]+)"/g)].map(m => m[1]).filter(id => !idSet.has(id));
  const bareHash = /href="#"/.test(html) ? ['href="#" x' + (html.match(/href="#"/g) || []).length] : [];
  if (bad.length || hashLinks.length || bareHash.length) fail++;
  console.log(f, '| missing target pages:', bad.length ? bad : 'NONE', '| dead #anchors:', hashLinks.length ? hashLinks : 'NONE', '| bare href=#:', bareHash);
}
process.exit(fail ? 1 : 0);
