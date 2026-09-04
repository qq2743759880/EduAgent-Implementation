# critique-C5 契约登记：系列回收站「恢复」端点（软删三态最小闭环补全）

> 登记日期：2026-09-04 ｜ 批判来源：C5（软删+真删+?include_deleted+40908 三态无回收站恢复）
> 前端将对此后端消费：提供「回收站 → 恢复为草稿」入口
> 关系：**不改动**既有 `DELETE /api/admin/courses/series/{id}`（软删/?hard=true 真删）与 40908 拒引用逻辑；本端点只补齐恢复方向的最小闭环。

## 1. 端点总览
| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/admin/courses/series/{series_id}/restore` | `admin` / `manager` | 从回收站恢复已软删（`sale_status='off_sale'`）的系列 → `sale_status='draft'`（草稿，可再次上架） |

> 与既有管理端 course_admin CRUD 同前缀 `/api/admin/courses`，保持一致。在既有 `DELETE /api/admin/courses/series/{id}` 序列化前缀下新增，不改动既有 CRUD 契约。属 `AdminAuthMiddleware.ADMIN_PREFIXES` 覆盖，匿名访问一律 401。

## 2. 统一响应壳
- 成功：`{ "code": 0, "message": "ok", "data": { "series_id": <id>, "status": "restored" } }`
- 失败：`{ "code": <string 错误码>, "message": "<用户可读>", "data": null }`（全局异常处理器产出）

## 3. 请求
```
POST /api/admin/courses/series/2659/restore
Authorization: Bearer <admin|manager access_token>
Content-Type: application/json
Body: {}   （空体即可，无需任何入参）
```

## 4. 成功响应 `data`（HTTP 200，`code:0`）
```json
{
  "series_id": 2659,
  "status": "restored"
}
```
恢复语义：`sale_status` 由 `off_sale` → `draft`（草稿态，默认列表可见，管理员可再 PATCH 上架）。

## 5. 错误语义（前端据此处分支）
| HTTP | code | message 示例 | 场景 |
|------|------|--------------|------|
| 404 | `40400` | `系列 2659 未处于回收站（已下架）状态，无法恢复` | 系列不存在 **或** 未处于软删（`off_sale`）态 |
| 409 | `40901` | `系列编码 'xxx' 已被其它系列占用，无法恢复` | 恢复时 `institution_id + series_code` 唯一冲突（该编码已被另一系列占用） |
| 401 | `40101` | `凭证无效或未登录` | 匿名 / 非 `admin`/`manager` 请求（中间件短路） |

> 说明：不存在与「未软删」统一收敛到 404，不泄露系列是否存在。`40901 = SERIES_CODE_CONFLICT`（复用既有错误码 `error_codes.py`，已在契约生效中登记于本域）。

## 6. curl 示例
### 6.1 成功（软删 → include_deleted 可见 → 恢复 → 重新上架）
```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"account":"adm02test","password":"Test@123456"}' | python -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")

# 新建并软删一个系列（得到 series_id，contract 以 2659 作示例）
curl -s -X POST http://127.0.0.1:8000/api/admin/courses/series/2659/restore \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
# => {"code":0,"message":"ok","data":{"series_id":2659,"status":"restored"}}

# 恢复后默认列表可见且 sale_status=draft
curl -s "http://127.0.0.1:8000/api/admin/courses/series?page=1&page_size=100" \
  -H "Authorization: Bearer $TOKEN"
```

### 6.2 错误分支
```bash
# 未处于软删态 / 不存在 → 404 40400
curl -s -X POST http://127.0.0.1:8000/api/admin/courses/series/99999999/restore \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
# => {"code":"40400","message":"系列 99999999 未处于回收站（已下架）状态，无法恢复","data":null}

# series_code 已被其它系列占用 → 409 40901
curl -s -X POST http://127.0.0.1:8000/api/admin/courses/series/{sid}/restore \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
# => {"code":"40901","message":"系列编码 'xxx' 已被其它系列占用，无法恢复","data":null}

# 匿名 → 401 40101
curl -s -X POST http://127.0.0.1:8000/api/admin/courses/series/1/restore \
  -H "Content-Type: application/json" -d '{}'
# => {"code":"40101","message":"凭证无效或未登录","data":null}
```

## 7. 测试证据
`tests/test_course_admin_restore.py`（真实 HTTP 直连 8000）：
- ✅ `test_restore_full_cycle`：创建→软删→include_deleted 可见→restore→默认列表可见 draft→重新上架 on_sale
- ✅ `test_restore_nonexistent_404`：不存在 → 404/40400
- ✅ `test_restore_not_soft_deleted_404`：on_sale 态恢复 → 404/40400 且状态不变
- ✅ `test_restore_anonymous_401`：匿名 → 401/40101
- ✅ `test_hard_delete_with_reference_still_40908`：既有 `DELETE ?hard=true` 有引用仍 409/40908（恢复端点不影响原语义）