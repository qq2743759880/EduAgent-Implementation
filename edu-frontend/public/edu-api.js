/* EduAgent 静态页共享 API 客户端（fe-html 对接后端 9988）
 * - 封装 fetch + JWT + 响应壳解包 {code,message,data}
 * - task101 加固契约：
 *   1) 401 判定 = resp.status === 401：无条件清 token，并跳 login-register.html?redirect=<当前路径+query>
 *      （登录页自身跳过跳转，避免登录失败原地循环）
 *   2) 非 2xx（含非 JSON 网关错误、FastAPI {detail}、壳外响应）一律抛带 status 的 Error（err.status/err.body），
 *      禁止静默 return null；2xx 空 body 才允许 null（204/无内容）
 *   3) BASE 级联覆盖：window.EDU_API_BASE > 同源 :3322→:9988 > 默认 http://127.0.0.1:9988；
 *      运行时可再直接赋值 EAPI.BASE（request 每次调用时读取）
 *   4) AbortController 超时，默认 15s（EAPI.TIMEOUT_MS 可调）；chat SSE 走页面原生 fetch，不经此通道不受影响
 *   5) EAPI.logout()（清 token+跳登录）；EAPI.onError(fn) 全局错误钩子（task122 toast 接入点，返回退订函数）；
 *      所有 API 错误统一 console.error("[EAPI]", err) 后 rethrow，不再静默吞
 *   6) EAPI.getRedirectParam() / EAPI.buildLoginUrl(url)：?redirect= 参数读取与登录链接构造（task108 登录页复用），
 *      仅接受站内相对路径（防开放跳转）
 *   7) EAPI.pageId(name)：从 location.search 统一读 ?name= 取参（trim，缺参返回 ""），
 *      供详情页/列表页取 id（task102/103/119 复用）；query 优先，不读路径
 * - 向后兼容：EAPI.get/post/put/patch/del、EAPI.store.{getToken,setToken,clear}、EAPI.BASE、EAPI.TOKEN_KEY 签名不变
 * - 用法：<script src="/edu-api.js"></script>，调 EAPI.get/post(...)
 */
