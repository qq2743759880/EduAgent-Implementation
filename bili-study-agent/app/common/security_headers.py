"""
安全响应头中间件（Phase 1 安全加固）。

注入标准安全响应头，防御常见 Web 攻击。对标 OWASP 推荐配置。

面试考点：
- CSP（Content-Security-Policy）：防止 XSS 攻击，限制页面可以加载哪些资源
- HSTS（Strict-Transport-Security）：强制 HTTPS，防止 SSL 剥离攻击
- X-Content-Type-Options：防止 MIME 类型嗅探攻击
- X-Frame-Options：防止点击劫持（Clickjacking）
- Referrer-Policy：控制 Referer 头信息泄露
- Permissions-Policy：限制浏览器 API 使用（摄像头/麦克风/定位等）
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    为所有响应注入安全头。

    注意：CSP 策略中 script-src 允许 'unsafe-inline' 是因为 Next.js 开发模式
    需要内联脚本。生产环境应该用 nonce 或 hash 替代。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # ── 1. CSP：内容安全策略，防 XSS ──
        # 生产环境建议：
        #   - 移除 'unsafe-inline'，改用 nonce 或 hash
        #   - 限制 connect-src 为具体 API 域名
        #   - 限制 img-src 为具体 CDN 域名
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

        # ── 2. HSTS：强制 HTTPS（仅生产环境启用） ──
        # max-age=31536000 = 1年；includeSubDomains 覆盖子域名；preload 可加入浏览器预加载列表
        # 开发环境不设置（localhost 没有 HTTPS）
        if not request.url.hostname.startswith(("localhost", "127.0.0.1", "192.168.")):
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # ── 3. 防 MIME 类型嗅探 ──
        # 浏览器会根据内容猜测 MIME 类型（如把 plain text 当 HTML 执行），
        # nosniff 强制浏览器按服务器声明的 Content-Type 处理
        response.headers["X-Content-Type-Options"] = "nosniff"

        # ── 4. 防点击劫持 ──
        # DENY：完全禁止被任何页面用 iframe 嵌入
        response.headers["X-Frame-Options"] = "DENY"

        # ── 5. 启用浏览器 XSS 过滤器 ──
        # 1; mode=block：检测到 XSS 攻击时阻止页面加载（而非尝试过滤）
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # ── 6. Referrer 策略 ──
        # strict-origin-when-cross-origin：
        #   - 同源：发送完整 URL
        #   - 跨域 HTTPS→HTTPS：只发送域名
        #   - 跨域 HTTPS→HTTP：不发送
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ── 7. 权限策略：限制浏览器 API ──
        # 教育平台不需要摄像头/麦克风/定位等敏感 API
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )

        # ── 8. 跨域隔离（可选，需要 COEP/COOP/CORP 三者配合） ──
        # 暂时不启用，因为需要 CDN 配合 CORP 头
        # response.headers["Cross-Origin-Opener-Policy"] = "same-origin"

        return response