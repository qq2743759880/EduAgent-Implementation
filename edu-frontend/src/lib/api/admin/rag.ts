/**
 * 管理端 RAG API（task04，G4 RAG 控制台）
 *
 * 契约来源（L1：以 edu-agent 后端代码为准，design-guide §4.6 仅是摘要）：
 *  - app/admin/rag_admin/router.py + schemas.py + service.py（P7 路径 B）
 *
 * 与 design-guide 摘要的差异（后端代码实测，勿照抄摘要）：
 *  - GET /collections 返回**数组**（list[CollectionMeta]），非分页对象
 *  - 重建 POST /collections/rebuild body 是 {collection_name, partition_name, mode}，
 *    不是摘要里的 {name}；mode 取 incremental|full
 *  - 审计日志字段是 query（非 user_message），返回 {page, page_size, total, items}
 *  - search 返回 {docs[], graph_entities[], retrieved_count, final_count, rewrite_query,
 *    degraded_reason, applied_preset_name}
 *  - 全部路由 require_role([ADMIN])，student/manager 一律 403
 *
 * 错误契约（R-7）：所有写操作失败一律向上抛 ApiError，由 useMutation onError → toast。
 */
import { adminDelete, adminGet, adminPost } from "@/lib/api/admin";
import type { AdminPage } from "@/lib/admin-api-types";

/* ============================================================
 * 枚举
 * ============================================================ */
/** 集合状态（rag_collection_meta.status） */
export type RagCollectionStatus = "ready" | "rebuilding" | "error";

/** 预设模型偏好 */
export const RAG_MODEL_OPTIONS = [
  { value: "fast", label: "fast · 快速" },
  { value: "quality", label: "quality · 高质量" },
  { value: "local", label: "local · 本地" },
] as const;
export type RagModelPref = (typeof RAG_MODEL_OPTIONS)[number]["value"];

/* ============================================================
 * 类型（对齐后端 schemas）
 * ============================================================ */
/** CollectionMeta：知识库/Partition 元数据（含 Milvus 行数快照） */
export interface RagCollection {
  id: number;
  collection_name: string;
  partition_name: string;
  tenant_id?: string | null;
  display_name: string;
  row_count: number;
  source_count: number;
  last_rebuild_at?: string | null;
  last_snapshot_at: string;
  status: RagCollectionStatus;
  status_message?: string | null;
  visibility: "public" | "private";
  created_at: string;
  updated_at: string;
}

/** 重建索引请求 */
export interface RagRebuildInput {
  collection_name?: string;
  partition_name?: string;
  mode?: "incremental" | "full";
}

/** 重建索引响应（202 + job_id） */
export interface RagRebuildResult {
  job_id: string;
  accepted: boolean;
  message: string;
  estimated_rows: number;
}

/** ParamPreset：检索参数预设 */
export interface RagPreset {
  id: number;
  preset_name: string;
  is_default: boolean;
  description?: string | null;
  top_k: number;
  final_max_k: number;
  cutoff_drop_ratio: number;
  rrf_k: number;
  use_hyde: boolean;
  enable_graph: boolean;
  llm_model_pref: RagModelPref | string;
  created_by?: number | null;
  created_at: string;
  updated_at: string;
}

/** ParamPresetCreate：新建预设请求体 */
export interface RagPresetInput {
  preset_name: string;
  is_default?: boolean;
  description?: string | null;
  top_k?: number;
  final_max_k?: number;
  cutoff_drop_ratio?: number;
  rrf_k?: number;
  use_hyde?: boolean;
  enable_graph?: boolean;
  llm_model_pref?: RagModelPref | string;
}

/** AuditLogEntry：审计日志单条 */
export interface RagAuditEntry {
  id: number;
  audit_id: string;
  user_id: number;
  session_id?: string | null;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  role: string;
  query: string;
  rewrite_query?: string | null;
  retrieved_count?: number | null;
  final_count?: number | null;
  llm_model?: string | null;
  latency_ms: number;
  degraded_reason?: string | null;
  is_stream: boolean;
  error_message?: string | null;
  param_preset_id?: number | null;
  created_at: string;
}

