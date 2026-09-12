/**
 * B2 refine-layer · HTTP 请求封装 + 401 single-flight interceptor
 * 行为基准 = edu-frontend/public/edu-api.js(B2 只读参考,禁改该文件),语义逐条等价:
 *  1) 壳解包:2xx + {code:0,data} → data;2xx + code!==0 → 抛业务错;裸 DTO 原样;空 body → null;非 JSON 非空 → 抛错
 *  2) 401(W1-C1 单飞):无条件先判 _replayed → 已重放则清 token+跳登录+抛错;
 *     无 refresh_token → 清 token+跳登录+抛错;
 *     否则模块级单飞 refresh(并发 401 复用同一 Promise,仅发一次 /api/auth/refresh)
 *     → 成功:重放原请求恰一次;失败:清 token+跳登录+抛错
 *  3) refresh 请求:POST {base}/api/auth/refresh,body {refresh_token},不带过期 access(防 401 死锁);
 *     成功更新 access + 滑动续期 refresh
 *  4) BASE 级联:window.EDU_API_BASE > 同源 :3000→:8000 > http://127.0.0.1:8000
 *  5) AbortController 超时,默认 15s,超时错误 name=TimeoutError
 * 差异(诚实登记):登录页路径/跳转动作改为可注入(默认值仍为 /login-register.html + location.href),
 *   便于 React 宿主(B3)与 scratch 测试替换;默认行为与 edu-api 等价。
 */

import { tokenStore, type TokenStore } from "./auth-store";

const DEFAULT_BASE = "http://127.0.0.1:8000";
const REFRESH_PATH = "/api/auth/refresh";
const DEFAULT_LOGIN_PAGE = "/login-register.html";
const DEFAULT_TIMEOUT_MS = 15000;

/** 带 status/body 的 API 错误(与 edu-api apiError 同形) */
export class ApiError extends Error {
  status: number;
  isApiError = true;
  body?: unknown;
  constructor(status: number, message?: string, payload?: unknown) {
    super(message || "HTTP " + status);
    this.name = "ApiError";
    this.status = status;
    if (payload !== undefined) this.body = payload;
  }
}

export interface HttpConfig {
  /** API 基址;缺省走 edu-api 同款级联解析 */
  baseURL?: string;
  /** 登录页路径(用于 onLoginPage 判断与跳转目标),默认 /login-register.html */
  loginPage?: string;
  /** 请求超时 ms,默认 15000 */
  timeoutMs?: number;
  /** 跳登录动作注入点;默认 window.location.href(浏览器),测试注入 stub */
  onRedirect?: (loginUrl: string) => void;
  /** token 存取注入点;默认 localStorage 同键名 tokenStore */
  store?: TokenStore;
}

interface ResolvedConfig {
  loginPage: string;
  timeoutMs: number;
  onRedirect: (loginUrl: string) => void;
  store: TokenStore;
}

function trimSlash(s: string | undefined): string {
  return String(s || "").replace(/\/+$/, "");
}

function sanitizeRedirect(r: unknown): string {
  if (typeof r !== "string") return "";
  const s = r.trim();
  if (!s || s.charAt(0) !== "/") return ""; // 只允许站内相对路径
  if (s.charAt(1) === "/") return ""; // 禁 //protocol-relative
  if (/^[a-zA-Z][a-zA-Z0-9+.\-]*:/.test(s)) return ""; // 禁带协议的外链
  return s;
}

function currentPathWithQuery(): string {
  try {
    if (typeof location === "undefined") return "/";
    return (location.pathname || "/") + (location.search || "");
  } catch {
    return "/";
  }
}

function buildLoginUrl(loginPage: string, redirectPath?: string): string {
  const target = sanitizeRedirect(redirectPath || "");
  return target ? loginPage + "?redirect=" + encodeURIComponent(target) : loginPage;
}

function isOnLoginPage(loginPage: string): boolean {
  try {
    if (typeof location === "undefined") return false;
    const escaped = loginPage.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp("(^|\\/)" + escaped + "$").test(location.pathname || "");
  } catch {
    return false;
  }
}

function defaultRedirect(loginUrl: string): void {
  try {
    if (typeof window !== "undefined") window.location.href = loginUrl;
  } catch {
    /* 非浏览器环境:静默(等价 edu-api 的 try/catch) */
  }
}

