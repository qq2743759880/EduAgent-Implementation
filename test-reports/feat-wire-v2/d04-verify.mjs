/* 缺陷#4 验证：RAG 五 tab 切换 + 各面板真实数据（CDP） */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";

await withBrowser(async (browser) => {
  await browser.navigate(`${BASE}/admin-rag-upload.html`, 2000);
  await shot(browser, "d04-tab-upload-default");

  const switchTab = async (name) => {
    await evalPage(browser, `(function(){var b=document.querySelector('.tabs .tab[data-tab="${name}"]'); if(b){b.click(); return true;} return false;})()`);
    await sleep(1400);
    return evalPage(browser, `({
      panelVisible: !document.getElementById('rag-panel-${name}').classList.contains('hidden'),
      tabOn: document.querySelector('.tabs .tab.on').textContent.trim(),
      othersHidden: ${JSON.stringify(["collections","upload","presets","audit","search"])}.filter(function(n){return n!=='${name}' && !document.getElementById('rag-panel-'+n).classList.contains('hidden');})
    })`);
  };

  // ① 集合
  console.log("collections:", await switchTab("collections"));
  console.log("col rows:", await evalPage(browser, `document.querySelectorAll('#ragColBody tr').length + ' | first=' + (document.querySelector('#ragColBody tr td')||{}).textContent`));
  await shot(browser, "d04-tab-collections");

  // ② 调参
  console.log("presets:", await switchTab("presets"));
  console.log("preset rows:", await evalPage(browser, `document.querySelectorAll('#ragPresetBody tr').length`));
  await shot(browser, "d04-tab-presets");

  // ③ 审计日志
  console.log("audit:", await switchTab("audit"));
  console.log("audit:", await evalPage(browser, `({rows: document.querySelectorAll('#ragAuditBody tr').length, cnt: document.getElementById('ragAuditCnt').textContent})`));
  await shot(browser, "d04-tab-audit");
  // 翻页
  await evalPage(browser, `document.getElementById('ragAuditNext').click()`);
  await sleep(1000);
  console.log("audit page2:", await evalPage(browser, `({cnt: document.getElementById('ragAuditCnt').textContent, pageBtn: document.getElementById('ragAuditPageBtn').textContent})`));

  // ④ 高级检索（真实 POST search）
  console.log("search:", await switchTab("search"));
  await evalPage(browser, `(function(){
    var q=document.getElementById('ragSQuery'); q.value='向量检索';
    document.getElementById('ragSBtn').click();
  })()`);
  await sleep(3000);
  console.log("search res:", await evalPage(browser, `({
    text: document.getElementById('ragSRes').textContent.slice(0,80),
    docCards: document.querySelectorAll('#ragSRes .doc-card').length,
    firstScore: (document.querySelector('.doc-card .dc-score')||{}).textContent
  })`));
  await shot(browser, "d04-tab-search");

  // ⑤ 回上传 tab 仍可用
  console.log("upload back:", await switchTab("upload"));
});
