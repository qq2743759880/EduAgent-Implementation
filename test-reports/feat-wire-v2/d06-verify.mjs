/* 缺陷#6 验证：回收站真实列表 + 恢复/彻底删除全生命周期（自建系列，终态=物理删除，无残留） */
import { withBrowser, shot, evalPage, sleep, BASE } from "./evidence-lib.mjs";

const API = "http://127.0.0.1:9988";
const token = process.env.EDU_GATE_TOKEN;
const H = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
const code = "fw2d06" + Date.now().toString().slice(-8);

// ① 建测试系列
const created = await fetch(`${API}/api/admin/courses/series`, {
  method: "POST", headers: H,
  body: JSON.stringify({ institution_id: 1, delivery_mode: "online_live", series_code: code, series_name: "FEAT-WIRE-V2回收站测试" + code, created_by: 100003 }),
}).then((r) => r.json());
const sid = created.data?.id;
console.log("created series:", sid, code);
if (!sid) throw new Error("create failed: " + JSON.stringify(created).slice(0, 200));

// ② 软删（下架）→ 进回收站
const softdel = await fetch(`${API}/api/admin/courses/series/${sid}`, { method: "DELETE", headers: H }).then((r) => r.json());
console.log("soft delete:", softdel.code, softdel.message);

await withBrowser(async (browser) => {
  await browser.navigate(`${BASE}/admin-courses-recycle-proto.html`, 2500);
  // 搜索定位我们的系列（防抖 400ms）
  await evalPage(browser, `(function(){
    var kw=document.getElementById('f-kw'); kw.value='${code}';
    kw.dispatchEvent(new Event('input',{bubbles:true}));
  })()`);
  await sleep(1400);
  const found = await evalPage(browser, `(function(){
    var trs=[...document.querySelectorAll('#tbl-body tr')];
    var tr=trs.find(t=>t.textContent.indexOf('${code}')>=0);
    return { rows: trs.length, hit: !!tr, meta: document.getElementById('meta-count').textContent };
  })()`);
  console.log("bin list after search:", found);
  await shot(browser, "d06-after-list");

  // ③ 恢复流程
  const opened = await evalPage(browser, `(function(){
    var trs=[...document.querySelectorAll('#tbl-body tr')];
    var tr=trs.find(t=>t.textContent.indexOf('${code}')>=0);
    if(!tr) return false;
    tr.querySelector('button.btn-primary').click(); return true;
  })()`);
  await sleep(500);
  const dlg = await evalPage(browser, `document.getElementById('confirm-restore').classList.contains('show')`);
  console.log("restore confirm shown:", opened, dlg);
  await shot(browser, "d06-restore-confirm");
  await evalPage(browser, `doRestore()`);
  await sleep(1500);
  await shot(browser, "d06-restore-done");

  // 恢复后 API 校验：sale_status=draft
  const afterRestore = await fetch(`${API}/api/admin/courses/series/${sid}`, { headers: H }).then((r) => r.json());
  console.log("after restore:", afterRestore.data?.sale_status);

  // ④ 再软删 → 彻底删除两步确认流程
  await fetch(`${API}/api/admin/courses/series/${sid}`, { method: "DELETE", headers: H });
  await sleep(400);
  await evalPage(browser, `(function(){
    var kw=document.getElementById('f-kw'); kw.value='${code}';
    kw.dispatchEvent(new Event('input',{bubbles:true}));
  })()`);
  await sleep(1400);
  await evalPage(browser, `(function(){
    var trs=[...document.querySelectorAll('#tbl-body tr')];
    var tr=trs.find(t=>t.textContent.indexOf('${code}')>=0);
    if(tr) tr.querySelector('button.btn-danger').click();
  })()`);
  await sleep(500);
  await shot(browser, "d06-purge-step1");
  await evalPage(browser, `toPurgeStep2()`);
  await sleep(400);
  // 输入系列编码解锁按钮
  const unlocked = await evalPage(browser, `(function(){
    var i=document.getElementById('purge-code-input'); i.value='${code}';
    i.dispatchEvent(new Event('input',{bubbles:true}));
    return { btnEnabled: !document.getElementById('purge-confirm-btn').disabled,
             echo: document.getElementById('purge-code-echo').textContent };
  })()`);
  console.log("purge step2 unlocked:", unlocked);
  await shot(browser, "d06-purge-step2");
  await evalPage(browser, `doPurge()`);
  await sleep(1800);
  await shot(browser, "d06-purge-done");

  // 硬删后 API 校验：404
  const gone = await fetch(`${API}/api/admin/courses/series/${sid}`, { headers: H }).then((r) => r.json());
  console.log("after hard delete:", gone.code, gone.message);

  // ⑤ 列表实时刷新（自建行已消失）
  const stillThere = await evalPage(browser, `(function(){
    var trs=[...document.querySelectorAll('#tbl-body tr')];
    return trs.filter(t=>t.textContent.indexOf('${code}')>=0).length;
  })()`);
  console.log("row removed from list:", stillThere === 0);
});
