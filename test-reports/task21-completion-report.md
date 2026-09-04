# task21-completion-report · 后端 study/learning 学习域（契约⑪ task21 段）

> 类型：backend + database ｜ 阶段：P4/W2 ｜ 执行：TraeCode 手动调度（dev-standard 8 阶段）
> 契约依据：`plans/tasks/task21-study.md` + api-request §2 + 前端 `study.ts`（task40 权威）
> 状态：**待编排者验收**（未经验收不开始 task22）

---

## 范围裁定
前端 study.ts 仅封装 3 端点（access/outline/complete）；作业/考试提交 + tick-batch 已由 `/api/progress`（task14）实现。经用户裁定：实现 **3 端点 + session 详情**（覆盖 GWT③ session_asset 过滤 + GWT④ transcode）。本域为新建 `app/domains/learning/`。

## 交付内容
| 端点 | 说明 |
|------|------|
| GET `/api/study/courses/{series_id}/access` | 访问鉴权（access_scope 矩阵） |
| GET `/api/study/courses/{series_id}/outline` | 学习大纲（模块/课次/进度 + 资源过滤） |
| POST `/api/study/sessions/{session_id}/complete` | 课次完成态（completed_flag） |
| GET `/api/study/sessions/{session_id}` | 课次详情（session_asset 过滤 + transcode） |

## 新增/修改文件
| 文件 | 说明 |
|------|------|
| `edu-agent/app/domains/learning/{schemas,repository,service,router,__init__}.py` | study/learning 域 |
| `edu-agent/app/main.py` | 注册 learning_router |
| `edu-agent/tests/test_contract_task21.py` | task21 契约测试（in-process ASGI） |
| `edu-agent/scripts/_verify_task21_study.py` | GWT② 打点/外键 DB 证据 |

---

## 验收标准逐条对照

### GWT① 未报名请求 enrolled_only 资源 → 403
> Given 未报名用户请求 enrolled_only 资源，When GET 该课次视频，Then 403（前端 ErrorState「需报名」）。

**实现**：session 详情与 complete 端点均对 `enrolled_only/internal_only` 视频做访问守卫——未报名返回 `403 40330`（service.py 详情:169、complete:144）。`access` 端点返回 `accessible=false` 供前端守卫。

**实测**：`test_non_enrolled_403_detail` PASS——未报名用户 GET enrolled_only 课次详情 → **403 / code 40330**；已报名 → 200。

### GWT② 15s 打点落库 + 外键 play_session_id + 提交表外键
> Given 学习 15s 打点提交（tick-batch），Then play_event 落库且外键 play_session_id 语义正确；作业/考试提交写 submission 表且恢复 edu.sql 外键。

**实测（scripts/_verify_task21_study.py，DB 证据）**：
```
[外键] play_event 列名 = [created_at, event_payload, event_time, event_type, id,
        network_type, play_session_id, playback_rate, position_seconds]  ← 无 user_id/session_id，仅 play_session_id FK
[打点] record_video_ticks 返回 inserted=2
[打点] 最新 play_event rows (play_session_id=1): [(1865571,1,'TICK',20), (1865570,1,'PLAY',5)]
[打点] watched_seconds: 4349 -> 4364（期望 +15 左右）
[作业] submit_homework 成功，submission homework_id=15（FK 指向 session_homework）
[考试] submit_exam 成功，submission exam_id=15445（FK 指向 session_exam）
  GWT② 打点落库 + play_session_id 外键语义 + 作业/考试提交外键 [OK]
```
- play_event 确无 `user_id/session_id` 列，`play_session_id` FK 关联 session_video_play（外键语义正确）
- 打点经 progress.service.record_video_ticks 落库全国 + watched_seconds 增量；数据已清理回收

### GWT③ 课次含 session_asset 按 material_category + access_scope 过滤返回
> Given 课次含 session_asset（video/handout/exercise/reference/image），When 请求课次详情，Then 按 material_category + access_scope 正确过滤返回。

**实测**：`test_assets_filtered_by_scope` PASS——assets 不含 `internal_only`；`material_category ∈ {video,handout,exercise,reference,image}`。
**修复**：未报名用户在 outline 中折叠 enrolled_only/internal_only 课次（避免元数据越权可见）。

### GWT④ 视频 transcode_status 与 task12 管线一致
> Given 视频 transcode_status，When 查询，Then pending/in_progress/completed/failed 状态与 task12 转码管线一致。

**实测**：`test_transcode_status_valid` PASS——`transcode_status ∈ {pending,in_progress,completed,failed}`；**非 completed 不返回可播 url**（video_url=None），completed 才给 url。与 task12 转码管线枚举一致。

---

## 契约测试结果
| 套件 | 结果 |
|------|------|
| `tests/test_contract_task21.py`（in-process ASGI） | **8/8 通过** |
| `tests/test_contract_task20.py`（回归） | **7/7 通过** |
| GWT② 打点/外键 DB 证据 | 全通过 |
| 语法诊断（GetDiagnostics） | learning 全域 + main + tests + scripts 均 0 错误 |

> ⚠️ 环境：外部存储机（192.168.85.101）不可用，uvicorn 起服挂；task21 测试改 **in-process httpx ASGITransport**（不跑 lifespan）。

## 资金/安全红线（独立子代理 review）
| 红线 | 结论 |
|------|------|
| R1 access_scope 鉴权矩阵 | ✅ 通过（enrolled_only 需 active；internal_only C 端不可见；未报名 403） |
| R2 列对照（session_asset/session_video/chapter/play/submission） | ✅ 通过（无坏列） |
| R3 资源过滤（internal_only 不出现在 C 端） | ✅ 通过 |
| R4 transcode（非 completed 不给 url） | ✅ 通过 |
| R5 进度/完成率真实（play.pos/duration、submission=submitted，无 MOCK） | ✅ 通过 |
| complete 不越权写他人 | ✅ 通过 |

**审查修复项**：403 错误码 docstring 40320→40330 纠正；删除死代码（_VISIBLE_SCOPES/_TRANSCODE_ORDER）；outline 折叠 enrolled_only/internal_only 元数据（未报名不可见）；complete 端点补访问守卫。

## 验证命令
```bash
.venv\Scripts\python -m pytest tests/test_contract_task21.py -v
.venv\Scripts\python scripts\_verify_task21_study.py
```

## 关键经验留痕
- **session_video_play_event 无 user_id/session_id 列**（仅 play_session_id FK，task 指导明确）；打点落库依赖 play_session_id 语义正确。
- **access_scope 鉴权矩阵**：enrolled_only 需 student_cohort_rel.active；internal_only C 端不可见。
- 测试 in-process ASGI（外部存储机不可用，起服挂）；打点/作业/考试提交写明 FK 语义并清理回收测试数据。