/**
 * auth-client store 持久化单测（task69 · task42 批判①「登录态持久化/刷新/登出」）
 *
 * Playwright 被项目禁用（AGENTS.md 硬性规则），以真实 zustand store + jsdom localStorage
 * 的存储往返替代「刷新 / 多标签」浏览器用例：
 *  - 刷新：state 重置（模拟刷新/新会话）→ hydrate() 从 localStorage 恢复 → isAuthenticated()=true
 *  - 多标签：localStorage 是浏览器同源跨标签共享存储，hydrate 恢复即等价新标签共享会话
 *    （jsdom 单环境无法真的开标签，此项以其存储语义还原）
 *  - 登出：logout() 清 localStorage + state → isAuthenticated()=false
 */
import { beforeEach, describe, expect, it } from "vitest";
import { useAuthStore } from "./auth-client";

function resetStore() {
  useAuthStore.setState({
    ready: false,
    token: null,
    refreshToken: null,
    tenantId: null,
    me: null,
  });
  window.localStorage.clear();
}

/** 模拟「页面刷新 / 新标签加载」：仅清空内存态，localStorage 保留（持久化数据仍在） */
function reloadStateOnly() {
  useAuthStore.setState({
    ready: false,
    token: null,
    refreshToken: null,
    tenantId: null,
    me: null,
  });
}

beforeEach(() => resetStore());

const ME = { id: 90001, nickname: "小明", email: "s@example.com", roles: ["student"] };

describe("登录态持久化（task42 批判①）", () => {
  it("setAuth persist 写入 localStorage 四键（token/refresh/me/tenant）", () => {
    useAuthStore.getState().setAuth({
      token: "access-jwt",
      refreshToken: "refresh-jwt",
      tenantId: "T100",
      me: ME,
      persist: true,
    });
    expect(window.localStorage.getItem("edu:auth:token")).toBe("access-jwt");
    expect(window.localStorage.getItem("edu:auth:refresh")).toBe("refresh-jwt");
    expect(window.localStorage.getItem("edu:auth:tenant")).toBe("T100");
    expect(JSON.parse(window.localStorage.getItem("edu:auth:me")!).nickname).toBe("小明");
  });

  it("模拟刷新（state 重置）→ hydrate() 恢复登录态（token/user 均在）", () => {
    useAuthStore.getState().setAuth({
      token: "access-jwt",
      refreshToken: "refresh-jwt",
      tenantId: "T100",
      me: ME,
      persist: true,
    });
    // 刷新 = 全新 store 状态（ready=false、token 空）但 localStorage 留存
    reloadStateOnly();
    useAuthStore.getState().hydrate();
    expect(useAuthStore.getState().ready).toBe(true);
    expect(useAuthStore.getState().token).toBe("access-jwt");
    expect(useAuthStore.getState().refreshToken).toBe("refresh-jwt");
    expect(useAuthStore.getState().tenantId).toBe("T100");
    expect(useAuthStore.getState().me?.nickname).toBe("小明");
    expect(useAuthStore.getState().isAuthenticated()).toBe(true);
  });

  it("多标签共享会话（localStorage 同源共享 → hydrate 即达受保护态）", () => {
    // 标签 A 登录写入 localStorage
    useAuthStore.getState().setAuth({
      token: "access-jwt",
      refreshToken: "refresh-jwt",
      tenantId: "T100",
      me: ME,
      persist: true,
    });
    // 标签 B 全新加载 → 直接 hydrate → 无需二次登录
    reloadStateOnly();
    useAuthStore.getState().hydrate();
    expect(useAuthStore.getState().isAuthenticated()).toBe(true);
    expect(useAuthStore.getState().token).toBe("access-jwt");
  });

  it("logout 清空 localStorage 四键 + state → isAuthenticated()=false", () => {
    useAuthStore.getState().setAuth({
      token: "access-jwt",
      refreshToken: "refresh-jwt",
      tenantId: "T100",
      me: ME,
      persist: true,
    });
    useAuthStore.getState().logout({ silent: true });
    expect(window.localStorage.getItem("edu:auth:token")).toBeNull();
    expect(window.localStorage.getItem("edu:auth:refresh")).toBeNull();
    expect(window.localStorage.getItem("edu:auth:me")).toBeNull();
    expect(window.localStorage.getItem("edu:auth:tenant")).toBeNull();
    expect(useAuthStore.getState().token).toBeNull();
    expect(useAuthStore.getState().isAuthenticated()).toBe(false);
  });
});