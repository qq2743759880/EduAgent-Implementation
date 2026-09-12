/**
 * B2 refine-layer · 凭证存取(auth-store)
 * - localStorage 键名与 public/edu-api.js 完全一致(fe-html 与 Refine 侧共享同一份凭证,互不踢线)
 * - Storage 可注入:scratch/单测注入内存 stub,浏览器默认 localStorage(edu-api 等价)
 * - 只读参考来源:edu-frontend/public/edu-api.js(B2 禁改该文件)
 */

export const TOKEN_KEY = "edu:auth:token";
export const REFRESH_KEY = "edu:auth:refresh";

/** 存储抽象:默认 localStorage;测试注入内存实现 */
export interface TokenStore {
  getToken(): string;
  setToken(t: string): void;
  getRefreshToken(): string;
  setRefreshToken(t: string): void;
  clear(): void;
}

function safeGet(storage: Storage | undefined, key: string): string {
  try {
    return (storage && storage.getItem(key)) || "";
  } catch {
    return "";
  }
}

function safeSet(storage: Storage | undefined, key: string, value: string): void {
  try {
    if (storage) storage.setItem(key, value);
  } catch {
    /* 隐私模式等存储不可用:与 edu-api 同为静默降级 */
  }
}

function safeRemove(storage: Storage | undefined, key: string): void {
  try {
    if (storage) storage.removeItem(key);
  } catch {
    /* 同上 */
  }
}

function defaultStorage(): Storage | undefined {
  try {
    return typeof localStorage !== "undefined" ? localStorage : undefined;
  } catch {
    return undefined;
  }
}

/** 创建绑定到指定 Storage 的 token 存取器(生产默认 localStorage,测试注入 stub) */
export function createTokenStore(storage?: Storage): TokenStore {
  const s = storage ?? defaultStorage();
  return {
    getToken() {
      return safeGet(s, TOKEN_KEY);
    },
    setToken(t) {
      safeSet(s, TOKEN_KEY, t);
    },
    getRefreshToken() {
      return safeGet(s, REFRESH_KEY);
    },
    setRefreshToken(t) {
      safeSet(s, REFRESH_KEY, t);
    },
    clear() {
      safeRemove(s, TOKEN_KEY);
      safeRemove(s, REFRESH_KEY);
    },
  };
}

/** 生产默认单例(edu-api 等价:localStorage 同键名) */
export const tokenStore: TokenStore = createTokenStore();
