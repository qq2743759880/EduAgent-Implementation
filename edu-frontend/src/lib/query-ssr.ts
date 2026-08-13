import "server-only";

import { dehydrate, type QueryClient, type QueryKey } from "@tanstack/react-query";

/**
 * 页面级服务端 prefetch 助手（fe-task00 / D3 能力就绪）。
 *
 * 消费方（页面 server wrapper）：
 * ```tsx
 * import { getQueryClient } from "@/lib/query-client";
 * import { prefetchHydratedState } from "@/lib/query-ssr";
 *
 * export default async function Page() {
 *   const queryClient = getQueryClient();               // server 端每请求 fresh
 *   const state = await prefetchHydratedState(queryClient, [
 *     { queryKey: ["module", "entity", "scope"], queryFn: () => fetchPublicData() },
 *   ]);
 *   return <HydrationBoundary state={state}><ClientPage /></HydrationBoundary>;
 * }
 * ```
 *
 * 契约约束：
 *  - 逐条 await prefetchQuery（失败不抛出、随 query 状态脱水）；
 *    `query-client.ts` 的 `dehydrate.shouldDehydrateQuery`（含 pending）随本助手调用生效。
 *  - **鉴权数据禁止传入**：token 存 localStorage（SSR 进程读不到）→ server 端无法注入
 *    Authorization，必然 401。本轮消费方仅限公开/壳层数据。
 *  - 本模块为 server-only（Next.js 16 编译器级实现，无需安装 server-only 包），
 *    禁止被 Client Component 导入。
 */
export interface PrefetchQuerySpec<T = unknown> {
  queryKey: QueryKey;
  queryFn: () => Promise<T>;
  /** 可选：透传 Query 选项（staleTime 等） */
  queryOptions?: Partial<{ staleTime: number; retry: boolean }>;
}

export async function prefetchHydratedState(
  queryClient: QueryClient,
  queries: PrefetchQuerySpec[],
): Promise<ReturnType<typeof dehydrate>> {
  await Promise.all(
    queries.map((q) =>
      queryClient.prefetchQuery({
        queryKey: q.queryKey,
        queryFn: q.queryFn,
        ...q.queryOptions,
      }),
    ),
  );
  return dehydrate(queryClient);
}
