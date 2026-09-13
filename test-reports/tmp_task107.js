
/* ===== 真实接入：admin-questions 对接 /api/admin/questions（task107）=====
 * 契约见页头注释（均已 curl 实测）。首期新建/编辑仅 SINGLE(1)/MULTI(2)/JUDGE(3)，其余题型只读展示。
 * 无 token 静默降级：提示 admin 账号，不发任何请求。注入不重定义全局 $ / renderSides。 */
(function(){
  if(!window.EAPI) return;
  var qs=function(id){ return document.getElementById(id); };
  var esc=function(s){ var d=document.createElement("div"); d.textContent=(s==null?"":String(s)); return d.innerHTML; };
  var PAGE_SIZE=10;
  var state={ bankPage:1,qPage:1,curBank:null,typeMap:{},currentBanks:[],currentQuestions:[],qEditId:null,editOpts:null,importItems:null };

  /* ---- token 闸门：无 token 提示 admin 账号，不发任何请求 ---- */
  if(!EAPI.store.getToken()){
    var sub=document.querySelector(".page-head .sub");
    if(sub && sub.textContent.indexOf("admin 账号")<0) sub.textContent="⚠ 请用 admin 账号登录（adm02test / Test@123456）后刷新本页";
    qs("bank-body").innerHTML=""; qs("q-body").innerHTML="";
    var bc=qs("bank-count"); if(bc) bc.textContent="0";
    return;
  }
  /* 隐藏演示控制器（审核用，非产物） */
  var demo=document.querySelector(".demo-ctrl"); if(demo) demo.style.display="none";

  function toast(m){ var d=document.createElement("div"); d.className="toast-stub"; d.textContent=m; document.body.appendChild(d); setTimeout(function(){ d.remove(); },3000); }
  function closeModals(){ document.querySelectorAll(".scrim.show").forEach(function(x){ x.classList.remove("show"); }); }
  function setState3(n1,a1,n2,a2,n3,a3){ qs(n1).classList.toggle("hidden",!a1); qs(n2).classList.toggle("hidden",!a2); qs(n3).classList.toggle("hidden",!a3); }
  function typeName(id){ var t=state.typeMap[id]; return t?t.type_name:("#"+id); }
  function typeObj(id){ var t=state.typeMap[id]; return !!(t&&t.objective_flag); }

  /* ---- 题型维表（GET types） —— 用于题型名/客观徽章/题型筛选 ---- */
  function loadTypes(){
    return EAPI.get("/api/admin/questions/types").then(function(d){
      var items=(d&&d.items)||[], map={};
      items.forEach(function(t){ map[t.id]=t; }); state.typeMap=map;
      var sel=qs("f-q-type");
      if(sel&&items.length){ sel.innerHTML='<option value="">全部题型</option>'+items.map(function(t){ return '<option value="'+t.id+'">'+esc(t.type_name)+'</option>'; }).join(""); }
      return map;
    }).catch(function(){ return state.typeMap; });
  }

  /* ---- 题库列表（GET banks） ---- */
  function loadBanks(page){
    page=page||1; state.bankPage=page;
    var kw=(qs("f-bank-kw")?qs("f-bank-kw").value.trim():"");
    var url="/api/admin/questions/banks?page="+page+"&page_size="+PAGE_SIZE;
    if(kw) url+="&keyword="+encodeURIComponent(kw);
    return EAPI.get(url).then(function(d){
      var items=(d&&d.items)||[], total=(d&&d.total)||0;
      state.currentBanks=items;
      qs("bank-count").textContent=total;
      if(!items.length){ qs("bank-body").innerHTML=""; setState3("bank-empty",true,"bank-error",false,"bank-pager",false); return; }
      setState3("bank-empty",false,"bank-error",false,"bank-pager",true);
      qs("bank-body").innerHTML=items.map(bankTr).join("");
      qs("bank-pager").innerHTML=pagerHTML("bankPage",page,total);
      qs("bank-pager").onclick=function(e){ var k=e.target.closest("button[data-bkpg]"); if(k) loadBanks(+k.getAttribute("data-bkpg")); };
    }).catch(function(err){ qs("bank-err-msg").textContent=(err&&err.message)||"后端不可用"; setState3("bank-empty",false,"bank-error",true,"bank-pager",false); });
  }
  function bankTr(b){
    var status=b.yn?'<span class="badge badge-on"><span class="pd"></span>启用</span>':'<span class="badge badge-mut"><span class="pd"></span>停用</span>';
    return '<tr class="hov"><td><div class="prim-cell"><div class="ico" style="background:linear-gradient(120deg,var(--primary-deep),var(--primary))">📚</div><div><div class="nm">'+esc(b.bank_name)+'</div><div class="cd">'+esc(b.bank_code)+' · institution#'+b.institution_id+'</div></div></div></td><td><span class="tag-chips">分类 #'+b.category_id+'</span></td><td class="nb">'+b.id+'</td><td>'+status+'</td><td class="cell-actions" style="justify-content:flex-end"><button class="btn btn-primary btn-mini" data-manage-bank="'+b.id+'">管理</button></td></tr>';
  }
  function findBank(id){ for(var i=0;i<state.currentBanks.length;i++){ if(state.currentBanks[i].id===id) return state.currentBanks[i]; } return null; }

  /* ---- 题目列表（GET banks/{id}/questions），按题型/关键词过滤 ---- */
  function selectBank(b){ state.curBank=b; state.qPage=1; var tip=qs("tab-q-bank"); if(tip){ tip.style.display="inline"; tip.textContent="· "+b.bank_name; } qs("q-cur-bank").textContent=b.bank_name+"（"+b.bank_code+"）"; switchTab("questions"); }
  function switchTab(t){
    document.querySelectorAll(".tab").forEach(function(x){ x.classList.toggle("on", x.getAttribute("data-tab")===t); });
    qs("pane-banks").classList.toggle("hidden", t!=="banks");
    qs("pane-questions").classList.toggle("hidden", t!=="questions");
    if(t==="questions"&&state.curBank) loadQuestions(state.qPage);
  }
  function loadQuestions(page){
    page=page||1; state.qPage=page;
    if(!state.curBank){ qs("q-body").innerHTML=""; qs("q-count").textContent="0"; qs("q-pager").innerHTML=""; setState3("q-none",true,"q-empty",false,"q-error",false); return; }
    var url="/api/admin/questions/banks/"+state.curBank.id+"/questions?page="+page+"&page_size="+PAGE_SIZE;
    var tv=qs("f-q-type")?qs("f-q-type").value:""; if(tv) url+="&question_type_id="+tv;
    var kwv=qs("f-q-kw")?qs("f-q-kw").value.trim():""; if(kwv) url+="&keyword="+encodeURIComponent(kwv);
    return EAPI.get(url).then(function(d){
      var items=(d&&d.items)||[], total=(d&&d.total)||0;
      state.currentQuestions=items;
      qs("q-count").textContent=total;
      setState3("q-none",false,"q-empty",!items.length,"q-error",false);
      qs("q-body").innerHTML=items.map(qTr).join("");
      qs("q-pager").innerHTML=pagerHTML("qPage",page,total);
      qs("q-pager").onclick=function(e){ var k=e.target.closest("button[data-qpg]"); if(k) loadQuestions(+k.getAttribute("data-qpg")); };
    }).catch(function(){ setState3("q-none",false,"q-empty",false,"q-error",true); });
  }
  function qTr(q){
    var obj=typeObj(q.question_type_id);
    var objBadge=obj?'<span class="badge badge-obj"><span class="pd"></span>客观</span>':'<span class="badge badge-subj"><span class="pd"></span>主观</span>';
    var status=q.yn?'<span class="badge badge-on"><span class="pd"></span>启用</span>':'<span class="badge badge-mut"><span class="pd"></span>停用</span>';
    var editable=(q.question_type_id===1||q.question_type_id===2||q.question_type_id===3);
    var op=editable?'<button class="btn btn-ghost btn-mini" data-edit-q="'+q.id+'">编辑</button>':'<span class="muted" title="其余题型本期只读展示">只读</span>';
    return '<tr class="hov" data-qrow="'+q.id+'" style="cursor:pointer"><td class="nb">'+esc(q.question_code)+'</td><td>'+esc(typeName(q.question_type_id))+'</td><td><div class="stem-clamp">'+esc(q.stem)+'</div></td><td>'+objBadge+'</td><td>'+status+'</td><td class="cell-actions" style="justify-content:flex-end"><span class="muted" style="font-size:12px">详情</span>'+op+'</td></tr>';
  }
  function findQ(id){ for(var i=0;i<state.currentQuestions.length;i++){ if(state.currentQuestions[i].id===id) return state.currentQuestions[i]; } return null; }

  /* ---- 行点击：题目行 → 详情页跳转 admin-question-detail.html?id= ---- */
  qs("q-body").addEventListener("click", function(e){
    var eb=e.target.closest("[data-edit-q]");
    if(eb){ e.stopPropagation(); openQForm(+eb.getAttribute("data-edit-q")); return; }
    var row=e.target.closest("[data-qrow]");
    if(row) window.location.href="admin-question-detail.html?id="+row.getAttribute("data-qrow");
  });
  qs("bank-body").addEventListener("click", function(e){
    var mb=e.target.closest("[data-manage-bank]");
    if(mb){ var b=findBank(+mb.getAttribute("data-manage-bank")); if(b) selectBank(b); }
  });

  /* ---- 分页按钮 ---- */
  function pagerHTML(bind,page,total){
    var tp=Math.max(1,Math.ceil(total/PAGE_SIZE));
    var attr=(bind==="qPage")?"data-qpg":"data-bkpg";
    var h='<button '+attr+'="'+Math.max(1,page-1)+'"'+(page<=1?' disabled':'')+'>‹</button>';
    for(var i=1;i<=tp;i++) h+='<button '+attr+'="'+i+'" class="'+(i===page?'cur':'')+'">'+i+'</button>';
    h+='<button '+attr+'="'+Math.min(tp,page+1)+'"'+(page>=tp?' disabled':'')+'>›</button>';
    return h;
  }

  /* ---- 新建题库（POST /banks） ---- */
  window.openBankForm=function(){
    qs("bank-form-title").textContent="新建题库";
    var f=qs("bank-form-fields"); f.bank_name.value=""; f.bank_code.value=""; f.category_id.value="1"; f.institution_id.value="1";
    qs("bank-form").classList.add("show");
  };
  window.saveBank=function(){
    var f=qs("bank-form-fields");
    var body={ institution_id:+f.institution_id.value||1, category_id:+f.category_id.value||1, bank_code:f.bank_code.value.trim(), bank_name:f.bank_name.value.trim() };
    if(!body.bank_name||!body.bank_code){ toast("题库名称与编码必填"); return; }
    closeModals();
    EAPI.post("/api/admin/questions/banks", body).then(function(){ toast("题库已创建"); loadBanks(1); })
      .catch(function(err){ toast("创建失败："+((err&&err.message)||"未知错误")); });
  };

  /* ---- 新建/编辑题目（POST/PATCH questions） ---- */
  window.openQForm=function(id){
    state.qEditId=id||null;
    qs("q-form-title").textContent=id?"编辑题目":"新建题目";
    qs("qf-code-wrap").style.display=id?"none":"block";
    qs("qf-options-wrap").style.display="block";
    qs("qf-stem").value=""; qs("qf-answer").value=""; qs("qf-analysis").value="";
    state.editOpts=null;
    if(id){ var q=findQ(id); if(q){ qs("qf-type").value=q.question_type_id; qs("qf-stem").value=q.stem||""; qs("qf-answer").value=q.answer_text||""; qs("qf-analysis").value=q.analysis_text||""; state.editOpts=q.options_json||null; } else { qs("qf-type").value="1"; } }
    else { qs("qf-type").value="1"; }
    qs("qf-bank-hint").textContent=state.curBank?("目标题库：#"+state.curBank.id+" "+state.curBank.bank_name):"未选中题库";
    qfTypeChange();
    qs("q-form").classList.add("show");
  };
  window.qfTypeChange=function(){
    var t=+qs("qf-type").value;
    qs("qf-options-wrap").style.display=(t===3)?"none":"block";
    qs("qf-answer").placeholder=t===2?"填连续字母，如 AB":(t===3?"填 正确 / 错误":"填选项字母，如 A");
    if(t!==3) renderQFOptions();
  };
  function renderQFOptions(){
    var byLabel={}; (state.editOpts||[]).forEach(function(o){ byLabel[o.label]=o.content; });
    var html="";
    ["A","B","C","D"].forEach(function(l){ html+='<div style="display:flex;gap:8px;align-items:center;margin-bottom:6px"><span style="font-weight:700;width:16px">'+l+'</span><input data-opt-label="'+l+'" style="flex:1;height:34px;border:1px solid var(--line);border-radius:8px;padding:0 10px;font:inherit;font-size:0.8125rem" value="'+esc(byLabel[l]||"")+'"></div>'; });
    qs("qf-options-body").innerHTML=html;
  }
  function collectQFOptions(){
    var arr=[];
    document.querySelectorAll("#qf-options-body input[data-opt-label]").forEach(function(inp){ var v=inp.value.trim(); if(v) arr.push({ label:inp.getAttribute("data-opt-label"), content:v }); });
    return arr;
  }
  window.saveQuestion=function(){
    if(!state.curBank){ toast("请先在题库 Tab 选中题库"); return; }
    var t=+qs("qf-type").value, stem=qs("qf-stem").value.trim(), ans=qs("qf-answer").value.trim(), analysis=qs("qf-analysis").value.trim();
    if(!stem){ toast("题干为必填"); return; }
    if(!ans){ toast("答案为必填"); return; }
    var options=null; if(t!==3){ options=collectQFOptions(); if(!options.length){ toast("请填写至少一项选项"); return; } }
    var base={ question_type_id:t, stem:stem, options_json:options, answer_text:ans, analysis_text:analysis };
    var p, editing=!!state.qEditId;
    if(editing) p=EAPI.patch("/api/admin/questions/questions/"+state.qEditId, base);
    else { var code=qs("qf-code").value.trim(); if(!code){ toast("题号必填"); return; } base.bank_id=state.curBank.id; base.question_code=code; p=EAPI.post("/api/admin/questions/questions", base); }
    closeModals();
    p.then(function(){ toast(editing?"题目已更新":"题目已创建"); state.qEditId=null; loadQuestions(state.qPage); })
      .catch(function(err){ toast("保存失败："+((err&&err.message)||"未知错误")); });
  };

  /* ---- 批量导入：import-preview → import-execute ---- */
  window.openImport=function(){ impShowBankHint(); qs("import-dialog").classList.add("show"); impStep(1); };
  function impShowBankHint(){ var h=qs("imp-bank-hint"); if(h) h.textContent=state.curBank?("目标题库：#"+state.curBank.id+" "+state.curBank.bank_name):"当前未选中题库（先到题库 Tab 点「管理」）"; }
  window.impStep=function(n){
    document.querySelectorAll(".imp-step").forEach(function(x){ x.classList.toggle("hidden", Number(x.getAttribute("data-idx"))!==n); });
    qs("imp-step-hint").textContent="Step "+n+"/4 · "+["上传文件","校验预览","导入进度","结果报告"][n-1];
    document.querySelectorAll(".stp,.stp-conn").forEach(function(x){ var i=Number(x.getAttribute("data-step")||x.getAttribute("data-conn")||0); x.classList.toggle("done", !!i&&i<n); x.classList.toggle("cur", i===n); });
  };
  window.impBack=function(n){ impStep(n); };
  window.previewDone=function(){
    if(!state.curBank){ toast("请先选中目标题库（题库 Tab 点「管理」）"); return; }
    var raw=qs("imp-json-input").value.trim(); if(!raw){ toast("请粘贴待导入题目数组 JSON"); return; }
    var arr; try{ arr=JSON.parse(raw); }catch(e){ toast("JSON 解析失败："+e.message); return; }
    if(!Array.isArray(arr)||!arr.length){ toast("需为非空数组"); return; }
    if(arr.length>10){ toast("首期单次导入 ≤10 题"); return; }
    EAPI.post("/api/admin/questions/import-preview?bank_id="+state.curBank.id, { items:arr }).then(function(d){
      state.importItems=arr; renderPreview(d); impStep(2);
    }).catch(function(err){ toast("校验失败："+((err&&err.message)||"")); });
  };
  function renderPreview(d){
    d=d||state.importPreview||{total_rows:0,valid_rows:0,invalid_rows:0,rows:[]};
    qs("pv-total").textContent=d.total_rows; qs("pv-valid").textContent=d.valid_rows; qs("pv-invalid").textContent=d.invalid_rows;
    var arr=state.importItems||[];
    qs("pv-body").innerHTML=(d.rows||[]).map(function(r){
      var item=arr[r.row_index]||{}; var valid=!!r.valid;
      var errs=(r.errors||[]).map(function(x){ return '<span class="err-pill">'+esc(x)+'</span>'; }).join("");
      return '<tr class="'+(valid?'':'row-bad')+'"><td class="nb">#'+r.row_index+'</td><td class="nb">'+esc(r.question_code||"—")+'</td><td>'+(item.question_type_id!=null?esc(typeName(item.question_type_id)):"")+'</td><td class="stem-clamp">'+(item.stem?esc(item.stem):"<em>（空）</em>")+'</td><td>'+(valid?'<span class="ok-pill">✓ 有效</span>':errs)+'</td></tr>';
    }).join("");
    qs("import-confirm-btn").textContent="确认导入 "+d.valid_rows+" 行 →";
  }
  window.startImport=function(){
    if(!state.curBank){ toast("请先选中题库"); return; }
    if(!state.importItems){ toast("请先进行校验预览"); return; }
    EAPI.post("/api/admin/questions/import-execute?bank_id="+state.curBank.id, { items:state.importItems }).then(function(d){
      renderResult(d); if(state.curBank) loadQuestions(1); impStep(4);
    }).catch(function(err){ toast("导入失败："+((err&&err.message)||"")); });
  };
  function renderResult(d){
    d=d||{total:0,imported:0,skipped:0,failed:0,messages:[]};
    qs("res-imp").textContent=d.imported; qs("res-skip").textContent=d.skipped; qs("res-fail").textContent=d.failed;
    var msgs=(d.messages&&d.messages.length)?d.messages:["导入处理完成"];
    qs("res-msgs").innerHTML=msgs.map(function(m){ var cls=m.indexOf("失败")>=0?"ms-fail":(m.indexOf("跳过")>=0?"ms-skip":"ms-ok"); return '<div class="'+cls+'">'+esc(m)+'</div>'; }).join("");
  }

  /* ---- 覆盖原演示渲染入口，使切页/重试走真实数据 ---- */
  window.renderBanks=function(){ loadBanks(state.bankPage); };
  window.renderQuestions=function(){ loadQuestions(state.qPage); };
  window.switchTab=switchTab;
  window.selectBank=selectBank;
  window.resetBankFilter=function(){ qs("f-bank-kw").value=""; qs("f-bank-cat").value=""; loadBanks(1); };
  window.resetQFilter=function(){ qs("f-q-kw").value=""; qs("f-q-type").value=""; loadQuestions(1); };

  /* ---- 搜索/筛选触发 ---- */
  var bkw=qs("f-bank-kw"); if(bkw) bkw.addEventListener("keydown", function(e){ if(e.key==="Enter"){ e.preventDefault(); loadBanks(1); } });
  var qkw=qs("f-q-kw"); if(qkw) qkw.addEventListener("keydown", function(e){ if(e.key==="Enter"){ e.preventDefault(); loadQuestions(1); } });
  var qtype=qs("f-q-type"); if(qtype) qtype.addEventListener("change", function(){ loadQuestions(1); });

  /* ---- 初始化 ---- */
  state.importPreview=null;
  loadTypes().then(function(){ return loadBanks(1); });
})();
