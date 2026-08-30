import fs from "fs";
import path from "path";

const srcDir = "E:/stu/project/stu/EduAgent实施手册/test-reports/fe-html";
const pubDir = "E:/stu/project/stu/EduAgent实施手册/edu-frontend/public";

// 每页：注入的 JS 片段（真实数据加载，失败静默保留演示值）
const inject = {
  "courses.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;EAPI.get("/api/series?page=1&page_size=12").then(function(d){var items=d&&d.items?d.items:(Array.isArray(d)?d:[]);if(!items.length)return;var cards=document.querySelectorAll(".course-card,.grid>.card");if(!cards.length)return;items.slice(0,cards.length).forEach(function(s,i){var c=cards[i];var t=c.querySelector("h3,.title,.name");if(t)t.textContent=s.series_name||t.textContent;var p=c.querySelector(".price,[class*=price]");if(p&&s.min_price)p.textContent="¥"+Number(s.min_price).toFixed(2);});}).catch(function(){});})();`,
  "achievements.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;Promise.allSettled([EAPI.get("/api/gamification/me/badges"),EAPI.get("/api/gamification/me/points")]).then(function(r){var b=r[0].status==="fulfilled"?r[0].value:null;if(b&&b.items&&b.items.length){var wall=document.querySelector(".badge-wall,.badges");if(wall&&wall.querySelectorAll(".badge").length){var bts=wall.querySelectorAll(".badge");b.items.slice(0,bts.length).forEach(function(bd,i){var n=bts[i].querySelector(".name,.t");if(n)n.textContent=bd.badge_name||bd.name||n.textContent;});}}var p=r[1].status==="fulfilled"?r[1].value:null;if(p){var el=document.querySelector(".points-num,[class*=points] .num");if(el)el.textContent=p.total_points||el.textContent;}}).catch(function(){});})();`,
  "my-cohorts.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;EAPI.get("/api/enrollments/me/cohorts?page=1&page_size=10").then(function(d){var items=d&&d.items?d.items:[];if(!items.length)return;var list=document.querySelector(".cohort-list,.list");if(!list)return;var rows=list.querySelectorAll(".cohort,.item,.row");if(!rows.length)return;items.slice(0,rows.length).forEach(function(c,i){var n=rows[i].querySelector("h3,.name,.title");if(n)n.textContent=c.series_title||c.cohort_name||n.textContent;var s=rows[i].querySelector(".status,[class*=status]");if(s&&c.enroll_status)s.textContent=c.enroll_status;});}).catch(function(){});})();`,
  "practice.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;EAPI.get("/api/interactive/quiz/wrong-book?page=1&page_size=10").then(function(d){var items=d&&d.items?d.items:(Array.isArray(d)?d:[]);if(!items.length)return;var el=document.querySelector(".wrong-book .count,[class*=count]");if(el)el.textContent=items.length+(items.length?" 题":"");}).catch(function(){});})();`,
  "learning.html": `(function(){if(!window.EAPI||!EAPI.store.getToken())return;var m=/\\/learning\\/(\\d+)\\/(\\d+)/.exec(location.pathname);var sid=m?m[2]:null;if(!sid)return;EAPI.get("/api/learning/sessions/"+sid).then(function(d){if(!d)return;var t=document.querySelector("h1,.title,[class*=title]");if(t&&d.session_title)t.textContent=d.session_title;}).catch(function(){});})();`,
};

for (const [file, js] of Object.entries(inject)) {
  const src = path.join(srcDir, file);
  if (!fs.existsSync(src)) { console.log("skip", file); continue; }
  let html = fs.readFileSync(src, "utf8");
  if (html.includes("edu-api.js")) { console.log("already", file); continue; }
  // 在 </body> 前注入 edu-api.js + 数据加载
  const block = `<script src="/edu-api.js"></script>\n<script>\n${js}\n</script>\n`;
  html = html.replace(/<\/body>/i, block + "</body>");
  // 写回源 + public
  fs.writeFileSync(src, html, "utf8");
  fs.writeFileSync(path.join(pubDir, file), html, "utf8");
  console.log("injected", file);
}
