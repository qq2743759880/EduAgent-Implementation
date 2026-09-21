import type { NextConfig } from "next";

/* F-1：/media 同源代理目标。视频等媒体文件由后端 9988 直出（W-NEXT-PORTS-001 端口迁移
   2026-09-20 起 8000→9988；旧默认 8000 为死端口，曾致 /media/* 同源代理 500——FEAT-WIRE-V2 #1 修正），
   页面 <video src="/media/..."> 是相对路径（落 3322 origin 会 404 无限 loading），
   故由 Next 把 /media/* 反代到后端，浏览器始终同源访问。
   - 本机 dev 不设该变量 → http://127.0.0.1:9988
   - Docker 生产：构建期经 build arg MEDIA_PROXY_TARGET 注入（rewrites 在 next build 时求值烘焙）*/
const MEDIA_PROXY_TARGET = process.env.MEDIA_PROXY_TARGET || "http://127.0.0.1:9988";

const nextConfig: NextConfig = {
  /* 允许 127.0.0.1 访问 dev server 静态资源（Next.js 16 默认仅信任 localhost，IP 访问返回 403）*/
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  /* Docker 部署：standalone 输出（极小镜像，仅含运行时所需文件）*/
  output: "standalone",
  /* C2 生产构建：设 NEXT_PROD_DIST_DIR 时把 build/start 产物隔离到独立目录，
     避免与在跑 dev server 的 .next/dev 互相覆盖（不设该变量则行为不变，仍用 .next）*/
  ...(process.env.NEXT_PROD_DIST_DIR ? { distDir: process.env.NEXT_PROD_DIST_DIR } : {}),
  /* F-1：/media/* → 后端媒体服务（afterFiles：public 无 /media，落到此 rewrite 反代；
     dev 热重载对 next.config.ts 不生效，改后需重启 next dev）*/
  async rewrites() {
    return [
      {
        source: "/media/:path*",
        destination: `${MEDIA_PROXY_TARGET}/media/:path*`,
      },
    ];
  },
};

export default nextConfig;
