/**
 * AI 问答助手 Chat API（task40 对齐 app/chat/schemas.py 契约）
 * 路由：
 *   - POST   /api/chat/sessions               创建会话（201）
 *   - GET    /api/chat/sessions               会话列表
 *   - DELETE /api/chat/sessions/{session_id}  删除会话 {ok:true}
 *   - GET    /api/chat/sessions/{sid}/history 历史消息（裸数组）
 *   - POST   /api/chat/search                 仅检索（References）
 *   - POST   /api/chat                        非流式问答（RagAnswerResponse）
 *   - POST   /api/chat/stream                 SSE 流式（事件 start/retrieval/token/done/error）
 *
 * task40 改造要点：
 *   1. 类型与后端 schemas 一一对应（ChatSession/ChatMessage/RetrievedDoc）
 *   2. 删除三轨别名归一层（normalizeSession/normalizeDocPayload/normalizeToolCall）
 *   3. 列表/历史删除 catch 兜底吞错（R-7 保留：错误向上抛，组件层负责空态）
 *   4. searchRagOnly 返回契约对象 {docs,...}（旧实现读数组恒空，注释自证）
 */
"use client";

import { http, API_BASE, type ApiErrorPayload } from "@/lib/api-client";

/* =========================================================
 * TYPES（对齐 app/chat/schemas.py）
 * =======================================================*/

export type ChatRole = "user" | "assistant" | "system";

/** RetrievedDoc：检索命中文档 */
export interface RetrievedDoc {
  doc_id: string;
  score: number;
  content: string;
  source_file: string | null;
  content_type: string | null;
  series_code: string | null;
  series_name: string | null;
  module_codes: string[];
  keywords: string[];
  tenant_id: string | null;
  visibility: string | null;
  source_channel: string;
}

/** GraphEntity：知识图谱实体（retrieval 事件附带） */
export interface GraphEntity {
  entity_type: string;
  entity_name: string;
  related: string[];
  hop: number;
}

/** MCPToolCallSummary：MCP 工具调用摘要（retrieval 事件附带） */
export type MCPToolCallStatus = "pending" | "running" | "success" | "error" | "timeout";

export interface MCPToolCall {
  call_id: string;
  tool_name: string;
  args_summary: string;
  status: MCPToolCallStatus;
  latency_ms: number | null;
  result_summary: string | null;
  /** 前端流式扩展（SSE 状态机），非后端契约字段 */
  error_message?: string | null;
  progress_pct?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
}

/** ChatMessage：后端权威字段 + 前端解析扩展（sources/tool_calls 由 *_json 解析） */
export interface ChatMessage {
  message_id: string;
  session_id: string;
  user_id: number;
  role: ChatRole;
  content: string;
  rag_query_rewrite: string | null;
  rag_retrieved_count: number | null;
  rag_final_count: number | null;
  rag_docs_json: string | null;
  rag_error: string | null;
  latency_ms: number | null;
  mcp_tool_calls_json: string | null;
  mcp_called_count: number | null;
  created_at: string;
  /** 前端解析扩展：rag_docs_json → RetrievedDoc[]（视图层消费） */
  sources?: RetrievedDoc[] | null;
  /** 前端解析扩展：mcp_tool_calls_json → MCPToolCall[]（视图层消费） */
  tool_calls?: MCPToolCall[] | null;
  /** 前端流式渲染用：是否还在生成中 */
  streaming?: boolean;
}

/** ChatSession（后端权威） */
export interface ChatSession {
  session_id: string;
  user_id: number;
  title: string;
  visibility: "private" | "shared";
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  yn: number;
}

/** ChatSessionCreate 请求体 */
export interface ChatSessionCreate {
  title?: string | null;
  visibility?: "private" | "shared";
}

/** DeleteSessionResponse */
export interface DeleteSessionResponse {
  ok: boolean;
}

/** RagSearchOnlyRequest（POST /api/chat/search 请求体） */
export interface RagSearchOnlyRequest {
  query: string;
  session_id?: string | null;
  use_hyde?: boolean;
  top_k?: number;
  final_max_k?: number;
  cutoff_drop_ratio?: number;
  enable_graph?: boolean;
  use_mcp_tools?: boolean;
  format_docs?: boolean;
}

