# task117 完工报告 · 前端 admin-courses CRUD 真实接线

> 域：FE ｜ 波次：W2 ｜ 依赖：**task116 DONE**（C-C 冻结单 `handoffs/task116-contract.md` 已验收）
> 唯一改动文件：`edu-frontend/public/admin-courses.html`
> 硬性守则履约：✅ 只改这一个文件 ｜ ✅ 未切分支 / 未 commit ｜ ✅ 未改 `edu-api.js` ｜ ✅ 未用 Playwright
> 验证端口：本机 8078（从当前含 task116 语义的代码 `uvicorn app.main:app`，`MYSQL_HOST=127.0.0.1`）全链实测

---

## §0 概述

把管理端课程列表的"保存 / 上架 / 下架 / 删除"从 alert 占位变成**真实 CRUD**，严格消费 task116 冻结的 C-C 契约：
- 删除走 `DELETE /api/admin/courses/series/{id}` **默认软删路径**（`?hard` 绝不在前端出现），返回 `"系列已下架"`；
- 行从默认列表消失（后端 `WHERE sale_status != 'off_sale'` 过滤），`include_deleted=true` 回收站仍可见；
- 上下架用 `PATCH sale_status`；新建用 `POST`（必填按实测 schema，含 `created_by`）；
- 错误接行内 toast 透出后端 message（40901 重复码 / 42200 校验 / 40908 引用拒绝）。

---

## §1 改动清单（grep 行号证据）

| 区域 | 位置 | 改动 |
|---|---|---|
| 删除确认弹窗文案 | `admin-courses.html` 删除 ConfirmDialog `<b>`+`<p>` | "下架优先于删除" → **"下架系列「X」（可在回收站查看）"**；明确"不会永久删除数据" |
| 删除确认按钮 | 同上 `onclick="doDelete()"` 按钮 | "删除（软删）" → **"确认下架（软删）"** |
| 视频上传占位 | 新建/编辑 Dialog `.mfoot` | 新增 `disabled` 按钮 **"🎬 视频上传（占位）"**（后端 4 端点 stub，禁调假接口） |
| toast 样式 | 第一个 `<style>` 块末尾 | 新增 `.em-toast`（`ok`/`err` 两态，固定底部居中） |
| 写路径函数 | 原 `openCreate/openEdit/openDel/openOff/doOnSale/doOffSale/doDelete/saveSeries`（原 alert 占位） | 全部重写为真实 API 调用 + toast 反馈 |
| 新增助手 | 同区块 | `esc / errMsg / toast / ensureAdminId / loadSeries / rowHtml / refreshList` |
| `bootAdmin` | 末尾 `<script>` | 由"alert 行内按钮"改为调用 `loadSeries()`（真实渲染 + 真实"管理"按钮） |

**未触碰**：task109 角色守卫 IIFE、`edu-api.js`、mock `SERIES` 演示数组、`render()` 演示视图（"审核用，非产物"）。

---

## §2 消费 C-C 契约（task116）的落点

| C-C 契约条款 | 前端落点 |
|---|---|
| §1.1 软删默认路径（`hard` 缺省=off_sale，message `"系列已下架"`） | `doDelete()` → `EAPI.del("/api/admin/courses/series/"+id)`，**不带 `hard`**；toast 用返回 message |
| §1.1 严禁"永久删除" | 删除文案含"下架"、显式"不会永久删除数据"；前端**永不发 `?hard=true`** |
| §2 默认列表过滤 `WHERE sale_status != 'off_sale'` | `loadSeries()` 渲染默认列表；软删后 `refreshList()` 复拉，行自动消失 |
| §2 `include_deleted=true` 回收站 | 契约已落地于后端；本任务确认软删行在回收站仍可见（实证见 §4 第 9 项） |
| §7.2 series 软删仅 `sale_status='off_sale'`，不新增 `yn` 列 | 前端不依赖任何 `yn` 字段，仅读 `sale_status` |

---

## §3 前端 → 后端映射（字段形态，实测一致）

- **新建** `POST /api/admin/courses/series`
  - 必填：`series_name, series_code, institution_id, delivery_mode`，外加 `created_by`（取自 `GET /api/auth/me` 的 `user_id`）。
  - 可选：`sale_status(默认 draft), description, cover_url`。
  - 校验：`series_code` 唯一 → 冲突 `40901`；`delivery_mode` 越界 → `42200`。
