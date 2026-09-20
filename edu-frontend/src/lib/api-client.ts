import axios, {
  AxiosError,
  AxiosRequestConfig,
  InternalAxiosRequestConfig,
} from "axios";

/**
 * 契约冻结①（task10-contract.md v1.1）响应壳：
 *   成功 {code: 0, message: "ok", data: <T>}
 *   失败 {code: "<字符串错误码>", message: "...", data: null}
 * 后端现状（交接单 §8）：成功响应存在「壳」与「裸模型」两种形态
 * （RespWrapMiddleware 为透传占位，task11+ 逐域补壳），因此拦截器对
 * 壳形态解包返回 data，对裸形态透传业务体 —— 调用方统一拿到业务数据。
 */
export interface ApiEnvelope<T = unknown> {
  code?: number | string;
  message?: string;
  data?: T;
}

export interface ApiErrorPayload {
  code?: number | string;
  message?: string;
  detail?: unknown;
}

function isEnvelope(body: unknown): body is ApiEnvelope {
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    return false;
  }
  const code = (body as ApiEnvelope).code;
  return (
    "code" in body &&
    (typeof code === "number" || typeof code === "string") &&
    // 裸业务体中恰好带 code 字段的防御：壳必须同时携带 message
    typeof (body as ApiEnvelope).message === "string"
  );
}

export class ApiError extends Error {
  public readonly status: number;
  /** 契约 v1.1：失败码为字符串（"40111"）；保留 number 兼容网络错误哨兵与旧调用点 */
  public readonly code: number | string;
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

/**
 * 是否为认证类接口（登录 / 注册）。
 *
 * 这类接口的 401/403 是「业务性失败」（密码错误 / 账号禁用 / 账号已存在），
 * 应由 LoginForm / RegisterForm 原地渲染表单错误横幅（root.server / setError），
 * 而非触发全局登出 + `location.href = "/login"` 重载 —— 否则页面重载会清空
 * 刚设置好的错误横幅，用户看不到任何失败原因（task03 复测 #1）。
 */
export function isAuthEndpoint(url: string | undefined): boolean {
  if (!url) return false;
  return /\/api\/auth\/(?:login|register)(?:[?#]|$)/.test(url);
}

const API_BASE_URL =
  (typeof process !== "undefined" &&
    process.env &&
    (process.env.NEXT_PUBLIC_API_BASE_URL || process.env.API_BASE_URL)) ||
  "http://127.0.0.1:9988";

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
    const controller = config.signal ? null : new AbortController();
    if (controller && !config.signal) {
      config.signal = controller.signal;
    }
    return config;
  },
  (err) => Promise.reject(err),
);

/**
 * 成功路径拦截器（task40 核心）：
 * - 壳形态且 code === 0 → 直接返回 data（调用方零解包）
 * - 壳形态且 code !== 0（string|number 兼容）→ reject ApiError（message 可 toast）
 * - 裸形态（auth JWT / 未包壳端点）→ 透传业务体
 */
api.interceptors.response.use(
  (resp) => {
    const body = resp.data;
    if (isEnvelope(body)) {
      if (body.code === 0) {
        return body.data;
      }
      return Promise.reject(
        new ApiError(resp.status, {
          code: body.code,
          message: body.message,
          detail: body.data ?? undefined,
        }),
      );
    }
    return body;
  },
  async (error: AxiosError<ApiErrorPayload>) => {
    const status = error.response?.status ?? 0;
    const rawData = error.response?.data;
    let payload: ApiErrorPayload;
    /* 兼容响应体结构：
       0) 网络错误 / 连接拒绝 / 超时：无响应体（error.response 为 undefined），
          status 保留 0，输出明确文案，不伪装成 500（对抗 #5 修复）
       1) 标准：{ code, message, data:null }  ← 契约① 失败壳（AppException handler）
       2) FastAPI 默认 HTTPException：{ detail: { code, message, detail? } }  ← 走不到我们 handler 的降级场景
       3) FastAPI 默认校验错误：{ detail: [{ loc, msg, type }] }
       4) 有响应体但结构未知：用 error.message
    */
    if (!error.response) {
      payload = {
        code: 0,
        message:
          error.code === "ECONNABORTED"
            ? "请求超时，请检查网络后重试"
            : "网络错误，无法连接后端服务，请检查网络",
      };
    } else if (rawData && typeof rawData === "object") {
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
          code:
            typeof d.code === "number" || typeof d.code === "string"
              ? d.code
              : undefined,
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
        payload = { code: "42200", message: msg, detail: obj.detail };
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
      // 登录/注册等认证接口失败：由表单页原地渲染错误横幅（root.server / setError），
      // 不触发全局登出 + 页面重载（否则重载会清空错误提示，用户看不到失败原因）。
      // 仅对非认证接口的 401/403 执行全局回调（清 token + 跳 /login）。
      if (!isAuthEndpoint(error.config?.url)) {
        try {
          await _onUnauthorized?.(status);
        } catch {
          /* ignore handler own errors, keep propagating ApiError */
        }
      }
    }
    return Promise.reject(new ApiError(status, payload));
  },
);

/**
 * 类型化 HTTP 辅助（task40）：拦截器已解包，await 结果即业务数据，
 * 客户端函数禁止再写 `.data` 解包。类型断言与运行时行为一致
 * （axios 泛型声明的是 AxiosResponse，拦截器已剥壳）。
 */
export const http = {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return api.get(url, config) as unknown as Promise<T>;
  },
  post<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return api.post(url, body, config) as unknown as Promise<T>;
  },
  put<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return api.put(url, body, config) as unknown as Promise<T>;
  },
  patch<T>(url: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return api.patch(url, body, config) as unknown as Promise<T>;
  },
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return api.delete(url, config) as unknown as Promise<T>;
  },
};

export default api;
