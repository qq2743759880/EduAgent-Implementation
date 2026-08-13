"use client";

import { create } from "zustand";
import { AxiosResponse } from "axios";
import { toast } from "sonner";

import { api, onApiUnauthorized, ApiError } from "./api-client";
import type { LoginInput } from "./validators/auth-schemas";
import type { RegisterInput } from "./validators/auth-schemas";

/** localStorage keys（前缀避免和其他应用冲突） */
const K_TOKEN = "edu:auth:token";
const K_ME = "edu:auth:me";
const K_TENANT = "edu:auth:tenant";

/** 登录用户基础信息（后端 me 返回更丰富，这里取够用的最小集） */
export interface UserInfo {
  id: number | string;
  nickname: string;
  email: string;
  username?: string | null;
  avatar?: string | null;
  roles?: string[];
  tenantId?: string | null;
}

export interface AuthLoginResponse {
  token: string;
  accessToken?: string;
  access_token?: string;
  refreshToken?: string;
  refresh_token?: string;
  tenantId?: string | null;
  user?: Partial<UserInfo> | RawUserInfo | null;
}

/** 后端返回的原始 user 结构（可能来自 /login.user 或 /api/auth/me 直接返回） */
export interface RawUserInfo {
  user_id?: number | string;
  id?: number | string;
  nickname?: string;
  email?: string | null;
  account?: string | null;
  username?: string | null;
  real_name?: string | null;
  mobile?: string | null;
  avatar_url?: string | null;
  avatar?: string | null;
  role?: string | { value?: string } | null;
  role_code?: string | null;
  roles?: string[];
  tenant_id?: string | null;
  tenantId?: string | null;
}