- **编辑** `PATCH /api/admin/courses/series/{id}`
  - 仅发 `SeriesUpdateAdmin` 允许字段：`series_name, delivery_mode, sale_status, description, cover_url`（**不含** `series_code`/`institution_id`，避免 422 越界）。
- **上架/下架** `PATCH .../{id}` + `{sale_status:"on_sale"|"off_sale"}`。
- **删除** `DELETE .../{id}`（默认软删）。
- **错误透出**：`EAPI` 抛 `Error{ message, body }`；`errMsg()` 优先读 `e.message`，422 回退读 `e.body.data[].msg`。

---

## §4 全链路真实 HTTP 实证（14 PASS / 0 FAIL）

脚本：`test-docs/t117_full.py`（建→改→上下架→软删→include_deleted 复查 + 40901/42200 + 清理）。
原始输出：`test-reports/t117_full_out.txt`（exit=0）。

关键结果节选：
```
[PASS] 新建系列成功            id=2650
[PASS] 列表立现新建行          in_list=True
[PASS] PATCH 改名成功
[PASS] 刷新后为新值            got=task117 改名 T117_...
[PASS] 上架成功 / 状态=on_sale
[PASS] 下架成功 / 状态=off_sale
[PASS] 软删 message=系列已下架  msg=系列已下架
[PASS] 默认列表已剔除软删行     in_list=False
[PASS] 回收站视图仍可见        in_recycle=True
[PASS] 重复编码 409/40901       code=40901   ("系列编码 'T117_...' 已存在")
[PASS] 非法字段 422/42200       code=42200   (delivery_mode pattern mismatch)
[PASS] 清理：hard 删除成功      msg=系列已彻底删除
PASS=14 FAIL=0
```
> 实证口径：创建 id=2650 → 软删后默认列表剔除、回收站可见 → 清理 `?hard=true` 彻底清除（零引用），与 C-C §1.1/§2 完全一致。

---

## §5 七维 UX 自检（review/critique 内核）

1. **AI slop**：无模板化填充；全部沿用既有 candy-playful 设计 token（`.badge-on/.badge-mut`、`.dd-item`、`.b-dm`），视觉语言与 8 个 admin 页一致。
2. **视觉层级**：写操作反馈分两级——模态（删除/下架确认）用于破坏性操作，toast（底部居中 3.4s）用于成功/错误瞬时反馈；不抢视觉焦点。
3. **信息架构**：列表行"管理 ▾"下拉收敛 编辑/班次/上架或下架/删除；"班次"跳详情页。`sale_status` 三态徽章（在售/草稿/已下架-虚线）直观。
4. **可发现性 & affordance**：破坏性操作集中在下拉末项且为红色 `.dd-item.danger`；软删文案明确"可在回收站查看"，降低误操作焦虑。
5. **交互态**：保留既有 loading skeleton / success / error / empty 四态；写后局部 `refreshList()`（非整页刷新），状态即时闭环。
6. **错误反馈**：必填校验（名称/编码/机构ID）行内 toast；后端 409/422/40908 文案**直接透出**（如"系列编码已存在""delivery_mode 不匹配"），无吞错。
7. **性能**：写后仅重拉当前页列表（单请求），`EAPI` 15s 超时兜底；无额外阻塞。

**诚实标注的残余缺口（非本任务范围）**：顶部筛选栏（关键词/交付/状态/排序）的 `onchange` 仍走演示层 `render()`（mock `SERIES`），在真实数据下切换筛选会回落到演示数据。本任务硬性范围仅"写路径"，筛选器接 API 参数归后续 task；已在 §8 列风险。

---

## §6 机验结果

- `grep -c "alert(" admin-courses.html` → **0**（写路径相关 0，全文件 0）。
- 删除文案：含 **"下架"**、**不含** "永久删除"（改为"不会永久删除数据"）。
- 内联脚本语法：`node --check` 4 个 `<script>` 块 **全部 OK**。
- 全链实证：**14 PASS / 0 FAIL**（§4）。

---

## §7 资产消费证据（B 级）