/** RagSearchOnlyResponse */
export interface RagSearchOnlyResponse {
  docs: RetrievedDoc[];
  graph_entities: GraphEntity[];
  retrieved_count: number;
  final_count: number;
  rewrite_query: string | null;
  degraded_reason: string | null;
}

/** RagQueryRequest（POST /api/chat、/api/chat/stream 请求体） */
export interface RagQueryRequest {
  query: string;
  session_id?: string | null;
  use_hyde?: boolean;
  top_k?: number;
  final_max_k?: number;
  cutoff_drop_ratio?: number;
  enable_graph?: boolean;
  use_mcp_tools?: boolean;
  stream?: boolean;
  model?: "fast" | "strong";
  include_history?: number;
}

/** RagAnswerResponse（POST /api/chat 非流式响应） */
export interface RagAnswerResponse {
  session_id: string | null;
  message_id: string | null;
  answer: string;
  docs: RetrievedDoc[];
  graph_entities: GraphEntity[];
  rewrite_query: string | null;
  retrieved_count: number;
  final_count: number;
  latency_ms: number;
  degraded_reason: string | null;
  mcp_tool_calls: Array<{
    call_id: string;
    tool_name: string;
    args_summary: string;
    status: "success" | "error" | "timeout";
    latency_ms: number;
    result_summary: string;
  }>;
}

/** 流式 SSE 事件（内部 kind；后端事件名 start/retrieval/token/done/error 经 sseEventNameToKind 映射） */
export type SSEEventKind =
  | "delta" // token 事件 {delta}
  | "sources" // retrieval 事件 {docs, graph_entities, mcp_tool_calls}
  | "tool_start" // 保留：未来 LangGraph 工具事件（task24+）
  | "tool_progress"
  | "tool_result"
  | "message_start" // start 事件 {session_id, query}
  | "message_end" // done 事件 {session_id, message_id}
  | "error";

export interface SSEEvent {
  kind: SSEEventKind;
  id?: string;
  payload: unknown;
}

export interface ChatSendOptions {
  sessionId?: string | null;
  stream?: boolean;
  use_hyde?: boolean;
  top_k?: number;
  final_max_k?: number;
  enable_graph?: boolean;
  use_mcp_tools?: boolean;
  model?: "fast" | "strong";
  include_history?: number;
  signal?: AbortSignal | null;
  onDelta?: (chunk: string) => void;
  onSources?: (sources: RetrievedDoc[]) => void;
  onToolStart?: (call: MCPToolCall) => void;
  onToolProgress?: (update: Pick<MCPToolCall, "call_id"> & Partial<MCPToolCall>) => void;
  onToolResult?: (update: Pick<MCPToolCall, "call_id"> & Partial<MCPToolCall>) => void;
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

/** rag_docs_json（后端 JSON 字符串）→ RetrievedDoc[]（按契约解析，非别名兜底） */
function parseDocsJson(raw: string | null | undefined): RetrievedDoc[] | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as RetrievedDoc[]) : null;
  } catch {
    return null;
  }
}

/** mcp_tool_calls_json（后端 JSON 字符串）→ MCPToolCall[]（按契约解析） */
function parseToolCallsJson(
  raw: string | null | undefined,
): MCPToolCall[] | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as MCPToolCall[]) : null;
  } catch {
    return null;
  }
}

/* =========================================================
 * SESSIONS & HISTORY（拦截器已解包，零 .data）
 * =======================================================*/

export function listChatSessions(limit = 50): Promise<ChatSession[]> {
  return http.get<ChatSession[]>("/api/chat/sessions", { params: { limit } });
}

export function createChatSession(
  body: ChatSessionCreate = {},
): Promise<ChatSession> {
  return http.post<ChatSession>("/api/chat/sessions", body);
}

export function deleteChatSession(
  sessionId: string,
): Promise<DeleteSessionResponse> {
  return http.delete<DeleteSessionResponse>(`/api/chat/sessions/${sessionId}`);
}

