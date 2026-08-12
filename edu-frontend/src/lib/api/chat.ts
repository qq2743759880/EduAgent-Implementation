/**
 * AI 问答助手（能力 7 & 10）Chat API
 * 路由：
 *   - P9 Chat (能力7)        /api/chat/sessions          GET/POST/DELETE
 *                              /api/chat/sessions/{sid}/messages  GET
 *                              /api/chat/chat              POST 非流式
 *                              /api/chat/stream            POST SSE 流式
 *                              /api/chat/search            POST 仅检索（用于 References）
 *   - MCP Tool Calls (能力10)  /api/chat/mcp/{tool_id}/invoke  POST
 *
 * 设计要点：
 *   1. chatStream 使用 fetch + ReadableStream + NDJSON/SSEEvent 解析（axios 不适合流输出）
 *   2. 所有消息/会话/检索结果统一用 type 标记，便于组件分类型渲染
 *   3. 若后端未上线，FallbackMode 返回本地 mock，保证 UI 不崩溃
 */
"use client";

import { api, API_BASE, type ApiErrorPayload } from "@/lib/api-client";

/* =========================================================
 * TYPES
 * =======================================================*/

export type ChatRole = "user" | "assistant" | "system";

export type RagDocType = "section" | "question" | "doc";

export interface RagDoc {
  id: string | number;
  type: RagDocType;
  title: string;
  snippet?: string | null;
  score?: number | null;
  series_id?: number | null;
  session_id?: number | null;
  question_id?: number | null;
  anchor_url?: string | null;
}

export type MCPToolCallStatus = "pending" | "running" | "success" | "error";

