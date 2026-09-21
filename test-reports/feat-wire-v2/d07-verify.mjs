/* 缺陷#7 验证：practice.html 学生态 选题型→复习会话真实加载对应题型 */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";

const API = "http://127.0.0.1:9988";
const stoken = process.env.EDU_GATE_STUDENT_TOKEN;

await withBrowser(async (browser) => {
  // 以学生身份注入 token（createBrowser 读 EDU_GATE_TOKEN，故此处手动写 localStorage）
  await browser.navigate(`${BASE}/practice.html`, 1500);
  await browser.cdp.send("Runtime.evaluate", {
    expression: `localStorage.setItem("edu:auth:token", ${JSON.stringify(stoken)});`,
  });
  await browser.navigate(`${BASE}/practice.html`, 2500);
  await shot(browser, "d07-practice-loaded");

  const boot = await evalPage(browser, `({
    wbRealVisible: !document.getElementById('wb-real').classList.contains('hid'),
    topicVisible: !document.getElementById('topic-real').classList.contains('hid'),
    demoHidden: document.getElementById('wbDemoPanel').style.display === 'none',
    wbRows: document.querySelectorAll('#wrongTbody tr').length,
    wbCount: document.getElementById('wbCount').textContent,
    statWrong: document.getElementById('statWrong').textContent
  })`);
  console.log("practice boot:", boot);

  // 点「多选」题型 pill → 复习会话应加载 MULTI 题
  await evalPage(browser, `(function(){
    var b=document.querySelector('#topic-real .pill[data-ttype="MULTI"]'); if(b) b.click();
  })()`);
  await sleep(1800);
  const rv1 = await evalPage(browser, `({
    visible: !document.getElementById('review-real').classList.contains('hid'),
    text: document.getElementById('rvBody').textContent.slice(0, 150)
  })`);
  console.log("MULTI review:", rv1);
  await shot(browser, "d07-review-multi");

  // 点「连线匹配」pill → 应加载 MATCH 题
  await evalPage(browser, `(function(){
    var b=document.querySelector('#topic-real .pill[data-ttype="MATCH"]'); if(b) b.click();
  })()`);
  await sleep(1800);
  const rv2 = await evalPage(browser, `({
    hasMatchGrid: !!document.querySelector('#rvBody .match-grid'),
    text: document.getElementById('rvBody').textContent.slice(0, 120)
  })`);
  console.log("MATCH review:", rv2);
  await shot(browser, "d07-review-match");

  // 错题本「重做」入口（无题型）：应加载到期错题（SINGLE）
  await evalPage(browser, `(function(){
    var b=document.querySelector('[data-wredo]'); if(b) b.click();
  })()`);
  await sleep(1800);
  const rv3 = await evalPage(browser, `({
    hasOptions: !!document.querySelector('#rvBody .options'),
    text: document.getElementById('rvBody').textContent.slice(0, 120)
  })`);
  console.log("wrong-book redo:", rv3);
  await shot(browser, "d07-review-wrongredo");
});
