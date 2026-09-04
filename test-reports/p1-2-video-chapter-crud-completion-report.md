# P1-2 视频章节 CRUD 路由接线完工报告（task57 gap）

- 任务：补后端「视频章节 CRUD」（`session_video_chapter`）管理端路由接线——schema/repo 已有章节模型，路由层缺失。

- agent：EduAgent P1-2 执行 agent ｜ 日期：2026-09-04 ｜ 结论：**已接线，真实 HTTP 200 实证通过，create/delete 闭环完成**。

- 关联脚本/证据：`test-reports/p1-2_chapter_crud_probe.py`（可重跑闭环）。

***

## 1. 资产消费证据段

| 资产       | 路径                                                                                          | 消费内容                                                                                                                                                  | 本次自检发现                                                                               |
| -------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| ponytail | `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md`                                   | 全程"最懒可用解"：复用既有 module/session 四级 CRUD 的 service/router 命名与路由风格，未新造抽象；只在 `repository/__init__.py` 导出 + service 补 5 个函数 + router 补 5 端点，单文件内插段，未波及主路由文件 | 契合 bower ladder rung2（代码内已有模式→复用），最小 diff                                            |
| tt       | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2（回传/验收强制独立实证）                       | 验收必须真实 HTTP 独立实证、不采信报告——采用 python requests（UTF-8 正确）逐段断言；override 脚本                                                                                  | 首次 PowerShell `Invoke-WebRequest` 传中文 body 会乱码（客户端 artifact）→ 改用 requests 复核，纠正后闭环全过 |
| review   | `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` + `reference/critique.md` | 完工前根治边界/错误/状态三视角：查证 get\_by\_id 缺失、双重启后确认新路由被加载                                                                                                       | 自检发现 `ChapterAdminRepo` 无 `get_by_id`（service 需要）→ 补齐该 repo 方法                       |

**agent×skill×workflow 矩阵**

| agent（执行者）             | skill（具名消费）          | workflow            | MCP                  | 产出                    |
| ---------------------- | -------------------- | ------------------- | -------------------- | --------------------- |
| EduAgent P1-2 执行 agent | ponytail（最懒可用解）      | tt 单平台退化（N=1，换视角复验） | 无                    | 3 文件最小接线 + 实证闭环       |
| <br />                 | review（critique 三视角） | tt §5.2 独立实证验收轨     | mcp\_filesystem/read | 缺层判定 + 修复 get\_by\_id |

**逐批判记录**

1. **「只补 route，连 service 都没有」**：查证后发现缺的不仅是 router——service 层无任何章节函数，`repository/__init__.py` 未导出 `ChapterAdminRepo`。故实际缺「service 函数 + router 路由 + repo 导出 + repo get\_by\_id」四小项，属路由层以下的最小补齐，未改 contract 响应壳。
2. **「裸 route 会不会 500」**：git 前自查——章节冲突有既有错误码 `CHAPTER_NO_CONFLICT="40907"`，create 复用之，实测 dup 返回 409`code:"40907"`，非 500。
3. **「reload 假象」**：8000 上 uvicorn 无 `--reload`，改完不重启代码不生效。重启后（先 200 后端口冲突误判）确认监听进程切换到新代码，GET 列表才从 404 变 200。避免读到旧的 stub 假象。

***

## 2. 现状查证 → 缺哪层 → 补了哪些

**现行事实（rg 实证）**

- schema（`course_admin/schemas.py`）：已有 `ChapterCreateAdmin / ChapterUpdateAdmin / ChapterResponseAdmin`，字段 `chapter_no(≥1) / chapter_title / start_second / end_second`，含 `start<end` 校验。

- repository（`course_admin/repository/video_repo.py`）：`ChapterAdminRepo` 已有 `list_by_video / get_by_chapter_no / insert / update / hard_delete`，**缺** **`get_by_id`**。

- service：**零章节函数**。

- router：**零章节路由**（仅分片上传占位）。

- `repository/__init__.py`：未导出 `ChapterAdminRepo`。

**缺哪层**：service 函数层 + router 路由层 + repo 导出 + repo `get_by_id`。任务描述的「缺路由」只是表象，根因在 service/router 两整段未接线。

**补了哪些（最小 diff，3 文件）**

