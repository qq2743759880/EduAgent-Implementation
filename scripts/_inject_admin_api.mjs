import fs from "fs";
import path from "path";

const srcDir = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html";
const pubDir = "E:/stu/project/stu/EduAgent实施手册/edu-frontend/public";

const common = `(function(){if(!window.EAPI)return;if(!EAPI.store.getToken()){var t=document.querySelector(".toolbar-meta,.page-head .sub");if(t&&!t.textContent.includes("admin 账号")){t.textContent="⚠ 请用 admin 账号登录（adm02test / Test@123456）后刷新本页";}}})();`;

const inject = {
  "admin-courses.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;EAPI.get("/api/admin/courses/series?page=1&page_size=20").then(function(d){var items=d&&d.items?d.items:[];if(!items.length)return;var body=document.querySelector("tbody");if(!body)return;var esc=function(t){var x=document.createElement("div");x.textContent=t==null?"":t;return x.innerHTML};var rows=items.map(function(s){return '<tr><td>'+esc(s.series_code||"")+'</td><td>'+esc(s.series_name||"")+'</td><td>'+esc(s.delivery_mode||"")+'</td><td>'+esc(s.sale_status||"")+'</td><td>¥'+Number(s.min_price||0).toFixed(2)+'</td></tr>';}).join("");body.innerHTML=rows;}).catch(function(){});})();`,
  "admin-dashboard.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;EAPI.get("/api/admin/users/dashboard/metrics").then(function(d){if(!d)return;var map={total_users:d.total_users,active_users:d.active_users,new_users_today:d.new_users_today};Object.keys(map).forEach(function(k){var el=document.querySelector("[data-metric='"+k+"'],[data-k='"+k+"'],."+k+" .num");if(el&&map[k]!=null)el.textContent=map[k];});}).catch(function(){});})();`,
  "admin-users.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;EAPI.get("/api/admin/users?page=1&page_size=20").then(function(d){var items=d&&d.items?d.items:[];if(!items.length)return;var body=document.querySelector("tbody");if(!body)return;var esc=function(t){var x=document.createElement("div");x.textContent=t==null?"":t;return x.innerHTML};body.innerHTML=items.map(function(u){return '<tr><td>'+esc(u.account)+'</td><td>'+esc(u.nickname)+'</td><td>'+esc(u.role_code||u.role)+'</td><td>'+(u.yn===1?"启用":"停用")+'</td></tr>';}).join("");}).catch(function(){});})();`,
  "admin-question-detail.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;var m=(location.pathname.match(/\/(\d+)/)||[])[1];if(!m)return;EAPI.get("/api/admin/questions/questions/"+m).then(function(q){if(!q)return;var t=document.querySelector("h1,.title");if(t)t.textContent=q.question_code||t.textContent;var s=document.querySelector(".stem,[class*=stem]");if(s&&q.stem_html)s.innerHTML=q.stem_html;}).catch(function(){});})();`,
  "admin-course-detail.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;var m=(location.pathname.match(/\/(\d+)/)||[])[1];if(!m)return;EAPI.get("/api/admin/courses/series/"+m).then(function(s){if(!s)return;var t=document.querySelector("h1,.title");if(t&&(s.series_name))t.textContent=s.series_name;}).catch(function(){});})();`,
  "admin-rag-upload.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;Promise.allSettled([EAPI.get("/api/knowledge/tasks?page=1&page_size=10"),EAPI.get("/api/admin/rag/collections")]).then(function(r){var tasks=r[0].status==="fulfilled"?r[0].value:null;if(tasks&&(tasks.items||tasks.tasks||Array.isArray(tasks))){var list=tasks.items||tasks.tasks||tasks;var body=document.querySelector("#taskTable tbody,#task-table tbody");if(body&&list.length){var esc=function(t){var x=document.createElement("div");x.textContent=t==null?"":t;return x.innerHTML};body.innerHTML=list.map(function(x){return '<tr><td>'+esc(x.task_id||x.id)+'</td><td>'+esc(x.status)+'</td><td>'+esc(x.total_chunks||0)+'</td><td>'+esc(x.created_at||"")+'</td></tr>';}).join("");}}var cols=r[1].status==="fulfilled"?r[1].value:null;if(cols&&cols.items){var el=document.querySelector("[data-collection-count],[class*=row-count]");if(el&&cols.total!=null)el.textContent=cols.total;}}).catch(function(){});})();`,
};

for (const [file, js] of Object.entries(inject)) {
  const src = path.join(srcDir, file);
  if (!fs.existsSync(src)) { console.log("skip", file); continue; }
  let html = fs.readFileSync(src, "utf8");
  if (html.includes("edu-api.js")) { console.log("already", file); continue; }
  const block = `<script src="/edu-api.js"></script>\n<script>\n${js}\n${common}\n</script>\n`;
  html = html.replace(/<\/body>/i, block + "</body>");
  fs.writeFileSync(src, html, "utf8");
  fs.writeFileSync(path.join(pubDir, file), html, "utf8");
  console.log("injected", file);
}
