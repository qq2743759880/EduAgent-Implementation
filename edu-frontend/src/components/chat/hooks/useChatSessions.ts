/**
 * useChatSessions
 *
 * 会话列表 & 选中状态管理：
 *   - React Query 缓存 sessions（staleTime=15s），create/delete 乐观更新
 *   - 选中的 sessionId 保存到 localStorage.edu:chat:last_session_id（跨页面恢复）
 *   - useEnsureSession() 懒创建会话，用于发送第一条消息前的占位
 */
"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  createChatSession,
  deleteChatSession,
  listChatSessions,
  type ChatSession,
} from "@/lib/api/chat";

const LS_LAST = "edu:chat:last_session_id";
const STALE_MS = 15_000;

export interface UseChatSessionsOptions {
  /** 初始选中会话（如从 URL ?sid= 来） */
  initialSessionId?: string | number | null;
  /** 未登录 / 无权限时跳过 query（避免 401 全局 toast） */
  enabled?: boolean;
}

export interface UseChatSessionsHandle {
  sessions: ChatSession[];
  sessionsLoading: boolean;
  sessionsError: Error | null;
  selectedId: string | number | null;
  selectSession: (id: string | number | null) => void;
  createAndSelect: (
    body?: { title?: string; subject_code?: string | null },
  ) => Promise<ChatSession>;
  deleteSession: (id: string | number, nextId?: string | number | null) => Promise<void>;
  /** 保证存在一个 session（若未选中则新建）；返回 id */
  ensureSession: (
    body?: { title?: string; subject_code?: string | null },
  ) => Promise<string | number | null>;
  refetch: () => void;
}

function readLastId(): string | number | null {
  try {
    const v = localStorage.getItem(LS_LAST);
    if (!v) return null;
    const num = Number(v);
    return Number.isFinite(num) ? num : v;
  } catch {
    return null;
  }
}

function writeLastId(id: string | number | null) {
  try {
    if (id == null) localStorage.removeItem(LS_LAST);
    else localStorage.setItem(LS_LAST, String(id));
  } catch {
    /* ignore */
  }
}

export function useChatSessions(opts: UseChatSessionsOptions = {}): UseChatSessionsHandle {
  const queryClient = useQueryClient();
  const enabled = opts.enabled !== false;
  const qk = useMemo(() => ["chat_sessions"] as const, []);

  const {
    data = [],
    isLoading: sessionsLoading,
    error,
    refetch,
  } = useQuery<ChatSession[], Error, ChatSession[], typeof qk>({
    queryKey: qk,
    async queryFn() {
      return listChatSessions();
    },
    staleTime: STALE_MS,
    enabled,
    refetchOnWindowFocus: false,
  });

  const sessionsError = error ?? null;

  // ======== 选中状态管理 ========
  const selectedIdRef = useRef<string | number | null>(readLastId());
  // 如果调用方传了 initialSessionId（例如 URL sid），优先它
  const initRef = useRef(false);
  if (!initRef.current) {
    initRef.current = true;
    if (opts.initialSessionId !== undefined && opts.initialSessionId !== null) {
      selectedIdRef.current = opts.initialSessionId;
    }
  }

  // 监听 sessions 变化：若选中值已不在列表中 → 清掉
  useEffect(() => {
    if (!data?.length) return;
    const current = selectedIdRef.current;
    if (current == null) return;
    const exist = data.some((s) => String(s.id) === String(current));
    if (!exist) {
      selectedIdRef.current = data[0]?.id ?? null;
      writeLastId(selectedIdRef.current);
    }
  }, [data]);

  const selectSession = useCallback<UseChatSessionsHandle["selectSession"]>((id) => {
    selectedIdRef.current = id ?? null;
    writeLastId(id ?? null);
    // 轻量触发一次（避免闭包拿不到最新值，这里不走 state）
    queryClient.invalidateQueries({ queryKey: qk, exact: true }).catch(() => { /* ignore */ });
  }, [qk, queryClient]);

  // ======== Mutations ========
  const createMut = useMutation({
    mutationFn: (body: { title?: string; subject_code?: string | null } = {}) =>
      createChatSession(body),
    onMutate: async (body) => {
      await queryClient.cancelQueries({ queryKey: qk, exact: true });
      const prev = queryClient.getQueryData<ChatSession[]>(qk) ?? [];
      const temp: ChatSession = {
        id: `tmp_${Date.now()}`,
        title: body.title || "新对话",
        preview: "",
        messages_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      queryClient.setQueryData<ChatSession[]>(qk, [temp, ...prev]);
      return { prev, tempId: temp.id };
    },
    onSuccess: (resp, _args, ctx) => {
      const prev = ctx?.prev ?? [];
      queryClient.setQueryData<ChatSession[]>(qk, (cached) => {
        const cur = Array.isArray(cached) ? cached : prev;
        return cur.map((s) => (s.id === ctx?.tempId ? resp : s));
      });
      selectedIdRef.current = resp.id;
      writeLastId(resp.id);
    },
    onError: (err, _args, ctx) => {
      queryClient.setQueryData<ChatSession[]>(qk, ctx?.prev ?? []);
      toast.error("创建会话失败", { description: err instanceof Error ? err.message : undefined });
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string | number) => deleteChatSession(id),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: qk, exact: true });
      const prev = queryClient.getQueryData<ChatSession[]>(qk) ?? [];
      queryClient.setQueryData<ChatSession[]>(qk, prev.filter((s) => String(s.id) !== String(id)));
      return { prev };
    },
    onSuccess: (_resp, id, ctx) => {
      if (String(selectedIdRef.current) === String(id)) {
        const remain = (ctx?.prev ?? []).filter((s) => String(s.id) !== String(id));
        selectedIdRef.current = remain[0]?.id ?? null;
        writeLastId(selectedIdRef.current);
      }
    },
    onError: (err, id, ctx) => {
      queryClient.setQueryData<ChatSession[]>(qk, ctx?.prev ?? []);
      toast.error("删除会话失败", { description: err instanceof Error ? err.message : undefined });
      void id;
    },
  });

  const createAndSelect = useCallback<UseChatSessionsHandle["createAndSelect"]>(async (body) => {
    return createMut.mutateAsync(body ?? {});
  }, [createMut]);

  const deleteSession = useCallback<UseChatSessionsHandle["deleteSession"]>(async (id, nextId) => {
    await deleteMut.mutateAsync(id);
    if (nextId != null) {
      selectedIdRef.current = nextId;
      writeLastId(nextId);
    }
  }, [deleteMut]);

  const ensureSession = useCallback<UseChatSessionsHandle["ensureSession"]>(async (body) => {
    if (!enabled) return null;
    const current = selectedIdRef.current;
    if (current != null) {
      // 保证当前 id 真实存在，否则重建
      const list = queryClient.getQueryData<ChatSession[]>(qk) ?? [];
      if (list.some((s) => String(s.id) === String(current))) return current;
    }
    const created = await createMut.mutateAsync(body ?? {});
    return created.id;
  }, [enabled, createMut, qk, queryClient]);

  return {
    sessions: data ?? [],
    sessionsLoading,
    sessionsError,
    selectedId: selectedIdRef.current,
    selectSession,
    createAndSelect,
    deleteSession,
    ensureSession,
    refetch: () => { void refetch(); },
  };
}
