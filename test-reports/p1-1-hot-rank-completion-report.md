# P1-1 完工报告：`GET /api/series` 热门榜排序端点（task16 gap）

- 执行 agent：EduAgent P1-1（课程域后端排序补全）
- 版本：P1-1 v1
- 状态：待验收（未 commit，禁 Playwright，全部真实 HTTP 实证）
- 日期：2026-09-04

---

## 0. 资产消费证据

| 资产（anchor 路径） | 消费方式 | 实际产出（自检应用） |
|---|---|---|
| `C:\Users\Administrator\.agents\skills\ponytail` | 全文精读 | 用户侧热榜无需独立新端点，复用既有 `list_series` 的 `sort` 白名单机制 + `_SORT_MAP` 分发扩展 1 键即覆盖，不新造域、不新增聚合端点（避免 YAGNI）。销量排序表达式复用既有「派生表别名参与 ORDER BY」结构，非新写框架 |
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 | 精读 §5.2「回传机制 + 完工前自检」 | 完工前按 critique 三视角自检（见 §3）；报告含「资产消费证据」段；验收必须独立实证（本报告全部为真实 HTTP + MySQL 实测，不采信臆测） |
| `C:\Users\Administrator\.agents\skills\harden\SKILL.md` | 精读「输入校验 & 白名单 / 边界」 | `_SORT_MAP.get(sort, default)` 白名单映射，排序表达式禁止直接拼接用户输入；殃及 hot 聚合值域 `IN ('paid','completed')` 为常量表达式，不进入任何参数化路径；`sort` 非法值仍由 router Query `pattern` 拦截返回 422 |

> harden 补充（边缘输入）：新增排序分支对 `sort` 缺失（默认 `default`）/非法值/与既有筛选（category/delivery_mode/keyword/price 区间）共存均验证通过（§2.3 组合实证）；销量为 0 的系列天然落末（COUNT 一致 0，`id DESC` 拍平平局），无 NULL 排序陷阱。

### agent × skill × workflow 矩阵

| 维度 | 取值 |
|---|---|
| agent | EduAgent P1-1 执行 agent（课程域后端） |
| skill | ponytail（最小 diff）、harden（白名单/注入防护）、tt §5.2（完工报告/独立实证纪律） |
| workflow | 最简补充：既有 `sort` 白名单 + `_SORT_MAP` 分发 → 真实 HTTP 实证（不启用多平台编排，N=1） |
| MCP | 无需（本地 MySQL CLI 直查热度数据源，接口用 curl 实证） |

---

## 1. 热度来源查证（先查 DB，非猜）

**结论：`series` 主表无任何热度/计数列**（无 `view_count`/`buy_count`/`click_count`/`sales_count`），
但存在**可聚合的真实成交数据**：`order_item`（订单明细，`cohort_id` 挂班次 → 经 `series_cohort.series_id` 归系列）。

MySQL 实测（本地 `edu` 库）：

```
series on_sale                      2628
order_item 总数                      80328
order_item paid+completed           62400     ← 真实有效销量
order_item 状态值域                 cancelled,completed,paid,pending,refunded
series_visit_log                    40000     （可选热度信号）
series_favorite                     30004     （可选热度信号）
```

阈值判定：paid+completed 销量显著非零（62400），按系列聚合后呈有效降序分布（Top 系列销量 39/37/…/，非全平局）→ **热度语义可直接用「系列实付销量」表达**。

```sql
-- 实证聚合排序（与接口返回一致）
SELECT s.id,
  (SELECT COUNT(*) FROM order_item oi JOIN series_cohort sc ON sc.id=oi.cohort_id
   WHERE sc.series_id=s.id AND sc.yn=1 AND oi.order_item_status IN ('paid','completed')) sales_count
FROM series s WHERE s.sale_status='on_sale'
ORDER BY sales_count DESC, s.id DESC LIMIT 8;
-- 742  39 / 2518 37 / 2148 37 / 2036 37 / 1626 37 / 1318 37 / 695 37 / 2543 36
```

### 落点决议（ponytail §1：Does this need to exist at all？）

**不需要独立聚合端点。** 热门榜本质 = `series` 排序的又一形态，既有 `_SORT_MAP` 白名单 + 派生列即可表达。
选**最简可行落点**：`sort=popular` → `sales_count DESC, id DESC`（销量等值时 id 降序，结果稳定）。

> 仅当未来要跨维度（收藏+好评+曝光加权）做复杂热度公式时，才登记需新聚合端点；当前用户热门榜最简表达式即「热销」，
> 满足前端消费需求，不提前自建加权公式（YAGNI）。

