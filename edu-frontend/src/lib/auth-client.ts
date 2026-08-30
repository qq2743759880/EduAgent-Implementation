"use client";

import { create } from "zustand";
import { toast } from "sonner";

import { api, http, onApiUnauthorized, ApiError } from "./api-client";
import type { LoginInput } from "./validators/auth-schemas";
import type { RegisterInput } from "./validators/auth-schemas";

/** localStorage keys（前缀避免和其他应用冲突） */
const K_TOKEN = "edu:auth:token";
const K_REFRESH = "edu:auth:refresh";
const K_ME = "edu:auth:me";
const K_TENANT = "edu:auth:tenant";

/**
 * 后端 UserInfo（edu-agent/app/auth/schemas.py，snake_case 契约）：
 * /api/auth/login 的 user 与 /api/auth/me 直接返回此结构。
 */
export interface RawUserInfo {
  user_id?: number;
  id?: number;
  account?: string | null;
  username?: string | null;
  nickname?: string;
  real_name?: string | null;
  mobile?: string | null;
  email?: string | null;
  gender?: string | null;
  avatar_url?: string | null;
  avatar?: string | null;
  role?: string | { value?: string } | null;
  role_code?: string | null;
  roles?: string[];
  tenant_id?: string | null;
  tenantId?: string | null;
}

/** 登录用户展示模型（store 内部形状；由 _normalizeUser 从契约 RawUserInfo 归一化） */
export interface UserInfo {
  id: number | string;
  nickname: string;
  email: string;
  username?: string | null;
  avatar?: string | null;
  roles?: string[];
  tenantId?: string | null;
}

/** 后端 LoginResponse（auth/schemas.py）：access_token/refresh_token/expires_in/user */
export interface AuthLoginResponse {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in?: number;
  user?: RawUserInfo | Partial<UserInfo> | null;
  /** 兼容字段：本地归一化后回填，调用方可直接读 */
  token?: string;
  tenantId?: string | null;
}

/** 后端 register 返回：壳拦截器解包后为 { user_id } */
export interface AuthRegisterResponse {
  ok: boolean;
  user_id?: number;
  token?: string;
  user?: RawUserInfo | Partial<UserInfo>;
  autoLogin?: boolean;
}

function _normalizeUser(
  raw: Partial<UserInfo> | RawUserInfo | null | undefined,
  fallbackAccount?: string | null,
): UserInfo | null {
  if (!raw) return null;
  const r = raw as RawUserInfo;
  const roleStr: string | null =
    (typeof r.role === "string"
      ? r.role
      : (r.role && typeof r.role === "object" ? r.role.value ?? null : null)) ||
    (typeof r.role_code === "string" ? r.role_code : null) ||
    null;
  const accountVal =
    (typeof r.username === "string" ? r.username : null) ||
    (typeof r.account === "string" ? r.account : null) ||
    fallbackAccount ||
    null;
  const emailVal = (typeof r.email === "string" ? r.email : null) ?? "";
  const avatarVal =
    typeof r.avatar_url === "string"
      ? r.avatar_url
      : typeof r.avatar === "string"
        ? r.avatar
        : (raw as Partial<UserInfo>).avatar ?? null;
  const rolesVal =
    Array.isArray(r.roles) && r.roles.length
      ? r.roles
      : roleStr
        ? [roleStr]
        : [];
  return {
    id: r.user_id ?? r.id ?? (raw as Partial<UserInfo>).id ?? "",
    nickname: r.nickname ?? (raw as Partial<UserInfo>).nickname ?? "同学",
    email: emailVal,
    username: accountVal,
    avatar: avatarVal,
    roles: rolesVal,
    tenantId: r.tenantId ?? r.tenant_id ?? (raw as Partial<UserInfo>).tenantId ?? null,
  };
}

interface AuthState {
  /** 是否完成客户端 hydrate（避免 SSR 窗口与 localStorage 读写冲突） */
  ready: boolean;
  token: string | null;
  refreshToken: string | null;
  tenantId: string | null;
  me: UserInfo | null;
  /** 判断是否已登录：完成 hydrate 且存在非空 token */
  isAuthenticated: () => boolean;
  /** 从 localStorage 恢复（客户端启动后调用 1 次） */
  hydrate: () => void;
  /** 直接写状态（后端登录成功后调用）；可选写 localStorage */
  setAuth: (payload: {
    token: string;
    refreshToken?: string | null;
    tenantId?: string | null;
    me?: UserInfo | Partial<UserInfo> | null;
    persist?: boolean;
  }) => void;
  login: (input: LoginInput) => Promise<AuthLoginResponse>;
  register: (input: RegisterInput) => Promise<AuthRegisterResponse>;
  /** 后端 /api/auth/me 刷新 me（404 时降级 /api/users/me） */
  refreshMe: () => Promise<UserInfo>;
  /** 登出：默认带 toast/redirect；silent=true 仅清状态不跳路由（401 时用） */
  logout: (options?: { silent?: boolean; redirectTo?: string }) => void;
}

