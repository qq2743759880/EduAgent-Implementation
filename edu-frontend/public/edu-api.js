/* EduAgent 静态页共享 API 客户端（fe-html 对接后端 8000）
 * - 封装 fetch + JWT + 响应壳解包 {code,message,data}
 * - 供各糖果色静态页内联 JS 复用
 * - 用法：<script src="/edu-api.js"></script>，调 EAPI.get/post(...)
 */
(function (global) {
  const BASE = "http://127.0.0.1:8000";
  const TOKEN_KEY = "edu:auth:token";

  const store = {
    getToken() {
      try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
    },
    setToken(t) {
      try { localStorage.setItem(TOKEN_KEY, t); } catch (e) {}
    },
    clear() {
      try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
    },
  };

  async function request(method, path, body) {
    const headers = { "Content-Type": "application/json" };
    const token = store.getToken();
    if (token) headers.Authorization = "Bearer " + token;
    const resp = await fetch(BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let json = null;
    try { json = await resp.json(); } catch (e) {}
    if (!resp.ok && json && json.code && typeof json.code === "string") {
      // 业务错误壳：401 清 token 并跳登录
      if (resp.status === 401 && typeof window !== "undefined") {
        store.clear();
        window.location.href = "/login-register.html";
      }
      throw new Error(json.message || ("HTTP " + resp.status));
    }
    if (json && json.code === 0) return json.data;
    if (json && json.code !== undefined) throw new Error(json.message || "请求失败");
    return json; // 裸 DTO（如分页壳）
  }

  const EAPI = {
    BASE,
    TOKEN_KEY,
    get: (p) => request("GET", p),
    post: (p, b) => request("POST", p, b),
    put: (p, b) => request("PUT", p, b),
    patch: (p, b) => request("PATCH", p, b),
    del: (p) => request("DELETE", p),
    store,
  };

  global.EAPI = EAPI;
})(window);
