/**
 * 管理端 API 通用骨架（task02，G2 管理端布局与权限）
 *
 * 数据流：页面 → lib/api/admin.ts（本骨架） → lib/api-client.ts（axios 实例，
 *         baseURL=http://127.0.0.1:9988，JWT 由 auth-client 拦截器注入 Authorization）
 *
 * 错误契约（R-7 治理 / 设计指南 §5.1 / dev-plan 红线 4）：
 *  - 后端统一错误壳 {code, message, detail} 已由 api-client 响应拦截器归一为
 *    ApiError（status / code / message / detail 四字段）；
 *  - 本层**绝不 catch 吞错**：列表与写操作失败一律向上抛 ApiError，由调用方
 *    （useMutation onError → toast + console.error）提示；
 *  - 写操作（POST/PATCH/DELETE）失败必须抛，禁止返回空态冒充成功。
 *
 * task03/04 模块（lib/api/admin/{courses,questions,users,rag,mcp}.ts）统一 import 本骨架。
 */
import { http, ApiError } from "@/lib/api-client";

export type { ApiError };
export type { AdminApiErrorBody, AdminPage, AdminPageParams, AdminOkResponse } from "@/lib/admin-api-types";

/** 通用 GET：query params 交给 axios 序列化；失败抛 ApiError（不静默吞错） */
export function adminGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  return http.get<T>(path, { params });
}

/**
 * 通用 POST：写操作失败必须抛（调用方 toast + console.error）。
 * config.params：部分管理端端点（如分片上传 init/finalize/bind）虽是 POST，但参数走 query string。
 * 仅当传 config 时携带第三个参数，避免破坏无 config 调用方的既有 2 参数契约。
 */
export function adminPost<T>(
  path: string,
  body?: unknown,
  config?: { params?: Record<string, unknown> },
): Promise<T> {
  return config ? http.post<T>(path, body, config) : http.post<T>(path, body);
}

/** 通用 PATCH：写操作失败必须抛 */
export function adminPatch<T>(path: string, body?: unknown): Promise<T> {
  return http.patch<T>(path, body);
}

/** 通用 DELETE：写操作失败必须抛 */
export function adminDelete<T>(path: string): Promise<T> {
  return http.delete<T>(path);
}

/** 把任意错误归一为 {status, code, message, detail} 壳（供调用方展示 / console.error） */
export function toAdminErrorBody(
  err: unknown,
): { status: number; code: number | string; message: string; detail?: unknown } {
  if (err instanceof ApiError) {
    // status=0 为网络错误（api-client 已输出明确文案，见对抗 #5），不再伪装成 500
    const message =
      err.status === 0
        ? err.message || "网络错误，无法连接后端服务，请检查网络"
        : err.message || `请求失败（${err.status}）`;
    return {
      status: err.status,
      code: err.code,
      message,
      detail: err.detail,
    };
  }
  return {
    status: 0,
    code: 0,
    message:
      err instanceof Error
        ? err.message
        : "网络错误，无法连接后端服务，请检查网络",
    detail: undefined,
  };
}