const cfg: ResolvedConfig = {
  loginPage: DEFAULT_LOGIN_PAGE,
  timeoutMs: DEFAULT_TIMEOUT_MS,
  onRedirect: defaultRedirect,
  store: tokenStore,
};

/** 宿主/测试覆盖配置(部分覆盖,合并进当前配置) */
export function configureHttp(patch: HttpConfig): void {
  if (patch.loginPage !== undefined) cfg.loginPage = patch.loginPage;
  if (patch.timeoutMs !== undefined && patch.timeoutMs > 0) cfg.timeoutMs = patch.timeoutMs;
  if (patch.onRedirect !== undefined) cfg.onRedirect = patch.onRedirect;
  if (patch.store !== undefined) cfg.store = patch.store;
  if (patch.baseURL !== undefined) explicitBase = trimSlash(patch.baseURL) || DEFAULT_BASE;
}

// ---- BASE 级联(edu-api resolveBase 等价;模块加载时定初值) ----
let explicitBase = "";

function resolveInitialBase(): string {
  try {
    if (typeof window !== "undefined") {
      const override = (window as unknown as { EDU_API_BASE?: string }).EDU_API_BASE || "";
      if (override) return trimSlash(override);
    }
    if (typeof location !== "undefined" && location.origin && /:3000$/.test(location.origin)) {
      return trimSlash(location.origin.replace(":3000", ":8000"));
    }
  } catch {
    /* 非浏览器环境走默认 */
  }
  return DEFAULT_BASE;
}

function baseURL(): string {
  return explicitBase || resolveInitialBase();
}

/** 当前生效 BASE(B3 挂接/诊断用) */
export function getBaseURL(): string {
  return baseURL();
}

// ---- 全局错误钩子(与 edu-api onError 同形:注册返回退订函数) ----
type ErrorHandler = (err: unknown) => void;
const errorHandlers: ErrorHandler[] = [];

export function onError(fn: ErrorHandler): () => void {
  if (typeof fn !== "function") return () => {};
  errorHandlers.push(fn);
  return () => {
    const i = errorHandlers.indexOf(fn);
    if (i >= 0) errorHandlers.splice(i, 1);
  };
}

function emitOnce(err: unknown): void {
  const e = err as { __eduEmitted?: boolean };
  if (!e || e.__eduEmitted) return;
  e.__eduEmitted = true;
  for (const fn of errorHandlers) {
    try {
      fn(err);
    } catch {
      /* 钩子自身异常不外泄(edu-api 等价) */
    }
  }
  try {
    console.error("[edu-refine-http]", (err as Error)?.message || err, err);
  } catch {
    /* ignore */
  }
}

// ---- 响应壳解包(edu-api parseResponse 等价) ----
function parseResponse(resp: Response): Promise<unknown> {
  return resp.text().then((text) => {
    let json: unknown = null;
    let isJson = false;
    if (text && text.length) {
      try {
        json = JSON.parse(text);
        isJson = true;
      } catch {
        /* 落入下方非 JSON 分支 */
      }
    }
    if (!resp.ok) {
      const j = json as { message?: string; detail?: string } | null;
      const msg = isJson && j ? j.message || (typeof j.detail === "string" ? j.detail : "") : "";
      throw new ApiError(resp.status, msg || "HTTP " + resp.status, json);
    }
    if (!isJson) {
      if (text && text.length) throw new ApiError(resp.status, "响应非 JSON（HTTP " + resp.status + "）");
      return null; // 204/空 body
    }
    const obj = json as { code?: unknown; message?: string; data?: unknown } | null;
    if (obj && typeof obj === "object" && !Array.isArray(obj) && obj.code !== undefined) {
      if (obj.code === 0) return obj.data; // 标准壳:解包 data
      throw new ApiError(resp.status, obj.message || "请求失败（code=" + String(obj.code) + "）", json); // 2xx 业务错误
    }
    return json; // 裸 DTO(如分页壳 {total,page,page_size,items})
  });
}

// ---- W1-C1:单飞 refresh + 重放(模块级 Promise,并发 401 只发一次 /refresh) ----
let refreshPromise: Promise<boolean> | null = null;

