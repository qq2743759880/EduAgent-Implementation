import { z } from "zod";

/** 学科偏好可选值（5 个，对齐用户拍板：英语 / 编程 / 数学 / 语文 / 物理） */
export const SUBJECT_OPTIONS = [
  "english",
  "coding",
  "math",
  "chinese",
  "physics",
] as const;

export type SubjectKey = (typeof SUBJECT_OPTIONS)[number];

export const SUBJECT_LABELS: Record<SubjectKey, string> = {
  english: "英语",
  coding: "编程",
  math: "数学",
  chinese: "语文",
  physics: "物理",
};

const SubjectKeySchema = z.enum(SUBJECT_OPTIONS, {
  error: "请选择至少一个学科",
});

/** 学科偏好数组：至少 0 个（允许清空）、最多 5 个、去重 */
const SubjectPreferencesSchema = z
  .array(SubjectKeySchema)
  .max(SUBJECT_OPTIONS.length, `最多选择 ${SUBJECT_OPTIONS.length} 个学科`)
  .superRefine((list, ctx) => {
    const seen = new Set<string>();
    for (let i = 0; i < list.length; i += 1) {
      const v = list[i];
      if (seen.has(v)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: [i],
          message: "学科不能重复",
        });
      }
      seen.add(v);
    }
  });

/** 个人中心 - 基本资料与偏好更新表单 */
export const UpdateProfileSchema = z.object({
  nickname: z
    .string({ error: "请输入昵称" })
    .min(2, "昵称最少 2 个字符")
    .max(32, "昵称最多 32 个字符")
    .regex(/^[\u4e00-\u9fa5A-Za-z0-9_\- ]+$/, "昵称仅支持中英文、数字、下划线、短横线、空格"),
  avatar: z
    .string()
    .max(500, "头像链接过长")
    .url("头像必须是合法 URL")
    .or(z.literal(""))
    .optional(),
  learningGoal: z
    .string()
    .max(500, "学习目标最多 500 字")
    .optional()
    .or(z.literal("")),
  subjectPreferences: SubjectPreferencesSchema.default([]),
});

export type UpdateProfileInput = z.infer<typeof UpdateProfileSchema>;
