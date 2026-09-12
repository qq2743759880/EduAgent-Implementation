/**
 * B2 refine-layer · Refine dataProvider 骨架(B0 §5 修订定义的最小形态)
 * 契约来源(实测/冻结,不臆造):
 *  - 响应壳:{code:0,message:"ok",data}(http.ts 统一解包)
 *  - 列表分页:请求 ?page=N&page_size=M(edu-frontend/public/admin-users.html:556 实测);
 *              响应裸 DTO {total,page,page_size,items}(AGENTS.md 分页契约)
 *  - Refine 映射:getList → { data: d.items, total: d.total }(tech-source-audit.md §2③ 同构)
 * 骨架边界(诚实声明):B2 只交付壳解包+分页映射;filters/sorters 传入即抛明确
 *   "未映射"错误(不臆造后端筛选参数名),由 B3 按各端点实测契约补齐。
 */

import type {
  BaseRecord,
  CreateParams,
  DataProvider,
  DeleteOneParams,
  GetListParams,
  GetOneParams,
  UpdateParams,
} from "@refinedev/core";
import { getBaseURL, http } from "./http.js";

function joinUrl(resource: string, suffix = ""): string {
  return "/" + String(resource || "").replace(/^\/+|\/+$/g, "") + suffix;
}

/**
 * Refine 分页参数 → 后端 ?page=&page_size= 查询串(server 模式)。
 * v5 字段名实测为 currentPage(types.d.mts:166,v4 的 current 已改名),不臆造。
 */
function paginationQuery(params: GetListParams): string {
  const q = new URLSearchParams();
  const { currentPage, pageSize, mode } = params.pagination ?? {};
  if (mode !== "client" && currentPage !== undefined) q.set("page", String(currentPage));
  if (mode !== "client" && pageSize !== undefined) q.set("page_size", String(pageSize));
  const s = q.toString();
  return s ? "?" + s : "";
}

export function eduDataProvider(): DataProvider {
  return {
    // 后端全部业务端点挂 /api 前缀(edu-api.js 各页调用实测,如 /api/admin/users),
    // Refine 约定 URL = getApiUrl() + resource → resource 用相对路径("admin/users")
    getApiUrl: () => getBaseURL() + "/api",

    getList: async <TRecord extends BaseRecord = BaseRecord>({ resource, pagination, filters, sorters }: GetListParams) => {
      if ((filters && filters.length) || (sorters && sorters.length)) {
        throw new Error(
          "[eduDataProvider] filters/sorters 未映射:B2 骨架只承诺分页映射,B3 按端点实测契约补齐(resource=" + String(resource) + ")"
        );
      }
      const raw = await http.get<{ total?: number; items?: TRecord[] } | TRecord[]>(
        joinUrl(resource) + paginationQuery({ resource, pagination, filters, sorters })
      );
      // 分页裸 DTO → Refine 形状;纯数组(无分页壳的端点)按整包返回
      if (Array.isArray(raw)) return { data: raw, total: raw.length };
      return { data: raw?.items ?? [], total: raw?.total ?? 0 };
    },

    getOne: async <TRecord extends BaseRecord = BaseRecord>(params: GetOneParams) => {
      const data = await http.get<TRecord>(joinUrl(params.resource, "/" + encodeURIComponent(String(params.id))));
      return { data };
    },

    create: async <TRecord extends BaseRecord = BaseRecord, TVariables = {}>(params: CreateParams<TVariables>) => {
      const data = await http.post<TRecord>(joinUrl(params.resource), params.variables);
      return { data };
    },

    update: async <TRecord extends BaseRecord = BaseRecord, TVariables = {}>(params: UpdateParams<TVariables>) => {
      const data = await http.patch<TRecord>(joinUrl(params.resource, "/" + encodeURIComponent(String(params.id))), params.variables);
      return { data };
    },

    deleteOne: async <TRecord extends BaseRecord = BaseRecord, TVariables = {}>(params: DeleteOneParams<TVariables>) => {
      const data = await http.del<TRecord>(joinUrl(params.resource, "/" + encodeURIComponent(String(params.id))));
      return { data };
    },

    // ---- B2 骨架不承诺的能力:返回明确 not-implemented 错误,由 B3 按端点实测契约补齐 ----
    getMany: async () => {
      throw new Error("[eduDataProvider] getMany 未实现:B3 按实测契约补齐(B2 骨架边界)");
    },
    createMany: async () => {
      throw new Error("[eduDataProvider] createMany 未实现:B3 按实测契约补齐(B2 骨架边界)");
    },
    updateMany: async () => {
      throw new Error("[eduDataProvider] updateMany 未实现:B3 按实测契约补齐(B2 骨架边界)");
    },
    deleteMany: async () => {
      throw new Error("[eduDataProvider] deleteMany 未实现:B3 按实测契约补齐(B2 骨架边界)");
    },
  };
}
