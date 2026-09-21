/* 缺陷#11 E2E：会话A自述→提取落库→新建会话B问答对（CDP 实测） */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";

const stoken = process.env.EDU_GATE_STUDENT_TOKEN;
const NAME = "fw2小明" + Date.now().toString().slice(-4);

async function ask(browser, text, waitMs) {
  await evalPage(browser, `(function(){
    const inp=document.getElementById('composerInput');
    inp.value=${JSON.stringify(text)};
    document.getElementById('sendBtn').click();
  })()`);
  // 等回答完成（发送按钮恢复 + 无思考指示），上限 waitMs
  let t = 0, last = "";
  while (t < waitMs) {
    await sleep(800); t += 800;
    const s = await evalPage(browser, `({
      thinking: (document.getElementById('aiResp')||{textContent:''}).textContent.indexOf('思考中')>=0,
      streaming: document.getElementById('sendBtn').disabled
    })`);
    if (!s.thinking && !s.streaming && t > 2000) break;
  }
  last = await evalPage(browser, `(document.getElementById('aiResp')||{textContent:''}).textContent`);
  return last;
}

await withBrowser(async (browser) => {
  await browser.navigate(`${BASE}/chat.html`, 1200);
  await browser.cdp.send("Runtime.evaluate", { expression: `localStorage.setItem("edu:auth:token", ${JSON.stringify(stoken)});` });
  await browser.navigate(`${BASE}/chat.html`, 2500);

  // ① 会话A：新建并自述
  await evalPage(browser, `document.getElementById('sideNew').click()`);
  await sleep(1200);
  const ansA = await ask(browser, `我叫${NAME}，请记住我的名字`, 60000);
  console.log("session A answer:", ansA.slice(0, 120));
  await shot(browser, "d11-session-a");

  // ② 等异步记忆提取（worker 消费队列）
  console.log("waiting for memory extraction…");
  await sleep(55000);  // 提取链路实测 ~40s 落库（队列+LLM 抽取窗口）

  // ③ 会话B：新建并问名字
  await evalPage(browser, `document.getElementById('sideNew').click()`);
  await sleep(1200);
  const ansB = await ask(browser, `我叫什么名字？`, 60000);
  console.log("session B answer:", ansB.slice(0, 160));
  await shot(browser, "d11-session-b");
  console.log("RECALL_HIT:", ansB.includes(NAME));
});
