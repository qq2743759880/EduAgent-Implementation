/**
 * 管理端 API 通用骨架（task02，G2 管理端布局与权限）
 *
 * 数据流：页面 → lib/api/admin.ts（本骨架） → lib/api-client.ts（axios 实例，
 *         baseURL=http://127.0.0.1:8000，JWT 由 auth-client 拦截器注入 Authorization）
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
import { api, ApiError } from "@/lib/api-client";

export type { ApiError };
export type { AdminApiErrorBody, AdminPage, AdminPageParams, AdminOkResponse } from "@/lib/admin-api-types";

/** 通用 GET：query params 交给 axios 序列化；失败抛 ApiError（不静默吞错） */
export async function adminGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const { data } = await api.get<T>(path, { params });
  return data;
}

/** 通用 POST：写操作失败必须抛（调用方 toast + console.error） */
export async function adminPost<T>(path: string, body?: unknown): Promise<T> {
  const { data } = await api.post<T>(path, body);
  return data;
}

/** 通用 PATCH：写操作失败必须抛 */
export async function adminPatch<T>(path: string, body?: unknown): Promise<T> {
  const { data } = await api.patch<T>(path, body);
  return data;
}

/** 通用 DELETE：写操作失败必须抛 */
export async function adminDelete<T>(path: string): Promise<T> {
  const { data } = await api.delete<T>(path);
  return data;
}

/** 把任意错误归一为 {status, code, message, detail} 壳（供调用方展示 / console.error） */
export function toAdminErrorBody(
  err: unknown,
): { status: number; code: number; message: string; detail?: unknown } {
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
