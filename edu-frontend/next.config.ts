import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* 允许 127.0.0.1 访问 dev server 静态资源（Next.js 16 默认仅信任 localhost，IP 访问返回 403）*/
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  /* Docker 部署：standalone 输出（极小镜像，仅含运行时所需文件）*/
  output: "standalone",
  /* C2 生产构建：设 NEXT_PROD_DIST_DIR 时把 build/start 产物隔离到独立目录，
     避免与在跑 dev server 的 .next/dev 互相覆盖（不设该变量则行为不变，仍用 .next）*/
  ...(process.env.NEXT_PROD_DIST_DIR ? { distDir: process.env.NEXT_PROD_DIST_DIR } : {}),
};

export default nextConfig;