1. `repository/__init__.py`：导出 `ChapterAdminRepo`。
2. `repository/video_repo.py`：`ChapterAdminRepo.get_by_id(chapter_id)`（供 service 读写回查，与其它 repo 一致）。
3. `service.py`：新增 5 函数 `create_chapter / update_chapter / delete_chapter / list_chapters_by_video / get_chapter_admin`（冲突 40907，物理删除），复用 `ConflictError / NotFoundError / AppException` 既有语意。
4. `router.py`：新增 5 端点（对齐 module/session）：

   - `GET    /api/admin/courses/videos/{video_id}/chapters`  列表（按视频）

   - `GET    /api/admin/courses/chapters/{chapter_id}`       详情

   - `POST   /api/admin/courses/chapters`                    创建

   - `PATCH  /api/admin/courses/chapters/{chapter_id}`       更新

   - `DELETE /api/admin/courses/chapters/{chapter_id}`       删除

`main.py` 无需改——为既有 `course_admin_router` 内插段，已 include（line 367）。

> 路径归属：现数据模型 `session_video_chapter.video_id` 外键真实挂在 `video`（非 series），repo/schema 均按 `video_id + chapter_no` 唯一、`list_by_video()` 表达，故选用 `videos/{video_id}/chapters`，与任务给定路径一致。

***

## 3. 真实 HTTP 实证（python requests，UTF-8 正确）

admin token `adm02test/Test@123456`（验收日志见探针脚本输出）：

| 步骤   | 请求                                                       | 结果                                                           |
| ---- | -------------------------------------------------------- | ------------------------------------------------------------ |
| 列表   | `GET /api/admin/courses/videos/1/chapters`               | **200**, `code:0`, 返回 video\_id=1 既有 3 章节（第1/2/3章）——404 消灭   |
| 创建   | `POST /api/admin/courses/chapters`（chapter\_no=99, 中文标题） | **200**, id=617330, `chapter_title:"P1-2临时章节"` 中文 UTF-8 正确落库 |
| 冲突   | 重复 `POST` chapter\_no=99                                 | **409**, `code:"40907"` 视频1章节号99已存在                          |
| 详情   | `GET /api/admin/courses/chapters/617330`                 | **200**                                                      |
| 更新   | `PATCH .../chapters/617330`（改标题/截止）                      | **200**, 标题变 `P1-2临时章节-改`, end\_second 60→120                |
| 列表   | `GET /videos/1/chapters`                                 | **200**, 章节数 = 基线+1                                          |
| 删除   | `DELETE .../chapters/617330`                             | **200**                                                      |
| 清理核验 | `GET /videos/1/chapters`                                 | **200**, 回到基线 3 条，无 617330                                   |
| 删后详情 | `GET .../chapters/617330`                                | **404**                                                      |

**闭环结论**：create→duplicate(409)→get→patch→delete→删后 404 全通过，临时章节已清理；既有 3 章节数据未受影响。另：实证期间发现 PowerShell 客户端传中文 body 会乱码，已用 requests 复核确认服务端 UTF-8 正常。

***

## 4. 与同域 module/session 风格一致性

- **路径风格**：列表挂子集下 `/{parent}/{parent_id}/{resource}s`（对齐 `GET /cohorts/{cohort_id}/modules`、`GET /cohorts/{cohort_id}/sessions`）；详情/增/改/删挂资源自身根 `/{resource}/{id}`（对齐 module/session）。新增章节完全复用该约定。

- **鉴权**：复用 `router` 顶部 `dependencies=[Depends(require_role([ADMIN, MANAGER]))]`，端点仅追加 `me: CurrentUser = Depends(get_current_user)`，与 module/session 逐字一致。

- **响应壳**：`ok(data=...)` / 列表 `[i.model_dump(mode="json") for i in items]`，不改契约。

- **service 语意**：创建冲突用 `ConflictError(code=CHAPTER_NO_CONFLICT)`（对齐 `SESSION_NO_CONFLICT` 用法）、物理删除对齐 module/session（该表无 yn 列）。

***

## 副产物 / 备注

- 未 commit（依 tt 纪律，等验收）。

- 后端 8000 已重启加载新路由（原无 reload，重启必要）。

- 探针脚本 `test-reports/p1-2_chapter_crud_probe.py` 保留，便于验收方独立复跑。