(function (global) {
  const TOKEN_KEY = "edu:auth:token";
  const REFRESH_KEY = "edu:auth:refresh";
  const REFRESH_PATH = "/api/auth/refresh";
  const DEFAULT_BASE = "http://127.0.0.1:9988";
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
      if (typeof location !== "undefined" && location.origin && /:3322$/.test(location.origin)) {
        return trimSlash(location.origin.replace(":3322", ":9988"));
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
    getRefreshToken() {
      try { return localStorage.getItem(REFRESH_KEY) || ""; } catch (e) { return ""; }
    },
    setRefreshToken(t) {
      try { localStorage.setItem(REFRESH_KEY, t); } catch (e) {}
    },
    clear() {
      try { localStorage.removeItem(TOKEN_KEY); } catch (e) {}
      try { localStorage.removeItem(REFRESH_KEY); } catch (e) {}
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
  // ---- 改动点7：EAPI.pageId(name) 统一查 query 取参（task102/103/119 复用）----
  function pageId(name) {
    try {
      const q = new URLSearchParams(location.search || "");
      const v = typeof name === "string" ? q.get(name) : q.get("id");
      return v === null || v === undefined ? "" : String(v).trim();
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
      // 改动点1_rev：401 不再在此处理——已上移 request() 走「单飞 refresh + 重放」（W1-C1）；
      //               非 2xx 一律抛带 status 的 Error，禁止 return null
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

  // ---- W1-C1：单飞 refresh + 重放（harden 并发防护；多标签并发 401 只发一次 /refresh）----
  let refreshPromise = null; // 模块级单飞：并发 401 复用同一 refresh Promise，不重复发请求
  function doRefresh(okHandler) {
    const rt = store.getRefreshToken();
    if (!rt) { okHandler(false); return; } // 无 refresh_token → 直接降级登录跳转
    // refresh 用 body 携带 refresh_token，不带过期 access（否则 401 死锁）；独立超时
    const timeoutMs = typeof EAPI.TIMEOUT_MS === "number" && EAPI.TIMEOUT_MS > 0 ? EAPI.TIMEOUT_MS : DEFAULT_TIMEOUT_MS;
    const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    fetch(trimSlash(EAPI.BASE) + REFRESH_PATH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: rt }),
      signal: controller ? controller.signal : undefined,
    }).then((resp) => {
      if (timer !== null) clearTimeout(timer);
      if (resp.status !== 200) { okHandler(false); return; } // refresh 401/失败 → 走登录
      resp.text().then((text) => {
        let json = null;
        try { json = JSON.parse(text); } catch (e) {}
        const data = json && json.code === 0 && json.data ? json.data : null;
        if (data && typeof data.access_token === "string" && data.access_token) {
          store.setToken(data.access_token);               // 更新 access
          if (typeof data.refresh_token === "string" && data.refresh_token) {
            store.setRefreshToken(data.refresh_token);     // 滑动续期 refresh
          }
          okHandler(true);
        } else { okHandler(false); }
      }).catch(() => { okHandler(false); });
    }).catch(() => {
      if (timer !== null) clearTimeout(timer);
      okHandler(false); // 网络失败：refresh 挂了 → 登录跳转（不静默抛网络错误给页面）
    });
  }
  function scheduleRefresh() {
    if (!refreshPromise) {
      refreshPromise = new Promise((resolve) => doRefresh(resolve)).then((ok) => {
        refreshPromise = null; // 完成后复位，供下一轮 401 再进入
        return ok;
      });
    }
    return refreshPromise;
  }
  // 原 401 分支逻辑（改动点1）收敛于此：清 token + 跳登录带 redirect + 抛错（复用 apiError）
  function handleUnauthorized(status, msg) {
    store.clear();
    if (typeof window !== "undefined" && !onLoginPage()) gotoLogin(currentPathWithQuery());
    throw apiError(status || 401, msg || "登录凭证无效或已过期");
  }

  function request(method, path, body, _replayed) {
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
        // 401 → W1-C1 单飞 refresh 后重放一次；已重放/无 refresh_token/refresh 失败 → 走登录
        if (resp.status === 401) {
          if (_replayed) return handleUnauthorized(401, "重新登录后凭证仍无效");
          if (!store.getRefreshToken()) return handleUnauthorized(401);
          return scheduleRefresh().then((ok) => {
            if (!ok) return handleUnauthorized(401, "登录已过期，请重新登录");
            return request(method, path, body, true); // 用新 access 重放原请求一次
          });
        }
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

  // ---- 改动点8（task122）：默认统一错误提示，3s toast + 自动消失 ----
  // 页面无需重复注册；如页面需自定义提示，可再调 EAPI.onError(customFn) 追加。
  // console.error("[EAPI]", ...) 已在 emitOnce 统一输出，此处只负责可见的 toast。
  function defaultErrorToast(err) {
    try {
      if (!err || err.__toasted) return;
      err.__toasted = true;
      if (err.status === 401) return; // 即将跳转登录，不再追加 toast
      var msg = (err && err.message) || "请求失败";
      var reduceMotion = false;
      try { reduceMotion = (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (e) {}
      var root = document.getElementById("eapi-toast-root");
      if (!root) {
        root = document.createElement("div");
        root.id = "eapi-toast-root";
        root.setAttribute("aria-live", "assertive");
        root.setAttribute("role", "status");
        root.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:2147483000;display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none;max-width:min(92vw,520px);font:600 13px/1.45 -apple-system,'Segoe UI',system-ui,sans-serif";
        try { document.body.appendChild(root); } catch (e) { return; }
      }
      var t = document.createElement("div");
      t.textContent = "⚠ " + msg;
      t.style.cssText = "background:#fff;color:#1f2937;border:1px solid #fecaca;border-left:4px solid #ef4444;border-radius:8px;padding:10px 14px;box-shadow:0 6px 18px rgba(0,0,0,.16);opacity:0;transform:translateY(6px);transition:opacity .2s ease,transform .2s ease;pointer-events:auto;max-width:100%;text-align:left;white-space:normal;word-break:break-word";
      root.appendChild(t);
      requestAnimationFrame(function () { t.style.opacity = "1"; t.style.transform = "none"; });
      setTimeout(function () {
        if (reduceMotion) { if (t.parentNode) t.parentNode.removeChild(t); return; }
        t.style.opacity = "0"; t.style.transform = "translateY(6px)";
        setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 220);
      }, 3000);
    } catch (e) {}
  }
  onError(defaultErrorToast);

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
    pageId,
  };

  global.EAPI = EAPI;
})(window);
