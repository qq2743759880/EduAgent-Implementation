import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";
const stoken = process.env.EDU_GATE_STUDENT_TOKEN;
await withBrowser(async (browser) => {
  await browser.navigate(`${BASE}/practice.html`, 1200);
  await browser.cdp.send("Runtime.evaluate", { expression: `localStorage.setItem("edu:auth:token", ${JSON.stringify(stoken)});` });
  await browser.navigate(`${BASE}/practice.html`, 2500);
  await evalPage(browser, `(function(){var b=document.querySelector('#topic-real .pill[data-ttype="MATCH"]'); if(b) b.click();})()`);
  await sleep(2000);
  await shot(browser, "d07-review-match-scrolled");
  console.log(await evalPage(browser, `({matchGrid: !!document.querySelector('#rvBody .match-grid'), count: document.getElementById('topic-real').querySelector('.count').textContent})`));
});