/** 管理员高级检索请求 */
export interface RagSearchInput {
  query: string;
  tenant_ids?: string[];
  content_types?: string[];
  preset_id?: number | null;
  top_k?: number;
  final_max_k?: number;
  cutoff_drop_ratio?: number;
  use_hyde?: boolean;
  enable_graph?: boolean;
  rrf_k?: number;
  model?: RagModelPref | string;
}

/** 检索命中文档（RetrievedDoc） */
export interface RagSearchDoc {
  doc_id: string;
  score: number;
  content: string;
  source_file?: string | null;
  content_type?: string | null;
  series_code?: string | null;
  series_name?: string | null;
  module_codes?: string[];
  keywords?: string[];
  tenant_id?: string | null;
  visibility?: string | null;
  source_channel?: string;
}

/** 管理员高级检索响应 */
export interface RagSearchResult {
  docs: RagSearchDoc[];
  graph_entities: Array<Record<string, unknown>>;
  retrieved_count: number;
  final_count: number;
  rewrite_query?: string | null;
  degraded_reason?: string | null;
  applied_preset_name?: string | null;
}

/* ============================================================
 * 接口
 * ============================================================ */
/** 知识库列表（含 Milvus 行计数快照；Milvus 缺时返回 MySQL 快照 + degraded 语义，不 500） */
export async function listRagCollections(): Promise<RagCollection[]> {
  return adminGet<RagCollection[]>("/api/admin/rag/collections");
}

/** 重建索引 → 202 {job_id} */
export async function rebuildRagCollection(
  input: RagRebuildInput,
): Promise<RagRebuildResult> {
  const body: { collection_name: string; partition_name: string; mode: "incremental" | "full" } = {
    collection_name: input.collection_name ?? "knowledge_chunk_v1",
    partition_name: input.partition_name ?? "_default",
    mode: input.mode ?? "incremental",
  };
  return adminPost<RagRebuildResult>("/api/admin/rag/collections/rebuild", body);
}

/** 参数预设列表（默认项在前） */
export async function listRagPresets(): Promise<RagPreset[]> {
  return adminGet<RagPreset[]>("/api/admin/rag/presets");
}

/** 新建参数预设（is_default=true 时旧 default 事务置 0） */
export async function createRagPreset(input: RagPresetInput): Promise<RagPreset> {
  const body: Record<string, unknown> = { preset_name: input.preset_name };
  if (typeof input.is_default === "boolean") body.is_default = input.is_default;
  if (input.description) body.description = input.description;
  if (typeof input.top_k === "number") body.top_k = input.top_k;
  if (typeof input.final_max_k === "number") body.final_max_k = input.final_max_k;
  if (typeof input.cutoff_drop_ratio === "number") body.cutoff_drop_ratio = input.cutoff_drop_ratio;
  if (typeof input.rrf_k === "number") body.rrf_k = input.rrf_k;
  if (typeof input.use_hyde === "boolean") body.use_hyde = input.use_hyde;
  if (typeof input.enable_graph === "boolean") body.enable_graph = input.enable_graph;
  if (input.llm_model_pref) body.llm_model_pref = input.llm_model_pref;
  return adminPost<RagPreset>("/api/admin/rag/presets", body);
}

/** 审计日志过滤参数 */
export interface RagAuditLogParams {
  page?: number;
  page_size?: number;
  user_id?: number;
  role?: string;
  created_after?: string;
}

/** 审计日志分页（user_id/role/created_after 过滤） */
export async function listRagAuditLog(
  params: RagAuditLogParams = {},
): Promise<AdminPage<RagAuditEntry>> {
  const query: Record<string, unknown> = {
    page: params.page ?? 1,
    page_size: params.page_size ?? 20,
  };
  if (typeof params.user_id === "number") query.user_id = params.user_id;
  if (params.role?.trim()) query.role = params.role.trim();
  if (params.created_after) query.created_after = params.created_after;
  return adminGet<AdminPage<RagAuditEntry>>("/api/admin/rag/audit-log", query);
}

