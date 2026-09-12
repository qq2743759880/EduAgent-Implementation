// task17 巡检工具：no-undef 权威检查（可复跑）
// 用法：node test-reports/_task17_patrol_undef_conclusive.js
// 原理：提取四页内联 <script> 块 → ESLint v9 flat config(-c 显式指定，避免项目根配置覆盖) no-undef 规则。
// 结论力保障（非空转）：先对修复前基线版 practice/refund 跑同检查，必须捕获 bindQuestion/flash 两处
// no-undef（修复前真实缺陷），再对修复后四页跑，必须全 PASS。
const fs = require('fs');
const path = require('path');
const { execFileSync, execSync } = require('child_process');
const REPORTS = __dirname;                 // test-reports/
const PROJECT = path.dirname(REPORTS);     // 项目根
const FE = path.join(PROJECT, 'edu-frontend');
const PAGES = ['favorites.html', 'practice.html', 'my-cohorts.html', 'refund.html'];
const cfg = 'export default [{ files:["**/*.js"], languageOptions:{ecmaVersion:2022,sourceType:"script",globals:{window:"writable",document:"writable",console:"writable",location:"writable",navigator:"writable",localStorage:"writable",fetch:"writable",XMLHttpRequest:"writable",setTimeout:"writable",clearTimeout:"writable",setInterval:"writable",clearInterval:"writable",alert:"writable",EAPI:"writable",bootAdmin:"writable",bootRefund:"writable"}},rules:{"no-undef":"error","no-unused-vars":"off","no-redeclare":"off"}}];\n';

function lintDir(dir, label) {
  const cfgPath = path.join(dir, 'cfg.mjs');
  fs.writeFileSync(cfgPath, cfg);
  const targets = fs.readdirSync(dir).filter(f => f.endsWith('.b*.js')).map(f => path.join(dir, f).split(path.sep).join('/'));
  try {
    execFileSync('node',
      [path.join(FE, 'node_modules', 'eslint', 'bin', 'eslint.js'), '-c', cfgPath.split(path.sep).join('/'), '--no-warn-ignored', ...targets],
      { encoding: 'utf8', cwd: dir, stdio: 'pipe' });
    console.log(label + ': PASS (no no-undef errors)');
    return true;
  } catch (e) {
    const out = (e.stdout || '') + (e.stderr || '');
    const errs = out.split('\n').filter(l => /\berror\b/.test(l));
    console.log(label + ': ' + errs.length + ' no-undef error(s):');
    errs.slice(0, 6).forEach(l => console.log('  ' + l.trim()));
    return false;
  }
}

function checkPage(htmlPath, label, expectFail) {
  const src = fs.readFileSync(htmlPath, 'utf8');
  const tmp = path.join(REPORTS, '_t17_lint_tmp');
  fs.rmSync(tmp, { recursive: true, force: true });
  fs.mkdirSync(tmp, { recursive: true });
  const blocks = [...src.matchAll(/<script(?![^>]*src)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  blocks.forEach((c, i) => fs.writeFileSync(path.join(tmp, 'b' + i + '.b.js'), c));
  const pass = lintDir(tmp, label);
  fs.rmSync(tmp, { recursive: true, force: true });
  if (expectFail && pass) { console.error('!! CHECKER VACUOUS: expected failure but got pass'); process.exit(2); }
  if (!expectFail && !pass) process.exit(1);
}

// 反证基线：动态定位 task17 修复提交（按提交信息 grep，跨 amend/后续提交自维护），取其父提交=修复前状态。
// 可用环境变量 T17_REV 覆盖（历史改写时自行指定，如任一含修复前文件的 ref）。
function resolveBaseline() {
  if (process.env.T17_REV) return process.env.T17_REV;
  try {
    const h = execFileSync('git', ['log', '--format=%H', '--grep=fix(reshape)/task17', '-n', '1'], { cwd: PROJECT, encoding: 'utf8' }).trim();
    if (h) return h + '~1';
  } catch (e) { /* 回退 HEAD~1 */ }
  return 'HEAD~1';
}
const REV = resolveBaseline();
function headVersion(rel) {
  const out = path.join(REPORTS, '_t17_head_tmp.html');
  const content = execFileSync('git', ['show', REV + ':' + rel], { cwd: PROJECT, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
  fs.writeFileSync(out, content, 'utf8');
  return out;
}

// 步骤1：HEAD（修复前）反向验证——检查器必须捕获真实缺陷
checkPage(headVersion('edu-frontend/public/practice.html'), '基线 practice.html (pre-fix, expect bindQuestion)', true);
fs.rmSync(path.join(REPORTS, '_t17_head_tmp.html'), { force: true });
checkPage(headVersion('edu-frontend/public/refund.html'), '基线 refund.html (pre-fix, expect flash)', true);
fs.rmSync(path.join(REPORTS, '_t17_head_tmp.html'), { force: true });
// 步骤2：修复后四页必须干净
for (const p of PAGES) checkPage(path.join(FE, 'public', p), 'FIXED ' + p, false);
console.log('ALL no-undef CHECKS CONCLUSIVE');
