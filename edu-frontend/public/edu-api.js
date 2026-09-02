/* EduAgent 静态页共享 API 客户端（fe-html 对接后端 8000）
 * - 封装 fetch + JWT + 响应壳解包 {code,message,data}
 * - task101 加固契约：
 *   1) 401 判定 = resp.status === 401：无条件清 token，并跳 login-register.html?redirect=<当前路径+query>
 *      （登录页自身跳过跳转，避免登录失败原地循环）
 *   2) 非 2xx（含非 JSON 网关错误、FastAPI {detail}、壳外响应）一律抛带 status 的 Error（err.status/err.body），
 *      禁止静默 return null；2xx 空 body 才允许 null（204/无内容）
 *   3) BASE 级联覆盖：window.EDU_API_BASE > 同源 :3000→:8000 > 默认 http://127.0.0.1:8000；
 *      运行时可再直接赋值 EAPI.BASE（request 每次调用时读取）
 *   4) AbortController 超时，默认 15s（EAPI.TIMEOUT_MS 可调）；chat SSE 走页面原生 fetch，不经此通道不受影响
 *   5) EAPI.logout()（清 token+跳登录）；EAPI.onError(fn) 全局错误钩子（task122 toast 接入点，返回退订函数）；
 *      所有 API 错误统一 console.error("[EAPI]", err) 后 rethrow，不再静默吞
 *   6) EAPI.getRedirectParam() / EAPI.buildLoginUrl(url)：?redirect= 参数读取与登录链接构造（task108 登录页复用），
 *      仅接受站内相对路径（防开放跳转）
 * - 向后兼容：EAPI.get/post/put/patch/del、EAPI.store.{getToken,setToken,clear}、EAPI.BASE、EAPI.TOKEN_KEY 签名不变
 * - 用法：<script src="/edu-api.js"></script>，调 EAPI.get/post(...)
 */
