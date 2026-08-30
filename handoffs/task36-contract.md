# task36 契约冻结⑥（Contract Freeze）：RAG 上传后端

> 冻结日期：2026-08-30 ｜ 后端提交链：`e13d9a5 → a9747c6 → 860ea9d → 52a1d28`
> 解锁前端：TraeWork **task61（/admin/rag 上传入口）**
> 状态词汇（全局统一）：`pending` / `running` / `succeeded` / `failed`

## 1. 端点总览
| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/knowledge/upload` | 登录用户（`get_current_user`） | 用户上传私有知识，落 `user_{id}` Partition |
| POST | `/api/knowledge/admin/upload` | `admin` / `manager`（`require_role`） | 管理员上传公共知识，落 `_default` Partition |
| GET  | `/api/knowledge/tasks` | `admin` / `manager` | **分页倒序**查询导入任务（task36 新增） |
| GET  | `/api/knowledge/status/{task_id}` | 登录用户 | 查单任务状态 |
| GET  | `/api/knowledge/partitions` | `admin` / `manager` | 查所有 Milvus Partition |
| DELETE | `/api/knowledge/partitions/{tenant_id}` | `admin` / `manager` | 删指定 Partition（`_default` 禁止） |

## 2. 统一响应壳
成功：`{ "code": 0, "message": "ok", "data": <payload> }`
失败：`{ "code": <string 错误码>, "message": "<用户可读>", "data": null }`（由全局异常处理器产出）

## 3. FormData 规格（upload / admin/upload）
- 字段名：`files`（多文件，`list[UploadFile]`）
- 允许后缀：`.md` `.txt` `.markdown` `.pdf` `.docx`
- 单文件大小上限：**200MB**
- 数量上限：`upload` ≤ 20 个；`admin/upload` ≤ 50 个
- 越界响应：400（类型/数量）/ 413（单文件超限）/ 500（落盘失败）

### upload / admin_upload 响应 `data`
```json
{
  "task_id": "task_<ts>_<rand>",
  "status": "pending",
  "message": "文件已接收，正在后台执行 parse→chunk→embed→load→graph_build 全流程",
  "tenant_id": "user_<id> | _default",
  "visibility": "private | public"
}
```

## 4. GET /api/knowledge/tasks（分页倒序）— task61 核心契约
- Query：`page`(≥1, 默认 1) / `page_size`(1~100, 默认 20) / `status`(可选：`pending|running|succeeded|failed`)
- 响应 `data`：
```json
{
  "items": [
    {
      "task_id": "task_...",
      "task_type": "user_upload | system_init",
      "tenant_id": "user_123 | _default",
      "visibility": "private | public",
      "status": "pending | running | succeeded | failed",
      "total_chunks": 0,
      "imported_chunks": 0,
      "source_files": [
        { "object_key": "knowledge/20260830/ab12cd34/a.md", "file_name": "a.md", "file_size": 1024, "content_type": "text/markdown" }
      ],
      "error": null,
      "created_at": "2026-08-30T12:47:53",
      "started_at": null,
      "finished_at": null
    }
  ],
  "total": 42,
  "page": 1,
  "page_size": 20,
  "total_pages": 3
}
```
- 排序：`created_at DESC`（最新在前）
- 进度展示建议：`imported_chunks / total_chunks`；状态徽标：`pending=处理中/排队`, `running=导入中`, `succeeded=成功`, `failed=失败`（失败可展示 `error`）
- 轮询：前端 TaskTable 建议每 3~5s 拉一次本接口（或 `GET /status/{task_id}`）

## 5. 存储与留存语义（task61 无需关心但需知）
- **MySQL** `knowledge_import_task`：持久真相源 + 对账 + 分页列表（重启不丢）
- **Redis** `edu:knowledge:task:{id}`：TTL 24h 热缓存（进程重启后从 MySQL 恢复），Redis 不可用时自动降级 MySQL
- **MinIO** `edu-upload`：源文件留存，**30 天生命周期自动过期**；`object_key` 记入任务表 `source_files`；导入完成不删源文件
- `status` 一致性：内部模型旧值 `done` 已统一映射为表词汇 `succeeded`，前端只看到 `succeeded`

## 6. 前后端对接注意事项
1. task61 只用 `GET /tasks` + `POST /admin/upload` 即可实现 /admin/rag 上传入口与任务列表。
2. 状态轮询以 `status` 字段为准，禁止用 `source_files` 长度推断进度。
3. 大文件（>200MB）或视频走独立 MinIO 预签名接口（不在本契约范围）。
4. 响应一律解 `data` 字段；非 0 `code` 按错误码处理。
