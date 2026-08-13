/**
 * useChatSessions
 *
 * 会话列表 & 选中状态管理：
 *   - React Query 缓存 sessions（staleTime=15s），create/delete 乐观更新
 *   - 选中的 sessionId 保存到 localStorage.edu:chat:last_session_id（跨页面恢复）
 *   - useEnsureSession() 懒创建会话，用于发送第一条消息前的占位
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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

  // ======== 选中状态管理（必须用 state，不能用 ref） ========
  // G7 联调实证：selectedId 用 ref + 靠 invalidate 重渲染"顺带"刷新时，
  // TanStack Query 结构共享会让相同数据的 refetch 不产生新状态 → 无重渲染 →
  // 点击会话行历史永远不加载（删除等数据变化时才偶发触发）。选中态必须可观察。
  const [selectedId, setSelectedId] = useState<string | number | null>(() => {
    // 调用方传了 initialSessionId（例如 URL sid）优先，否则用上次会话
    if (opts.initialSessionId !== undefined && opts.initialSessionId !== null) {
      return opts.initialSessionId;
    }
    return readLastId();
  });

  // 渲染期派生：选中项已被移除（软删/他人操作）时回退到列表第一项。
  // 用派生值而非 effect 内 setState（React Compiler 规则，避免 cascading render）。
  const effectiveSelectedId = useMemo<string | number | null>(() => {
    if (!data.length || selectedId == null) return selectedId;
    return data.some((s) => String(s.id) === String(selectedId))
      ? selectedId
      : (data[0]?.id ?? null);
  }, [data, selectedId]);

  // 派生值与本地持久化同步（纯副作用，不 setState）
  useEffect(() => {
    if (effectiveSelectedId !== selectedId) writeLastId(effectiveSelectedId);
  }, [effectiveSelectedId, selectedId]);

  const selectSession = useCallback<UseChatSessionsHandle["selectSession"]>((id) => {
    setSelectedId(id ?? null);
    writeLastId(id ?? null);
    // 轻量触发一次（让列表与选中态保持一致）
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
      setSelectedId(resp.id);
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
      // 函数式 setState：删除的是当前选中项才切到邻居，避免闭包陈旧值（L7 原则）
      setSelectedId((prev) => {
        if (String(prev) === String(id)) {
          const remain = (ctx?.prev ?? []).filter((s) => String(s.id) !== String(id));
          const next = remain[0]?.id ?? null;
          writeLastId(next);
          return next;
        }
        return prev;
      });
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
      setSelectedId(nextId);
      writeLastId(nextId);
    }
  }, [deleteMut]);

  const ensureSession = useCallback<UseChatSessionsHandle["ensureSession"]>(async (body) => {
    if (!enabled) return null;
    const current = effectiveSelectedId;
    if (current != null) {
      // 保证当前 id 真实存在，否则重建
      const list = queryClient.getQueryData<ChatSession[]>(qk) ?? [];
      if (list.some((s) => String(s.id) === String(current))) return current;
    }
    const created = await createMut.mutateAsync(body ?? {});
    return created.id;
  }, [enabled, createMut, qk, queryClient, effectiveSelectedId]);

  return {
    sessions: data ?? [],
    sessionsLoading,
    sessionsError,
    selectedId: effectiveSelectedId,
    selectSession,
    createAndSelect,
    deleteSession,
    ensureSession,
    refetch: () => { void refetch(); },
  };
}
