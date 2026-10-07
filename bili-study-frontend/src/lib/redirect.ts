/**
 * 安全回跳（open redirect 防护）工具
 *
 * 问题（对抗 #4，2026-08-12）：LoginForm / GuestOnlyRoute / 根路由曾共用正则
 * `^\/[A-Za-z0-9?=&/%\-_@+.~#]*$` 校验 ?redirect=，该正则允许 `//evil.com`
 * （`/` 与 `.` 都在字符集内，且 `^\/` 后可直接再 `/`），router.replace 会把
 * 协议相对 URL 解析为外域跳转（钓鱼攻击面）。
 *
 * 修复：拒绝以 `//` 或 `/\` 开头（协议相对路径）的值，仅放行站内绝对路径
 * （形如 /admin/dashboard、/dashboard?tab=1#sec）。
 *
 * 使用方：components/auth/LoginForm.tsx / lib/protected-route.tsx（GuestOnlyRoute）/
 * app/page.tsx —— 一律 import 本函数，禁止复制正则。
 */

/** 合法站内绝对路径：以单个 / 开头，且紧跟的第一个字符不得是 / 或 \（防协议相对跳转） */
const SAFE_REDIRECT_RE = /^\/(?![/\\])[A-Za-z0-9?=&/%\-_@+.~#]*$/;

/** 校验 ?redirect= 值是否为安全的站内路径（非协议相对、非外域、非伪协议） */
export function isSafeRedirect(value: string | null | undefined): boolean {
  if (!value) return false;
  return SAFE_REDIRECT_RE.test(value);
}