---

## 2. 改动内容（最小 diff：2 文件，均在 course 域，未动响应壳契约）

### 2.1 `app/domains/course/router.py`
- `sort` Query 的正则白名单加入 `popular`：
  `^(default|newest|price_asc|price_desc|popular)$`
- 调整该参数 description 与模块头注释「排序白名单」行。
- > 注：`schemas.py` **无正式 sort Enum**（`sort` 校验由 router `Query(...pattern=...)` 承载），故契约「schemas 枚举」一栏为 N/A，白名单实际落点 = router pattern + repo `_SORT_MAP`。

### 2.2 `app/domains/course/repository/series_repo.py`
- `_SORT_MAP` 新增：`"popular": "sales_count DESC, id DESC"`（白名单表达式，用户不可拼接）。
- `list_series()` 在 `sort == "popular"` 时向派生表注入销量列 `sales_count`（**仅该分支注入**，避免非热门请求为每行跑销量子查询——性能硬化）：

```sql
(SELECT COUNT(*) FROM order_item oi
   JOIN series_cohort sc ON sc.id = oi.cohort_id
   WHERE sc.series_id = s.id AND sc.yn = 1
     AND oi.order_item_status IN ('paid','completed')) AS sales_count
```

- 长度：router +6 行改注释/正则，repo 约 +15 行（含注释）。`service.py` 零改动（`list_series` 透传 `sort` 已就绪）。

### 边界遵守
- 只改 course 域 `sort` 支持；未动响应壳契约（`{code,message,data}`、分页三重 {total,page,page_size,items} 原样）。
- `program_admin` 系列列表端点（`course_admin/router.py`，白名单 `default|newest|name_asc|name_desc`）是**管理端列表**，非用户热门榜，**未触碰**（避免越界）。
- 未加字段/迁移/建表——聚合基于既有 `order_item`+`series_cohort`，无需改表。

---

## 3. 完工前 self-check（tt §5.2 / critique 三视角）

| 视角 | 自检发现 | 处置 |
|---|---|---|
| 交互/语义 | `sort=popular` 未先注入 `sales_count` 就引用会 SQL 报错 | 检查：`sales_sel` 仅在 `sort=='popular'` 注入，`_SORT_MAP["popular"]` 与注入分支同条件成立；其余 sort 不注入也不引用 → 不会发生 |
| 边界 | 非法 sort 是否仍 422；排序表达式是否可注入 | `_SORT_MAP.get(sort, default)` 白名单兜底 + router pattern 前置拦截 → 非法值 422（实证 §2.3）；无字符串拼接用户输入 |
| 错误处理 | 销量列是否破坏分页/计数 | `ORDER BY` 引用派生表列、`COUNT(*)` 外层自包含，均实证 normal |

---

## 4. 验收实证（真实 HTTP，uvicorn 8000）

| 用例 | 端点 | HTTP | 结果 |
|---|---|---|---|
| 热门降序 | `GET /api/series?sort=popular&page_size=5` | **200** | `code:0`，items 顺序 = 742(法律资格·39) → 2518(37) → 2148(37) → 2036(37) → 1626(37)，与 §1 MySQL 聚合降序完全一致（销量等值 37 按 id DESC） |
| 非法 sort | `GET /api/series?sort=xxx` | **422** | `code:"42200"`，「String should match pattern '^(default\|newest\|price_asc\|price_desc\|popular)$'」 |
| 回归 default | `GET /api/series?sort=default&page_size=3` | 200 | `total:2628`，id 降序正确 |
| 回归 newest | `GET /api/series?sort=newest&page_size=2` | 200 | `created_at DESC` 正确 |
| 回归 price_asc | `GET /api/series?sort=price_asc&page_size=2` | 200 | 最低价 1999.00 在前，语义正确 |
| 组合筛选 | `GET /api/series?sort=popular&category=编程&page_size=3` | 200 | 分类内仍按销量降序，`total:144`，与筛选正常叠加 |

> 说明：`sort=popular` 返回 200 且降序正确；`sort=xxx` 保持 422；`sort=default` 及既有 `newest/price_asc` 回归不受影响。

---

## 5. 结论
- **热度来源**：`series` 无计数字段；用既有 `order_item`（paid/completed）按系列聚合销量表达热度，真实且有效。
- **落点**：最简「加 popular 到 sort 白名单」，**无需**独立聚合端点。
- **popular 已生效**：真实 HTTP 200，降序正确（已实证）。
- **无额外聚合端点需求**：当前热销排序已满足用户热门榜；加权热度公式留待未来按需登记。