// TB3 诊断：抓取 G7 实际读到的 backgroundColor，定位 contrast-4.5 误报根因。
import { createBrowser } from "../../scripts/gates/_shared.mjs";

const TOKEN = process.env.EDU_GATE_TOKEN;

const browser = await createBrowser({ token: TOKEN, base: "http://127.0.0.1:3322" });
try {
  await browser.navigate("http://127.0.0.1:3322/admin-infra.html", 2500);
  await browser.setViewport(1280, 900);

  const out = await browser.cdp.send("Runtime.evaluate", {
    returnByValue: true,
    expression: `(() => {
      const pick = (sel) => {
        const el = document.querySelector(sel);
        if (!el) return { sel, missing: true };
        const cs = getComputedStyle(el);
        return { sel, bg: cs.backgroundColor, color: cs.color, tag: el.tagName, cls: el.className };
      };
      // rebuild the gate's backgroundFor stack for #k-rl-hits
      const target = document.getElementById('k-rl-hits');
      const stack = [];
      let n = target;
      while (n && n.nodeType === 1) { stack.push(n.tagName + (n.id ? '#'+n.id : '') + (n.className ? '.'+String(n.className).split(' ').join('.') : '') + ' => ' + getComputedStyle(n).backgroundColor); n = n.parentElement; }
      return {
        probes: [
          pick('body'),
          pick('body.admin-html-page'),
          pick('.page'),
          pick('.metric'),
          pick('#k-rl-hits'),
          pick('.card'),
          pick('.note'),
        ],
        stack,
      };
    })()`,
  });

  console.log(JSON.stringify(out.result.value, null, 1));
} finally {
  await browser.close();
}