/** 历史消息：解析 *_json 字符串为视图层 sources/tool_calls（错误向上抛） */
export async function getChatHistory(
  sessionId: string,
  limit = 200,
): Promise<ChatMessage[]> {
  const messages = await http.get<ChatMessage[]>(
    `/api/chat/sessions/${sessionId}/history`,
    { params: { limit } },
  );
  if (!Array.isArray(messages)) {
    throw new Error(`会话历史响应结构异常 session=${sessionId}`);
  }
  for (const m of messages) {
    m.sources = parseDocsJson(m.rag_docs_json);
    m.tool_calls = parseToolCallsJson(m.mcp_tool_calls_json);
  }
  return messages;
}

/** 仅检索（References 面板）：返回契约对象，docs 为引用文档 */
export function searchRagOnly(
  input: RagSearchOnlyRequest,
): Promise<RagSearchOnlyResponse> {
  return http.post<RagSearchOnlyResponse>("/api/chat/search", input);
}

/* =========================================================
 * NON-STREAM CHAT — POST /api/chat（RagAnswerResponse）
 * =======================================================*/

export async function chatNonStream(
  message: string,
  opts: ChatSendOptions = {},
): Promise<ChatMessage> {
  const body: RagQueryRequest = {
    query: message,
    session_id: opts.sessionId ?? null,
    stream: false,
    ...(opts.use_hyde !== undefined ? { use_hyde: opts.use_hyde } : {}),
    ...(opts.top_k !== undefined ? { top_k: opts.top_k } : {}),
    ...(opts.final_max_k !== undefined ? { final_max_k: opts.final_max_k } : {}),
    ...(opts.enable_graph !== undefined ? { enable_graph: opts.enable_graph } : {}),
    ...(opts.use_mcp_tools !== undefined ? { use_mcp_tools: opts.use_mcp_tools } : {}),
    ...(opts.model ? { model: opts.model } : {}),
    ...(opts.include_history !== undefined
      ? { include_history: opts.include_history }
      : {}),
  };
  const resp = await http.post<RagAnswerResponse>("/api/chat", body);
  return {
    message_id: resp.message_id ?? `gen_${Date.now()}`,
    session_id: resp.session_id ?? opts.sessionId ?? "",
    user_id: 0,
    role: "assistant",
    content: resp.answer,
    rag_query_rewrite: resp.rewrite_query,
    rag_retrieved_count: resp.retrieved_count,
    rag_final_count: resp.final_count,
    rag_docs_json: null,
    rag_error: resp.degraded_reason,
    latency_ms: resp.latency_ms,
    mcp_tool_calls_json: null,
    mcp_called_count: resp.mcp_tool_calls?.length ?? 0,
    created_at: new Date().toISOString(),
    sources: resp.docs?.length ? resp.docs : null,
    tool_calls: resp.mcp_tool_calls?.length
      ? resp.mcp_tool_calls.map((c) => ({ ...c, latency_ms: c.latency_ms ?? null }))
      : null,
  };
}