function doRefresh(resolve: (ok: boolean) => void): void {
  const rt = cfg.store.getRefreshToken();
  if (!rt) {
    resolve(false);
    return;
  }
  // refresh 用 body 携带 refresh_token,不带过期 access(否则 401 死锁);独立超时(edu-api 等价)
  const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), cfg.timeoutMs) : null;
  fetch(baseURL() + REFRESH_PATH, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: rt }),
    signal: controller ? controller.signal : undefined,
  }).then(
    (resp) => {
      if (timer !== null) clearTimeout(timer);
      if (resp.status !== 200) {
        resolve(false); // refresh 401/失败 → 走登录
        return;
      }
      resp
        .text()
        .then((text) => {
          let json: unknown = null;
          try {
            json = JSON.parse(text);
          } catch {
            /* 解析失败按无凭证处理 */
          }
          const obj = json as { code?: number; data?: { access_token?: string; refresh_token?: string } } | null;
          const data = obj && obj.code === 0 && obj.data ? obj.data : null;
          const at = data && typeof data.access_token === "string" ? data.access_token : "";
          if (at) {
            cfg.store.setToken(at); // 更新 access
            if (data && typeof data.refresh_token === "string" && data.refresh_token) {
              cfg.store.setRefreshToken(data.refresh_token); // 滑动续期 refresh
            }
            resolve(true);
          } else {
            resolve(false);
          }
        })
        .catch(() => resolve(false));
    },
    () => {
      if (timer !== null) clearTimeout(timer);
      resolve(false); // 网络失败:refresh 挂了 → 登录跳转(edu-api 等价)
    }
  );
}

function scheduleRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = new Promise<boolean>((resolve) => doRefresh(resolve)).then((ok) => {
      refreshPromise = null; // 完成后复位,供下一轮 401 再进入(edu-api 等价)
      return ok;
    });
  }
  return refreshPromise;
}

/** 401 终态:清 token + 跳登录(带 redirect)+ 抛错(edu-api handleUnauthorized 等价) */
function handleUnauthorized(msg?: string): never {
  cfg.store.clear();
  if (typeof window !== "undefined" && !isOnLoginPage(cfg.loginPage)) {
    cfg.onRedirect(buildLoginUrl(cfg.loginPage, currentPathWithQuery()));
  }
  throw new ApiError(401, msg || "登录凭证无效或已过期");
}

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

function request<T>(method: HttpMethod, path: string, body?: unknown, _replayed?: boolean): Promise<T> {
  const base = baseURL();
  const p = path && path.charAt(0) === "/" ? path : "/" + (path || "");
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = cfg.store.getToken();
  if (token) headers.Authorization = "Bearer " + token;

  const controller = typeof AbortController !== "undefined" ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), cfg.timeoutMs) : null;

  return fetch(base + p, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: controller ? controller.signal : undefined,
  }).then(
    (resp) => {
      if (timer !== null) clearTimeout(timer);
      // 401 → W1-C1 单飞 refresh 后重放一次;已重放/无 refresh_token/refresh 失败 → 清 token 跳登录
      if (resp.status === 401) {
        if (_replayed) return handleUnauthorized("重新登录后凭证仍无效");
        if (!cfg.store.getRefreshToken()) return handleUnauthorized();
        return scheduleRefresh().then((ok) => {
          if (!ok) return handleUnauthorized("登录已过期，请重新登录");
          return request<T>(method, path, body, true); // 用新 access 重放原请求一次
        });
      }
      return parseResponse(resp) as Promise<T>;
    },
    (e: unknown) => {
      if (timer !== null) clearTimeout(timer);
      const err = e as { name?: string; message?: string } | undefined;
      if (controller && controller.signal.aborted) {
        const te = new ApiError(0, "请求超时（" + Math.round(cfg.timeoutMs / 1000) + "s）：" + method + " " + p);
        te.name = "TimeoutError";
        (te as ApiError & { isTimeout: boolean }).isTimeout = true;
        throw te;
      }
      const ne = err instanceof Error ? err : new Error(String(err || "网络错误"));
      (ne as Error & { isNetworkError?: boolean }).isNetworkError = true;
      if (!ne.message) ne.message = "网络错误：" + method + " " + p;
      throw ne;
    }
  ).catch((e: unknown) => {
    emitOnce(e); // 所有 API 错误统一过 onError 钩子(edu-api 等价)
    throw e;
  });
}

export const http = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};
