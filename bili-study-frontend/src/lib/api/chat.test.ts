/**
 * chat.ts API 封装单测（task40 对齐 app/chat/schemas.py 契约）
 * 覆盖：
 *   - 拦截器解包语义：mock http.* 直接返回业务体（无 .data 解包）
 *   - getChatHistory 请求路径 /api/chat/sessions/{sid}/history + rag_docs_json 解析
 *   - R-7 治理：读操作错误向上抛（不再 catch 兜底伪装成功）
 *   - deleteChatSession 走 DELETE /api/chat/sessions/{id}
 *   - searchRagOnly 返回契约对象 RagSearchOnlyResponse
 *   - chatNonStream：RagAnswerResponse → ChatMessage 映射
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { http } from "@/lib/api-client";
import {
  chatNonStream,
  chatStream,
  createChatSession,
  deleteChatSession,
  getChatHistory,
  listChatSessions,
  searchRagOnly,
} from "./chat";

vi.mock("@/lib/api-client", () => ({
  http: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
  API_BASE: "http://127.0.0.1:8000",
}));

const mockGet = vi.mocked(http.get);
const mockPost = vi.mocked(http.post);
const mockDelete = vi.mocked(http.delete);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getChatHistory（R-1 路径 + 契约字段）", () => {
  it("请求路径为 /api/chat/sessions/{id}/history，解析 rag_docs_json → sources", async () => {
    mockGet.mockResolvedValueOnce([
      {
        message_id: "m_1",
        session_id: "s_abc",
        user_id: 897,
        role: "user",
        content: "你好",
        rag_docs_json: null,
        mcp_tool_calls_json: null,
        created_at: "2026-08-13T00:51:41",
      },
      {
        message_id: "m_2",
        session_id: "s_abc",
        user_id: 897,
        role: "assistant",
        content: "你好，我是 AI 助手",
        rag_docs_json: JSON.stringify([
          { doc_id: "d1", score: 0.9, content: "片段", source_file: "a.pdf" },
        ]),
        mcp_tool_calls_json: JSON.stringify([
          { call_id: "c1", tool_name: "kb.search", args_summary: "q=x", status: "success", latency_ms: 12, result_summary: "ok" },
        ]),
        created_at: "2026-08-13T00:51:42",
      },
    ] as never);
    const history = await getChatHistory("s_abc");
    expect(mockGet).toHaveBeenCalledWith("/api/chat/sessions/s_abc/history", {
      params: { limit: 200 },
    });
    expect(history).toHaveLength(2);
    expect(history[1].role).toBe("assistant");
    expect(history[1].sources).toHaveLength(1);
    expect(history[1].sources?.[0].doc_id).toBe("d1");
    expect(history[1].tool_calls?.[0].tool_name).toBe("kb.search");
  });

  it("响应非数组时抛结构异常（R-7：错误向上抛，不伪装空态）", async () => {
    mockGet.mockResolvedValueOnce({ items: [] } as never);
    await expect(getChatHistory("s_abc")).rejects.toThrow(/结构异常/);
  });

  it("网络失败时向上抛（调用方负责空态渲染）", async () => {
    mockGet.mockRejectedValueOnce(new Error("Network Error"));
    await expect(getChatHistory("s_abc")).rejects.toThrow("Network Error");
  });
});

describe("deleteChatSession（R-2 后端契约）", () => {
  it("调用 DELETE /api/chat/sessions/{id}，返回 {ok:true}", async () => {
    mockDelete.mockResolvedValueOnce({ ok: true });
    const resp = await deleteChatSession("s_abc");
    expect(mockDelete).toHaveBeenCalledWith("/api/chat/sessions/s_abc");
    expect(resp.ok).toBe(true);
  });

  it("失败向上抛（调用方 useChatSessions 负责回滚 + toast）", async () => {
    mockDelete.mockRejectedValueOnce(new Error("403"));
    await expect(deleteChatSession("s_abc")).rejects.toThrow("403");
  });
});

describe("sessions（零解包 + 契约字段直通）", () => {
  it("createChatSession 走 POST /api/chat/sessions，返回 ChatSession 原样", async () => {
    const session = {
      session_id: "s_new",
      user_id: 1,
      title: "新会话",
      visibility: "private",
      message_count: 0,
      last_message_at: null,
      created_at: "2026-08-18T00:00:00",
      updated_at: "2026-08-18T00:00:00",
      yn: 1,
    };
    mockPost.mockResolvedValueOnce(session);
    const s = await createChatSession({ title: "新会话" });
    expect(mockPost).toHaveBeenCalledWith("/api/chat/sessions", { title: "新会话" });
    expect(s.session_id).toBe("s_new");
    expect(s.message_count).toBe(0);
  });

  it("listChatSessions 走 GET /api/chat/sessions?limit=50", async () => {
    mockGet.mockResolvedValueOnce([
      {
        session_id: "s_1",
        user_id: 1,
        title: "t",
        visibility: "private",
        message_count: 3,
        last_message_at: null,
        created_at: "2026-08-18T00:00:00",
        updated_at: "2026-08-18T00:00:00",
        yn: 1,
      },
    ] as never);
    const list = await listChatSessions();
    expect(mockGet).toHaveBeenCalledWith("/api/chat/sessions", {
      params: { limit: 50 },
    });
    expect(list).toHaveLength(1);
    expect(list[0].session_id).toBe("s_1");
  });

  it("listChatSessions 失败向上抛（R-7：不静默吞错）", async () => {
    mockGet.mockRejectedValueOnce(new Error("Network Error"));
    await expect(listChatSessions()).rejects.toThrow("Network Error");
  });
});

describe("searchRagOnly（契约对象，非旧数组形态）", () => {
  it("POST /api/chat/search，返回 RagSearchOnlyResponse", async () => {
    const resp = {
      docs: [
        {
          doc_id: "d1",
          score: 0.9,
          content: "雅思听力",
          source_file: "listen.pdf",
          content_type: "pdf",
          series_code: null,
          series_name: null,
          module_codes: [],
          keywords: [],
          tenant_id: null,
          visibility: "public",
          source_channel: "upload",
        },
      ],
      graph_entities: [],
      retrieved_count: 1,
      final_count: 1,
      rewrite_query: null,
      degraded_reason: null,
    };
    mockPost.mockResolvedValueOnce(resp);
    const out = await searchRagOnly({ query: "如何备考听力", top_k: 5 });
    expect(mockPost).toHaveBeenCalledWith("/api/chat/search", {
      query: "如何备考听力",
      top_k: 5,
    });
    expect(out.docs).toHaveLength(1);
    expect(out.docs[0].doc_id).toBe("d1");
    expect(out.retrieved_count).toBe(1);
  });

  it("失败向上抛（R-7：不静默吞错）", async () => {
    mockPost.mockRejectedValueOnce(new Error("Network Error"));
    await expect(searchRagOnly({ query: "查询失败" })).rejects.toThrow("Network Error");
  });
});

describe("chatNonStream（RagAnswerResponse → ChatMessage）", () => {
  it("POST /api/chat 非流式，映射 answer/docs/mcp_tool_calls", async () => {
    const resp = {
      session_id: "s_1",
      message_id: "m_9",
      answer: "答案内容",
      docs: [
        {
          doc_id: "d1",
          score: 0.8,
          content: "片段",
          source_file: null,
          content_type: null,
          series_code: null,
          series_name: null,
          module_codes: [],
          keywords: [],
          tenant_id: null,
          visibility: null,
          source_channel: "upload",
        },
      ],
      graph_entities: [],
      rewrite_query: "改写后",
      retrieved_count: 10,
      final_count: 1,
      latency_ms: 800,
      degraded_reason: null,
      mcp_tool_calls: [
        {
          call_id: "c1",
          tool_name: "kb.search",
          args_summary: "q",
          status: "success",
          latency_ms: 20,
          result_summary: "ok",
        },
      ],
    };
    mockPost.mockResolvedValueOnce(resp);
    const msg = await chatNonStream("问题", { sessionId: "s_1" });
    expect(mockPost).toHaveBeenCalledWith("/api/chat", {
      query: "问题",
      session_id: "s_1",
      stream: false,
    });
    expect(msg.role).toBe("assistant");
    expect(msg.content).toBe("答案内容");
    expect(msg.message_id).toBe("m_9");
    expect(msg.sources).toHaveLength(1);
    expect(msg.tool_calls?.[0].call_id).toBe("c1");
    expect(msg.rag_retrieved_count).toBe(10);
  });
});

/* ---------------- chatStream SSE（task114 C-A：delta/done 嵌套壳/error） ---------------- */

