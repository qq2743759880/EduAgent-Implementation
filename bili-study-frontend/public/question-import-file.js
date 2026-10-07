/* Read a local question file or the shipped sample; never imports by itself. */
(function(){
  'use strict';
  var file=document.getElementById('imp-file'),sample=document.getElementById('imp-load-sample'),input=document.getElementById('imp-json-input'),status=document.getElementById('imp-file-status');
  if(!file||!sample||!input||!status)return;
  var revision=0;
  function clear(){input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));}
  function load(text,label){
    var items=JSON.parse(text.replace(/^\uFEFF/,''));
    if(!Array.isArray(items)||!items.length)throw new Error('文件需要包含非空题目数组');
    if(items.length>10)throw new Error('当前每批最多 10 道题，请拆分文件');
    if(items.some(function(x){return !x||typeof x!=='object'||Array.isArray(x);}))throw new Error('每道题必须是完整题目记录');
    input.value=JSON.stringify(items,null,2);input.dispatchEvent(new Event('input',{bubbles:true}));
    status.textContent='已读取 '+label+'：'+items.length+' 道题。点击「开始校验」预览；此时尚未导入题库。';
  }
  file.addEventListener('change',async function(){
    var selected=file.files&&file.files[0];if(!selected)return;
    var own=++revision;clear();status.textContent='正在读取文件…';
    try{
      if(!/\.json$/i.test(selected.name))throw new Error('请选择 JSON 题库文件');
      if(selected.size>2*1024*1024)throw new Error('文件过大，单个文件限 2 MB');
      var text=await selected.text();if(own!==revision)return;load(text,selected.name);
    }catch(error){if(own===revision){clear();status.textContent='读取失败：'+error.message+'。请重新选择文件。';}}
  });
  sample.addEventListener('click',async function(){
    var own=++revision;clear();file.value='';status.textContent='正在载入 Python 样例…';
    try{
      var response=await fetch('/samples/python-basics-10.json',{cache:'no-store'});
      if(!response.ok)throw new Error('样例下载失败，请重试');
      var text=await response.text();if(own!==revision)return;load(text,'Python 基础样例');
    }catch(error){if(own===revision){clear();status.textContent='读取失败：'+error.message;}}
  });
})();