const safeLS = {
  get(key: string): string | null {
    if (typeof window === "undefined") return null;
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key: string, value: string) {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* ignore quota */
    }
  },
  remove(key: string) {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  },
};

export const useAuthStore = create<AuthState>((set, get) => ({
  ready: false,
  token: null,
  refreshToken: null,
  tenantId: null,
  me: null,

  isAuthenticated() {
    const s = get();
    return s.ready && !!s.token;
  },

  hydrate() {
    if (get().ready) return;
    const token = safeLS.get(K_TOKEN);
    const refreshToken = safeLS.get(K_REFRESH);
    const tenantId = safeLS.get(K_TENANT);
    let me: UserInfo | null = null;
    const meRaw = safeLS.get(K_ME);
    if (meRaw) {
      try {
        me = JSON.parse(meRaw) as UserInfo;
      } catch {
        me = null;
      }
    }
    set({ ready: true, token, refreshToken, tenantId, me });
  },

  setAuth({ token, refreshToken = null, tenantId = null, me = null, persist = true }) {
    const normalizedMe = _normalizeUser(me) ?? null;
    set({ token, refreshToken, tenantId, me: normalizedMe });
    if (persist) {
      safeLS.set(K_TOKEN, token);
      if (refreshToken) safeLS.set(K_REFRESH, refreshToken);
      else safeLS.remove(K_REFRESH);
      if (tenantId) safeLS.set(K_TENANT, tenantId);
      if (normalizedMe) safeLS.set(K_ME, JSON.stringify(normalizedMe));
    }
  },

  async login(input: LoginInput): Promise<AuthLoginResponse> {
    const identifier = (input.identifier ?? "").trim();
    if (!identifier) {
      throw new ApiError(400, { message: "请输入账号或邮箱" });
    }
    /* 统一以 account 字段提交（后端 schema：UserLogin.account 三选一兼容） */
    const payload = { account: identifier, password: input.password };
    /* 拦截器已对壳形态解包：await 结果即后端 LoginResponse 业务体 */
    const data = await http.post<AuthLoginResponse>("/api/auth/login", payload);
    const token: string = data.access_token ?? data.token ?? "";
    if (!token) {
      throw new ApiError(0, { message: "登录失败：未返回 token" });
    }
    (data as AuthLoginResponse).token = token;
    const fallbackAccount = identifier.includes("@") ? null : identifier;
    get().setAuth({
      token,
      refreshToken: data.refresh_token ?? null,
      tenantId: (data.user as RawUserInfo | undefined)?.tenant_id ?? null,
      me: _normalizeUser(data.user, fallbackAccount) ?? null,
      persist: true,
    });
    if (!data.user) {
      get().refreshMe().catch(() => undefined);
    }
    return data;
  },

  async register(input: RegisterInput): Promise<AuthRegisterResponse> {
    /* 后端 UserRegister 字段：account（登录账号）/ nickname / password / email | mobile */
    const accountVal = (input.username || "").trim() || (input.email || "").trim();
    const reqBody = {
      account: accountVal || undefined,
      username: (input.username || "").trim() || undefined,
      nickname: input.nickname,
      email: input.email,
      password: input.password,
    };
    const data = await http.post<{ user_id?: number } & Partial<AuthRegisterResponse>>(
      "/api/auth/register",
      reqBody,
    );
    const out: AuthRegisterResponse = { ok: true, user_id: data.user_id };

    /* 后端仅返回 user_id；为避免注册后还需手动登录，再发一次 login 完成自动登录 */
    const needExtraLogin = out.autoLogin !== false && !out.token;
    if (needExtraLogin && accountVal) {
      try {
        const loginResp = await get().login({ identifier: accountVal, password: input.password });
        out.token = loginResp.access_token ?? loginResp.token;
        out.user = loginResp.user ?? undefined;
        out.autoLogin = true;
      } catch {
        out.autoLogin = false;
        /* 不阻断 register 成功反馈：用户自行前往登录页，或调用方根据 autoLogin=false 判断 */
      }
    } else if (out.autoLogin !== false && out.token) {
      get().setAuth({
        token: out.token,
        me: _normalizeUser(out.user, accountVal) ?? null,
      });
    }
    return out;
  },

  async refreshMe(): Promise<UserInfo> {
    /* /api/auth/me 返回后端 UserInfo（snake_case）；404 时降级 /api/users/me */
    let raw: RawUserInfo | Partial<UserInfo>;
    try {
      raw = await http.get<RawUserInfo | Partial<UserInfo>>("/api/auth/me");
    } catch (err) {
      const status = (err as ApiError).status;
      if (status === 404) {
        raw = await http.get<RawUserInfo | Partial<UserInfo>>("/api/users/me");
      } else {
        throw err;
      }
    }
    const me = _normalizeUser(raw) as UserInfo;
    if (!me || !me.id) {
      throw new ApiError(0, { message: "获取个人信息失败：返回数据为空" });
    }
    set({ me });
    safeLS.set(K_ME, JSON.stringify(me));
    if (me.tenantId) {
      set({ tenantId: me.tenantId });
      safeLS.set(K_TENANT, me.tenantId);
    }
    return me;
  },

  logout(options = {}) {
    const { silent = false, redirectTo = "/login" } = options;
    safeLS.remove(K_TOKEN);
    safeLS.remove(K_REFRESH);
    safeLS.remove(K_ME);
    safeLS.remove(K_TENANT);
    set({ token: null, refreshToken: null, me: null, tenantId: null });

    if (silent) return;
    toast.success("已退出登录");
    if (typeof window !== "undefined") {
      const url = new URL(window.location.origin + redirectTo);
      const curPath = window.location.pathname + window.location.search;
      if (curPath && curPath !== redirectTo && !curPath.startsWith(redirectTo + "?")) {
        url.searchParams.set("redirect", curPath);
      }
      window.location.href = url.pathname + url.search;
    }
  },
}));