export interface MCPToolCall {
  id: string;
  tool_name: string;
  args_json?: string | Record<string, unknown> | null;
  status: MCPToolCallStatus;
  progress_pct?: number | null;
  result_json?: string | Record<string, unknown> | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ChatMessage {
  id: string;
  session_id: string | number | null;
  role: ChatRole;
  content: string;
  /** 引用来源（同一次 answer 的 sources 与 assistant 消息绑定） */
  sources?: RagDoc[] | null;
  /** 该消息关联的 MCP 工具调用链（可多步） */
  tool_calls?: MCPToolCall[] | null;
  /** 前端流式渲染用：是否还在生成中 */
  streaming?: boolean;
  created_at?: string | null;
}

export interface ChatSession {
  id: string | number;
  title: string;
  preview?: string | null;
  messages_count?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** 流式 SSE 事件（后端按逐帧 delta 推送） */
export type SSEEventKind =
  | "delta" // content 增量文本
  | "sources" // RagDoc 数组
  | "tool_start" // { id, tool_name, args_json? }
  | "tool_progress" // { id, progress_pct }
  | "tool_result" // { id, status=success|error, result_json?, error_message? }
  | "message_start" // { role, id? } — 可选，用于提前创建气泡占位
  | "message_end" // { id, created_at? } — 收尾
  | "error"; // { message, code? }

export interface SSEEvent {
  kind: SSEEventKind;
  id?: string;
  payload: unknown;
}

export interface ChatSendOptions {
  sessionId?: string | number | null;
  /** 开启流式（默认 true） */
  stream?: boolean;
  /** 附带学科/级别上下文（可选，后端会从当前用户 profile 推断） */
  subject_code?: string | null;
  level_code?: string | null;
  signal?: AbortSignal | null;
  onDelta?: (chunk: string) => void;
  onSources?: (sources: RagDoc[]) => void;
  onToolStart?: (call: MCPToolCall) => void;
  onToolProgress?: (update: Pick<MCPToolCall, "id"> & Partial<MCPToolCall>) => void;
  onToolResult?: (update: Pick<MCPToolCall, "id"> & Partial<MCPToolCall>) => void;
  onDone?: (finalMessage: ChatMessage) => void;
  onError?: (err: Error) => void;
}

/* =========================================================
 * HELPERS
 * =======================================================*/

function readToken(): string | null {
  try {
    return localStorage.getItem("edu:auth:token");
  } catch {
    return null;
  }
}

function normalizeDocPayload(d: unknown): RagDoc {
  const any = d as Record<string, unknown>;
  return {
    id: (any.id as string | number) ?? String(any.id ?? ""),
    type: ((any.type as RagDocType) ?? "doc"),
    title: String(any.title ?? any.name ?? "未命名资料"),
    snippet: typeof any.snippet === "string" ? any.snippet : (any.summary as string | undefined) ?? null,
    score: typeof any.score === "number" ? any.score : (any.relevance as number | undefined) ?? null,
    series_id: typeof any.series_id === "number" ? any.series_id : (any.course_id as number | undefined) ?? null,
    session_id: typeof any.session_id === "number" ? any.session_id : (any.lesson_id as number | undefined) ?? null,
    question_id: typeof any.question_id === "number" ? any.question_id : null,
    anchor_url: typeof any.anchor_url === "string" ? any.anchor_url : (any.url as string | undefined) ?? null,
  };
}

/** 归一化 MCP 工具调用的 JSON 字段：字符串原样、对象原样、其余转 null */
function normalizeJsonField(
  v: unknown,
): string | Record<string, unknown> | null {
  if (typeof v === "string") return v;
  if (v && typeof v === "object") return v as Record<string, unknown>;
  return null;
}

function normalizeToolCall(t: unknown): MCPToolCall {
  const any = t as Record<string, unknown>;
  return {
    id: String(any.id ?? any.call_id ?? Math.random().toString(36).slice(2, 10)),
    tool_name: String(any.tool_name ?? any.tool ?? "mcp.tool"),
    args_json: normalizeJsonField(any.args_json ?? any.args),
    status: (any.status as MCPToolCallStatus) ?? "pending",
    progress_pct: typeof any.progress_pct === "number" ? any.progress_pct : null,
    result_json: normalizeJsonField(any.result_json ?? any.result),
    error_message: typeof any.error_message === "string" ? any.error_message : null,
    started_at: typeof any.started_at === "string" ? any.started_at : null,
    finished_at: typeof any.finished_at === "string" ? any.finished_at : null,
  };
}

/* =========================================================
 * SESSIONS & HISTORY (axios 封装，走拦截器统一错误处理)
 * =======================================================*/

export async function listChatSessions(): Promise<ChatSession[]> {
  try {
    const { data } = await api.get<ChatSession[]>("/api/chat/sessions");
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export async function createChatSession(
  body: { title?: string; subject_code?: string | null } = {},
): Promise<ChatSession> {
  const { data } = await api.post<ChatSession>("/api/chat/sessions", body);
  return data as ChatSession;
}

export async function deleteChatSession(id: string | number): Promise<void> {
  await api.delete(`/api/chat/sessions/${id}`);
}

export async function getChatHistory(sessionId: string | number): Promise<ChatMessage[]> {
  try {
    const { data } = await api.get<ChatMessage[]>(`/api/chat/sessions/${sessionId}/messages`);
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export async function searchRagOnly(
  query: string,
  opts: { subject_code?: string | null; limit?: number } = {},
): Promise<RagDoc[]> {
  try {
    const { data } = await api.post<unknown[]>("/api/chat/search", {
      query,
      subject_code: opts.subject_code ?? null,
      limit: opts.limit ?? 5,
    });
    const arr = Array.isArray(data) ? data : [];
    return arr.map(normalizeDocPayload);
  } catch {
    return [];
  }
}

/* =========================================================
 * NON-STREAM CHAT — 后端只有 /api/chat/stream（SSE），
 *   因此非流式走同一 SSE 端点但把整个流读完，返回最后一条 assistant 消息。
 * =======================================================*/

export async function chatNonStream(
  message: string,
  opts: ChatSendOptions = {},
): Promise<ChatMessage> {
  return await new Promise<ChatMessage>((resolve, reject) => {
    const controller = chatStream(message, {
      ...opts,
      stream: false,
      onDone: (m) => resolve(m),
      onError: (e) => reject(e),
    });
    const timeoutId = setTimeout(() => {
      controller.abort();
      reject(new Error("非流式响应超时"));
    }, 60_000);
    const cleanup = () => clearTimeout(timeoutId);
    const origDone = opts.onDone;
    opts.onDone = (m) => { cleanup(); origDone?.(m) };
    const origErr = opts.onError;
    opts.onError = (e) => { cleanup(); origErr?.(e) };
  });
}

/* =========================================================
 * STREAM CHAT (fetch + ReadableStream, 绕过 axios)
 *   后端约定两种帧格式二选一：
 *     ① SSE text/event-stream：event: <kind> \n data: {...} （以空行分隔事件组）
 *        支持的 event 名：start / retrieval / delta / sources /
 *                         tool_start / tool_progress / tool_result /
 *                         message_start / message_end / error
 *     ② NDJSON application/x-ndjson：每行 {kind: "...", payload: ...}
 * =======================================================*/

export function chatStream(
  message: string,
  opts: ChatSendOptions & { signal?: AbortSignal | null } = {},
): AbortController {
  const controller = new AbortController();
  const userSignal = opts.signal ?? null;
  if (userSignal) {
    if (typeof userSignal.addEventListener === "function") {
      userSignal.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }

  void (async () => {
    const token = readToken();
    /*
     * 注意：后端 chat/stream 的 FastAPI Pydantic schema 要求字段名是 query，
     * 不是前端语义化命名的 content。这里同步对齐，否则会 422：
     * "Field required" @ loc=["body","query"]
     */
    const body: Record<string, unknown> = {
      session_id: opts.sessionId ?? null,
      query: message,
      content: message,
      subject_code: opts.subject_code ?? null,
      level_code: opts.level_code ?? null,
      stream: true,
    };

    let finalContent = "";
    let finalSources: RagDoc[] = [];
    const finalTools: Record<string, MCPToolCall> = {};
    let assistantId = `gen_${Date.now()}`;
    let finalSessionId = opts.sessionId ?? null;

    try {
      const resp = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream, application/x-ndjson, */*",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      });

      if (!resp.ok) {
        let parsed: ApiErrorPayload = { message: `HTTP ${resp.status}` };
        try {
          const txt = await resp.text();
          try {
            parsed = JSON.parse(txt) as ApiErrorPayload;
          } catch {
            parsed = { message: txt || parsed.message };
          }
        } catch {
          /* keep default */
        }
        throw new Error(parsed.message || `HTTP ${resp.status}`);
      }

      if (!resp.body) {
        throw new Error("no readable body for stream");
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      /* -------- SSE group buffer（event / data 两行一组，用空行分隔） -------- */
      let sseEventName: string | null = null;
      let sseDataBuf: string[] = [];

      const flushSSEGroup = () => {
        const eventName = sseEventName ?? "message";
        const joined = sseDataBuf.join("\n").trim();
        sseEventName = null;
        sseDataBuf = [];
        if (!joined) return;
        // 把 event 名 翻译成 内部 kind
        const kindFromEvent = sseEventNameToKind(eventName);
        dispatchRawLine(joined, kindFromEvent);
      };

      const flushLine = (rawLine: string) => {
        const line = rawLine.trimEnd();
        // SSE 空行 => 结束一个 group
        if (line.length === 0) {
          flushSSEGroup();
          return;
        }
        // SSE field: "event: xxx"
        if (line.startsWith("event:")) {
          sseEventName = line.slice(6).trim();
          return;
        }
        // SSE field: "data: xxx" 或 "data:xxx"
        if (line.startsWith("data:")) {
          const rest = line.slice(5).trimStart();
          if (rest === "[DONE]") {
            flushSSEGroup();
            return;
          }
          sseDataBuf.push(rest);
          return;
        }
        // 不是 SSE field → 当作 NDJSON 行直接派（kind 由 inferLegacyKind 推断）
        flushSSEGroup();
        dispatchRawLine(line, undefined);
      };

      const dispatchRawLine = (text: string, hintKind?: SSEEventKind | undefined) => {
        if (!text) return;
        let json: Record<string, unknown> | null = null;
        try {
          json = JSON.parse(text) as Record<string, unknown>;
        } catch {
          // 纯文本增量 => 视为 delta
          finalContent += text;
          opts.onDelta?.(text);
          return;
        }
        if (!json) return;

        const kind: SSEEventKind =
          hintKind ??
          ((json.kind as SSEEventKind | undefined)) ??
          inferLegacyKind(json);
        const payload = json.payload ?? json;

        switch (kind) {
          case "message_start": {
            const p = payload as Record<string, unknown>;
            if (typeof p.id === "string") assistantId = p.id;
            if (typeof p.message_id === "string") assistantId = p.message_id as string;
            if (p.session_id !== undefined) finalSessionId = p.session_id as string | number;
            break;
          }
          case "delta": {
            const p = payload as Record<string, unknown>;
            let chunk = "";
            if (typeof payload === "string") chunk = payload;
            else if (typeof p.chunk === "string") chunk = p.chunk as string;
            else if (typeof p.delta === "string") chunk = p.delta as string;
            else if (typeof p.content === "string") chunk = p.content as string;
            else if (typeof p.answer === "string") chunk = p.answer as string;
            finalContent += chunk;
            opts.onDelta?.(chunk);
            break;
          }
          case "sources": {
            const arr =
              Array.isArray(payload) ? (payload as unknown[]) :
              Array.isArray((payload as Record<string, unknown>).sources) ?
                ((payload as Record<string, unknown>).sources as unknown[]) :
              Array.isArray((payload as Record<string, unknown>).docs) ?
                ((payload as Record<string, unknown>).docs as unknown[]) : [];
            finalSources = arr.map(normalizeDocPayload);
            opts.onSources?.(finalSources);
            break;
          }
          case "tool_start": {
            const tc = normalizeToolCall(payload);
            tc.status = "running";
            finalTools[tc.id] = tc;
            opts.onToolStart?.(tc);
            break;
          }
          case "tool_progress": {
            const p = payload as Record<string, unknown>;
            const id = String(p.id ?? p.call_id ?? "");
            const prev = finalTools[id] ?? {
              id, tool_name: String(p.tool_name ?? "mcp.tool"), status: "running" as const,
            };
            const next: MCPToolCall = {
              ...prev,
              progress_pct: typeof p.progress_pct === "number" ? p.progress_pct : prev.progress_pct,
              status: "running",
            };
            finalTools[id] = next;
            opts.onToolProgress?.(next);
            break;
          }
          case "tool_result": {
            const p = payload as Record<string, unknown>;
            const id = String(p.id ?? p.call_id ?? "");
            const prev = finalTools[id] ?? {
              id, tool_name: String(p.tool_name ?? "mcp.tool"), status: "success" as const,
            };
            const statusVal = (p.status as MCPToolCallStatus | undefined);
            const next: MCPToolCall = {
              ...prev,
              status:
                statusVal === "success" || statusVal === "error" ? statusVal :
                (p.error_message ? "error" : "success"),
              result_json: normalizeJsonField(p.result_json ?? p.result ?? prev.result_json),
              error_message: typeof p.error_message === "string" ? p.error_message : prev.error_message,
              progress_pct: 100,
              finished_at: typeof p.finished_at === "string" ? p.finished_at : new Date().toISOString(),
            };
            finalTools[id] = next;
            opts.onToolResult?.(next);
            break;
          }
          case "message_end": {
            const p = payload as Record<string, unknown>;
            if (typeof p.id === "string") assistantId = p.id;
            if (typeof p.message_id === "string") assistantId = p.message_id as string;
            if (p.session_id !== undefined) finalSessionId = p.session_id as string | number;
            break;
          }
          case "error": {
            const p = payload as Record<string, unknown>;
            throw new Error(String(p.message ?? p.detail ?? p.error_message ?? "生成失败"));
          }
        }
      };

      const inferLegacyKind = (j: Record<string, unknown>): SSEEventKind => {
        if ("chunk" in j || "delta" in j || "content" in j || "answer" in j) return "delta";
        if (("sources" in j && Array.isArray((j as Record<string, unknown>).sources)) || ("docs" in j && Array.isArray((j as Record<string, unknown>).docs))) return "sources";
        if ("tool_name" in j && ("status" in j || "args" in j)) {
          const s = (j.status as string | undefined);
          if (s === "success" || s === "error" || "result" in j || "error_message" in j) return "tool_result";
          if ("progress_pct" in j) return "tool_progress";
          return "tool_start";
        }
        return "delta";
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let eol: number;
        while ((eol = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, eol);
          buffer = buffer.slice(eol + 1);
          flushLine(line.replace(/\r$/, ""));
        }
      }
      // flush remaining
      if (buffer.trim()) flushLine(buffer.replace(/\r$/, ""));
      // close SSE group if still open
      flushSSEGroup();

      // Emit DONE with assembled ChatMessage
      const finalMessage: ChatMessage = {
        id: assistantId,
        session_id: finalSessionId,
        role: "assistant",
        content: finalContent,
        sources: finalSources.length ? finalSources : null,
        tool_calls: Object.values(finalTools).length ? Object.values(finalTools) : null,
        created_at: new Date().toISOString(),
      };
      opts.onDone?.(finalMessage);
    } catch (err) {
      if ((err as Error).name === "AbortError" || controller.signal.aborted) {
        opts.onDone?.({
          id: assistantId,
          session_id: finalSessionId,
          role: "assistant",
          content: finalContent,
          sources: finalSources.length ? finalSources : null,
          tool_calls: Object.values(finalTools).length ? Object.values(finalTools) : null,
          created_at: new Date().toISOString(),
        });
        return;
      }
      opts.onError?.(err instanceof Error ? err : new Error(String(err)));
    }
  })();

  return controller;
}

/* ---------------- SSE event 名 映射到内部 kind ---------------- */

function sseEventNameToKind(name: string): SSEEventKind {
  switch (name) {
    case "start":
    case "message_start":
      return "message_start";
    case "end":
    case "message_end":
    case "done":
      return "message_end";
    case "delta":
    case "content":
    case "token":
    case "chunk":
      return "delta";
    case "sources":
    case "retrieval":
    case "docs":
    case "context":
      return "sources";
    case "tool_start":
    case "tool_call_start":
      return "tool_start";
    case "tool_progress":
      return "tool_progress";
    case "tool_result":
    case "tool_end":
    case "tool_call_end":
      return "tool_result";
    case "error":
    case "err":
      return "error";
    default:
      // 未知事件：payload 判断形态
      return "delta";
  }
}