export interface AuthRegisterResponse {
  ok: boolean;
  userId?: number | string;
  user_id?: number | string;
  token?: string;
  user?: Partial<UserInfo> | RawUserInfo;
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
    (typeof r.email === "string" ? r.email : null) ||
    (typeof (raw as Partial<UserInfo>).username === "string"
      ? ((raw as Partial<UserInfo>).username as string)
      : null) ||
    null;
  const emailVal = (typeof r.email === "string" ? r.email : (raw as Partial<UserInfo>).email) || "";
  const avatarVal =
    typeof r.avatar === "string"
      ? r.avatar
      : typeof r.avatar_url === "string"
        ? r.avatar_url
        : (raw as Partial<UserInfo>).avatar ?? null;
  const rolesVal =
    Array.isArray((raw as Partial<UserInfo>).roles) && (raw as Partial<UserInfo>).roles!.length
      ? (raw as Partial<UserInfo>).roles!
      : Array.isArray(r.roles) && r.roles.length
        ? r.roles
        : roleStr
          ? [roleStr]
          : [];
  return {
    id:
      r.user_id !== undefined && r.user_id !== null
        ? r.user_id
        : r.id !== undefined && r.id !== null
          ? r.id
          : (raw as Partial<UserInfo>).id ?? "",
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
  tenantId: string | null;
  me: UserInfo | null;
  /** 判断是否已登录：完成 hydrate 且存在非空 token */
  isAuthenticated: () => boolean;
  /** 从 localStorage 恢复（客户端启动后调用 1 次） */
  hydrate: () => void;
  /** 直接写状态（后端登录成功后调用）；可选写 localStorage */
  setAuth: (payload: {
    token: string;
    tenantId?: string | null;
    me?: UserInfo | Partial<UserInfo> | null;
    persist?: boolean;
  }) => void;
  login: (input: LoginInput) => Promise<AuthLoginResponse>;
  register: (input: RegisterInput) => Promise<AuthRegisterResponse>;
  /** 后端 /api/auth/me 或 /api/users/me 刷新 me */
  refreshMe: () => Promise<UserInfo>;
  /** 登出：默认带 toast/redirect；silent=true 仅清状态不跳路由（401 时用） */
  logout: (options?: { silent?: boolean; redirectTo?: string }) => void;
}

/** 兼容后端两种常见返回：{ code, message, data: {...} } 或 直接 {...} */
function unwrap<T>(resp: AxiosResponse<T | { code?: number; message?: string; data: T }>): T {
  const body = resp.data;
  if (body && typeof body === "object" && "data" in body) {
    return (body as { data: T }).data;
  }
  return body as T;
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
  tenantId: null,
  me: null,

  isAuthenticated() {
    const s = get();
    return s.ready && !!s.token;
  },

  hydrate() {
    if (get().ready) return;
    const token = safeLS.get(K_TOKEN);
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
    set({ ready: true, token, tenantId, me });
  },

  setAuth({ token, tenantId = null, me = null, persist = true }) {
    const normalizedMe = _normalizeUser(me) ?? null;
    set({ token, tenantId, me: normalizedMe });
    if (persist) {
      safeLS.set(K_TOKEN, token);
      if (tenantId) safeLS.set(K_TENANT, tenantId);
      if (normalizedMe) safeLS.set(K_ME, JSON.stringify(normalizedMe));
    }
  },

  async login(input: LoginInput): Promise<AuthLoginResponse> {
    const identifier = (input.identifier ?? "").trim();
    if (!identifier) {
      throw new ApiError(400, { message: "请输入账号或邮箱" });
    }
    /* 统一以 account 字段提交（edu-agent 后端 schema：UserLogin.account 三选一兼容） */
    const payload = { account: identifier, password: input.password };
    const resp = await api.post<
      AuthLoginResponse | { code?: number; message?: string; data: AuthLoginResponse }
    >("/api/auth/login", payload);
    const data = unwrap<AuthLoginResponse>(resp);
    const token: string = data.access_token ?? data.accessToken ?? data.token ?? "";
    if (!token) {
      throw new ApiError(0, { message: "登录失败：未返回 token" });
    }
    (data as AuthLoginResponse).token = token;
    const fallbackAccount = identifier.includes("@") ? null : identifier;
    get().setAuth({
      token,
      tenantId: data.tenantId ?? (data.user as RawUserInfo | undefined)?.tenant_id ?? null,
      me: _normalizeUser(data.user, fallbackAccount) ?? null,
      persist: true,
    });
    if (!data.user) {
      get().refreshMe().catch(() => undefined);
    }
    return data;
  },

  async register(input: RegisterInput): Promise<AuthRegisterResponse> {
    /* edu-agent 后端 UserRegister 字段：account（登录账号）/ nickname / password / email | mobile */
    const accountVal = (input.username || "").trim() || (input.email || "").trim();
    const reqBody = {
      account: accountVal || undefined,
      username: (input.username || "").trim() || undefined,
      nickname: input.nickname,
      email: input.email,
      password: input.password,
    };
    const resp = await api.post<
      AuthRegisterResponse | { code?: number; message?: string; data: AuthRegisterResponse }
    >("/api/auth/register", reqBody);
    const data = unwrap<AuthRegisterResponse>(resp);
    data.userId = data.userId ?? data.user_id;
    data.ok = true;

    /* 后端可能仅返回 user_id；为避免注册后还需手动登录，再发一次 login 请求完成自动登录 */
    const needExtraLogin = data.autoLogin !== false && !data.token;
    if (needExtraLogin && accountVal) {
      try {
        const loginResp = await get().login({ identifier: accountVal, password: input.password });
        data.token = loginResp.access_token ?? loginResp.accessToken ?? loginResp.token;
        data.user = loginResp.user ?? undefined;
        data.autoLogin = true;
      } catch {
        data.autoLogin = false;
        /* 不阻断 register 成功反馈：用户自行前往登录页，或调用方根据 autoLogin=false 判断 */
      }
    } else if (data.autoLogin !== false && data.token) {
      get().setAuth({
        token: data.token,
        tenantId: (data.user as RawUserInfo | undefined)?.tenant_id ?? null,
        me: _normalizeUser(data.user, accountVal) ?? null,
      });
    }
    return data;
  },

  async refreshMe(): Promise<UserInfo> {
    /* 后端可能放在 /api/auth/me 或 /api/users/me；先 me 再 fallback。返回形态可能是 RawUserInfo。 */
    let resp: AxiosResponse<
      RawUserInfo | UserInfo | { code?: number; message?: string; data: RawUserInfo | UserInfo }
    >;
    try {
      resp = await api.get("/api/auth/me");
    } catch (err) {
      const status = (err as ApiError).status;
      if (status === 404) {
        resp = await api.get("/api/users/me");
      } else {
        throw err;
      }
    }
    const raw = unwrap<RawUserInfo | UserInfo>(resp);
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
    safeLS.remove(K_ME);
    safeLS.remove(K_TENANT);
    set({ token: null, me: null, tenantId: null });

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