| 资产 | 读了什么 | 在 task117 哪里应用 |
|---|---|---|
| **task116 C-C 冻结单**（`handoffs/task116-contract.md`） | §1.1 软删默认路径 + message `"系列已下架"`；§2 默认列表过滤 `sale_status!='off_sale'`、`include_deleted` 回收站；§7.2 不新增 `yn` 列 | `doDelete()` 走默认软删、toast 用返回 message；`loadSeries()` 软删后行自动消失；前端不依赖 `yn` |
| **course_admin Schemas**（`app/domains/course_admin/schemas.py`） | `SeriesCreateAdmin` 必填 `institution_id/delivery_mode/series_code/series_name/created_by`；`SeriesUpdateAdmin` 全 Optional 且**无** `series_code/institution_id` | `saveSeries()` POST 发全字段含 `created_by`；PATCH 仅发 `series_name/delivery_mode/sale_status/description/cover_url` |
| **error_codes**（`app/common/error_codes.py`） | `SERIES_CODE_CONFLICT="40901"`、`VALIDATION="42200"`、`SERIES_IN_USE="40908"` | `errMsg()` 透出 `e.body.code` 对应文案；前端错误反馈与后端码一致 |
| **EAPI 契约**（`edu-frontend/public/edu-api.js`，只读未改） | 解包 `{code,message,data}`；非 2xx/业务错误抛 `Error{message,body}`；`EAPI.get/post/patch/del` | 全部调用基于该契约；`errMsg()` 读 `e.message`/`e.body.data` |

---

## §8 风险与未达标

- **筛选栏未接 API（已在 task121 续作中闭环）**：顶部筛选栏（关键词/交付/状态/排序）现已接到真实 `GET /series` 参数（`keyword`/`delivery_mode`/`sale_status`/`sort`）+ 真实分页（`page_meta`）。详见 §10。
- **环境漂移（已解决并沉淀）**：本机 `.env` 写 `MYSQL_HOST=localhost`；VM `192.168.85.101` 的 MySQL **拒绝** `root@192.168.85.1`（grant 不允许），故后端须以 `MYSQL_HOST=127.0.0.1` 启动（本机 Windows MySQL 有 `root@127.0.0.1`/`%` 授权）才能连上。已据此启动 8078 实证，未动 8000 托管旧实例。
- **Redis 不可达**：`app/core/cache.py::invalidate` 已 try/except 容错，series CRUD 不受影响（实证已证明）。

---

## §9 交付物清单

- `edu-frontend/public/admin-courses.html` — 真实 CRUD 接线（写路径全改，机验 `alert(`=0、删除文案合规、语法 OK）。
- `test-docs/t117_full.py` — 可复跑全链验收脚本（建→改→上下架→软删→回收站复查 + 40901/42200 + 清理）。
- `test-reports/t117_full_out.txt` — 14 PASS / 0 FAIL 原始实证。
- 本报告 `test-reports/task117-completion-report.md`。

> 注：本任务**未 commit**（遵守硬性守则）；如需入版控，请编排者单独执行提交。

## §10 筛选栏接线（task121 续作，已完成）

将顶部筛选栏从「演示层 `render()`/mock `SERIES`」改为驱动真实 `loadSeries()`：
- `#f-kw` 输入 → `keyword`（350ms 防抖 `onKwInput`）；`#f-dm`/`#f-ss`/`#f-sort` 的 `onchange` → `applyFilter()`。
- `applyFilter()`/`resetFilter()` 现在重置 `__page=1` 并调用 `loadSeries()`（不再走 mock）。
- `buildSeriesQuery()` 按四输入拼 `keyword/delivery_mode/sale_status/sort`（`sort=default` 省略）+ `page/page_size`。
- `loadSeries()` 读 `page_meta.total` 写「共 X 个系列」，并 `renderPagerReal()` 渲染真实分页（`gotoPage` 翻页）。
- 后端契约核对（实测）：`GET /series?keyword|delivery_mode|sale_status|sort` 均生效，非法 `sort`→422（前端 `<option>` 枚举与契约 `^(default|newest|name_asc|name_desc)$` 一致）。

实证：`test-docs/t121_filter_check.py`（只读）跑 **8 PASS/0 FAIL**（`test-reports/t121_filter_out.txt`）；内联脚本 `node --check` 4 块全 OK；前端接线 grep 确认。仍只改 `admin-courses.html`、未 commit。
