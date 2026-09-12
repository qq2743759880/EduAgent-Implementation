/**
 * B2 refine-layer · 共享 queryClient 单例(TanStack Query v5)
 * - B2 的 queryClient = B3 dataProvider/Refine 的同一个 queryClient(杜绝双轨,B0 §5 修订定义)
 * - 注入方式经实测以 @refinedev/core@5 的 <Refine queryClient={...}> 为准(见 index.ts bindEduRefine)
 * - retry 规则:4xx 一律不重试(401 已被 http.ts interceptor 单飞刷新消化,不该在 query 层重试)
 */

import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "./http.js";

/** 按项目约定构造 QueryClient(与 edu 后端契约对齐的默认项) */
export function createEduQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false, // 管理端多面板场景,避免聚焦抖动
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false; // 4xx 不重试
          return failureCount < 2; // 网络错/5xx 最多重试 2 次
        },
      },
      mutations: {
        retry: false, // 写路径永不自动重试(幂等性未逐端点证实,保守)
      },
    },
  });
}

/** 模块级单例:整个应用(Refine + 任何裸 useQuery)共享同一实例 */
let singleton: QueryClient | null = null;

export function getEduQueryClient(): QueryClient {
  if (!singleton) singleton = createEduQueryClient();
  return singleton;
}
