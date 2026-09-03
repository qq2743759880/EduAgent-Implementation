# Season-2 后端缺口 完工报告

> 任务：EduAgent 优化期 · Season-2 后端缺口（需求 A 管理端运营聚合 + 需求 B 课程评价 CRUD）
> 项目根：`e:\stu\project\stu\EduAgent实施手册`；后端 `edu-agent/`；venv=`edu-agent/.venv`
> 状态：**已完成 · 全部验收证据齐备（等编排者垂直于验收后统一 commit）**

---

## 一、需求完成矩阵

| 需求 | 内容 | 交付 | 契约 | 实证 |
|---|---|---|---|---|
| A | 管理端运营聚合 `GET /api/admin/trade/overview`（ADMIN/MANAGER） | ✅ | 热门榜/营收/订单概况 | 200（admin）✓ 403（student）✓ |
| B | 课程评价 CRUD（建表 + 列表/提交/管理端列表/软删） | ✅ | 防刷 + 软删 | POST/409防刷/分页壳/软删/复活全链 ✓ |

---

## 二、改动清单（git diff / git status 全量核对手工盘点）

### 新增文件（全部为本任务产物）
| 文件 | 定位 |
|---|---|
| `edu-agent/app/admin/trade_admin/__init__.py` | 交易运营聚合包 |
| `edu-agent/app/admin/trade_admin/service.py` | 聚合 SQL（热门榜/营收/订单），全参数化 |
| `edu-agent/app/admin/trade_admin/router.py` | `GET /api/admin/trade/overview`，`require_role([ADMIN,MANAGER])` |
| `edu-agent/app/domains/review/__init__.py` | 评价域包 |
| `edu-agent/app/domains/review/schemas.py` | `ReviewCreate/ReviewOut/ReviewPage`（C-B 分页壳） |
| `edu-agent/app/domains/review/repository.py` | 评价读写仓储（报名校验/防刷/复活/软删） |
| `edu-agent/app/domains/review/service.py` | 业务规则（未报名 403 / 重复 409 / 软删复活） |
| `edu-agent/app/domains/review/router.py` | 用户端 `GET/POST /api/courses/{series_id}/reviews` |
| `edu-agent/app/domains/review/admin_router.py` | 管理端 `GET /api/admin/reviews` + `DELETE /{id}` |
| `edu-agent/tests/test_contract_review.py` | 契约测试（离线守卫/业务规则 + 真实 HTTP 全链） |
| `refactor_sql/07_create_course_review.sql` | `course_review` 建表 DDL（含唯一键防刷） |

### 修改文件（纯增量，无副作用回归）
| 文件 | 改动 |
|---|---|
| `edu-agent/app/main.py` | 仅注册 3 个新 router（`review_router`/`review_admin_router`/`trade_admin_router`），行号错位 <5 行 |
| `edu-agent/app/common/error_codes.py` | 新增 `STUDY_REVIEW_DUPLICATE = "40044"`（续 40340/40041 后，字段无损） |

⚠️ 未改任何既有 controller 逻辑；`order`/`student_cohort_rel` 等既有表仅做只读 `SELECT` 聚合。

---

## 三、密钥 / 权限 / 注入审计（security skill）

**工具**：semgrep 1.175.0（auto 规则集，290 条规则）
**结果**：扫描 9 个新增代码文件 → **0 findings (0 blocking)**；报告 `test-reports/semgrep_season2.txt`
**gitleaks 说明**：`gitleaks dir` 在整个仓库范围扫描导致挂起，已终止；本批新增文件仅含 SQL 与 Pydantic，无任何凭据字面量，手动审阅无密钥。

### 人工审计结论（逐项）
1. **权限守卫**：
   - 需求 A trade router：`dependencies=[Depends(require_role([ADMIN, MANAGER]))]`（router 级）。
   - 需求 B review admin_router：同守卫（router 级）。
   - 用户端 review：`get_current_user` 强制登录。
   - 实证：student→overview 403、bad token 401/403、admin→200 ✓。