/** 管理员高级检索（跨租户全库 / tenant_ids / content_types / preset） */
export async function ragAdminSearch(input: RagSearchInput): Promise<RagSearchResult> {
  const body: Record<string, unknown> = { query: input.query };
  if (Array.isArray(input.tenant_ids) && input.tenant_ids.length) body.tenant_ids = input.tenant_ids;
  if (Array.isArray(input.content_types) && input.content_types.length) body.content_types = input.content_types;
  if (typeof input.preset_id === "number") body.preset_id = input.preset_id;
  if (typeof input.top_k === "number") body.top_k = input.top_k;
  if (typeof input.final_max_k === "number") body.final_max_k = input.final_max_k;
  if (typeof input.cutoff_drop_ratio === "number") body.cutoff_drop_ratio = input.cutoff_drop_ratio;
  if (typeof input.use_hyde === "boolean") body.use_hyde = input.use_hyde;
  if (typeof input.enable_graph === "boolean") body.enable_graph = input.enable_graph;
  if (typeof input.rrf_k === "number") body.rrf_k = input.rrf_k;
  if (input.model) body.model = input.model;
  return adminPost<RagSearchResult>("/api/admin/rag/search", body);
}

/* ============================================================
 * 知识文件上传 / 任务 / 分区（task40，契约来源 app/knowledge/routers/upload.py）
 * ============================================================ */
export type KnowledgeTaskStatus = "pending" | "running" | "done" | "failed";

/** POST /api/knowledge/(admin/)upload 返回 */
export interface KnowledgeUploadResult {
  task_id: string;
  status: KnowledgeTaskStatus;
  message: string;
  tenant_id: string;
  visibility: "public" | "private";
}

/** GET /api/knowledge/status/{task_id} 返回 */
export interface KnowledgeTaskDetail {
  task_id: string;
  status: KnowledgeTaskStatus;
  total_chunks: number;
  imported_chunks: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  source_files: string[];
}

/** GET /api/knowledge/partitions 返回（Milvus 原生列表，字段未定形） */
export interface KnowledgePartitionList {
  total_partitions: number;
  partitions: Array<Record<string, unknown>>;
}

/** DELETE /api/knowledge/partitions/{tenant_id} 返回 */
export interface KnowledgePartitionDeleted {
  message: string;
}

/**
 * 上传知识文件（管理端公共库入口）。
 * 后端约束：≤50 个文件，.md/.txt/.markdown/.pdf/.docx，单文件 ≤200MB。
 */
export async function uploadKnowledgeFiles(
  files: File[],
): Promise<KnowledgeUploadResult> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return adminPost<KnowledgeUploadResult>(
    "/api/knowledge/admin/upload",
    form,
  );
}

/** 上传知识文件（学员私有库入口，≤20 个文件，tenant 隔离） */
export async function uploadMyKnowledgeFiles(
  files: File[],
): Promise<KnowledgeUploadResult> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  return adminPost<KnowledgeUploadResult>("/api/knowledge/upload", form);
}

/** 查询导入任务状态（轮询用；total→imported 进度） */
export function getKnowledgeTaskStatus(
  taskId: string,
): Promise<KnowledgeTaskDetail> {
  return adminGet<KnowledgeTaskDetail>(`/api/knowledge/status/${taskId}`);
}

/**
 * 任务列表（PROPOSED — 后端仅有单查 status/{task_id}，列表端点缺失，
 * 已上浮 .opencode/handoffs/api-request.md 请求后端补齐；实现前调用会 404）
 */
export function listKnowledgeTasks(): Promise<KnowledgeTaskDetail[]> {
  return adminGet<KnowledgeTaskDetail[]>("/api/knowledge/tasks");
}

/** 分区列表（Milvus 原生；不可达时后端 503） */
export function listKnowledgePartitions(): Promise<KnowledgePartitionList> {
  return adminGet<KnowledgePartitionList>("/api/knowledge/partitions");
}

/** 删除分区（_default 公共分区后端拒绝 400，不存在 404） */
export function deleteKnowledgePartition(
  tenantId: string,
): Promise<KnowledgePartitionDeleted> {
  return adminDelete<KnowledgePartitionDeleted>(
    `/api/knowledge/partitions/${tenantId}`,
  );
}

/* ============================================================
 * 显示辅助（纯函数）
 * ============================================================ */
export function ragCollectionStatusLabel(status: RagCollectionStatus): string {
  switch (status) {
    case "ready": return "就绪";
    case "rebuilding": return "重建中";
    case "error": return "异常";
    default: return status;
  }
}

export function ragModelLabel(pref: string): string {
  return RAG_MODEL_OPTIONS.find((m) => m.value === pref)?.label ?? pref;
}
