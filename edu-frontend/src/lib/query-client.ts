"use client";

import { MutationCache, QueryCache, QueryClient, defaultShouldDehydrateQuery, isServer } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "./api-client";

/** 通用 ApiError → toast（message + 可读 detail） */
function toastApiError(error: ApiError) {
  const msg = error.message || `请求失败（${error.status}）`;
  toast.error(msg, { description: typeof error.detail === "string" ? error.detail : undefined });
}

/**
 * QueryCache onError（读操作）：401/403 早退静默 —— api-client 的 onApiUnauthorized
 * 已负责清 token + 跳登录/无权限守卫，加载场景重复 toast 反而噪声（task37 差异单② 保持此语义）。
 */
export function globalQueryError(error: unknown) {
  if (isServer) return;
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      console.error("[query] 请求被拒绝", { status: error.status, message: error.message });
      return;
    }
    toastApiError(error);
    return;
  }
  if (error instanceof Error) {
    toast.error(error.message || "请求失败");
    return;
  }
  toast.error("请求失败，请稍后重试");
}

/**
 * MutationCache onError（写操作）：401/403 统一 toast，不再依赖组件级重复补偿
 * （task37 差异单② 修复）。api-client 的 onApiUnauthorized 仍负责清 token+跳登录；
 * 此处 toast 仅提示「本次写操作被拒」，与登出跳转职责不重叠、不成双弹。
 */
export function globalMutationError(error: unknown) {
  if (isServer) return;
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      console.error("[query] 请求被拒绝", { status: error.status, message: error.message });
    }
    toastApiError(error);
    return;
  }
  if (error instanceof Error) {
    toast.error(error.message || "请求失败");
    return;
  }
  toast.error("请求失败，请稍后重试");
}

/** 导出工厂：测试可复用真实 globalQueryError/globalMutationError 缓存校验契约行为 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30 * 1000,
        gcTime: 5 * 60 * 1000,
        refetchOnWindowFocus: false,
        refetchOnMount: true,
        retry: (count, err) => {
          if (count >= 1) return false;
          if (err instanceof ApiError) {
            /* 4xx 不重试，5xx 最多重试 1 次 */
            return err.status >= 500;
          }
          return false;
        },
      },
      dehydrate: {
        shouldDehydrateQuery: (q) => defaultShouldDehydrateQuery(q) || q.state.status === "pending",
      },
    },
    queryCache: new QueryCache({
      onError: globalQueryError,
    }),
    mutationCache: new MutationCache({
      onError: globalMutationError,
    }),
  });
}

let browserQueryClient: QueryClient | undefined;

/** App Router 推荐：SSR 每次 fresh；客户端 singleton 避免水合冲突 */
export function getQueryClient(): QueryClient {
  if (isServer) return createQueryClient();
  if (!browserQueryClient) browserQueryClient = createQueryClient();
  return browserQueryClient;
}

export default getQueryClient;
