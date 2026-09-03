const fs = require('fs');
const path = require('path');
const dir = 'edu-frontend/public';
const files = fs.readdirSync(dir).filter(f => f.endsWith('.html'));
let syntaxErr = 0, bodyClassMulti = 0, dupIdFiles = 0, langMissing = 0;
for (const f of files) {
  const html = fs.readFileSync(path.join(dir, f), 'utf8');
  const scripts = [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)];
  for (const m of scripts) {
    try { new Function(m[1]); } catch (e) { syntaxErr++; console.log('SYNTAX', f); break; }
  }
  const bodyTags = html.match(/<body[^>]*>/g) || [];
  for (const x of bodyTags) { if (/class=.*class=/.test(x)) { bodyClassMulti++; console.log('BODYMULTI', f); } }
  const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map(m => m[1]);
  const seen = new Set(), dup = new Set();
  for (const id of ids) { if (seen.has(id)) dup.add(id); seen.add(id); }
  if (dup.size) { dupIdFiles++; console.log('DUPID', f, [...dup]); }
  if (!/<html[^>]+\blang\s*=/.test(html)) { langMissing++; console.log('LANGMISSING', f); }
  if (/\/@vite\/client/.test(html)) console.log('HMR', f);
  if (/catch\(function\(\)\{\}\)/.test(html)) console.log('CATCH', f);
}
console.log('files=' + files.length + ' syntaxErr=' + syntaxErr + ' bodyClassMulti=' + bodyClassMulti + ' dupIdFiles=' + dupIdFiles + ' langMissing=' + langMissing);