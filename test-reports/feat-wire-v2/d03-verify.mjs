/* 缺陷#3 修复后验证：三弹窗弹出 + 编辑/禁用真实接口往返（user000001 禁用→复启用，终态恢复） */
import { withBrowser, shot, click, evalPage, sleep, BASE } from "./evidence-lib.mjs";

const API = "http://127.0.0.1:9988";
const token = process.env.EDU_GATE_TOKEN;

async function apiStatus() {
  const r = await fetch(`${API}/api/admin/users?keyword=redhat777777&page=1&page_size=5`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then((x) => x.json());
  const it = (r.data?.items || [])[0] || {};
  return { status: it.status, user_id: it.user_id, username: it.username };
}

console.log("before:", await apiStatus());

await withBrowser(async (browser) => {
  await browser.navigate(`${BASE}/admin-users.html`, 1600);
  await shot(browser, "d03-after-list");

  // ① 查看
  const v = await click(browser, "#u-body [data-view]");
  const s1 = await evalPage(browser, `({
    shown: document.getElementById('learn-dlg').classList.contains('show'),
    fields: document.querySelectorAll('#learn-fields .sc6').length
  })`);
  console.log("view:", v, s1);
  await shot(browser, "d03-after-view");
  await click(browser, "#learn-dlg [data-close]");

  // ② 编辑弹窗（表单可见）
  const e = await click(browser, "#u-body [data-edit]");
  const s2 = await evalPage(browser, `({
    shown: document.getElementById('edit-dlg').classList.contains('show'),
    roleSel: !!document.getElementById('e-role'),
    segBtns: document.querySelectorAll('#e-status-seg button').length,
    saveBtn: !!document.getElementById('e-save')
  })`);
  console.log("edit:", e, s2);
  await shot(browser, "d03-after-edit");

  // ③ 编辑保存真实调接口：把 user000001 状态切为禁用 → 保存
  // 在页面搜索框过滤出该学生（防抖 400ms）
  await evalPage(browser, `(function(){
    const kw=document.getElementById('f-kw');
    kw.value='redhat777777';
    kw.dispatchEvent(new Event('input',{bubbles:true}));
  })()`);
  await sleep(1200);
  const rowSel = await evalPage(browser, `(function(){
    const trs=[...document.querySelectorAll('#u-body tr')];
    const i=trs.findIndex(tr=>tr.textContent.indexOf('redhat777777')>=0);
    return i>=0?String(i):'';
  })()`);
  if (rowSel === "") throw new Error("redhat777777 not found after search");
  // 先点该行编辑
  const r2 = await click(browser, `#u-body tr:nth-child(${+rowSel+1}) [data-edit]`);
  const seg = await evalPage(browser, `(function(){
    const cur=document.querySelector('#e-status-seg button.on');
    const target=document.querySelector('#e-status-seg button[data-st="'+(cur.getAttribute('data-st')==='1'?'0':'1')+'"]');
    if(target){target.click();}
    return {was:cur.getAttribute('data-st'), now:document.querySelector('#e-status-seg button.on').getAttribute('data-st')};
  })()`);
  console.log("edit row:", r2, "seg switch:", seg);
  await shot(browser, "d03-after-edit-form");
  await click(browser, "#e-save");
  await sleep(1500);
  console.log("after save (API):", await apiStatus());
  await shot(browser, "d03-after-edit-saved");

  // ④ 禁用确认弹窗 + 状态变更真实调接口：此时应为启用→点禁用按钮走 st 流程（若上一步已禁用则此处点启用，反向同证）
  // 上面编辑已把 user000001 设为禁用；现从列表行点「启用」按钮走 st-dlg 确认弹窗（同为状态变更真实接口）
  await sleep(600);
  const toggleLabel = await evalPage(browser, `(function(){
    const trs=[...document.querySelectorAll('#u-body tr')];
    const tr=trs[${+rowSel}];
    const b=tr.querySelector('[data-toggle]');
    return b?b.textContent.trim():'';
  })()`);
  const t2 = await click(browser, `#u-body tr:nth-child(${+rowSel+1}) [data-toggle]`);
  const s4 = await evalPage(browser, `({
    shown: document.getElementById('st-dlg').classList.contains('show'),
    title: document.getElementById('st-title').textContent,
    confirm: !!document.getElementById('st-confirm')
  })`);
  console.log("toggle btn label:", toggleLabel, "click:", t2, "st-dlg:", s4);
  await shot(browser, "d03-after-toggle-confirm");
  await click(browser, "#st-confirm");
  await sleep(1500);
  console.log("after toggle confirm (API):", await apiStatus());
  await shot(browser, "d03-after-toggle-done");

  // ⑤ 关闭后可重开
  const reopen = await click(browser, "#u-body [data-view]");
  const s5 = await evalPage(browser, `document.getElementById('learn-dlg').classList.contains('show')`);
  console.log("reopen after close:", reopen, s5);
});
