import { defineConfig, devices } from "@playwright/test";

const PORT = Number(process.env.PORT || 3000);
const BASE_URL = `http://127.0.0.1:${PORT}`;

/**
 * task69 E2E —— Playwright 配置
 *  - 服务已由编排者/本任务手动启动（前端 3000、后端 8000 已在线），baseURL 直连，不再内嵌 webServer。
 *  - 断点截图矩阵（tech-source-audit §六）：375 / 768 / 1024 / 1280 / 1440
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1, // 共享登录态/数据，避免并发污染
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 15_000 },
  reporter: [
    ["list"],
    ["html", { outputFolder: "test-reports/e2e-html-report", open: "never" }],
    ["json", { outputFile: "test-reports/e2e-results.json" }],
  ],
  outputDir: "test-reports/e2e-artifacts",
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    // 全链路/批判/状态机主项目 —— 多个视口跑关键用例
    { name: "chromium-1280", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } },
    { name: "chromium-375", use: { ...devices["Pixel 7"], viewport: { width: 375, height: 667 } } },
  ],
});