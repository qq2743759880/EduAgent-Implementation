/* 缺陷#9/#10 验证：chat.html 连续 5 轮问答——流式渐进渲染（打字机）+ done 后零思考指示器残留 */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";

const stoken = process.env.EDU_GATE_STUDENT_TOKEN;
const QUESTIONS = [
  "用一句话解释什么是向量检索",
  "1+1 等于几？只回答数字",
  "说一个学习 Python 的建议",
  "什么是错题本？",
  "用一句话打个招乎",
];

await withBrowser(async (browser) => {
  await browser.navigate(`${BASE}/chat.html`, 1200);
  await browser.cdp.send("Runtime.evaluate", { expression: `localStorage.setItem("edu:auth:token", ${JSON.stringify(stoken)});` });
  await browser.navigate(`${BASE}/chat.html`, 2500);

  const boot = await evalPage(browser, `({
    sessions: document.querySelectorAll('#sideList .sess').length,
    firstTitle: (document.querySelector('#sideList .sess .t')||{}).textContent
  })`);
  console.log("chat boot:", boot);
  await shot(browser, "d09-chat-boot");

  let progressiveRounds = 0, residueRounds = 0;
  for (let i = 0; i < QUESTIONS.length; i++) {
    const q = QUESTIONS[i];
    await evalPage(browser, `(function(){
      const inp=document.getElementById('composerInput');
      inp.value=${JSON.stringify(q)};
      document.getElementById('sendBtn').click();
    })()`);
    // 采样流式长度：0.4s 间隔，直到流结束（发送按钮恢复可用）最长 60s
    const samples = [];
    let t = 0, done = false;
    while (t < 60000 && !done) {
      await sleep(400); t += 400;
      const s = await evalPage(browser, `({
        len: (document.getElementById('aiResp')||{textContent:''}).textContent.length,
        thinking: (document.getElementById('aiResp')||{textContent:''}).textContent.indexOf('思考中')>=0,
        streaming: document.getElementById('sendBtn').disabled
      })`);
      samples.push(s.len);
      if (s.len > 0 && !s.thinking && !s.streaming && t > 1500) done = true;
      if (s.thinking && !s.streaming && t > 8000) { done = true; } // 异常态兜底退出
    }
    const final = await evalPage(browser, `({
      len: (document.getElementById('aiResp')||{textContent:''}).textContent.length,
      thinking: (document.getElementById('aiResp')||{textContent:''}).textContent.indexOf('思考中')>=0,
      err: (document.querySelector('#aiResp .md-err')||{}).textContent || ''
    })`);
    // 渐进渲染判定：采样序列中出现 ≥2 个不同长度且递增（打字机）
    const uniq = [...new Set(samples.filter(x => x > 0))];
    const grew = uniq.length >= 2 && uniq[uniq.length - 1] > uniq[0];
    if (grew) progressiveRounds++;
    if (final.thinking) residueRounds++;
    console.log(`round ${i + 1}: q="${q}" samples=[${samples.slice(0, 12).join(",")}${samples.length > 12 ? "…" : ""}] grew=${grew} final=${JSON.stringify(final)}`);
    if (i === 0) await shot(browser, "d10-stream-round1");
  }
  await shot(browser, "d09-after-5rounds");
  console.log(`SUMMARY: progressiveRounds=${progressiveRounds}/5 residueRounds=${residueRounds}/5`);
  if (residueRounds > 0) throw new Error("思考指示器残留 " + residueRounds + " 轮");
});
