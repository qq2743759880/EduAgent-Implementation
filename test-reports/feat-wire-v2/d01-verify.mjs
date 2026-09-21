/* 缺陷#1 验证：admin-course-detail.html 会话管理区「上传视频」入口 → 真实分片管线（≥1MB 文件落 /media/videos 可播放） */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";
import path from "node:path";

const testFile = path.resolve("test-reports/feat-wire-v2/tmp/fw2-d01-test.mp4");

await withBrowser(async (browser) => {
  const cdp = browser.cdp;
  await browser.navigate(`${BASE}/admin-course-detail.html?id=1`, 3000);
  await shot(browser, "d01-page-loaded");

  // 课次表已渲染？找第一行课次的「⬆ 上传视频」按钮
  const found = await evalPage(browser, `(function(){
    var btn=document.querySelector('[data-upl]');
    if(!btn) return {ok:false, reason:'no upload button'};
    var tr=btn.closest('tr');
    return {ok:true, sid:+btn.getAttribute('data-upl'), title:(tr.querySelector('.cell-strong')||{}).textContent};
  })()`);
  console.log("upload button:", found);
  if (!found.ok) throw new Error("upload button not found");

  // 点击「⬆ 上传视频」
  await evalPage(browser, `document.querySelector('[data-upl]').click()`);
  await sleep(1000);
  const panel = await evalPage(browser, `({
    visible: document.getElementById('video-panel').style.display!=='none',
    title: document.getElementById('vpTitle').textContent.slice(0,40),
    dropzone: !!document.getElementById('up-z')
  })`);
  console.log("video panel:", panel);
  await shot(browser, "d01-panel-open");

  // CDP 设置文件（真实 input#videoFile → onchange → startUpload）
  const doc = await cdp.send("DOM.getDocument");
  const node = await cdp.send("DOM.querySelector", { nodeId: doc.root.nodeId, selector: "#videoFile" });
  await cdp.send("DOM.setFileInputFiles", { files: [testFile], nodeId: node.nodeId });
  console.log("file set:", testFile);

  // 轮询上传状态（stepper + timeline + 转码徽章）
  let done = false;
  for (let i = 0; i < 40 && !done; i++) {
    await sleep(3000);
    const st = await evalPage(browser, `({
      steps: [...document.querySelectorAll('.stp')].map(s=>s.className.replace('stp ','')),
      tl: [...document.querySelectorAll('#timeline .tl-item .tt')].map(x=>x.textContent),
      tc: document.getElementById('tc-badge').textContent.trim(),
      err: document.getElementById('upErr').style.display==='block'?document.getElementById('upErr').textContent:''
    })`);
    console.log((i+1)*3 + "s:", JSON.stringify(st).slice(0, 220));
    await shot(browser, "d01-upload-progress");
    if (st.err) throw new Error("upload error: " + st.err);
    if (st.tl.some((t) => t === "转码") || st.tc.includes("完成") || st.tc.includes("失败")) done = true;
  }

  // 最终视频列表 + file_url
  const final = await evalPage(browser, `(function(){
    var v=document.querySelector('#videoList div');
    return {listText: document.getElementById('videoList').textContent.slice(0,200),
            link: (document.querySelector('#videoList a')||{}).href||null};
  })()`);
  console.log("final video list:", final);
  await shot(browser, "d01-upload-final");

  // 验证 file_url 可访问（200 + video content-type + 字节数）
  if (final.link) {
    const head = await fetch(final.link, { method: "HEAD" });
    console.log("file_url HEAD:", final.link, head.status, head.headers.get("content-type"), head.headers.get("content-length"));
  }
});
