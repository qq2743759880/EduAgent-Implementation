import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

/**
 * 后端结构化错误体（edu-agent AppException 统一返回）：
 * { code: number; message: string; detail: unknown }
 */
export interface ApiErrorPayload {
  code?: number;
  message?: string;
  detail?: unknown;
}

export class ApiError extends Error {
  public readonly status: number;
  public readonly code: number;
  public readonly detail?: unknown;

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.message || `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.code ?? status * 100;
    this.detail = payload.detail;
  }
}

export type UnauthorizedHandler = (status: 401 | 403) => void | Promise<void>;

let _onUnauthorized: UnauthorizedHandler | null = null;

/** 注册 401/403 全局回调（auth-client 在初始化后挂上，用来清 token 并跳登录） */
export function onApiUnauthorized(handler: UnauthorizedHandler) {
  _onUnauthorized = handler;
}

const API_BASE_URL =
  (typeof process !== "undefined" &&
    process.env &&
    (process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_BASE_URL)) ||
  "http://127.0.0.1:8000";

/**
 * 默认去掉末尾斜杠，避免拼 /api/auth/login 时出现双斜杠
 */
export const API_BASE = API_BASE_URL.endsWith("/")
  ? API_BASE_URL.slice(0, -1)
  : API_BASE_URL;

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 15_000,
  headers: {
    "Content-Type": "application/json",
  },
});

/** 请求拦截器：由 auth-client 动态注入 Authorization，这里不直接读 localStorage */
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const controller = config.signal
      ? null
      : new AbortController();
    if (controller && !config.signal) {
      config.signal = controller.signal;
    }
    return config;
  },
  (err) => Promise.reject(err),
);

/** 响应拦截器：非 2xx 统一转 ApiError；401/403 回调登出 */
api.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError<ApiErrorPayload>) => {
    const status = error.response?.status ?? 0;
    const rawData = error.response?.data;
    let payload: ApiErrorPayload;
    /* 兼容响应体结构：
       1) 标准：{ code, message, detail }  ← AppException / HTTPException handler / 422 handler 都会返回这种
       2) FastAPI 默认 HTTPException：{ detail: { code, message, detail? } }  ← 走不到我们 handler 的降级场景
       3) FastAPI 默认校验错误：{ detail: [{ loc, msg, type }] }
       4) 网络错误 / 无响应体：用 error.message
    */
    if (rawData && typeof rawData === "object") {
      const obj = rawData as ApiErrorPayload & {
        detail?: unknown;
      };
      if (typeof obj.message === "string") {
        payload = obj;
      } else if (
        obj.detail &&
        typeof obj.detail === "object" &&
        !Array.isArray(obj.detail)
      ) {
        const d = obj.detail as { code?: unknown; message?: unknown; detail?: unknown };
        payload = {
          code: typeof d.code === "number" ? d.code : undefined,
          message: typeof d.message === "string" ? d.message : undefined,
          detail: d.detail ?? obj.detail,
        };
      } else if (Array.isArray(obj.detail) && obj.detail.length) {
        // FastAPI 原生 422 形态：[{ loc, msg, type }]
        const first = obj.detail[0];
        const msg =
          first && typeof first === "object" && "msg" in first
            ? String((first as { msg?: unknown }).msg ?? "参数校验失败")
            : "参数校验失败";
        payload = { code: 42200, message: msg, detail: obj.detail };
      } else {
        payload = {
          message: (typeof (obj as unknown as { detail?: unknown }).detail === "string"
            ? String((obj as unknown as { detail: unknown }).detail)
            : undefined) ||
            error.message ||
            "网络错误",
          detail: obj.detail ?? rawData,
        };
      }
    } else {
      payload = { message: error.message || "网络错误" };
    }
    if (status === 401 || status === 403) {
      try {
        await _onUnauthorized?.(status);
      } catch {
        /* ignore handler own errors, keep propagating ApiError */
      }
    }
    return Promise.reject(new ApiError(status || 500, payload));
  },
);

export default api;
