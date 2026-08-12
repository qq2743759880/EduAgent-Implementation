import { z } from "zod";

/** 搜索页 / 课程商城列表的查询参数校验（URL query -> Zod -> 请求体） */
export const CourseSearchSchema = z.object({
  q: z.string().max(64, "关键词最多 64 个字符").optional(),
  subject: z
    .enum(["all", "english", "programming", "math", "chinese", "physics"], {
      message: "学科值无效",
    })
    .optional()
    .default("all"),
  level: z
    .enum(["all", "L1", "L2", "L3", "L4", "L5"], { message: "级别值无效" })
    .optional()
    .default("all"),
  min_price: z.coerce
    .number({ error: "最低价格必须是数字" })
    .gte(0, "最低价格不能小于 0")
    .lte(999999, "最低价格超出范围")
    .optional(),
  max_price: z.coerce
    .number({ error: "最高价格必须是数字" })
    .gte(0, "最高价格不能小于 0")
    .lte(999999, "最高价格超出范围")
    .optional(),
  page: z.coerce
    .number({ error: "页码必须是数字" })
    .int("页码必须是整数")
    .gte(1, "页码从 1 开始")
    .lte(1000, "页码过大")
    .optional()
    .default(1),
  page_size: z.coerce
    .number({ error: "页大小必须是数字" })
    .int("页大小必须是整数")
    .gte(1, "最少 1 条/页")
    .lte(60, "最多 60 条/页")
    .optional()
    .default(12),
}).superRefine((v, ctx) => {
  if (
    typeof v.min_price === "number" &&
    typeof v.max_price === "number" &&
    v.min_price > v.max_price
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ["min_price"],
      message: "最低价不能大于最高价",
    });
  }
});

export type CourseSearchInput = z.infer<typeof CourseSearchSchema>;
