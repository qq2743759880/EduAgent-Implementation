/* FEAT-WIRE-V2 取证工具：CDP 真实点击 + 截图（复用 scripts/gates/_shared.mjs 的 createBrowser）
 * 用法：node test-reports/feat-wire-v2/evidence.mjs <scenario.js路径场景名...>
 * 环境变量：EDU_GATE_TOKEN（admin JWT）、EDU_GATE_STUDENT_TOKEN（student JWT，可选）
 */
import { createBrowser, ensureDir, sleep } from "../../scripts/gates/_shared.mjs";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const OUT_DIR = path.join(HERE, "shots");
export const BASE = process.env.EDU_GATE_BASE || "http://127.0.0.1:3322";

export async function withBrowser(fn, { viewport = [1440, 900] } = {}) {
  const browser = await createBrowser({ settleMs: 900 });
  try {
    await browser.setViewport(viewport[0], viewport[1]);
    return await fn(browser);
  } finally {
    await browser.close();
  }
}

export async function shot(browser, name) {
  const file = path.join(OUT_DIR, `${name}.jpg`);
  await browser.screenshot(file, { quality: 62 });
  console.log(`[shot] ${name} -> ${path.relative(process.cwd(), file)}`);
  return file;
}

/* 在页面里执行点击并等待，返回 evaluate 值 */
export async function click(browser, selector, { settleMs = 600 } = {}) {
  return browser.cdp.evaluate(`(function(){
    const el = document.querySelector(${JSON.stringify(selector)});
    if (!el) return { ok:false, reason:'not-found' };
    el.scrollIntoView({block:'center'});
    el.click();
    return { ok:true, tag: el.tagName, text: (el.textContent||'').trim().slice(0,60) };
  })()`).then(async (r) => { await sleep(settleMs); return r; });
}

export async function evalPage(browser, expr) {
  return browser.cdp.evaluate(expr);
}

export { sleep, ensureDir, writeFileSync };
