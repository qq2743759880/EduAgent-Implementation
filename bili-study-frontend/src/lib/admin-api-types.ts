/**
 * 管理端通用类型（task02 骨架）
 * 后续 task03/04 的 lib/api/admin/{courses,questions,users,rag,mcp}.ts 统一复用。
 */

/** 后端统一错误壳（契约① v1.1：{code:<字符串>, message, data:null}；兼容旧数字码） */
export interface AdminApiErrorBody {
  code?: number | string;
  message?: string;
  detail?: unknown;
}

/** 管理端 RBAC 四级角色 */
export type AdminUserRole = "admin" | "manager" | "teacher" | "student";

/** 管理端分页响应（后端列表契约：total/page/page_size/items） */
export interface AdminPage<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

/** 管理端列表通用查询参数（后端列表强制分页，默认 20 / max 100） */
export interface AdminPageParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  status?: string;
  /** 软删过滤：1 正常 / 0 已删 */
  yn?: number | boolean;
  [key: string]: unknown;
}

/** 通用写操作响应（如会话软删 {ok:true}） */
export interface AdminOkResponse {
  ok: boolean;
}
