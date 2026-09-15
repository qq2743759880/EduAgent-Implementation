# ============================================================
# EduAgent 前端镜像 —— 生产部署（Next.js standalone）
#   1) deps    : 装依赖
#   2) builder : next build（产出 .next/standalone）
#   3) runtime : 仅拷贝 standalone 运行时 + static/public
# ============================================================
FROM node:20-alpine AS deps
WORKDIR /app
COPY edu-frontend/package.json edu-frontend/package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
# 浏览器访问后端的地址（build 时内联，Next 的 NEXT_PUBLIC_* 语义）
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
# F-1：服务端 /media 同源代理目标（rewrites 在 next build 时求值烘焙；
# 容器内走 compose 网络 → http://backend:8000，区别于浏览器侧 NEXT_PUBLIC_API_BASE_URL）
ARG MEDIA_PROXY_TARGET=http://backend:8000
ENV MEDIA_PROXY_TARGET=$MEDIA_PROXY_TARGET
COPY --from=deps /app/node_modules ./node_modules
COPY edu-frontend/ ./
# 生产环境不构建 dev 用测试
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# standalone 输出（Next 16 产物结构）
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -qO- http://127.0.0.1:3000/ >/dev/null 2>&1 || exit 1

CMD ["node", "server.js"]
