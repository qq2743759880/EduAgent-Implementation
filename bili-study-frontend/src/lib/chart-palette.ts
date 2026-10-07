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
  // §1.7 图表 8 色定性序（task55 补充，charts/管理端仪表盘多系列专用；sky/violet 仅图表允许）
  chart1: "#4f46e5", // indigo-600 —— 主系列
  chart2: "#10b981", // emerald-500 —— 第二系列
  chart3: "#f59e0b", // amber-500 —— 第三系列
  chart4: "#f43f5e", // rose-500 —— 状态趋势
  chart5: "#0ea5e9", // sky-500（图表仅允许）
  chart6: "#8b5cf6", // violet-500（图表仅允许）
  chart7: "#64748b", // slate-500
  chart8: "#a5b4fc", // indigo-300
} as const;

/**
 * §1.7 多系列 ChartSet：饼图/多系列按序取色。
 * 饼图禁用相邻同系：改按 1/3/5/7/2/4/6/8 疏取，避免同系相邻。
 */
export const CHART_SERIES_8: readonly string[] = [
  CHART_COLORS.chart1, // indigo-600
  CHART_COLORS.chart3, // amber-500
  CHART_COLORS.chart5, // sky-500
  CHART_COLORS.chart7, // slate-500
  CHART_COLORS.chart2, // emerald-500
  CHART_COLORS.chart4, // rose-500
  CHART_COLORS.chart6, // violet-500
  CHART_COLORS.chart8, // indigo-300
];

/**
 * 角色分布饼图疏色序（§1.7 饼图禁用相邻同系）：admin 主色、student/teacher/manager 疏取不与其相邻。
 * 固定 role_code → 色的映射，供 RoleDonutChart 与 KPI 角色分布卡取色（echarts canvas 需静态 hex）。
 */
export const ROLE_CHART_COLORS: Readonly<Record<string, string>> = {
  admin: CHART_COLORS.chart1, // indigo-600
  manager: CHART_COLORS.chart4, // rose-500
  teacher: CHART_COLORS.chart5, // sky-500（图表仅允许）
  student: CHART_COLORS.chart6, // violet-500（图表仅允许）
};

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
