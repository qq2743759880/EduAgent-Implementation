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
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
