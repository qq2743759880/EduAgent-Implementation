import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* 允许 127.0.0.1 访问 dev server 静态资源（Next.js 16 默认仅信任 localhost，IP 访问返回 403）*/
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  /* Docker 部署：standalone 输出（极小镜像，仅含运行时所需文件）*/
  output: "standalone",
};

export default nextConfig;
