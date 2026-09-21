/* 缺陷#3 复现：admin-users.html 查看/编辑/禁用 三弹窗现状（修复前取证） */
import { withBrowser, shot, click, evalPage, sleep, BASE } from "./evidence-lib.mjs";

const url = `${BASE}/admin-users.html`;
await withBrowser(async (browser) => {
  await browser.navigate(url, 1600);
  const list = await evalPage(browser, `document.querySelectorAll('#u-body tr').length`);
  console.log("rows:", list);
  await shot(browser, "d03-before-list");

  for (const [label, sel, dlg] of [
    ["view", "[data-view]", "#learn-dlg"],
    ["edit", "[data-edit]", "#edit-dlg"],
    ["toggle", "[data-toggle]", "#st-dlg"],
  ]) {
    const r = await click(browser, `#u-body ${sel}`);
    const state = await evalPage(browser, `({
      dlgShown: !!document.querySelector(${JSON.stringify(dlg)}) && document.querySelector(${JSON.stringify(dlg)}).classList.contains('show'),
      maskShown: document.querySelector('.mask.show') ? true : false,
      bodyRows: document.querySelectorAll('#u-body tr').length
    })`);
    console.log(label, "click:", r, "dialog:", state);
    await shot(browser, `d03-before-${label}`);
    // 关闭后再试下一个
    await click(browser, `${dlg} [data-close]`);
    const closed = await evalPage(browser, `document.querySelectorAll('.dialog.show,.mask.show').length`);
    console.log(label, "closed remnant:", closed);
  }
});
