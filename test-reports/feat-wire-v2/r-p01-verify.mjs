/* REWORK P0-1+P0-2 验收：A 会话自述→done 帧带 memorized+反馈条→B 会话 5 秒内问答对 */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";

const stoken = process.env.EDU_GATE_STUDENT_TOKEN;
const NAME = "返工验收员" + Date.now().toString().slice(-4);

async function ask(browser, text) {
  const t0 = Date.now();
  await evalPage(browser, `(function(){
    const inp=document.getElementById('composerInput');
    inp.value=${JSON.stringify(text)};
    document.getElementById('sendBtn').click();
  })()`);
  let t = 0, last = "", memoBar = false;
  while (t < 60000) {
    await sleep(600); t += 600;
    const s = await evalPage(browser, `({
      thinking: (document.getElementById('aiResp')||{textContent:''}).textContent.indexOf('思考中')>=0,
      streaming: document.getElementById('sendBtn').disabled,
      memoBar: !!document.querySelector('#aiResp .memo-bar'),
      memoText: (document.querySelector('#aiResp .memo-bar')||{textContent:''}).textContent
    })`);
    memoBar = s.memoBar;
    if (!s.thinking && !s.streaming && t > 2000) { last = s; break; }
  }
  const ans = await evalPage(browser, `(function(){
    const bars = document.querySelectorAll('#aiResp .memo-bar');
    const b = bars.length ? bars[bars.length-1].textContent : '';
    const ai = document.getElementById('aiResp');
    return { text: ai ? ai.textContent : '', memo: b, doneMs: Date.now()-${t0} };
  })()`);
  return ans;
}

await withBrowser(async (browser) => {
  await browser.navigate(`${BASE}/chat.html`, 1200);
  await browser.cdp.send("Runtime.evaluate", { expression: `localStorage.setItem("edu:auth:token", ${JSON.stringify(stoken)});` });
  await browser.navigate(`${BASE}/chat.html`, 2500);

  // A 会话：自述新名字
  await evalPage(browser, `document.getElementById('sideNew').click()`);
  await sleep(1200);
  const a = await ask(browser, `我叫${NAME}，请记住我的名字`);
  console.log(`A done in ${a.doneMs}ms | memo-bar: ${JSON.stringify(a.memo).slice(0, 120)}`);
  await shot(browser, "r-p01-session-a-memobar");

  // B 会话：5 秒内问
  await evalPage(browser, `document.getElementById('sideNew').click()`);
  await sleep(1000);
  const gapStart = Date.now();
  const b = await ask(browser, `我叫什么名字？`);
  const gap = ((Date.now() - gapStart) / 1000).toFixed(1);
  console.log(`A→B 间隔 ${gap}s | B 答: ${b.text.slice(0, 150)}`);
  await shot(browser, "r-p01-session-b-5s");
  console.log(`RECALL_HIT(${NAME}):`, b.text.includes(NAME), `| ≤5s 窗口: ${gap <= 5}`);
});
