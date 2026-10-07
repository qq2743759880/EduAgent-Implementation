/* One native node/connector renderer for student and administrator previews. */
(function(global){
  'use strict';
  function el(tag,text,cls){var n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;}
  function stamp(t){t=Math.max(0,Math.floor(Number(t)||0));return Math.floor(t/60)+':'+String(t%60).padStart(2,'0');}
  global.EduVideoMindMap=function(map,onSeek){
    var wrap=el('div',null,'vk-map'),scroll=el('div',null,'vk-map-scroll'),tree=el('ul',null,'vk-mindmap vk-map-diagram');
    var detail=el('section','点击节点查看要点；使用详情中的回看按钮跳到原视频。','vk-map-detail');
    detail.setAttribute('aria-live','polite');scroll.setAttribute('aria-label','课程思维导图，可横向滚动');
    scroll.tabIndex=0;
    function node(value,depth){
      var li=el('li'),box=el('div',null,'vk-map-box'),card=el('button',null,'vk-map-node');card.type='button';card.setAttribute('aria-pressed','false');
      card.setAttribute('aria-label',value.label);card.appendChild(el('span',value.label,'vk-map-label'));
      if(value.time_anchor!=null)card.appendChild(el('span','▶ '+stamp(value.time_anchor),'vk-map-time'));
      card.addEventListener('click',function(){
        tree.querySelectorAll('.vk-map-node').forEach(function(b){b.setAttribute('aria-pressed',String(b===card));});
        detail.replaceChildren(el('strong',value.label),el('p',value.summary||''));
        if(value.time_anchor!=null&&onSeek){
          var jump=el('button','跳到视频 '+stamp(value.time_anchor),'vk-jump');jump.type='button';
          jump.addEventListener('click',function(){onSeek(value.time_anchor);});detail.appendChild(jump);
        }
      });
      box.appendChild(card);li.appendChild(box);
      if(value.children&&value.children.length){
        var children=el('ul');children.hidden=depth>0;
        value.children.forEach(function(c){children.appendChild(node(c,depth+1));});li.appendChild(children);
        if(depth>0){var expand=el('button','展开 '+value.children.length+' 个要点','vk-map-expand');expand.type='button';expand.setAttribute('aria-expanded','false');expand.addEventListener('click',function(){children.hidden=!children.hidden;expand.setAttribute('aria-expanded',String(!children.hidden));expand.textContent=children.hidden?'展开 '+value.children.length+' 个要点':'收起要点';});box.appendChild(expand);}
      }
      return li;
    }
    (map.nodes||[]).forEach(function(n){tree.appendChild(node(n,0));});scroll.appendChild(tree);wrap.appendChild(scroll);wrap.appendChild(detail);return wrap;
  };
})(window);
