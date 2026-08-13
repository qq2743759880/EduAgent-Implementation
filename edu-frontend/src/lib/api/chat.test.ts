/**
 * chat.ts API 封装单测（task05）
 * 覆盖：
 *   - R-1 修复：getChatHistory 请求路径必须是 /history（不是 /messages）
 *   - R-7 治理：getChatHistory 失败时保留空态兜底但必须 console.error（不再静默吞错）
 *   - deleteChatSession 走 DELETE /api/chat/sessions/{id}（R-2 后端契约 200/403/404）
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { api } from "@/lib/api-client";
import { createChatSession, deleteChatSession, getChatHistory, listChatSessions, searchRagOnly } from "./chat";

vi.mock("@/lib/api-client", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  API_BASE: "http://127.0.0.1:8000",
}));

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);
const mockDelete = vi.mocked(api.delete);

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("getChatHistory（R-1 路径修复）", () => {
  it("请求路径为 /api/chat/sessions/{id}/history（不再 /messages）", async () => {
    mockGet.mockResolvedValueOnce({
      data: [
        { id: "m_1", session_id: "s_abc", role: "user", content: "你好" },
        { id: "m_2", session_id: "s_abc", role: "assistant", content: "你好，我是 AI 助手" },
      ],
    });
    const history = await getChatHistory("s_abc");
    expect(mockGet).toHaveBeenCalledWith("/api/chat/sessions/s_abc/history");
    expect(history).toHaveLength(2);
    expect(history[1].role).toBe("assistant");
  });

  it("数字 sessionId 也拼进 /history 路径", async () => {
    mockGet.mockResolvedValueOnce({ data: [] });
    await getChatHistory(42);
    expect(mockGet).toHaveBeenCalledWith("/api/chat/sessions/42/history");
  });

  it("失败时返回空数组兜底，但必须 console.error（R-7 不静默吞错）", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mockGet.mockRejectedValueOnce(new Error("Network Error"));
    const history = await getChatHistory("s_abc");
    expect(history).toEqual([]);
    expect(consoleError).toHaveBeenCalled();
    expect(consoleError.mock.calls[0][0]).toContain("[chat]");
  });

  it("响应非数组时也兜底为空数组且 console.error", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mockGet.mockResolvedValueOnce({ data: { items: [] } });
    const history = await getChatHistory("s_abc");
    expect(history).toEqual([]);
    expect(consoleError).toHaveBeenCalled();
  });
});

describe("deleteChatSession（R-2 后端契约）", () => {
  it("调用 DELETE /api/chat/sessions/{id}", async () => {
    mockDelete.mockResolvedValueOnce({ data: { ok: true } });
    await deleteChatSession("s_abc");
    expect(mockDelete).toHaveBeenCalledWith("/api/chat/sessions/s_abc");
  });

  it("失败向上抛（调用方 useChatSessions 负责回滚 + toast）", async () => {
    mockDelete.mockRejectedValueOnce(new Error("403"));
    await expect(deleteChatSession("s_abc")).rejects.toThrow("403");
  });
});

describe("既有契约不回归", () => {
  it("createChatSession 走 POST /api/chat/sessions", async () => {
    mockPost.mockResolvedValueOnce({ data: { id: "s_new", title: "新会话" } });
    const s = await createChatSession({ title: "新会话" });
    expect(mockPost).toHaveBeenCalledWith("/api/chat/sessions", { title: "新会话" });
    expect(s.id).toBe("s_new");
  });

  it("listChatSessions 走 GET /api/chat/sessions", async () => {
    mockGet.mockResolvedValueOnce({ data: [{ id: "s_1", title: "t" }] });
    const list = await listChatSessions();
    expect(mockGet).toHaveBeenCalledWith("/api/chat/sessions");
    expect(list).toHaveLength(1);
  });

  it("归一化：后端 session_id/message_count → 前端 id/messages_count（G7 联调实证）", async () => {
    mockGet.mockResolvedValueOnce({
      data: [
        {
          session_id: "s_abc",
          user_id: 897,
          title: "后端字段会话",
          visibility: "private",
          message_count: 2,
          last_message_at: "2026-08-13T00:51:41",
          created_at: "2026-08-13T00:51:40",
          updated_at: "2026-08-13T00:51:41",
          yn: 1,
        },
      ],
    });
    const list = await listChatSessions();
    expect(list[0].id).toBe("s_abc");
    expect(list[0].messages_count).toBe(2);
    expect(list[0].title).toBe("后端字段会话");
    expect(list[0].created_at).toBe("2026-08-13T00:51:40");
  });

  it("归一化：createChatSession 返回 session_id 也能拿到 id", async () => {
    mockPost.mockResolvedValueOnce({
      data: { session_id: "s_new", title: "新会话", message_count: 0 },
    });
    const s = await createChatSession();
    expect(s.id).toBe("s_new");
    expect(s.messages_count).toBe(0);
  });

  it("列表失败返回空数组兜底且 console.error（R-7）", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mockGet.mockRejectedValueOnce(new Error("Network Error"));
    const list = await listChatSessions();
    expect(list).toEqual([]);
    expect(consoleError).toHaveBeenCalled();
  });
});

describe("searchRagOnly（R-7 #7 消除静默吞错）", () => {
  it("成功路径：POST /api/chat/search 并归一化 RagDoc[]（limit 默认 5）", async () => {
    mockPost.mockResolvedValueOnce({
      data: [
        { id: 1, type: "section", title: "雅思听力", snippet: "s1", score: 0.9 },
        { id: 2, type: "doc", title: "文档", snippet: null, score: null },
      ],
    });
    const docs = await searchRagOnly("如何备考听力");
    expect(mockPost).toHaveBeenCalledWith("/api/chat/search", {
      query: "如何备考听力",
      subject_code: null,
      limit: 5,
    });
    expect(docs).toHaveLength(2);
    expect(docs[0]).toMatchObject({ id: 1, type: "section", title: "雅思听力", score: 0.9 });
    expect(docs[1].title).toBe("文档");
  });

  it("catch 后返回空数组且 console.error 被调用（R-7 #7 主用例：不再静默吞错）", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    mockPost.mockRejectedValueOnce(new Error("Network Error"));
    const docs = await searchRagOnly("查询失败场景");
    expect(docs).toEqual([]);
    expect(consoleError).toHaveBeenCalled();
    expect(consoleError.mock.calls[0][0]).toContain("[chat]");
  });
});
