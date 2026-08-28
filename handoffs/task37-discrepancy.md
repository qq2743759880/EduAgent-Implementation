# task37 前端遗留项 — 差异单（discrepancy，上浮编排者派单 TraeWork）

> 依据：task37 任务文档 §6「前端残留写 discrepancy 单上浮，不越界修改」。
> 执行者角色为后端+数据库开发者，下列前端（edu-frontend）项**仅记录、不修改**，交前端开发者处理。

## 1. MarkdownView 硬编码字号 text-[15px]（task59 批判①）

- **位置**：`edu-frontend/src/components/community/MarkdownView.tsx:27`
- **现状**：Tailwind className 中含字面量 `text-[15px]`（与 `prose-sm` 语义类混用）：
  ```tsx
  "prose-sm max-w-none text-[15px] leading-7 text-foreground ..."
  ```
- **建议修复**：将硬编码 `text-[15px]` 替换为 candy design token 语义类（如 `text-sm`/`text-base`），
  与 `prose-sm` 保持层级一致，消除魔法字号。
- **证据**：`grep -rn "text-\[15px\]" edu-frontend/src/` 仅在 `MarkdownView.tsx:27` 命中（设计文档
  `.claude/specs/.../design-tokens.json` 仅作 token 定义，非代码实例）。

## 2. MutationCache 401/403 早退与组件级 onError 兜底覆盖一致性（task60 批判②）

- **位置**：`edu-frontend/src/components/admin/EditUserDialog.tsx:9-10, 215`
- **现状**：注释明确记载——全局 `MutationCache` 的 `onError` 对 **401/403 早退不弹 toast**，
  由本组件 `onError` 显式补齐「后端拒绝」可见提示；其余状态码走全局 `MutationCache` 兜底避免双弹。
  全仓 `src/` 中约 17 处 admin 写操作 dialog 注释声明「失败 → 全局 MutationCache onError → toast（R-7）」。
- **风险**：全局与组件级错误透传存在「早退缺口」，401/403 场景依赖各组件自行补偿，易遗漏。
- **建议修复**：在全局 `MutationCache` onError 统一处理 401/403（toast 化或统一错误透传），
  移除各组件重复补偿逻辑；并补契约测试覆盖 401/403 在全局与组件级均正确提示。
- **证据**：`grep -rn "MutationCache" edu-frontend/src/` 命中上述引用；`EditUserDialog.tsx` 注释为直接证据。

## 3. user_memory 512→1024 维度残留（task-VEC 批判①）— 后端侧已确认

- **结论（后端确认，无需前端动作）**：`app/ai/memory/vector.py` 明确说明
  `MEMORY_VECTOR_DIM=512` 仅作**哈希降级兜底维度**，Milvus 实际用 `EMBEDDING_DIM=1024`；
  task-VEC 已落地 BGE-M3 CUDA 1024 维，`app/config.py:311` 的 512 为有意的降级兜底常量，
  非脏数据。代码中已含「若 user_memory schema 仍为旧 512 维则重建 1024」的保护逻辑。
- **剩余 512 字面量核查**：`CHUNK_SIZE=512`、`TARGET_CHUNK_SIZE=512`、reranker `RERANKER_MAX_LENGTH=512`、
  `max_length=512` 字段均为分块/截断长度，与向量维度无关，非残留。

> 前端两项（1、2）请编排者派单 TraeWork 处理；本任务不越界修改 edu-frontend。
