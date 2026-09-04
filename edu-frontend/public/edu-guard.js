/* EduAgent 管理端角色守卫（task109 共用片段：8 个 admin 页内联 → 抽离单点）
 * 用法（admin-*.html，先于各页 bootAdmin 定义引入，避免重定义全局 $ 覆盖原脚本）：
 *   <script src="/edu-api.js"></script>
 *   <script src="/edu-guard.js"></script>
 *   <script>eduGuard.requireAdmin();</script>
 * 守卫三段（纪律 lesson10 不可省）：
 *   1) 本地无 token → 跳 login-register 带 redirect（第一道判定，不依赖后端——防 DEBUG 态虚拟 admin 绕过）
 *   2) 有 token   → GET /api/auth/me 校验 role∈{admin,manager}，否则跳 /dashboard.html + 横幅"无管理权限"
 *   3) auth/me 失败(网络/停机)无法确认身份 → 按未授权跳登录，不静默
 * 守卫通过前不发任何 admin API 请求：数据注入收敛为 window.bootAdmin()，由守卫通过后调用。
 * 兼容性：requireAdmin(onPass?) 缺省 onPass 时，通过后轮询 window.bootAdmin（向后兼容原 runBoot，
 *          因为各页 bootAdmin 定义在其后独立 <script>，需等待其就绪）。
 */
(function (global) {
  var ADMIN = { admin: 1, manager: 1 };

  function banner(txt) {
    try {
      var d = document.createElement("div");
      d.style.cssText = "position:fixed;left:0;right:0;top:0;z-index:99999;padding:14px;text-align:center;font-weight:700;background:#fb7185;color:#fff;box-shadow:0 2px 10px rgba(0,0,0,.25)";
      d.textContent = txt;
      document.body.appendChild(d);
    } catch (e) {}
  }

  // 缺省回调：轮询 window.bootAdmin 最多 30 次（3s），兜底页面 bootAdmin 定义滞后的竞态
  var __rt = 0;
  function runBoot() {
    var fn = global.bootAdmin;
    if (typeof fn === "function") { try { fn(); } catch (e) {} }
    else if (__rt++ < 30) setTimeout(runBoot, 10);
  }

  function gotoLogin(redir) {
    var target = "";
    try { target = EAPI.buildLoginUrl(redir); } catch (e) { target = "/login-register.html"; }
    try { location.replace(target); } catch (e) {}
  }

  function requireAdmin(onPass) {
    if (!global.EAPI) return; // edu-api.js 未加载则不守卫（页面正常都已先引 edu-api.js）
    var redir = "";
    try { redir = location.pathname + location.search; } catch (e) { redir = "/"; }
    if (!EAPI.store.getToken()) { gotoLogin(redir); return; } // 第一道判定：无 token 直接跳登录
    EAPI.get("/api/auth/me").then(function (me) {
      if (me && ADMIN[me.role]) {
        if (typeof onPass === "function") { try { onPass(); } catch (e) {} }
        else runBoot();
      } else {
        banner("无管理权限（当前角色 " + (me && me.role ? me.role : "未知") + "），正在跳回学习端…");
        setTimeout(function () { try { location.replace("/dashboard.html"); } catch (e) {} }, 1200);
      }
    }).catch(function () {
      banner("身份校验失败，无法确认管理权限，正在跳转登录…");
      setTimeout(function () { gotoLogin(redir); }, 1200);
    });
  }

  global.eduGuard = { requireAdmin: requireAdmin };
})(window);