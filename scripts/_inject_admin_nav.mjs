import fs from "fs";
import path from "path";

const pubDir = "E:/stu/project/stu/EduAgent实施手册/edu-frontend/public";
const userPages = ["chat.html", "community.html", "community-post.html", "courses.html", "course-detail.html", "learning.html", "my-cohorts.html", "practice.html", "achievements.html", "me.html"];

const roleScript = `<script>
/* admin 角色显示管理后台入口 */
(function () {
  if (!window.EAPI) return;
  var el = document.getElementById("adminEntry");
  if (!el || !EAPI.store.getToken()) return;
  EAPI.get("/api/users/me").then(function (u) {
    if (u && (u.role === "admin" || u.role === "manager")) el.style.display = "";
  }).catch(function () {});
})();
</script>`;

for (const f of userPages) {
  const p = path.join(pubDir, f);
  if (!fs.existsSync(p)) continue;
  let html = fs.readFileSync(p, "utf8");
  const wasNav = html.includes('id="adminEntry"');
  if (!wasNav) {
    html = html.replace(/<div class="gnav-foot">[^<]*<\/div>/, '<div class="gnav-foot">Learning Hub · <a href="admin-dashboard.html" id="adminEntry" style="display:none;color:inherit">管理后台 →</a></div>');
  }
  if (!html.includes("admin 角色显示管理后台入口")) {
    // 在 edu-api.js script 后注入角色判断
    html = html.replace(/<script src="\/edu-api\.js"><\/script>/, '<script src="/edu-api.js"></script>\n' + roleScript);
  }
  fs.writeFileSync(p, html, "utf8");
  console.log((wasNav ? "skip-nav " : "nav+") + f);
}
console.log("done");
