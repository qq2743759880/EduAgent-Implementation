/* 缺陷#12 验证：learning.html 大纲节点展开/收起 + 标记完成真实写入（学生态） */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";

const stoken = process.env.EDU_GATE_STUDENT_TOKEN;
// 学生已报名班次：从 enrollments 接口取第一个（脚本外已确认 user000001 有报名）
const URLQ = process.env.D12_URL || `${BASE}/learning.html?cohort_id=1&series_id=1`;

await withBrowser(async (browser) => {
  await browser.navigate(`${BASE}/learning.html`, 1200);
  await browser.cdp.send("Runtime.evaluate", { expression: `localStorage.setItem("edu:auth:token", ${JSON.stringify(stoken)});` });
  await browser.navigate(URLQ, 3500);

  const boot = await evalPage(browser, `({
    accCount: document.querySelectorAll('#sylBody .acc').length,
    openCount: document.querySelectorAll('#sylBody .acc.open').length,
    headCnt: document.getElementById('sylCnt') ? document.getElementById('sylCnt').textContent : '',
    sessionRows: document.querySelectorAll('#sylBody .session').length
  })`);
  console.log("outline boot:", boot);
  if (!boot.accCount) throw new Error("outline empty — check cohort/series params");

  // 找一个未展开的模块点击 → 应展开
  const before = await evalPage(browser, `(function(){
    const accs=[...document.querySelectorAll('#sylBody .acc')];
    const target=accs.find(a=>!a.classList.contains('open')) || accs[0];
    if(!target) return null;
    target.querySelector('.acc-head').click();
    return { wasOpen: target.classList.contains('open') };
  })()`);
  await sleep(400);
  const after = await evalPage(browser, `(function(){
    const accs=[...document.querySelectorAll('#sylBody .acc')];
    const opened=[...document.querySelectorAll('#sylBody .acc.open')];
    const head=opened.length?opened[0].querySelector('.acc-head'):null;
    return { openCount: opened.length,
      aria: head?head.getAttribute('aria-expanded'):null,
      ind: head?head.querySelector('.acc-ind').textContent:null };
  })()`);
  console.log("click expand:", before, "->", after);
  await shot(browser, "d12-outline-expanded");

  // 再点一次 → 收起
  const collapse = await evalPage(browser, `(function(){
    const opened=document.querySelector('#sylBody .acc.open');
    if(!opened) return null;
    opened.querySelector('.acc-head').click();
    return { wasOpen: true };
  })()`);
  await sleep(400);
  const closed = await evalPage(browser, `document.querySelectorAll('#sylBody .acc.open').length`);
  console.log("click collapse:", collapse, "-> openCount:", closed);
  await shot(browser, "d12-outline-collapsed");

  // 标记完成（真实写入）：回到一个课次，点标记完成按钮
  const sessUrl = await evalPage(browser, `(function(){
    const a=document.querySelector('#sylBody .session');
    return a?a.getAttribute('href'):null;
  })()`);
  if (sessUrl) {
    await browser.navigate(`${BASE}/${sessUrl}`, 3000);
    const cbtn = await evalPage(browser, `(function(){
      const b=document.getElementById('realCompleteBtn');
      if(!b) return {ok:false};
      b.click(); return {ok:true};
    })()`);
    await sleep(1500);
    const flag = await evalPage(browser, `document.getElementById('doneFlag') ? document.getElementById('doneFlag').textContent : ''`);
    console.log("complete click:", cbtn, "flag:", flag);
    await shot(browser, "d12-complete");
  }
});
