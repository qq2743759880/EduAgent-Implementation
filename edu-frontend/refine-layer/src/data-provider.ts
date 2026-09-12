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
  LogicalFilter,
  UpdateParams,
} from "@refinedev/core";
import { getBaseURL, http } from "./http";

function joinUrl(resource: string, suffix = ""): string {
  return "/" + String(resource || "").replace(/^\/+|\/+$/g, "") + suffix;
}

/**
 * B3-impl 集成期修正(B2 缺陷):B2 的 getList 只拼了 joinUrl(resource),漏掉 /api 前缀
 * ——注释里写明 "URL = getApiUrl() + resource",但 getApiUrl() 从未参与 URL 构造,
 * 实发 URL = base + "/admin/users"(2026-09-12 B3 组件测试桩 fetch 实证 unhandled fetch)。
 * 后端契约(contracts/reshape-a.json + edu-api.js 实测)全部业务端点挂 /api 前缀,故统一补 /api。
 */
function apiPath(resource: string, suffix = ""): string {
  return "/api" + joinUrl(resource, suffix);
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
  appendFilters(params, q);
  const s = q.toString();
  return s ? "?" + s : "";
}

/**
 * B3-impl 按 B2 报告 §5-3 交接项补齐:filters → 查询参数(白名单制,不臆造)。
 * admin/users 过滤参数 2026-09-12 curl 实测:keyword/role_code/status/yn 均为服务端过滤
 * (keyword=LIKE 组合,role_code/status/yn=等值);非白名单资源/字段/操作符仍抛"未映射"。
 */
const FILTER_FIELDS: Record<string, readonly string[]> = {
  "admin/users": ["keyword", "role_code", "status", "yn"],
};

function appendFilters(params: GetListParams, q: URLSearchParams): void {
  const filters = params.filters;
  if (!filters || !filters.length) return;
  const allowed = FILTER_FIELDS[String(params.resource || "")];
  if (!allowed) {
    throw new Error("[eduDataProvider] filters 未映射:B2/B3 仅映射白名单端点(resource=" + String(params.resource) + ")");
  }
  for (const f of filters) {
    const lf = f as LogicalFilter;
    if (!lf.field || Array.isArray(lf.value)) {
      throw new Error("[eduDataProvider] 仅支持单字段 eq/contains filter(resource=" + String(params.resource) + ")");
    }
    if (lf.operator !== "eq" && lf.operator !== "contains") {
      throw new Error("[eduDataProvider] filter 操作符未映射:" + lf.field + "/" + lf.operator);
    }
    if (!allowed.includes(lf.field)) {
      throw new Error("[eduDataProvider] filter 字段未映射:" + String(params.resource) + " " + lf.field + "(实测白名单=" + allowed.join(",") + ")");
    }
    if (lf.value !== undefined && lf.value !== null && String(lf.value) !== "") q.set(lf.field, String(lf.value));
  }
}

export function eduDataProvider(): DataProvider {
  return {
    // 后端全部业务端点挂 /api 前缀(edu-api.js 各页调用实测,如 /api/admin/users),
    // Refine 约定 URL = getApiUrl() + resource → resource 用相对路径("admin/users")
    getApiUrl: () => getBaseURL() + "/api",

    getList: async <TRecord extends BaseRecord = BaseRecord>({ resource, pagination, filters, sorters }: GetListParams) => {
      // filters 经 appendFilters 白名单映射(B3 按 admin/users 端点实测补齐);sorters 仍未映射
      if (sorters && sorters.length) {
        throw new Error(
          "[eduDataProvider] sorters 未映射:B2/B3 未承诺排序映射,按端点实测契约再补(resource=" + String(resource) + ")"
        );
      }
      const raw = await http.get<{ total?: number; items?: TRecord[] } | TRecord[]>(
        apiPath(resource) + paginationQuery({ resource, pagination, filters, sorters })
      );
      // 分页裸 DTO → Refine 形状;纯数组(无分页壳的端点)按整包返回
      if (Array.isArray(raw)) return { data: raw, total: raw.length };
      return { data: raw?.items ?? [], total: raw?.total ?? 0 };
    },

    getOne: async <TRecord extends BaseRecord = BaseRecord>(params: GetOneParams) => {
      const data = await http.get<TRecord>(apiPath(params.resource, "/" + encodeURIComponent(String(params.id))));
      return { data };
    },

    create: async <TRecord extends BaseRecord = BaseRecord, TVariables = {}>(params: CreateParams<TVariables>) => {
      const data = await http.post<TRecord>(apiPath(params.resource), params.variables);
      return { data };
    },

    update: async <TRecord extends BaseRecord = BaseRecord, TVariables = {}>(params: UpdateParams<TVariables>) => {
      const data = await http.patch<TRecord>(apiPath(params.resource, "/" + encodeURIComponent(String(params.id))), params.variables);
      return { data };
    },

    deleteOne: async <TRecord extends BaseRecord = BaseRecord, TVariables = {}>(params: DeleteOneParams<TVariables>) => {
      const data = await http.del<TRecord>(apiPath(params.resource, "/" + encodeURIComponent(String(params.id))));
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