/* =========================================================
 * STREAM CHAT (fetch + ReadableStream, 绕过 axios)
 *   后端 SSE 事件：start / retrieval / token / done / error
 *   （兼容 NDJSON {kind, payload} 降级形态）
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
    const body: RagQueryRequest = {
      query: message,
      session_id: opts.sessionId ?? null,
      stream: true,
      ...(opts.use_hyde !== undefined ? { use_hyde: opts.use_hyde } : {}),
      ...(opts.top_k !== undefined ? { top_k: opts.top_k } : {}),
      ...(opts.final_max_k !== undefined ? { final_max_k: opts.final_max_k } : {}),
      ...(opts.enable_graph !== undefined ? { enable_graph: opts.enable_graph } : {}),
      ...(opts.use_mcp_tools !== undefined ? { use_mcp_tools: opts.use_mcp_tools } : {}),
      ...(opts.model ? { model: opts.model } : {}),
      ...(opts.include_history !== undefined
        ? { include_history: opts.include_history }
        : {}),
    };

    let finalContent = "";
    let finalSources: RetrievedDoc[] = [];
    const finalTools: Record<string, MCPToolCall> = {};
    let assistantId = `gen_${Date.now()}`;
    let finalSessionId = opts.sessionId ?? null;
    // done 事件内嵌壳（契约⑬）{code,message,data} → data.degraded_reason 透出给 UI（排队/降级提示）
    let degradedReason: string | null = null;
    let finalRetrieved = 0;
    let finalLatency: number | null = null;

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
        const kindFromEvent = sseEventNameToKind(eventName);
        dispatchRawLine(joined, kindFromEvent);
      };

      const flushLine = (rawLine: string) => {
        const line = rawLine.trimEnd();
        if (line.length === 0) {
          flushSSEGroup();
          return;
        }
        if (line.startsWith("event:")) {
          sseEventName = line.slice(6).trim();
          return;
        }
        if (line.startsWith("data:")) {
          const rest = line.slice(5).trimStart();
          if (rest === "[DONE]") {
            flushSSEGroup();
            return;
          }
          sseDataBuf.push(rest);
          return;
        }
        flushSSEGroup();
        dispatchRawLine(line, undefined);
      };

      const dispatchRawLine = (text: string, hintKind?: SSEEventKind | undefined) => {
        if (!text) return;
        let json: Record<string, unknown> | null = null;
        try {
          json = JSON.parse(text) as Record<string, unknown>;
        } catch {
          finalContent += text;
          opts.onDelta?.(text);
          return;
        }
        if (!json) return;

        const kind: SSEEventKind =
          hintKind ?? (json.kind as SSEEventKind | undefined) ?? inferLegacyKind(json);
        const payload = json.payload ?? json;

        switch (kind) {
          case "message_start": {
            // start 事件：{session_id, query}
            const p = payload as Record<string, unknown>;
            if (typeof p.message_id === "string") assistantId = p.message_id;
            if (p.session_id !== undefined && p.session_id !== null) {
              finalSessionId = String(p.session_id);
            }
            break;
          }
          case "delta": {
            // token 事件：{delta}
            const p = payload as Record<string, unknown>;
            let chunk = "";
            if (typeof payload === "string") chunk = payload;
            else if (typeof p.delta === "string") chunk = p.delta;
            else if (typeof p.content === "string") chunk = p.content;
            else if (typeof p.answer === "string") chunk = p.answer;
            finalContent += chunk;
            opts.onDelta?.(chunk);
            break;
          }
          case "sources": {
            // retrieval 事件：{docs, graph_entities, mcp_tool_calls}
            const p = payload as Record<string, unknown>;
            const arr = Array.isArray(p.docs) ? (p.docs as RetrievedDoc[]) : [];
            finalSources = arr;
            opts.onSources?.(finalSources);
            // MCPToolCallSummary[] 附带在 retrieval 事件（后端契约字段 call_id/tool_name/args_summary）
            if (Array.isArray(p.mcp_tool_calls)) {
              for (const raw of p.mcp_tool_calls as Array<Record<string, unknown>>) {
                const callId = String(raw.call_id ?? "");
                if (!callId) continue;
                const tc: MCPToolCall = {
                  call_id: callId,
                  tool_name: String(raw.tool_name ?? "mcp.tool"),
                  args_summary: String(raw.args_summary ?? ""),
                  status: (raw.status as MCPToolCallStatus) ?? "success",
                  latency_ms: typeof raw.latency_ms === "number" ? raw.latency_ms : null,
                  result_summary:
                    typeof raw.result_summary === "string" ? raw.result_summary : null,
                  progress_pct: 100,
                };
                finalTools[callId] = tc;
                opts.onToolResult?.(tc);
              }
            }
            break;
          }
          case "tool_start": {
            const p = payload as Record<string, unknown>;
            const tc: MCPToolCall = {
              call_id: String(p.call_id ?? `t_${Date.now()}`),
              tool_name: String(p.tool_name ?? "mcp.tool"),
              args_summary: String(p.args_summary ?? ""),
              status: "running",
              latency_ms: null,
              result_summary: null,
            };
            finalTools[tc.call_id] = tc;
            opts.onToolStart?.(tc);
            break;
          }
          case "tool_progress": {
            const p = payload as Record<string, unknown>;
            const id = String(p.call_id ?? "");
            const prev = finalTools[id] ?? {
              call_id: id,
              tool_name: String(p.tool_name ?? "mcp.tool"),
              args_summary: "",
              status: "running" as const,
              latency_ms: null,
              result_summary: null,
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
            const id = String(p.call_id ?? "");
            const prev = finalTools[id] ?? {
              call_id: id,
              tool_name: String(p.tool_name ?? "mcp.tool"),
              args_summary: "",
              status: "success" as const,
              latency_ms: null,
              result_summary: null,
            };
            const statusVal = p.status as MCPToolCallStatus | undefined;
            const next: MCPToolCall = {
              ...prev,
              status:
                statusVal === "success" || statusVal === "error" || statusVal === "timeout"
                  ? statusVal
                  : p.error_message ? "error" : "success",
              result_summary: typeof p.result_summary === "string" ? p.result_summary : prev.result_summary,
              error_message: typeof p.error_message === "string" ? p.error_message : prev.error_message,
              progress_pct: 100,
              finished_at: typeof p.finished_at === "string" ? p.finished_at : new Date().toISOString(),
            };
            finalTools[id] = next;
            opts.onToolResult?.(next);
            break;
          }
          case "message_end": {
            // done 事件：契约⑬ 内嵌壳 {code,message,data:{session_id,message_id,retrieved_count,latency_ms,degraded_reason,...}}
            // 兼容二者：壳形态与自描述裸字段形态
            const raw = payload as Record<string, unknown> | null;
            const inner = (raw && raw.data && typeof raw.data === "object" && !Array.isArray(raw.data))
              ? (raw.data as Record<string, unknown>)
              : (raw ?? {});
            if (typeof inner.message_id === "string") assistantId = inner.message_id;
            if (inner.session_id !== undefined && inner.session_id !== null) {
              finalSessionId = String(inner.session_id);
            }
            if (typeof inner.degraded_reason === "string" && inner.degraded_reason) {
              degradedReason = inner.degraded_reason;
            }
            if (typeof inner.retrieved_count === "number") finalRetrieved = inner.retrieved_count;
            if (typeof inner.latency_ms === "number") finalLatency = inner.latency_ms;
            break;
          }
          case "error": {
            const p = payload as Record<string, unknown>;
            throw new Error(String(p.message ?? "生成失败"));
          }
        }
      };

      const inferLegacyKind = (j: Record<string, unknown>): SSEEventKind => {
        if ("delta" in j || "content" in j || "answer" in j) return "delta";
        if ("docs" in j && Array.isArray(j.docs)) return "sources";
        if ("tool_name" in j && ("status" in j || "args_summary" in j)) {
          const s = j.status as string | undefined;
          if (s === "success" || s === "error" || "result_summary" in j) return "tool_result";
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
      if (buffer.trim()) flushLine(buffer.replace(/\r$/, ""));
      flushSSEGroup();

      const finalMessage: ChatMessage = {
        message_id: assistantId,
        session_id: finalSessionId ?? "",
        user_id: 0,
        role: "assistant",
        content: finalContent,
        rag_query_rewrite: null,
        rag_retrieved_count: finalSources.length || finalRetrieved || null,
        rag_final_count: null,
        rag_docs_json: null,
        rag_error: degradedReason,
        latency_ms: finalLatency,
        mcp_tool_calls_json: null,
        mcp_called_count: Object.keys(finalTools).length,
        created_at: new Date().toISOString(),
        sources: finalSources.length ? finalSources : null,
        tool_calls: Object.values(finalTools).length ? Object.values(finalTools) : null,
      };
      opts.onDone?.(finalMessage);
    } catch (err) {
      if ((err as Error).name === "AbortError" || controller.signal.aborted) {
        opts.onDone?.({
          message_id: assistantId,
          session_id: finalSessionId ?? "",
          user_id: 0,
          role: "assistant",
          content: finalContent,
          rag_query_rewrite: null,
          rag_retrieved_count: finalSources.length || finalRetrieved || null,
          rag_final_count: null,
          rag_docs_json: null,
          rag_error: degradedReason,
          latency_ms: finalLatency,
          mcp_tool_calls_json: null,
          mcp_called_count: Object.keys(finalTools).length,
          created_at: new Date().toISOString(),
          sources: finalSources.length ? finalSources : null,
          tool_calls: Object.values(finalTools).length ? Object.values(finalTools) : null,
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
    case "done":
    case "end":
    case "message_end":
      return "message_end";
    case "token":
    case "delta":
    case "content":
    case "chunk":
      return "delta";
    case "retrieval":
    case "sources":
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
      return "delta";
  }
}
