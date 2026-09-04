# task：after_sales 建工单 500 修复 — 完工报告

> 后端缺陷：`POST /api/trade/after_sales/ticket` 带 `order_no` 时返回 HTTP 500 `{code:50000}`。
> 结论：根因已定位并修复，带/不带 order_no 均实证 200。**未 commit**。

---

## 1. 资产消费证据段 + agent×skill×workflow 矩阵

### 资产消费证据（assetConsumed）

| 必调资产 | 路径 | 消费方式 | 实际产出 |
|---|---|---|---|
| ponytail | `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md` | 全文读取（该目录仅含 SKILL.md） | 应用"根因修复非打补丁 + 最小 diff"：定位并删掉**不存在的列**过滤器；修复前先 grep `resolve_order_item` 全部调用者与全项目同类语法残留，确认单一落点后再改 |
| tt | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 | 全文读取（§5.2 回传机制/资产消费证据/完工前自检） | 完成报告按要求含「资产消费证据」段；每项验收均为**独立 HTTP 实证**（登录 → 建单 → 抓真实错误），不采信推断；无法起服务时如实记录降级情况 |

自检发现并修复项：任务描述假设的 MySQL 等价写法 `oi.yn <=> 1` 在真实库上仍会 500（`Unknown column 'oi.yn'`，因 MySQL `order_item` 表**根本没有 yn 列**）——进一步定位到真正的根因是"引用不存在的列"，非纯 PG 语法迁移。

### agent×skill×workflow 矩阵

| 维度 | 取值 |
|---|---|
| agent | 后端缺陷修复 agent（本任务） |
| skill | ponytail（最小根因修复）+ tt §5.2（验收/资产证据纪律） |
| workflow | 复现 → 定位 → 单点根因修复 → grep 全项目残留核实 → 起服务独立 HTTP 实证（带/不带 order_no）→ 回归 |
| MCP | 无（纯本地 HTTP + MySQL 实证，遵循项目"禁用 Playwright、接口验收用真实 HTTP"纪律） |

---

## 2. 根因 → 修复 → 实证

### 根因（两层）

1. **表象层（PG 语法）**：`edu-agent/app/domains/after_sales/repository.py` L27 `resolve_order_item` 的 `order_no` 分支 SQL 用了 PostgreSQL 语法 `oi.yn IS NOT DISTINCT FROM 1`，MySQL 解析失败 → 带 `order_no` 建工单时 HTTP 500。
2. **真实根因（列不存在）**：MySQL 的 `order_item` 表**没有 `yn` 列**（information_schema 实测，仅 `id/institution_id/order_id/user_id/student_id/cohort_id/order_item_status/...`，生命周期靠 `order_item_status` 状态值，无软删标记列）。因此任务建议的 `oi.yn <=> 1` 在真实库上**同样 500**（`Unknown column 'oi.yn'`）。这是一条无意义的"软删过滤"残留，直接删掉过滤器才是真正的根因修复。

### 修复（两行→最终一行，落在 `resolve_order_item`，公共查询函数，所有调用者受益）

文件：`edu-agent/app/domains/after_sales/repository.py` L27

- 首次改动：`oi.yn IS NOT DISTINCT FROM 1` → `oi.yn <=> 1`（按任务建议）
- 实测后确认真实根因：`order_item` 无 `yn` 列，`<=> 1` 仍 500 → 改为一并删掉该过滤器：

```sql
-- 改后
SELECT oi.id AS order_item_id, o.id AS order_id, o.order_no, o.institution_id
FROM `order` o JOIN order_item oi ON oi.order_id = o.id
WHERE o.order_no=%s AND o.user_id=%s LIMIT 1
```

分支内其余条件（`o.order_no=%s`、`o.user_id=%s`）保持原样，语义正确（task 要点 4 确认）。

### 实证（真实 HTTP + 数据库，独立复现）

**改前（旧进程，未 reload 前的原代码）**：
```
POST /api/trade/after_sales/ticket  Authorization: Bearer <user000001 token>
  {ticket_type:'refund', title:'t', content:'c', order_no:'1-260904101919-bf0fb5'}
→ HTTP 500  {"code":"50000","message":"服务内部错误，请稍后重试",
             "data":"(1064 ... 'You have an error in your SQL syntax; ... near 'DISTINCT FROM 1 LIMIT 1' at line 1')"}
```

**改后（重启加载修复后）—— 带 order_no**：
```
同上一请求
→ HTTP 200  {"code":0,"data":{"ticket_id":11027,"ticket_no":"T-1-260904102952-df2522",
   "user_id":1,"order_no":"1-260904101919-bf0fb5","status":"open", ...}}
```

**改后 —— 不带 order_no（回归）**：
```
{ticket_type:'refund', title:'t', content:'c'}
→ HTTP 200  {"code":0,"data":{"ticket_id":11028,"ticket_no":"T-1-260904102955-d5afb4",
   "user_id":1,"order_no":"1-260904101919-bf0fb5","status":"open", ...}}
```
（不带 order_no 命中 L31 分支，走该用户最近 order_item，回归通过。）

---

## 3. grep 全项目同类 PG 语法残留结论

- `rg -n "IS NOT DISTINCT FROM" edu-agent/app` → **仅 1 处**：即本次修复的 L27。全项目无其它 `IS NOT DISTINCT FROM`。
- 更宽泛 PG 特征 grep（`IS DISTINCT FROM` / `ILIKE` / `RETURNING` / `::<type>` 类型转换 / `ON CONFLICT`）→ **0 处**。
- `rg` 含 `order_item.yn`/`oi.yn` 的引用 → **仅本次修复处**，无其它调用点。
- **结论：本项目存在同类 PG 语法残留的仅 1 处（本次已修）；未发现其它同类问题，无需扩大修复范围。**

---

## 环境备注

- 修复后服务已用项目 venv 重启：`edu-agent\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --host 127.0.0.1`（原 uv 启动的进程已停止，服务保持可用）。外部依赖（Milvus/Mongo/MinIO 192.168.85.101）本轮不可达，开发模式可忽略，不影响本修复验证。
- 验证过程在库内写入 2 条测试工单（id 11027/11028），属可忽略测试数据。
- 未 commit。