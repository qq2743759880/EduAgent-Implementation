import { z } from "zod";

/**
 * AI 问答助手输入校验：
 *   - NewMessage: 非空 trim，长度 [1, 4000]（约一段短文 + 附件）
 *   - CreateSession: 标题可省略，省略时由后端根据第一条问题生成；不省略则 ≤ 64
 */

const MAX_MESSAGE_LEN = 4000;
const MAX_TITLE_LEN = 64;

export const NewMessageSchema = z
  .string({ error: "请输入内容" })
  .trim()
  .min(1, "内容不能为空")
  .max(MAX_MESSAGE_LEN, `内容最多 ${MAX_MESSAGE_LEN} 字符`);

export const CreateSessionSchema = z.object({
  title: z
    .string()
    .trim()
    .max(MAX_TITLE_LEN, `标题最多 ${MAX_TITLE_LEN} 字符`)
    .optional()
    .or(z.literal("")),
  subject_code: z.string().trim().max(16).optional().nullable(),
  level_code: z.string().trim().max(16).optional().nullable(),
});

export type NewMessageInput = z.infer<typeof NewMessageSchema>;
export type CreateSessionInput = z.infer<typeof CreateSessionSchema>;
