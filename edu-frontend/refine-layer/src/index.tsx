/**
 * B2 refine-layer · 统一出口(B3 挂接点)
 * 交付边界:B2 = 数据层骨架(共享 queryClient 单例 + 401 single-flight interceptor + dataProvider 骨架),
 *   不含任何业务页面代码;B3 在此基础上接 admin 页面。
 *
 * queryClient 注入方式(@refinedev/core@5.0.12 实测,dist/index.mjs):
 *   Refine 无 queryClient prop;v5 注入点 = options.reactQuery.clientConfig,
 *   且 clientConfig 传 QueryClient 实例时内部 `instanceof QueryClient → 直接 return 该实例`,
 *   即 <Refine options={{reactQuery:{clientConfig: getEduQueryClient()}}}> 实现共享单例、零新建。
 */

import { Refine, type AuthProvider, type ResourceProps, type RouterProvider } from "@refinedev/core";
import type { ReactNode } from "react";
import { eduDataProvider } from "./data-provider.js";
import { getEduQueryClient } from "./query-client.js";

export { createEduQueryClient, getEduQueryClient } from "./query-client.js";
export { ApiError, configureHttp, http, getBaseURL, onError } from "./http.js";
export type { HttpConfig } from "./http.js";
export { createTokenStore, tokenStore, TOKEN_KEY, REFRESH_KEY } from "./auth-store.js";
export type { TokenStore } from "./auth-store.js";
export { eduDataProvider } from "./data-provider.js";

export interface EduRefineProviderProps {
  children: ReactNode;
  /** B3 传入 @refinedev/nextjs-router 的 routerProvider(default 导出,B0 审计卡点1) */
  routerProvider?: RouterProvider;
  /** B3 按页面注册 resources */
  resources?: ResourceProps[];
  /** B3 如需 Refine 托管登录流程则传入;401 语义不依赖它(http.ts interceptor 已收敛) */
  authProvider?: AuthProvider;
}

/** B3 挂接入口:固定共享 queryClient 单例 + edu dataProvider,其余透传给 <Refine> */
export function EduRefineProvider({ children, routerProvider, resources, authProvider }: EduRefineProviderProps) {
  return (
    <Refine
      dataProvider={eduDataProvider()}
      options={{ reactQuery: { clientConfig: getEduQueryClient() } }}
      routerProvider={routerProvider}
      resources={resources}
      authProvider={authProvider}
    >
      {children}
    </Refine>
  );
}
