/* Admin course video production: one client of the existing authorized API.
 * open is called only inside bootAdmin after course/video assets are loaded.
 * A preview identity is retained until an explicit decision; polling never
 * approves or rejects a replacement generation on the operator's behalf. */
(function(global){
  "use strict";
  var root=document.getElementById("videoKnowledgeAdmin");if(!root)return;
  var $=function(id){return document.getElementById(id);}, base="/api/admin/video-knowledge/tasks";
  var context=null,tasks=[],current=null,review=null,epoch=0,pending=false,timer=null,refreshing=false;
  var stages={acquire:"获取视频",acquiring:"获取视频",bind:"校验并绑定播放源",transcribe:"字幕 / 语音识别",transcribing:"字幕 / 语音识别",compile:"生成学习资料",compiling:"生成学习资料",exercises:"生成本课习题",graph:"同步 Neo4j 课程图谱",review:"资料已生成",publish:"发布正式资料",publishing:"发布正式资料",rag:"接入课程知识",completed:"完成",complete:"完成",ingest:"接入课程知识",ingesting:"接入课程知识"};
  var states={queued:"等待处理",running:"处理中",awaiting_review:"资料已生成",approved:"准备发布 / 入库",completed:"已完成",failed:"处理失败"};
  var esc=function(value){var d=document.createElement("div");d.textContent=value==null?"":String(value);return d.innerHTML;};
  function stamp(value){var n=Math.max(0,Math.floor(Number(value)||0));return Math.floor(n/60)+":"+String(n%60).padStart(2,"0");}
  function generationLabel(value){return "生成发起时间："+String(value.created_at||"未提供").replace("T"," ").replace(/\.\d+/,"")+" · 本次修订 "+Number(value.review_revision||0)+" 次";}
  function notice(value){$("vkNotice").textContent=value;}
  function invalidate(){review=null;$("vkReview").hidden=true;$("vkDecisions").hidden=true;$("vkReason").value="";buttons();}
  function sameReview(){return review&&current&&review.task_id===current.id&&review.artifact_sha256===current.artifact_sha256&&review.review_revision===current.review_revision;}
  function buttons(){
    if($("vkGraph"))$("vkGraph").disabled=pending||!context||!context.videos.length;
    $("vkExercises").disabled=pending||!context||!context.videos.length||!!(current&&current.status!=="completed")||!!(current&&current.exercise_count);
    var videoReady=$("vkSource").value==="bilibili"||!!$("vkVideo").value;
    $("vkGenerate").disabled=pending||!context||!videoReady;
    $("vkRefresh").disabled=pending;$("vkTask").disabled=pending;
    $("vkRetry").disabled=pending||!current||!current.retry_allowed;
    $("vkPreview").disabled=pending||!current||!current.artifact_sha256;
    $("vkApprove").disabled=$("vkReject").disabled=pending||!sameReview()||!current.review_allowed;
    ["vkSource","vkVideo","vkBvid","vkPage","vkMode","vkRegenerate"].forEach(function(id){$(id).disabled=pending;});
  }
  function renderTask(){
    $("vkProgress").hidden=!current;
    if(!current){$("vkTaskStatus").textContent="尚未创建资料生产任务。";$("vkTaskError").textContent="";buttons();return;}
    var label=states[current.status]||current.status, stage=stages[current.stage]||current.stage||"等待处理";
    var parts=[label+" · "+stage,generationLabel(current)];
    if(current.exercises_only)parts.push("仅补生成本课习题；原视频与正式资料版本保留");
    else if(current.previous_task_id||current.previous_publication_id)parts.push("基于已发布资料重新生成，旧版仍可用");
    if(current.lease_expired&&current.status==="running")parts.push(current.retry_allowed?"租约已过期，任务停滞；可安全重试":"租约已过期，但工作进程仍在执行；等待安全释放后再重试");
    if(current.published&&!current.exercises_only)parts.push(current.rag_ready?"资料已发布":"审核通过资料已保存");
    if(current.rag_ready&&tasks[0]&&current.id===tasks[0].id&&current.video_id===Number($("vkVideo").value)&&$("vkGraphPanel")&&$("vkGraphPanel").dataset.artifactSha&&$("vkGraphPanel").dataset.artifactSha!==current.artifact_sha256){
      $("vkGraphPanel").textContent="正式资料版本已切换，请重新点击同步 / 查看当前 Neo4j 图谱。";delete $("vkGraphPanel").dataset.artifactSha;
    }
    if(current.rag_ready)parts.push("课程知识已可检索，学生可向 Tutor 提问");
    else if(current.published&&!current.exercises_only){
      parts.push("课程知识检索尚未就绪；待课程知识入库完成后学生可用");
      if(current.previous_publication_id)parts.push("已有旧正式版本继续可用");
    }
    if(current.graph_projection)parts.push(current.graph_projection.status==="succeeded"?"Neo4j 图谱已同步："+current.graph_projection.chapter_count+"章节 / "+current.graph_projection.chunk_count+"分块":"Neo4j 图谱暂不可用，可单独同步；正式 RAG 不受影响");
    if(current.playback_available)parts.push("原视频可播放");
    $("vkTaskStatus").textContent=parts.join(" · ");
    if($("vkTrace")){
      $("vkTrace").hidden=!/^[0-9a-f]{32}$/.test(current.production_trace_id||"");
      if(!$("vkTrace").hidden)$("vkTrace").href=current.jaeger_url.replace(/\/$/,"")+"/trace/"+current.production_trace_id;
    }
    $("vkTaskError").textContent=current.error_message?("失败阶段："+stage+"。"+current.error_message):"";
    var headline=label+" · "+stage, detail="";
    if(current.status==="queued"){headline="任务已提交 · 等待后台接单";detail="接单后会自动更新处理阶段，无需重复提交。";}
    if(current.status==="running"){headline="后台已接单 · 正在"+stage;detail=current.stage==="transcribing"?"字幕提取或语音识别可能需要数分钟；完成后自动进入学习资料生成，无需重复提交。":"正在处理，完成本阶段后会自动更新，无需重复提交。";}
    if(current.status==="awaiting_review"){headline="AI 学习资料已生成";detail="点击「预览本版资料」查看总结、笔记、章节、字幕和导图；阅读后批准或驳回。新版尚未正式发布。";}
    if(current.status==="approved"){headline="学习资料已校验 · 正在发布和入库";detail="系统会自动发布并接入课程知识；RAG 就绪前不会替换学生使用的正式版本。";}
    if(current.published&&!current.rag_ready&&!current.exercises_only){headline="新版资料已保存 · 课程知识入库尚未完成";detail="请等待入库完成；原视频和已有正式版本继续可用。";}
    if(current.status==="failed"){headline="处理失败 · "+stage;detail=current.error_message||"请查看下方失败原因及可用的重试操作。";}
    if(current.lease_expired){headline="任务更新异常 · "+stage;detail=current.retry_allowed?"执行租约已过期，可点击「重试失败阶段」。":"执行租约已过期，仍需等待后台安全释放，不能抢占执行。";}
    if(current.rag_ready){headline="已完成 · 学生资料和课程知识均已就绪";detail="学生可以查看正式资料，并向 Course Tutor 提问。"+(current.exercise_count?"本课 "+current.exercise_count+" 道视频习题已接入本课练习。":"旧视频尚未生成对应习题，可点击「补生成本课习题」。");}
    var updated=String(current.updated_at||"").replace("T"," ").replace(/\.\d+/,"");
    $("vkProgressTitle").textContent=headline;
    $("vkProgressDetail").textContent=detail+(updated?" 后台最近更新："+updated+"。":"");
    if(review&&!sameReview()){invalidate();notice("候选版本已更新。请重新预览后再审核；原视频和旧正式资料保留。");}
    buttons();
  }
  function selectedTask(syncSource){
    var id=$("vkTask").value;current=tasks.find(function(t){return t.id===id;})||null;
    if(syncSource&&current){$("vkBvid").value=current.bvid||"";$("vkPage").value=current.page||1;$("vkMode").value=current.transcript_mode||"auto";}
    renderTask();
  }
  async function refresh(){
    if(!context||refreshing)return;var e=epoch,sid=context.session_id;refreshing=true;
    try{
      var data=await EAPI.get(base+"?session_id="+sid);
      if(e!==epoch)return;
      tasks=(data.items||[]).filter(function(t){return Number(t.session_id)===Number(sid);});
      var keep=current&&current.id;
      $("vkTask").innerHTML=tasks.length?tasks.map(function(t,index){return '<option value="'+esc(t.id)+'">'+(index===0?"最新生产记录":"历史生产记录")+" · "+esc(states[t.status]||t.status)+" · "+esc(generationLabel(t))+"</option>";}).join(""):'<option value="">尚无生产记录</option>';
      if(tasks.some(function(t){return t.id===keep;}))$("vkTask").value=keep;
      var worker=data.worker||{},labels={running:"处理服务运行中",offline:"处理服务离线，任务等待服务恢复",paused:"处理服务暂停，任务尚未继续",stopping:"处理服务正在安全停止"};
      $("vkWorker").textContent=labels[worker.state]||"暂时无法确认处理服务状态";
      $("vkSync").textContent="最近同步："+new Date().toLocaleTimeString("zh-CN",{hour12:false})+" · 此面板可见时每 5 秒自动刷新；也可点击「刷新状态」。";
      if($("vkNotice").textContent.startsWith("状态读取失败："))notice("");
      selectedTask(!keep||!tasks.some(function(t){return t.id===keep;}));
    }catch(error){if(e===epoch){$("vkSync").textContent="同步失败，当前显示旧状态。请点击「刷新状态」重试。";notice("状态读取失败："+(error.message||"网络错误")+"。原视频可继续播放。");}}
    finally{if(e===epoch)refreshing=false;}
  }
  function sourceChange(){
    var bili=$("vkSource").value==="bilibili";
    $("vkVideoField").hidden=bili;$("vkBiliField").hidden=$("vkPageField").hidden=!bili;
    $("vkUploadHint").hidden=bili;buttons();
  }
  function biliInput(){
    var raw=$("vkBvid").value.trim(),bvid=raw,page=Number($("vkPage").value);
    if(raw.indexOf("https://")===0){
      var url;try{url=new URL(raw);}catch(_){throw new Error("请填写有效的 Bilibili 视频链接");}
      if(url.hostname!=="www.bilibili.com"&&url.hostname!=="bilibili.com")throw new Error("请填写 Bilibili 官方视频链接");
      bvid=url.pathname.split("/").filter(Boolean)[1]||"";
      if(url.searchParams.has("p"))page=Number(url.searchParams.get("p"));
    }
    if(!/^BV[0-9A-Za-z]{10}$/.test(bvid))throw new Error("请填写完整 BV 号或官方视频链接");
    if(!Number.isInteger(page)||page<1||page>1000)throw new Error("分 P 必须是 1 至 1000 的整数");
    return {bvid:bvid,page:page};
  }
  async function mutate(action,payload){
    if(pending||!context)return;var e=epoch;pending=true;buttons();notice("正在提交，请等待…");
    try{
      var value=await EAPI.post(action,payload);
      if(e!==epoch)return;
      if(action===base)$("vkRegenerate").checked=false;
      invalidate();current=value;notice(payload.exercises_only||value.exercises_only?"本课习题生成已提交。原视频与正式资料版本保留，请查看真实处理阶段。":"操作已提交。生成成功后自动发布并入库，请查看真实处理阶段；原视频保持可用。");
      await refresh();
      global.dispatchEvent(new CustomEvent("edu:video-knowledge-task-changed",{detail:{session_id:context.session_id,task:value}}));
    }catch(error){
      if(e!==epoch)return;
      if(error.status===409){invalidate();notice("状态或版本已更新。请刷新状态并重新预览后再审核；不会自动批准新版本。 "+(error.message||""));}
      else notice("操作失败："+(error.message||"网络错误")+"。原视频及旧正式资料保留，可安全重试。");
    }finally{if(e===epoch){pending=false;buttons();}}
  }
  $("vkGenerate").onclick=function(){
    if(pending||!context)return;
    try{
      var source=$("vkSource").value,payload={session_id:context.session_id,source_kind:source,transcript_mode:$("vkMode").value,regenerate:$("vkRegenerate").checked};
      if(source==="bilibili")Object.assign(payload,biliInput());
      else {payload.video_id=Number($("vkVideo").value);if(!payload.video_id)throw new Error("请先上传或选择本课视频");}
      if(current&&current.status==="completed"&&!payload.regenerate)throw new Error("已有完成的资料。如需重新生成，请勾选生成新版资料。");
      mutate(base,payload);
    }catch(error){notice(error.message);}
  };
  $("vkRetry").onclick=function(){if(current&&current.retry_allowed)mutate(base+"/"+current.id+"/retry",{});};
  $("vkExercises").onclick=function(){if(pending||!context)return;var id=Number($("vkVideo").value);if(!id)return notice("请先选择已正式发布的本课视频");mutate(base,{session_id:context.session_id,source_kind:"existing_video",video_id:id,transcript_mode:"auto",exercises_only:true});};
  $("vkRefresh").onclick=refresh;$("vkSource").onchange=sourceChange;$("vkVideo").onchange=buttons;
  $("vkTask").onchange=function(){invalidate();selectedTask(true);};
  $("vkPreview").onclick=async function(){
    if(!current||pending)return;var e=epoch,taskId=current.id;pending=true;buttons();notice("正在读取本版资料…");
    try{
      var data=await EAPI.get(base+"/"+taskId+"/preview");
      if(e!==epoch||!current||current.id!==taskId)return;
      if(data.artifact_sha256!==current.artifact_sha256||data.review_revision!==current.review_revision){invalidate();notice("版本已更新，请刷新状态并重新预览。");return;}
      review={task_id:taskId,artifact_sha256:data.artifact_sha256,review_revision:data.review_revision};
      var summary=data.summary||{},transcript=data.transcript||{},chapters=data.chapters||[];
      $("vkReview").innerHTML='<h4>当前预览 · '+esc((data.source||{}).title||summary.title||"当前视频")+'</h4><p>'+esc(generationLabel(current))+'</p>'
        +'<p class="vka-help">转写来源：'+(data.transcript_origin==="platform_subtitle"?"原生字幕":"语音识别")+' · '+(transcript.segments||[]).length+' 段字幕 · '+chapters.length+' 个章节</p>'
        +'<details open><summary>课程总结</summary><h4>'+esc(summary.title)+'</h4><p>'+esc(summary.overview)+'</p><ul>'+(summary.key_points||[]).map(function(t){return '<li>'+esc(t)+'</li>';}).join('')+'</ul></details>'
        +'<details open><summary>AI 笔记</summary><div class="vka-note">'+(global.EduMD?EduMD.toHtml(data.knowledge_note):esc(data.knowledge_note))+'</div></details>'
        +'<details><summary>章节（'+chapters.length+'）</summary>'+chapters.map(function(c){return '<article><span class="vka-time">'+stamp(c.start)+'</span> <b>'+esc(c.title)+'</b><p>'+esc(c.summary)+'</p></article>';}).join('')+'</details>'
        +'<details><summary>带时间戳字幕（'+(transcript.segments||[]).length+'）</summary><div class="vka-transcript">'+(transcript.segments||[]).map(function(s){return '<p><span class="vka-time">'+stamp(s.start)+'–'+stamp(s.end)+'</span> '+esc(s.text)+'</p>';}).join('')+'</div></details>'
        +'<details><summary>思维导图</summary><div id="vkPreviewMap"></div></details>'
        +'<details><summary>本课视频习题（'+(data.exercise_questions||[]).length+'）</summary>'+(data.exercise_questions||[]).map(function(q,i){return '<article><b>'+Number(i+1)+'. '+esc(q.stem)+'</b>'+q.options.map(function(o){return '<p>'+esc(o.label)+'. '+esc(o.content)+'</p>';}).join('')+'<p>答案：'+esc(q.answer)+' · '+esc(q.analysis)+'</p><p>视频依据 '+stamp(q.start_seconds)+'–'+stamp(q.end_seconds)+' · 导图节点 '+esc(q.node_id)+'</p></article>';}).join('')+'</details>';
      $("vkPreviewMap").appendChild(global.EduVideoMindMap(data.mindmap||{nodes:[]}));
      $("vkReview").hidden=false;$("vkDecisions").hidden=!current.review_allowed;
      notice(current.review_allowed?"已打开本版资料。请阅读内容后作出审核决定。":current.rag_ready?"本版已完成发布与入库，可直接阅读预览，无需人工审核。":"已打开本版资料。系统将自动发布和入库，学生可用状态以下方处理结果为准。");
    }catch(error){if(e===epoch){invalidate();notice("预览失败："+(error.message||"网络错误")+"。请刷新状态后重试。");}}
    finally{if(e===epoch){pending=false;buttons();}}
  };
  $("vkApprove").onclick=function(){if(sameReview()&&current.review_allowed)mutate(base+"/"+review.task_id+"/approve",{artifact_sha256:review.artifact_sha256,review_revision:review.review_revision});};
  $("vkReject").onclick=function(){
    if(!sameReview()||!current.review_allowed)return;
    var reason=$("vkReason").value.trim();if(!reason){notice("请填写具体审核意见再驳回。");$("vkReason").focus();return;}
    mutate(base+"/"+review.task_id+"/reject",{reason:reason,artifact_sha256:review.artifact_sha256,review_revision:review.review_revision});
  };
  global.AdminVideoKnowledge={open:async function(value){
    epoch++;var openedEpoch=epoch;context=value;tasks=[];current=null;pending=false;refreshing=false;root.hidden=false;invalidate();
    $("vkLesson").textContent="当前课次："+value.title;notice("");$("vkRegenerate").checked=false;
    $("vkBvid").value="";$("vkPage").value=1;$("vkMode").value="auto";
    $("vkVideo").innerHTML=value.videos.length?value.videos.map(function(v){return '<option value="'+Number(v.id)+'">'+esc(v.video_title||v.asset_name||"本课视频")+'</option>';}).join(''):'<option value="">尚无绑定视频，请在下方上传</option>';
    $("vkSource").value=value.videos.length?"existing_video":"bilibili";sourceChange();
    if($("vkGraphPanel")){$("vkGraphPanel").hidden=true;$("vkGraphPanel").replaceChildren();}
    if(timer)clearInterval(timer);await refresh();if(openedEpoch===epoch)timer=setInterval(function(){if(!document.hidden&&!pending)refresh();},5000);
  },close:function(){epoch++;context=null;pending=false;refreshing=false;root.hidden=true;invalidate();if(timer)clearInterval(timer);timer=null;}};
  if($("vkGraph"))$("vkGraph").onclick=async function(){
    if(pending||!context)return;var e=epoch,id=Number($("vkVideo").value);if(!id)return;
    pending=true;buttons();var panel=$("vkGraphPanel");panel.hidden=false;panel.textContent="正在同步当前正式版本的 Neo4j 图谱；保留原视频与 RAG…";
    try{
      var data=await EAPI.post("/api/admin/video-knowledge/videos/"+id+"/graph",{});if(e!==epoch)return;
      panel.replaceChildren();panel.dataset.artifactSha=data.graph.artifact_sha256;var title=document.createElement("h4");title.textContent="Neo4j 课程图谱 · "+data.receipt.chapter_count+" 章节 / "+data.receipt.chunk_count+" 个真实 RAG 分块";panel.appendChild(title);
      var detail=document.createElement("p");detail.textContent="正式版本 "+data.graph.artifact_sha256.slice(0,12)+" · "+data.graph.meaning;panel.appendChild(detail);
      function link(label,url){if(!url)return;var a=document.createElement("a");a.className="btn btn-ghost";a.textContent=label;a.href=url;a.target="_blank";a.rel="noopener noreferrer";panel.appendChild(a);}
      link("打开 Neo4j Browser",data.neo4j_url);
      if(/^[0-9a-f]{32}$/.test(data.receipt.trace_id||""))link("查看本次图谱同步 Trace",data.jaeger_url.replace(/\/$/,"")+"/trace/"+data.receipt.trace_id);
      var nodes=data.graph.nodes,edges=data.graph.edges,video=nodes.find(function(n){return n.kind==="video";});
      function children(id){return edges.filter(function(edge){return edge.source===id;}).map(function(edge){var node=nodes.find(function(n){return n.id===edge.target;});return {id:node.id,label:node.kind==="chunk"?"RAG 分块 · "+node.label.slice(0,45):node.label,summary:node.kind==="chunk"?"Milvus chunk_id："+node.id+"\n"+node.label:"Neo4j 节点："+node.id,time_anchor:node.time_anchor,children:children(node.id)};});}
      if(video&&global.EduVideoMindMap)panel.appendChild(global.EduVideoMindMap({nodes:[{id:video.id,label:context.title,summary:"当前 READY 版本的实际 Neo4j 投影",children:children(video.id)}]}));
    }catch(error){if(e===epoch)panel.textContent="图谱同步失败："+error.message+"。可重新点击同步；原视频与正式 RAG 保持可用。";}
    finally{if(e===epoch){pending=false;buttons();}}
  };
})(window);
