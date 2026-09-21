/* 缺陷#2 复现/验证：q-form 弹窗三路关闭（×/ESC/遮罩）。用法：node d02-modal.mjs before|after */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";

const phase = process.argv[2] || "before";
await withBrowser(async (browser) => {
  await browser.navigate(`${BASE}/admin-questions.html`, 2000);
  // 打开编辑题目弹窗（q-form）
  const opened = await evalPage(browser, `(function(){
    window.openQForm && window.openQForm();
    return !!document.querySelector('#q-form.show');
  })()`);
  console.log("q-form opened:", opened);
  await shot(browser, `d02-${phase}-open`);

  const probe = () => evalPage(browser, `document.querySelectorAll('.scrim.show').length`);

  // ① × 按钮
  await evalPage(browser, `document.querySelector('#q-form .m-close').click()`);
  await sleep(400);
  const afterX = await probe();
  console.log("after X click, open scrims:", afterX);
  await shot(browser, `d02-${phase}-after-x`);

  // ② ESC（若 × 已关则重开）
  if (afterX === 0) { await evalPage(browser, `window.openQForm()`); await sleep(200); }
  await browser.cdp.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await browser.cdp.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
  await sleep(400);
  const afterEsc = await probe();
  console.log("after ESC, open scrims:", afterEsc);
  await shot(browser, `d02-${phase}-after-esc`);

  // ③ 遮罩空白点击（重开后点 scrim 自身：坐标 8,8 处必为遮罩区域）
  if (afterEsc === 0) { await evalPage(browser, `window.openQForm()`); await sleep(200); }
  await browser.cdp.send("Input.dispatchMouseEvent", { type: "mousePressed", x: 8, y: 8, button: "left", clickCount: 1 });
  await browser.cdp.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: 8, y: 8, button: "left", clickCount: 1 });
  await sleep(400);
  const afterMask = await probe();
  console.log("after backdrop click, open scrims:", afterMask);
  await shot(browser, `d02-${phase}-after-backdrop`);

  // ④ 关闭后可重开
  const reopened = await evalPage(browser, `(function(){
    var scrims=document.querySelectorAll('.scrim.show').length;
    window.openQForm();
    return { wasOpen: scrims, reopened: !!document.querySelector('#q-form.show') };
  })()`);
  console.log("reopen check:", reopened);
  if (phase === "after") await shot(browser, "d02-after-reopen");
});
