"use client";

import { MutationCache, QueryCache, QueryClient, defaultShouldDehydrateQuery, isServer } from "@tanstack/react-query";
import { toast } from "sonner";

import { ApiError } from "./api-client";

function globalOnError(error: unknown) {
  if (isServer) return;
  if (error instanceof ApiError) {
    if (error.status === 401 || error.status === 403) {
      /* auth-client 已经处理了 logout + redirect，这里不重复 toast 登录过期消息 */
      return;
    }
    const msg = error.message || `请求失败（${error.status}）`;
    toast.error(msg, { description: typeof error.detail === "string" ? error.detail : undefined });
    return;
  }
  if (error instanceof Error) {
    toast.error(error.message || "请求失败");
    return;
  }
  toast.error("请求失败，请稍后重试");
}

function makeQueryClient(): QueryClient {
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
      onError: globalOnError,
    }),
    mutationCache: new MutationCache({
      onError: globalOnError,
    }),
  });
}

let browserQueryClient: QueryClient | undefined;

/** App Router 推荐：SSR 每次 fresh；客户端 singleton 避免水合冲突 */
export function getQueryClient(): QueryClient {
  if (isServer) return makeQueryClient();
  if (!browserQueryClient) browserQueryClient = makeQueryClient();
  return browserQueryClient;
}

export default getQueryClient;
