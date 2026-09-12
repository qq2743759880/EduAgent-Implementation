import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    // MDEditor 等组件引入的 css/less 由 Next 编译，vitest 直接跳过
    css: false,
    clearMocks: true,
    // 慢机全量并行时 jsdom 组件测试偶发超 5s 默认超时（资源竞争，非代码问题），放宽全局上限
    testTimeout: 20_000,
  },
  resolve: {
    alias: [
      { find: "@", replacement: path.resolve(__dirname, "./src") },
      // B3-impl:refine-layer 以 TS 源码入宿主(node_modules 为 B2 独立验证环境,react/rq 版本与宿主不同)
      { find: "@edu/refine-layer", replacement: path.resolve(__dirname, "./refine-layer/src/index.tsx") },
      // 单一副本强制(B2 scratch 同款技法):refine 全家+react 全家+rq 统一钉到宿主 node_modules,
      // 否则 refine-layer/node_modules 内嵌套解析出 react@19.3.0/rq@5.102.8 双副本,
      // 双 react 会让 Refine Context/hooks 跨副本失联(Invalid hook call)
      { find: "@refinedev/core", replacement: path.resolve(__dirname, "./node_modules/@refinedev/core") },
      { find: "@tanstack/react-query", replacement: path.resolve(__dirname, "./node_modules/@tanstack/react-query/build/modern/index.js") },
      { find: "react-dom", replacement: path.resolve(__dirname, "./node_modules/react-dom") },
      { find: "react", replacement: path.resolve(__dirname, "./node_modules/react") },
    ],
  },
});
