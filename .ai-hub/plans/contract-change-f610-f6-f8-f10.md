# 契约变更单 F610（F-6 / F-8② / F-10③，待用户签字）

> 来源：盲测 T2（lianq-admin-report.md §8 交接清单第 1/4/7 项）+ F610 修复工程师开工复核（curl/openapi/只读 SQL 实证）。
> 硬性守则：新增端点/请求形态变更必须先签后码。**签字前三项均不动实现代码。**
> 签字格式：`F6 选A  F8-2 同意  F10-3 暂缓` 或逐条改。

| CR | 变更 | 动机（实证） | 提案 | 优先级 |
|---|---|---|---|---|
| F6 | 新增 `POST /api/admin/courses/videos/{video_id}/unbind-session`（无请求体；ADMIN+MANAGER，与 bind-session 同级） | openapi 全量无任何 unbind/资产删除路径（2026-09-15 复核 `unbind paths: []`）；bind 仅 UPDATE `session_asset.session_id`（service.py L605），传错视频后课次删除被 session_asset 引用计数挡 40908，运营死锁 | 见下方"F6 语义两案"，**推荐 A 案** | P1 |
| F8-2 | 新增 `GET /api/admin/questions/questions`（跨题库只读列表/搜索） | 现 `GET …/questions?keyword=` → **HTTP 405**（路径仅注册 POST，实测 2026-09-15）；删库后题目失联无法找回。注意：`contracts/reshape-a.json` L32 **早已登记** `GET /api/admin/questions/questions/`——本项是实现补齐冻结契约，而非契约外扩张 | query：`keyword`(LIKE stem/analysis_text/question_code)、可选 `bank_id`/`question_type_id`、`page`/`page_size`(同限 100)；返回壳沿用分页 `{total,page,page_size,items}`，item 形状=既有 QuestionResponseAdmin；仅 yn=1；权限 ADMIN+MANAGER；**纯只读零写入** | P2 |
| F10-3 | 题库批量导入支持文件上传（multipart 文件 → items 数组） | 现 import-preview/import-execute 仅收 JSON items 数组（question_admin/router.py L150/L159）；运营手中的 xlsx/csv 无法直接导入 | **建议暂缓、登记本单**：需定文件格式（.json/.xlsx/.csv 三选一或全要）、xlsx 解析新依赖（openpyxl）、且前端入口在 `public/admin-questions.html`（本批禁改领地），须与前端批次联动。后端可先行兼容：在现有两端点增加 `multipart/form-data` 入参（file 与 JSON body 二选一），但无前端消费前价值有限 | P3 |

## F6 语义两案（数据模型实证后必须请用户拍板）

权威表结构（只读 information_schema 实证，全部外键 **NO ACTION**，三表均**无 yn 列**）：

- `session_asset`（id, **session_id NOT NULL**→series_cohort_session, asset_code, …, file_url, file_size, uploader_user_id）
- `session_video`（id, **asset_id NOT NULL**→session_asset, video_code, …）
- `session_video_chapter`（**video_id NOT NULL**→session_video）
- 物理文件：`DATA_DIR/media/videos/<file>.mp4`

现状链路：finalize 建 asset+video（asset.session_id=init 时课次）→ bind 只 UPDATE asset 的 session_id/sort_no（service.py:597-611）。

**A 案（推荐，与 kickoff 字面一致；元数据物理删、磁盘文件保留）**
- unbind 顺序删：session_video_chapter(video_id) → session_video(id) → session_asset(id)；不触碰 media 磁盘文件。
- 响应：`{video_id, asset_id, session_id, unbound:true, file_kept:true, file_url}`。
- 错误：video_id 不存在/已解绑（元数据行已无）→ **40400**；删除后再调 → 40400（天然幂等护栏）。
- 直接效果：课次引用计数归零，DELETE session 不再被 40908 挡；系列→班次→模块→课次回收链解锁。
- **"rebind 同视频可复用"的解释（请确认）**：元数据删后原 video_id 不存在，无法用原 id 再 bind；"复用"= 同一 mp4 文件重新走 init/finalize 上传（文件保留在磁盘可供核验/重新登记），新 asset/video 绑定成功。若期望"原 video_id 解绑后还能 bind 到别的课次"，那是 B 案。

**B 案（保留元数据的" detach"，需权威表结构变更）**
- session_asset.session_id 现为 NOT NULL，无 yn/状态列； detach 必须改 edu.sql 权威表（session_id 改可空或新增 detached 状态），并在所有读侧（list_session_assets、学习端播放解析、转码轮询）补"游离资产"语义。
- 成本与回归面显著大于 A；收益是原 video_id 可反复 bind/unbind。

GWT（签 A 后验收用）：①绑定视频的课次 unbind → 三表行删、磁盘文件在、GET assets 不再含该视频；②重新上传同一 mp4 并 bind 成功；③未绑定/不存在 video_id unbind → 40400；④解绑后原课次可删除（不再 40908）。

## 本批不待签即实施的项（无新增端点/无契约形态变更）

- F-7：建/改版式班次外键预校验（head_teacher_id 等）→ 非法值由 50301 改语义 40400（现有 POST/PATCH 端点的错误语义修正）。
- F-8①：现有 `DELETE /banks/{id}` 增加非空保护（409）与 `?force=true` 级联软删题目（查询参数扩展，非新端点）。
- F-9：现有 `DELETE /cohorts/{id}` 增加模块引用保护（40908）与 `?force=true`（仅 ADMIN；模块表无 yn，force=物理清空零课次模块后软删班次；模块下仍有课次则连 force 也拒绝）。
- F-10①：`/media/*` 的 404 由 JSON 壳改纯文本 404（静态资源非 API，不动统一响应壳契约）。
- F-10②：`GET /api/admin/rag/collections` 读侧过滤 Milvus 中物理不存在的幽灵集合（Milvus 不可达时不过滤，保持现降级；不删 MySQL 行）。
