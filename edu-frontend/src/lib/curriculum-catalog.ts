/**
 * 课程中心「两级导航」目录数据（task44，对齐用户方案 + HTML 效果图 courses.html v4）。
 *
 * 一级：学科大类（9 类）→ 二级：课程方向。
 * 后端 GET /api/series 的 category Query 为分类名模糊匹配：
 *   - 仅选一级 → category=大类名（如「编程」）
 *   - 选二级 → category=方向名（如「通用程序设计」，覆盖一级）
 * 封面糖果渐变 / emoji 均由真实 category_names 派生（非 MOCK 数据）。
 */
import type { SeriesListItem } from "@/lib/api/curriculum";

export interface CatalogCategory {
  /** 一级学科大类名（后端 category 模糊匹配关键词） */
  name: string;
  /** 一级 emoji（封面/空态图标） */
  emoji: string;
  /** 二级课程方向列表 */
  directions: string[];
}

export const COURSE_CATALOG: CatalogCategory[] = [
  {
    name: "编程",
    emoji: "💻",
    directions: [
      "通用程序设计",
      "系统级编程",
      "脚本与自动化编程",
      "Web编程语言",
      "底层与低级语言",
      "前端开发",
      "后端开发",
      "全栈开发",
    ],
  },
  {
    name: "计算机系统",
    emoji: "🖥️",
    directions: [
      "网络与通信系统",
      "操作系统与运行时",
      "数据存储系统",
      "编译与语言系统",
      "分布式与云系统",
    ],
  },
  {
    name: "数据与AI",
    emoji: "📊",
    directions: [
      "数据分析与可视化",
      "数据工程",
      "机器学习方法",
      "深度学习与感知智能",
      "基础模型与智能体",
    ],
  },
  {
    name: "图形与游戏",
    emoji: "🎮",
    directions: ["图形与渲染管线", "实时渲染", "仿真与物理系统", "交互媒体与游戏"],
  },
  {
    name: "数学",
    emoji: "📐",
    directions: [
      "分析学基础",
      "代数学基础",
      "几何学基础",
      "微积分与数列极限",
      "数学证明与逻辑",
      "概率与统计方法",
      "运筹优化",
      "数值与计算方法",
      "建模与仿真",
      "数据与定量分析",
      "现代分析理论",
      "现代代数理论",
      "几何与拓扑",
      "离散与组合数学",
      "交叉数学方向",
    ],
  },
  {
    name: "考研/考证/公考",
    emoji: "🎯",
    directions: [
      "考研数学",
      "考研英语",
      "考研政治",
      "考研专业课",
      "复试与调剂",
      "公务员考试",
      "事业单位考试",
      "教师招聘考试",
      "警务辅警招录",
      "面试与申论专项",
      "教师资格证",
      "会计与财税证书",
      "建工类证书",
      "法律与合规证书",
      "IT与数字化证书",
    ],
  },
  {
    name: "管理与职场",
    emoji: "📈",
    directions: ["基层管理", "项目管理", "跨部门协同", "领导力进阶", "人才培养", "组织变革"],
  },
  {
    name: "企业培训",
    emoji: "🏢",
    directions: ["新员工培训", "销售培训", "客服培训", "数据合规", "安全生产", "服务规范"],
  },
  {
    name: "校园成长",
    emoji: "🌱",
    directions: [
      "就业竞争力",
      "实习与求职准备",
      "升学与学业规划",
      "高中关键学科衔接",
      "中学数学提升",
      "中学英语提升",
      "中学物理提升",
      "中学化学提升",
      "信息学与编程启蒙",
    ],
  },
];

/** 一级学科 emoji 查找（未知返回 📚） */
export function categoryEmoji(name: string): string {
  return COURSE_CATALOG.find((c) => c.name === name)?.emoji ?? "📚";
}

/** 二级方向 emoji（HTML 效果图 SUB_EMOJI 映射；未知返回 📚） */
const DIRECTION_EMOJI: Record<string, string> = {
  通用程序设计: "💻",
  系统级编程: "⚙️",
  脚本与自动化编程: "🤖",
  Web编程语言: "🌐",
  底层与低级语言: "🔧",
  前端开发: "🎨",
  后端开发: "🗄️",
  全栈开发: "🧩",
};

export function directionEmoji(name: string): string {
  return DIRECTION_EMOJI[name] ?? "📚";
}

/** 交付模式中文化标签（HTML 效果图 DM 映射） */
export const DELIVERY_LABELS: Record<SeriesListItem["delivery_mode"], string> = {
  online_live: "在线直播",
  online_recorded: "在线录播",
  offline_face_to_face: "线下面授",
};

/** 排序选项（对齐后端 sort 白名单） */
export const SORT_OPTIONS = [
  { value: "default", label: "综合" },
  { value: "newest", label: "最新" },
  { value: "price_asc", label: "价格↑" },
  { value: "price_desc", label: "价格↓" },
] as const;

export type SortValue = (typeof SORT_OPTIONS)[number]["value"];

/** 价格区间选项（value 为 min-max 字符串；"any"=不限，兼容 task41 Select 空值处理） */
export const PRICE_RANGES = [
  { value: "any", label: "不限" },
  { value: "0-2000", label: "¥2000 以下" },
  { value: "2000-3000", label: "¥2000 – ¥3000" },
  { value: "3000-", label: "¥3000 以上" },
] as const;

export function parsePriceRange(value: string): { min?: number; max?: number } {
  if (!value || value === "any") return {};
  const [lo, hi] = value.split("-");
  return {
    min: lo ? Number(lo) : undefined,
    max: hi ? Number(hi) : undefined,
  };
}

/** 一级学科 → 封面糖果渐变（Tailwind 渐变类；浅端用同色 /30 透明度模拟糖果浅色） */
const CATEGORY_COVER: Record<string, string> = {
  编程: "from-candy-orange to-candy-orange/30",
  计算机系统: "from-candy-blue to-candy-blue/30",
  数据与AI: "from-candy-purple to-candy-purple/30",
  图形与游戏: "from-candy-pink to-candy-pink/30",
  数学: "from-candy-green to-candy-green/30",
  "考研/考证/公考": "from-candy-yellow to-candy-yellow/30",
  管理与职场: "from-candy-orange to-candy-orange/30",
  企业培训: "from-candy-blue to-candy-blue/30",
  校园成长: "from-candy-purple to-candy-purple/30",
};

const FALLBACK_COVER = "from-candy-green to-candy-green/30";

/** 系列 → 封面渐变类（取 category_names 首个命中；未知回退糖果绿） */
export function coverGradient(series: Pick<SeriesListItem, "category_names">): string {
  const name = series.category_names?.[0];
  return (name && CATEGORY_COVER[name]) || FALLBACK_COVER;
}

/** 系列 → 封面 emoji（优先二级方向 emoji，回退一级，再回退 📚） */
export function coverEmoji(series: Pick<SeriesListItem, "category_names">): string {
  const cats = series.category_names ?? [];
  if (cats[1]) return directionEmoji(cats[1]);
  if (cats[0]) return categoryEmoji(cats[0]);
  return "📚";
}

/** 系列 → 分类徽章文案（二级方向优先，回退一级，再回退「课程」） */
export function categoryLabel(series: Pick<SeriesListItem, "category_names">): string {
  const cats = series.category_names ?? [];
  return cats[1] ?? cats[0] ?? "课程";
}
