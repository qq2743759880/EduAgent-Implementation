"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useEffect, useRef, type ReactNode } from "react";
import { Toaster, toast } from "sonner";

import getQueryClient from "@/lib/query-client";
import { useAuthStore } from "@/lib/auth-client";
import { GlobalChatInjection } from "@/components/chat/GlobalChatInjection";

export function Providers({ children }: { children: ReactNode }) {
  const queryClient = getQueryClient();
  const hydratedRef = useRef(false);

  useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;
    try {
      useAuthStore.getState().hydrate();
    } catch (err) {
      toast.error("初始化失败", {
        description: err instanceof Error ? err.message : undefined,
      });
    }
    // Playwright E2E 探针：挂载 zustand store 与 hydrate 标记（仅浏览器，不影响生产）
    try {
      const win = window as unknown as Record<string, unknown>;
      win.__eduAuthStore = useAuthStore;
      win.__eduAuthHydrated = true;
    } catch {
      /* ignore */
    }
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <GlobalChatInjection />
      <Toaster
        position="top-center"
        richColors
        closeButton
        toastOptions={{
          duration: 3500,
        }}
      />
      {process.env.NODE_ENV !== "production" ? (
        <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-right" />
      ) : null}
    </QueryClientProvider>
  );
}

export default Providers;