describe("chatStream SSE（C-A：delta 累加 / done 嵌套壳 / error 分支）", () => {
  afterEach(() => {
    // @ts-expect-error 还原全局 fetch
    delete globalThis.fetch;
  });

  it("delta 事件累加 content（token 字段已弃用，只认 delta）", async () => {
    const body =
      "event: start\ndata: {\"session_id\":\"s_1\"}\n\n" +
      "event: delta\ndata: {\"delta\":\"你好\"}\n\n" +
      "event: delta\ndata: {\"delta\":\"，小柚\"}\n\n" +
      "event: done\ndata: {\"code\":0,\"message\":\"ok\",\"data\":{\"session_id\":\"s_1\",\"message_id\":\"m1\",\"retrieved_count\":1,\"latency_ms\":12}}\n\n";
    const encoder = new TextEncoder();
    const bodyReadable = new ReadableStream<Uint8Array>({
      start(ctrl) {
        ctrl.enqueue(encoder.encode(body));
        ctrl.close();
      },
    });
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, body: bodyReadable, text: () => Promise.resolve("") });

    const deltas: string[] = [];
    const final = new Promise<unknown>((resolve, reject) => {
      chatStream("问题", {
        sessionId: "s_1",
        onDelta: (d) => deltas.push(d),
        onDone: (m) => resolve(m),
        onError: (e) => reject(e),
      });
    });
    const msg = await Promise.race([final, delayTimeout()]) as { content: string };
    expect(deltas).toEqual(["你好", "，小柚"]);
    expect(msg.content).toBe("你好，小柚");
  });

  it("done 事件解嵌套壳 {code,message,data} → 透出 message_id/session_id", async () => {
    const body =
      "event: done\ndata: {\"code\":0,\"message\":\"ok\",\"data\":{\"session_id\":\"s_9\",\"message_id\":\"m99\",\"degraded_reason\":null}}\n\n";
    const encoder = new TextEncoder();
    const bodyReadable = new ReadableStream<Uint8Array>({
      start(ctrl) {
        ctrl.enqueue(encoder.encode(body));
        ctrl.close();
      },
    });
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, body: bodyReadable, text: () => Promise.resolve("") });

    const final = new Promise<{ session_id: string; message_id: string }>((resolve, reject) => {
      chatStream("问题", {
        sessionId: "s_1",
        onDone: (m) => resolve(m),
        onError: (e) => reject(e),
      });
    });
    const msg = await Promise.race([final, delayTimeout()]);
    expect(msg.session_id).toBe("s_9");
    expect(msg.message_id).toBe("m99");
  });

  it("error 事件分支 → onError（message 透出），不产出 done", async () => {
    const body = "event: error\ndata: {\"message\":\"生成失败\"}\n\n";
    const encoder = new TextEncoder();
    const bodyReadable = new ReadableStream<Uint8Array>({
      start(ctrl) {
        ctrl.enqueue(encoder.encode(body));
        ctrl.close();
      },
    });
    globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, body: bodyReadable, text: () => Promise.resolve("") });

    const doneCalled = vi.fn();
    const err = new Promise<Error>((resolve, reject) => {
      chatStream("问题", {
        sessionId: "s_1",
        onDone: doneCalled,
        onError: (e) => resolve(e),
      });
      void reject;
    });
    const resolved = await Promise.race([err, delayTimeout()]);
    expect(resolved.message).toBe("生成失败");
    expect(doneCalled).not.toHaveBeenCalled();
  });
});

/** 兜底超时（若流事件未如约触发，避免测试挂死） */
function delayTimeout(): Promise<never> {
  return new Promise((_, reject) =>
    setTimeout(() => reject(new Error("SSE 测试超时：流事件未按契约触发")), 2000),
  );
}