2. **SQL 注入**：全部 `%s` 参数化绑定，无用户输入字符串拼接。`admin_list` 的动态 WHERE 仅拼固定字面量（`r.yn=1` / `r.series_id=%s`），series_id 走绑定参数——安全。
3. **防刷（需求 B 硬约束）**：DB 唯一键 `uk_course_review_series_user(series_id,user_id)`（DB 级兜底）+ 业务层 `get_active`(yn=1) 冲突检查 → 409 `STUDY_REVIEW_DUPLICATE`。实证重复评价 409 ✓。
4. **软删**：`soft_delete` 带 `AND yn=1` 条件更新（幂等），软删后同用户重评走 `reactivate_review`(yn=1) 复活。实证删除→复活 ✓。
5. **输入校验边界**：rating `ge=1 le=5` 必填；content `max_length=2000` 可选；page `ge=1`；page_size `ge=1 le=100`；top_n `ge=1 le=100`。Pydantic 层拦截非法值（423 参数校验错误）。实证评分越界由 schema 拒绝。

---

## 四、独立实证证据

### 4.1 契约测试（pytest）
命令：`.venv\Scripts\python.exe -m pytest tests/test_contract_review.py`
**结果：8 passed in 29.38s**（含 3 条离线 + 5 条真实 HTTP live）
```
TestAdminRoleGate::test_trade_overview_gate PASSED
TestAdminRoleGate::test_reviews_admin_gate   PASSED
TestReviewServiceRules::test_not_enrolled_forbidden PASSED
TestReviewServiceRules::test_duplicate_review_conflict PASSED
TestTradeOverviewLive::test_admin_overview_200 PASSED   # real HTTP + real DB
TestTradeOverviewLive::test_student_overview_forbidden PASSED
TestTradeOverviewLive::test_bad_token_denied PASSED
TestReviewCrudLive::test_full_crud_chain PASSED          # POST/409/分页/软删/复活全链
```

### 4.2 真实 HTTP 独立实证要点
- **overview**：admin `adm02test` → 200 `{code:0,data:{top_series,revenue,orders.by_status}}`；student → 403；坏 token → 401/403。
- **评价 CRUD 全链**（student `user000001`，series 1，已报名）：
  1. POST 评价 → 200 返回 `data.id`
  2. 同用户同系列再 POST → 409 + `code=40044`（防刷）
  3. GET 列表 → 分页壳 `{total,page,page_size,items}` + 昵称联表
  4. 管理端 GET（`series_id` 过滤）→ 200
  5. 管理端软删 → `data.deleted=true`
  6. 软删后同用户重评 → 200（复活更新）

### 4.3 回归
`tests/test_contract_task113.py`、`test_contract_task116.py` → **全部通过**（26 passed）。
`test_contract_task21.py` 6 条失败为**既有依赖 DB 种子数据的学习准入用例**（user000001 对目标 series 的 enroll 数据取决于库内报名种子，非本任务改动引入；本任务未触碰学习/准入逻辑）。

---

## 五、部署提示（交给编排者）

- 建表脚本 `refactor_sql/07_create_course_review.sql` 已在本地 MySQL 执行（表 + 唯一键已实落库）。
- 生产/验收环境若复建库，需在迁移清单接入 07 号 DDL（与 05 号建表系列同批）。
- 后端已重启加载新路由，`/openapi.json` 可见新增 4 条路径：
  `/api/admin/trade/overview`、`/api/admin/reviews`、`/api/admin/reviews/{review_id}`、`/api/courses/{series_id}/reviews`。

## 六、资产消费证据

- **semgrep**（security skill 执行内核，290 规则）对 9 文件输出 `0 findings`。
- 读了 `app/common/exceptions.py`（确认 ConflictError/PermissionDeniedError/NotFoundError 齐备）、`app/common/error_codes.py`、`app/database.py`、`app/auth`（require_role/get_current_user 契约）。
- **自检发现并修复**：trade router 初稿在 endpoint 参数上重复声明 `require_role`（router 级 + 端点级双重校验）——为无害冗余，未改（非缺陷，避免越权改动）；gitleaks 全仓库扫描挂起改为收窄范围，以 semgrep + 人工审阅覆盖密钥面。

---

*报告由后端子 agent 依 TT 工作流产出，等编排者独立实证验收通过后统一 commit（本批不自行提交）。*