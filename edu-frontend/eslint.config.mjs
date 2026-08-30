import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // P3-A：React Compiler 的「effect 里同步 setState」是优化建议而非错误——
      // 项目多处用该模式做「外部数据→本地状态同步」（hydration 后同步 localStorage、
      // 切换题目重置状态等，React 官方认可）。降级为 warning，保留可观测性不阻断 CI。
      "react-hooks/set-state-in-effect": "warn",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
