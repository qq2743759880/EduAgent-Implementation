import { z } from "zod";

/** 账号（用户名 / 登录 ID）规则：3-20 位小写字母 / 数字 / 下划线 / 短横线，字母开头 */
const USERNAME_REGEX = /^[A-Za-z][A-Za-z0-9_\-]{2,19}$/;

const LoginIdentifier = z
  .string({ error: "请输入账号或邮箱" })
  .min(3, "最少 3 个字符")
  .max(120, "最多 120 个字符")
  .superRefine((val, ctx) => {
    const v = val.trim();
    if (!v) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: "请输入账号或邮箱" });
      return;
    }
    const looksLikeEmail = v.includes("@");
    if (looksLikeEmail) {
      const shape = z.string().email("邮箱格式不正确");
      const res = shape.safeParse(v);
      if (!res.success) {
        for (const issue of res.error.issues) ctx.addIssue(issue as never);
      }
      return;
    }
    if (!USERNAME_REGEX.test(v)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "账号需 3-20 位，以字母开头，仅支持字母、数字、下划线、短横线",
      });
    }
  });

export const LoginSchema = z.object({
  identifier: LoginIdentifier,
  password: z
    .string({ error: "请输入密码" })
    .min(6, "密码最少 6 位")
    .max(64, "密码最多 64 位"),
});

export type LoginInput = z.infer<typeof LoginSchema>;

export const RegisterSchema = z
  .object({
    username: z
      .string({ error: "请设置登录账号" })
      .min(3, "账号最少 3 个字符")
      .max(20, "账号最多 20 个字符")
      .regex(USERNAME_REGEX, "账号需 3-20 位，以字母开头，仅支持字母、数字、下划线、短横线"),
    nickname: z
      .string({ error: "请输入昵称" })
      .min(2, "昵称最少 2 个字符")
      .max(32, "昵称最多 32 个字符")
      .regex(/^[\u4e00-\u9fa5A-Za-z0-9_\- ]+$/, "昵称仅支持中英文、数字、下划线、短横线、空格"),
    email: z
      .string({ error: "请输入邮箱" })
      .min(5, "邮箱最少 5 个字符")
      .max(120, "邮箱最多 120 个字符")
      .email("邮箱格式不正确"),
    password: z
      .string({ error: "请输入密码" })
      .min(6, "密码最少 6 位")
      .max(64, "密码最多 64 位")
      .regex(/^[^\u4e00-\u9fa5]+$/, "密码不能包含中文字符"),
    confirmPassword: z
      .string({ error: "请再次输入密码" })
      .min(6, "确认密码最少 6 位")
      .max(64, "确认密码最多 64 位"),
  })
  .superRefine((data, ctx) => {
    if (data.confirmPassword !== data.password) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["confirmPassword"],
        message: "两次输入的密码不一致",
      });
    }
  });

export type RegisterInput = z.infer<typeof RegisterSchema>;
