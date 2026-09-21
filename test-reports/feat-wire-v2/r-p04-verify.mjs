/* REWORK P0-4 验收：≥100MB 全链 + 中途断片失败注入 → 重试 UI → 恢复成功 */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";
import path from "node:path";

const testFile = path.resolve("test-reports/feat-wire-v2/tmp/fw2-rwk-big.mp4");
const SIZE_MB = 114069910 / 1024 / 1024;

await withBrowser(async (browser) => {
  const cdp = browser.cdp;
  await browser.navigate(`${BASE}/admin-course-detail.html?id=1`, 3000);

  // 打开视频面板（等课次表渲染后点「⬆ 上传视频」）
  let uplReady = false;
  for (let i = 0; i < 15; i++) {
    uplReady = await evalPage(browser, `!!document.querySelector('[data-upl]')`);
    if (uplReady) break;
    await sleep(1000);
  }
  if (!uplReady) throw new Error("课次上传按钮未渲染（模块/课次链未加载）");
  await evalPage(browser, `document.querySelector('[data-upl]').click()`);
  await sleep(1200);

  // ============ 阶段1：注入失败（阻断分片 PUT）→ 自动重试 → 重试按钮出现 ============
  await cdp.send("Network.setBlockedURLs", { urls: ["*upload-chunk*"] });
  const doc = await cdp.send("DOM.getDocument");
  const node = await cdp.send("DOM.querySelector", { nodeId: doc.root.nodeId, selector: "#videoFile" });
  await cdp.send("DOM.setFileInputFiles", { files: [testFile], nodeId: node.nodeId });
  console.log("file set (blocked mode):", SIZE_MB.toFixed(1) + "MB");

  // 等失败链走完（20 分片 × 3 次 PUT 全被阻断，本地快速失败）
  let err = "", retryBtn = false;
  for (let i = 0; i < 40; i++) {
    await sleep(1500);
    const st = await evalPage(browser, `({
      err: document.getElementById('upErr').style.display==='block'?document.getElementById('upErr').textContent:'',
      retry: !!document.getElementById('upRetry'),
      tlBad: [...document.querySelectorAll('#timeline .tl-item.bad')].length
    })`);
    err = st.err; retryBtn = st.retry;
    if (retryBtn) { console.log(`inject-phase: err="${err.slice(0, 80)}" retryBtn=${retryBtn} tlBad=${st.tlBad}`); break; }
  }
  await shot(browser, "r-p04-fail-retry-ui");
  if (!retryBtn) throw new Error("失败注入后重试按钮未出现");
  console.log("阶段1 ✓ 断片注入 → 错误态+可重试 UI");

  // ============ 阶段2：解除阻断 → 点重试 → 整链重传成功 ============
  await cdp.send("Network.setBlockedURLs", { urls: [] });
  await evalPage(browser, `document.getElementById('upRetry').click()`);
  console.log("retry clicked (unblocked)");

  let done = false;
  for (let i = 0; i < 60 && !done; i++) {
    await sleep(4000);
    const st = await evalPage(browser, `({
      steps: [...document.querySelectorAll('.stp')].map(s=>s.className.replace('stp ','')),
      tl: [...document.querySelectorAll('#timeline .tl-item .tt')].map(x=>x.textContent),
      tc: document.getElementById('tc-badge').textContent.trim(),
      err: document.getElementById('upErr').style.display==='block'?document.getElementById('upErr').textContent:'',
      pct: document.getElementById('upMetaR') ? document.getElementById('upMetaR').textContent : ''
    })`);
    console.log(`retry ${(i+1)*4}s: pct=${st.pct} tc=${st.tc} tl=${st.tl.join(",")} err=${st.err.slice(0,60)}`);
    await shot(browser, "r-p04-retry-progress");
    if (st.err) throw new Error("重试仍失败: " + st.err);
    if (st.tl.some((t) => t === "转码") || st.tc.includes("完成") || st.tc.includes("失败")) { done = true; await shot(browser, "r-p04-retry-done"); }
  }

  const final = await evalPage(browser, `(function(){
    const first=document.querySelector('#videoList a');
    return { link: first ? first.href : null, list: document.getElementById('videoList').textContent.slice(0,120) };
  })()`);
  console.log("final:", JSON.stringify(final).slice(0, 300));
  if (final.link) {
    const head = await fetch(final.link, { method: "HEAD" });
    console.log("same-origin HEAD:", head.status, head.headers.get("content-type"), head.headers.get("content-length"));
  }
});