/* ---------------- 全局副作用：api interceptor + onUnauthorized ---------------- */

/** 请求拦截器：Authorization 注入 Bearer token */
api.interceptors.request.use(
  (config) => {
    const token = useAuthStore.getState().token;
    if (token && config.headers) {
      config.headers.set("Authorization", `Bearer ${token}`);
    }
    const tenantId = useAuthStore.getState().tenantId;
    if (tenantId && config.headers) {
      const hasHeader = config.headers.has("X-Tenant-Id");
      if (!hasHeader) config.headers.set("X-Tenant-Id", tenantId);
    }
    return config;
  },
  (err) => Promise.reject(err),
);

/** 401/403 全局回调（fe-task00 / D4 语义修正）：
 *  - 仅 401 登出跳登录（token 失效信号）；
 *  - 403 是「该账号无权访问该资源」——保会话 + toast「无权限」+ console.error，不登出不跳转。
 *    （student 偶发命中 admin 端点 403 不再被误杀会话，与 fx-task02 验收「student 拦截 + toast 无权限」一致） */
onApiUnauthorized((status) => {
  const s = useAuthStore.getState();
  const wasLoggedIn = Boolean(s.token);
  if (status === 401) {
    s.logout({ silent: true });
    if (wasLoggedIn) toast.warning("登录已过期，请重新登录");
    if (typeof window === "undefined") return;
    const cur = window.location.pathname + window.location.search;
    /* 兜底：当前已在认证页（/login /register）时不做整页重载 ——
       api-client 拦截器已对 login/register 接口跳过本回调；此处防御
       未来新增认证接口漏判，避免重载清空表单错误横幅 */
    if (/^\/(?:login|register)(?:[?#]|$)/.test(cur)) return;
    const loginUrl = new URL(window.location.origin + "/login");
    if (cur && cur !== "/login" && !cur.startsWith("/login?")) {
      loginUrl.searchParams.set("redirect", cur);
    }
    window.location.href = loginUrl.pathname + loginUrl.search;
  } else if (status === 403) {
    console.error("[auth] 无权限访问资源（403）", { path: window.location.pathname });
    toast.error("无权限", { description: "当前账号无权访问该资源" });
    /* 不 logout、不整页跳转 —— 保会话 */
  }
});

export default useAuthStore;
