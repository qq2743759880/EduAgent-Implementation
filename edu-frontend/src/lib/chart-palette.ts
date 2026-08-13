/**
 * ECharts 受控色板（fe-task07 新增）。
 * hex 与 .claude/specs/frontend/tokens/design-tokens.json chartPalette.entries 双写一致。
 * ECharts canvas 渲染不解析 CSS var()，故导出静态 hex（不导出 var(--x) 字符串）。
 * 色相源 ⊆ 语义色板 + chart neutral 系；sky(#0ea5e9)/blue(#3b82f6)/violet/fuchsia 越界色不得保留。
 */
export const CHART_COLORS = {
  primary: "#4f46e5", // indigo-600（tokens colors.primary）—— 主数据系列/折线/雷达主维
  primaryStrong: "#4338ca", // indigo-700（tokens colors.primary-strong）
  muted: "#94a3b8", // slate-400 —— 轴标签/次要文字
  mutedForeground: "#64748b", // slate-500（tokens colors.muted-foreground）—— 图例文字/次级线
  border: "#e2e8f0", // slate-200（tokens colors.border）—— 轴线/网格分割
  grid: "#f1f5f9", // slate-100 —— splitLine 虚线
  splitAreaBg: "#f8fafc", // slate-50 —— 雷达 splitArea 网格底色（浅底条）
  white: "#ffffff", // white —— 数据点描边/高亮对色
  axisName: "#475569", // slate-600 —— 轴名称
  success: "#059669", // emerald-600（tokens colors.success）—— 已完成/掌握/mastered
  warning: "#f59e0b", // amber-500（tokens colors.warning）—— PREREQUISITE 边/学习中（可选）
  destructive: "#e11d48", // rose-600（tokens colors.destructive）—— 错误/失败节点
  chartNeutral: [
    "#d4d4d4", // chart-1（neutral-300）
    "#737373", // chart-2（neutral-500）
    "#525252", // chart-3（neutral-600）
    "#404040", // chart-4（neutral-700）
    "#262626", // chart-5（neutral-800）
  ],
} as const;

/**
 * 线性渐变辅助（ECharts areaStyle 常用）：primary 透明度渐隐。
 * rgba(79, 70, 229, ...) 与 CHART_COLORS.primary (#4f46e5) 同源。
 */
export function primaryGradient(
  fromOpacity = 0.32,
  toOpacity = 0.02,
): { type: "linear"; x: number; y: number; x2: number; y2: number; colorStops: Array<{ offset: number; color: string }> } {
  return {
    type: "linear",
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: `rgba(79, 70, 229, ${fromOpacity})` },
      { offset: 1, color: `rgba(79, 70, 229, ${toOpacity})` },
    ],
  };
}
