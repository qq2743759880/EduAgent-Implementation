FROM node:22-alpine AS dependencies
WORKDIR /app
COPY bili-study-frontend/package.json bili-study-frontend/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_BASE_URL=""
ARG API_PROXY_TARGET=http://backend:9988
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL API_PROXY_TARGET=$API_PROXY_TARGET \
    MEDIA_PROXY_TARGET=$API_PROXY_TARGET NEXT_TELEMETRY_DISABLED=1
COPY --from=dependencies /app/node_modules ./node_modules
COPY bili-study-frontend/ ./
# JSON.stringify escapes the build argument; no private values are baked in.
RUN node -e 'const fs=require("fs"); const p="public/edu-api.js"; const s=fs.readFileSync(p,"utf8"); const marker="const DEPLOY_API_BASE = \"__EDU_API_BASE__\";"; if(!s.includes(marker))throw Error("missing API deployment marker");fs.writeFileSync(p,s.replace(marker,"const DEPLOY_API_BASE = "+JSON.stringify(process.env.NEXT_PUBLIC_API_BASE_URL||"")+";"));'
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3322 HOSTNAME=0.0.0.0 API_BASE_URL=http://backend:9988
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3322
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=20 \
    CMD wget -qO- http://127.0.0.1:3322/login-register.html >/dev/null || exit 1
CMD ["node", "server.js"]