(function (global) {
  const TOKEN_KEY = "edu:auth:token";
  const DEFAULT_BASE = "http://127.0.0.1:8000";
  const LOGIN_PAGE = "/login-register.html";
  const DEFAULT_TIMEOUT_MS = 15000;
  const errorHandlers = [];

  const trimSlash = (s) => String(s || "").replace(/\/+$/, "");

  // 改动点3：BASE 级联解析（加载时确定初值，运行时改 EAPI.BASE 亦可覆盖）
  function resolveBase() {
    let override = "";
    try { override = global.EDU_API_BASE || ""; } catch (e) {}
    if (override) return trimSlash(override);
    try {
      if (typeof location !== "undefined" && location.origin && /:3000$/.test(location.origin)) {
        return trimSlash(location.origin.replace(":3000", ":8000"));
      }
    } catch (e) {}
    return DEFAULT_BASE;
  }
  const initialBase = resolveBase();

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

  // ---- 改动点6：?redirect= 工具（task108 登录页复用）----
  function sanitizeRedirect(r) {
    if (typeof r !== "string") return "";
    const s = r.trim();
    if (!s || s.charAt(0) !== "/") return "";            // 只允许站内相对路径
    if (s.charAt(1) === "/") return "";                   // 禁 //protocol-relative
    if (/^[a-zA-Z][a-zA-Z0-9+.\-]*:/.test(s)) return ""; // 禁带协议的外链
    return s;
  }
  function getRedirectParam() {
    try {
      const q = new URLSearchParams(location.search || "");
      return sanitizeRedirect(q.get("redirect") || "");
    } catch (e) { return ""; }
  }
  function currentPathWithQuery() {
    try { return (location.pathname || "/") + (location.search || ""); } catch (e) { return "/"; }
  }
  function onLoginPage() {
    try { return /(^|\/)login-register\.html$/.test(location.pathname || ""); } catch (e) { return false; }
  }
  function buildLoginUrl(redirectPath) {
    const target = sanitizeRedirect(redirectPath || "");
    return target ? LOGIN_PAGE + "?redirect=" + encodeURIComponent(target) : LOGIN_PAGE;
  }
  function gotoLogin(redirectPath) {
    try { window.location.href = buildLoginUrl(redirectPath); } catch (e) {}
  }

  // ---- 改动点5：全局错误钩子 EAPI.onError(fn)，返回退订函数 ----
  function onError(fn) {
    if (typeof fn !== "function") return function () {};
    errorHandlers.push(fn);
    return function () {
      const i = errorHandlers.indexOf(fn);
      if (i >= 0) errorHandlers.splice(i, 1);
    };
  }
  function emitOnce(err) {
    if (!err || err.__eapiEmitted) return;
    err.__eapiEmitted = true;
    for (let i = 0; i < errorHandlers.length; i++) {
      try { errorHandlers[i](err); } catch (e) { /* 钩子自身异常不外泄 */ }
    }
    try { console.error("[EAPI]", (err && err.message) || err, err); } catch (e) {}
  }

  function apiError(status, message, payload) {
    const err = new Error(message || "HTTP " + status);
    err.status = status;
    err.isApiError = true;
    if (payload !== undefined) err.body = payload;
    return err;
  }

  function parseResponse(resp) {
    return resp.text().then((text) => {
      let json = null;
      let isJson = false;
      if (text && text.length) {
        try { json = JSON.parse(text); isJson = true; } catch (e) {}
      }
      // 改动点1：401 只看 HTTP 状态码，无条件清 token；非登录页跳登录并带回跳参数
      if (resp.status === 401) {
        store.clear();
        if (typeof window !== "undefined" && !onLoginPage()) gotoLogin(currentPathWithQuery());
        throw apiError(401, (isJson && json && (json.message || json.detail)) || "登录凭证无效或已过期", json);
      }
      // 改动点2：非 2xx 一律抛带 status 的 Error，禁止 return null
      if (!resp.ok) {
        const msg = isJson && json ? (json.message || (typeof json.detail === "string" ? json.detail : "")) : "";
        throw apiError(resp.status, msg || "HTTP " + resp.status, json);
      }
      if (!isJson) {
        if (text && text.length) throw apiError(resp.status, "响应非 JSON（HTTP " + resp.status + "）"); // 壳外/网关异常响应
        return null; // 204/空 body
      }
      if (json && typeof json === "object" && !Array.isArray(json) && json.code !== undefined) {
        if (json.code === 0) return json.data; // 标准壳：解包 data
        throw apiError(resp.status, json.message || "请求失败（code=" + json.code + "）", json); // 2xx 业务错误
      }
      return json; // 裸 DTO（如分页壳 {total,page,page_size,items}）
    });
  }

  function request(method, path, body) {
    const base = trimSlash(EAPI.BASE) || DEFAULT_BASE; // 每次调用时读取，支持运行时覆盖
    const p = path && path.charAt(0) === "/" ? path : "/" + (path || "");
    const headers = { "Content-Type": "application/json" };
    const token = store.getToken();
    if (token) headers.Authorization = "Bearer " + token;

    // 改动点4：AbortController 超时（chat SSE 用页面原生 fetch，不走这里）
    const timeoutMs = typeof EAPI.TIMEOUT_MS === "number" && EAPI.TIMEOUT_MS > 0 ? EAPI.TIMEOUT_MS : DEFAULT_TIMEOUT_MS;
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;

    return fetch(base + p, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller ? controller.signal : undefined,
    }).then(
      (resp) => {
        if (timer !== null) clearTimeout(timer);
        return parseResponse(resp);
      },
      (e) => {
        if (timer !== null) clearTimeout(timer);
        if (controller && controller.signal.aborted) {
          const te = apiError(0, "请求超时（" + Math.round(timeoutMs / 1000) + "s）：" + method + " " + p);
          te.name = "TimeoutError";
          te.isTimeout = true;
          throw te;
        }
        const ne = e instanceof Error ? e : new Error(String(e || "网络错误"));
        ne.isNetworkError = true;
        if (!ne.message) ne.message = "网络错误：" + method + " " + p;
        throw ne;
      }
    ).catch((e) => {
      emitOnce(e); // 改动点5：所有 API 错误统一过 onError 钩子 + console.error，不再静默
      throw e;
    });
  }

  // 改动点5：logout = 清 token + 跳登录（登录页自身只清 token）
  function logout() {
    store.clear();
    if (typeof window !== "undefined" && !onLoginPage()) gotoLogin(currentPathWithQuery());
  }

  const EAPI = {
    BASE: initialBase,
    TOKEN_KEY,
    TIMEOUT_MS: DEFAULT_TIMEOUT_MS,
    get: (p) => request("GET", p),
    post: (p, b) => request("POST", p, b),
    put: (p, b) => request("PUT", p, b),
    patch: (p, b) => request("PATCH", p, b),
    del: (p) => request("DELETE", p),
    store,
    logout,
    onError,
    getRedirectParam,
    buildLoginUrl,
  };

  global.EAPI = EAPI;
})(window);
