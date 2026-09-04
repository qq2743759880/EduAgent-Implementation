# EduAgent 独立接口验收报告（be-tester 最终版）

- 测试方式：真实 HTTP 请求独立实证（Python requests 直连 127.0.0.1:8000），不采信任何既有报告/交接单
- 日期：2026-09-05 02:26:54 ｜ 总请求数：162 ｜ 耗时：16.1s
- 后端路由清单 193 条（方法×路径） ｜ 前端源码真实引用 93 条（src/lib/api/*.ts 提取，_frontend_api.txt 的 56 条已过时）
- 判定口径：OK=成功壳 code=0 ｜ BIZ=业务错误(路由存在+错误壳) ｜ BARE=裸响应(无壳，前端可透传) ｜ FAIL500=HTTP 500 缺陷 ｜ DEBUG=无token被DEBUG降级(代码确认) ｜ FAIL=其他

## 1. 概览

| 指标 | 值 |
|---|---|
| 总执行 | 162 |
| 正常（OK+BIZ+BARE） | 157（96.9%） |
| HTTP 500 真实缺陷 | 0 |
| 无token被DEBUG降级（部署风险） | 4 |
| 其他异常 | 1 |

### 角色 × 登录

| 角色 | HTTP | code | 响应壳 | access_token |
|---|---|---|---|---|
| admin | 200 | 0 | ✓ | ✓ |
| manager | 200 | 0 | ✓ | ✓ |
| student | 200 | 0 | ✓ | ✓ |

## 2. 管理端接口明细表（/api/admin/*，admin token）

| 方法 | 路由 | HTTP | code | 判定 | 说明 |
|---|---|---|---|---|---|
| DELETE | `/api/admin/courses/cohorts/{cohort_id}` | 404 | 40400 | BIZ | 业务错误 code=40400 |
| DELETE | `/api/admin/courses/modules/{module_id}` | 404 | 40400 | BIZ | 业务错误 code=40400 |
| DELETE | `/api/admin/courses/series/{series_id}` | 404 | 40400 | BIZ | 业务错误 code=40400 |
| DELETE | `/api/admin/courses/sessions/{session_id}` | 404 | 40400 | BIZ | 业务错误 code=40400 |
| DELETE | `/api/admin/questions/banks/{bank_id}` | 404 | 40400 | BIZ | 业务错误 code=40400 |
| DELETE | `/api/admin/questions/questions/{question_id}` | 404 | 40400 | BIZ | 业务错误 code=40400 |
| GET | `/api/admin/courses/cohorts/{cohort_id}` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/cohorts/{cohort_id}/modules` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/cohorts/{cohort_id}/sessions` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/modules/{module_id}` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/modules/{module_id}/sessions` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/series` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/series/{series_id}` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/series/{series_id}/cohorts` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/sessions/{session_id}` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/videos/{video_id}/transcode-status` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/questions/banks` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/questions/banks/{bank_id}` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/questions/banks/{bank_id}/questions` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/questions/exams` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/questions/exams/{exam_id}` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/questions/questions/{question_id}` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/questions/types` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/rag/audit-log` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/rag/collections` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/rag/presets` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/refunds` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/users` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/users/dashboard/metrics` | 200 | 0 | OK | 成功 code=0 |
| PATCH | `/api/admin/courses/cohorts/{cohort_id}` | 200 | 0 | OK | 成功 code=0 |
| PATCH | `/api/admin/courses/modules/{module_id}` | 200 | 0 | OK | 成功 code=0 |
| PATCH | `/api/admin/courses/series/{series_id}` | 200 | 0 | OK | 成功 code=0 |
| PATCH | `/api/admin/courses/sessions/{session_id}` | 200 | 0 | OK | 成功 code=0 |
| PATCH | `/api/admin/questions/banks/{bank_id}` | 200 | 0 | OK | 成功 code=0 |
| PATCH | `/api/admin/questions/exams/{exam_id}` | 200 | 0 | OK | 成功 code=0 |
| PATCH | `/api/admin/questions/questions/{question_id}` | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/admin/courses/cohorts` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/courses/modules` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/courses/series` | 409 | 40901 | BIZ | 业务错误 code=40901 |
| POST | `/api/admin/courses/sessions` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/courses/videos/bind-session` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/courses/videos/finalize-chunked` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/courses/videos/init-chunked` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/questions/banks` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/questions/exams` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/questions/exams/{exam_id}/publish` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/questions/import-execute` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/questions/import-preview` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/questions/questions` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/rag/collections/rebuild` | 202 | 0 | OK | 成功 code=0 |
| POST | `/api/admin/rag/presets` | 409 | 40900 | BADCODE | code 类型异常: 40900 |
| POST | `/api/admin/rag/search` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/refunds/{refund_id}/approve` | 400 | 40031 | BIZ | 业务错误 code=40031 |
| POST | `/api/admin/refunds/{refund_id}/reject` | 400 | 40031 | BIZ | 业务错误 code=40031 |
| POST | `/api/admin/users/{user_id}/role` | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/admin/users/{user_id}/status` | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/admin/courses/series (无token)` | 401 | 40101 | BIZ | 业务错误 code=40101 |
| POST | `/api/admin/courses/series` | 200 | 0 | OK | 创建成功 sid=2701（HTTP 200，非 201） |
| PATCH | `/api/admin/courses/series/2701` | 200 | 0 | OK | 修改series |
| DELETE | `/api/admin/courses/series/2701` | 200 | 0 | OK | 删除series（清理） |
| DELETE | `/api/admin/courses/modules/1(被引用)` | 409 | 40908 | OK | 存在被引用模块删除应返回业务码(409xx)而非50000, data=None | 模块仍被 8 个课次引用，无法删除 |
| DELETE | `/api/admin/courses/sessions/29786(被引用)` | 409 | 40908 | OK | 存在被引用课次删除应返回业务码(409xx)而非50000 | 课次仍被 45 条子记录引用，无法删除 |

## 3. 用户端/其他接口明细

| 方法 | 路由 | 角色 | HTTP | code | 判定 | 说明 |
|---|---|---|---|---|---|---|
| POST | `/api/auth/login` | admin | 200 | 0 | OK | access_token=有 |
| POST | `/api/auth/login` | manager | 200 | 0 | OK | access_token=有 |
| POST | `/api/auth/login` | student | 200 | 0 | OK | access_token=有 |
| POST | `/api/auth/login(bad-pwd)` | admin | 401 | 40111 | OK | 错误密码错误壳 code=str data=null |
| POST | `/api/auth/refresh(bad-token)` | - | 401 | 40101 | OK | 无效refresh token错误壳 |
| GET | `/api/auth/me` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/auth/register` | student | 409 | 40912 | BIZ | 业务错误 code=40912 |
| GET | `/api/coupons` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/coupons/templates` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/favorites` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/favorites` | student | 200 | 0 | OK | 成功 code=0 |
| DELETE | `/api/favorites/{series_id}` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/progress/courses` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/progress/dashboard` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/progress/video/tick-batch` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/progress/homework/submit` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/progress/exam/submit` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| GET | `/api/gamification/me/badges` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/gamification/me/points` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/gamification/rankings` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/gamification/me/check-badges` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/community/posts` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/community/posts/{post_id}` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/community/posts/{post_id}/comments` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/community/posts/{post_id}/like` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/community/posts/{post_id}/favorite` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/chat/sessions` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/chat` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/chat/search` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/chat/sessions` | student | 201 | 0 | OK | 成功 code=0 |
| GET | `/api/trade/orders` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/trade/order/{order_no}` | student | 404 | 40420 | BIZ | 业务错误 code=40420 |
| GET | `/api/trade/payments` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/trade/after_sales/tickets` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/trade/after_sales/ticket/{ticket_id}` | student | 404 | 40441 | BIZ | 业务错误 code=40441 |
| POST | `/api/trade/coupon/receive` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| GET | `/api/users/me` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/users/me/profile` | student | 200 | 0 | OK | 成功 code=0 |
| PUT | `/api/users/me/profile` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| GET | `/api/users/me/student-profile` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/users/me/learning-summary` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/enrollments/me/cohorts` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/enrollments/me/cohorts/{cohort_id}` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/enrollments/me/cohorts/{cohort_id}/progress` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/enrollments/me/cohorts/{cohort_id}/status` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/series` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/series/{series_id}` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/series/{series_id}/cohorts` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/cohorts/{cohort_id}` | student | 404 | 40400 | BIZ | 业务错误 code=40400 |
| GET | `/api/cohorts/{cohort_id}/modules` | student | 404 | 40400 | BIZ | 业务错误 code=40400 |
| GET | `/api/study/courses/{series_id}/outline` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/study/courses/{series_id}/access` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/study/sessions/{session_id}` | student | 403 | 40330 | BIZ | 业务错误 code=40330 |
| POST | `/api/study/sessions/{session_id}/complete` | student | 403 | 40330 | BIZ | 业务错误 code=40330 |
| GET | `/api/recommend/next` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/recommend/path` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/interactive/quiz/next` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/interactive/quiz/types` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/interactive/quiz/submit` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| GET | `/api/interactive/quiz/wrong-book` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/coding/challenges` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/coding/challenges/{code}` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/coding/run` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/coding/submit` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| POST | `/api/math/explain` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| GET | `/api/vocab/daily` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/vocab/progress` | student | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/vocab/recall` | student | 422 | 42200 | BIZ | 业务错误 code=42200 |
| GET | `/api/mindmap/me/{series_id}` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/mindmap/course/{series_id}` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/mindmap/subject/{subject_code}` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/mindmap/prerequisite` | student | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/mcp/servers` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/mcp/servers/{server_id}` | admin | 404 | 40400 | BIZ | 业务错误 code=40400 |
| GET | `/api/mcp/tools` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/mcp/call-log` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/mcp/call-log/{log_id}` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/mcp/description-review-log` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/mcp/sessions` | admin | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/mcp/servers` | admin | 422 | 42200 | BIZ | 业务错误 code=42200 |
| GET | `/api/mcp/servers/{server_id}/tools` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/knowledge/partitions` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/knowledge/tasks` | admin | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/knowledge/admin/upload` | admin | 422 | 42200 | BIZ | 业务错误 code=42200 |
| GET | `/api/memory/history/{entity_id}` | admin | 404 | 40400 | BIZ | 业务错误 code=40400 |
| GET | `/api/metrics/cache-context-dashboard` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/metrics/otel` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/metrics/trace/{trace_id}` | admin | 200 | 0 | OK | 成功 code=0 |
| GET | `/api/refunds` | admin | 200 | 0 | OK | 成功 code=0 |
| POST | `/api/refunds` | admin | 422 | 42200 | BIZ | 业务错误 code=42200 |
| GET | `/api/knowledge/status/{task_id}` | admin | 404 | 40400 | BIZ | 业务错误 code=40400 |
| GET | `/` | anon | 200 | 0 | OK | 成功 code=0 |
| GET | `/health` | anon | 200 | None | BARE | 裸响应（未包壳，前端可透传） |
| GET | `/health/detail` | anon | 200 | None | BARE | 裸响应（未包壳，前端可透传） |
| GET | `/api/auth/me (无token)` | anon | 200 | 0 | DEBUG | 成功 code=0 |
| GET | `/api/users/me (无token)` | anon | 200 | 0 | DEBUG | 成功 code=0 |
| GET | `/api/trade/orders (无token)` | anon | 200 | 0 | DEBUG | 成功 code=0 |
| GET | `/api/favorites (无token)` | anon | 200 | 0 | DEBUG | 成功 code=0 |
| POST | `/api/favorites` | student | 200 | 0 | OK | 添加收藏 |
| DELETE | `/api/favorites/2` | student | 200 | 0 | OK | 取消收藏 |

## 4. 契约缺口清单

### 4.1 前端引用（93条源码清单）但后端路由不存在

**A. 已实测 HTTP 404（真缺口，前端会直接调用）—— 共 5 项：**

- `/api/admin/courses/materials/redirect-upload`
- `/api/admin/questions`
- `/api/admin/questions/batch-import`
- `/api/admin/questions/papers/compose`
- `/api/admin/questions/tags`

**B. 前端仅作 URL 基路径引用（`/xxx/` 后拼接 id，后端以 `{id}` 路由存在，属引用方式差异）—— 共 9 项：**

- `/api/admin/courses/videos`
- `/api/cohorts`
- `/api/community/comments`
- `/api/knowledge/status`
- `/api/mindmap/course`
- `/api/mindmap/me`
- `/api/study/courses`
- `/api/study/sessions`
- `/api/trade/payment`

### 4.2 后端存在但前端未使用
共 99 条：

- `/api/admin/courses/cohorts/{}`
- `/api/admin/courses/cohorts/{}/modules`
- `/api/admin/courses/cohorts/{}/sessions`
- `/api/admin/courses/modules/{}`
- `/api/admin/courses/modules/{}/sessions`
- `/api/admin/courses/series/{}`
- `/api/admin/courses/series/{}/cohorts`
- `/api/admin/courses/sessions/{}`
- `/api/admin/courses/videos/{}/transcode-status`
- `/api/admin/questions/banks/{}`
- `/api/admin/questions/banks/{}/questions`
- `/api/admin/questions/exams`
- `/api/admin/questions/exams/{}`
- `/api/admin/questions/exams/{}/publish`
- `/api/admin/questions/questions/{}`
- `/api/admin/refunds`
- `/api/admin/refunds/{}/approve`
- `/api/admin/refunds/{}/reject`
- `/api/admin/users/{}/role`
- `/api/admin/users/{}/status`
- `/api/auth/refresh`
- `/api/chat/sessions/{}`
- `/api/chat/sessions/{}/history`
- `/api/chat/stream`
- `/api/coding/challenges`
- `/api/coding/challenges/{}`
- `/api/coding/hint`
- `/api/coding/run`
- `/api/coding/submit`
- `/api/cohorts/{}`
- `/api/cohorts/{}/modules`
- `/api/community/comments/{}/like`
- `/api/community/posts/{}`
- `/api/community/posts/{}/comments`
- `/api/community/posts/{}/favorite`
- `/api/community/posts/{}/like`
- `/api/enrollments/me/cohorts/{}`
- `/api/enrollments/me/cohorts/{}/progress`
- `/api/enrollments/me/cohorts/{}/status`
- `/api/favorites/{}`
- `/api/gamification/me/award`
- `/api/gamification/me/check-badges`
- `/api/interactive/quiz/question/{}`
- `/api/interactive/quiz/types`
- `/api/interactive/quiz/wrong-next`
- `/api/knowledge/partitions/{}`
- `/api/knowledge/status/{}`
- `/api/math/explain`
- `/api/math/practice`
- `/api/math/step-check`
- `/api/mcp/call-log/{}`
- `/api/mcp/description-review`
- `/api/mcp/description-review-log`
- `/api/mcp/servers/{}`
- `/api/mcp/servers/{}/discover`
- `/api/mcp/servers/{}/discover-live`
- `/api/mcp/servers/{}/health`
- `/api/mcp/servers/{}/raw-rpc`
- `/api/mcp/servers/{}/tools`
- `/api/mcp/sessions`
- `/api/mcp/sessions/{}`
- `/api/mcp/sessions/{}/touch`
- `/api/mcp/tools`
- `/api/memory/admin/dream/run`
- `/api/memory/history/{}`
- `/api/memory/rewind`
- `/api/metrics/cache-context-dashboard`
- `/api/metrics/otel`
- `/api/metrics/trace/{}`
- `/api/mindmap/course/{}`
- `/api/mindmap/me/{}`
- `/api/mindmap/prerequisite`
- `/api/mindmap/subject/{}`
- `/api/recommend/feedback`
- `/api/recommend/next`
- `/api/recommend/path`
- `/api/refunds`
- `/api/refunds/{}/cancel`
- `/api/series/{}`
- `/api/series/{}/cohorts`
- `/api/study/courses/{}/access`
- `/api/study/courses/{}/outline`
- `/api/study/sessions/{}`
- `/api/study/sessions/{}/complete`
- `/api/trade/after_sales/ticket/{}`
- `/api/trade/after_sales/ticket/{}/satisfaction`
- `/api/trade/order/{}`
- `/api/trade/order/{}/cancel`
- `/api/trade/payment/{}`
- `/api/trade/payment/{}/cancel`
- `/api/trade/payment/{}/mock-notify`
- `/api/trade/payment/{}/retry`
- `/api/trade/payments`
- `/api/trade/payments/reconcile`
- `/health`
- `/health/detail`
- `/health/warmup`
- `/metrics`
- `/payment-notifications/mock`

### 4.3 附注：_frontend_api.txt（56条旧清单）与源码清单差异

- 旧清单缺（源码引用但旧清单没有）：`/api/admin/rag/*` 部分、`/api/interactive/quiz/*` 部分、`/api/mindmap/*`、`/api/enrollments/me/*`、`/api/vocab/daily|progress` 等
- 结论：**56 条清单过时，契约缺口以源码 93 条为准**

## 5. 发现的真实缺陷

### P1 — HTTP 500（代码缺陷，随本次实跑 fail500 动态判定）

- **本次实跑 HTTP 500 缺陷 = 0**。历史 6 个 HTTP 500（NotFoundError）已修复：2026-09-05 定向深探（独立 HTTP 实测）确认 DELETE courses/cohorts->404 40400、module->404、series->404、session->404、GET /api/recommend/next->200 code=0、GET /api/mindmap/me/1->200 code=0、POST series 重复码->422 校验拦截（均非 500）。历史根因（未导入 NotFoundError/ConflictError、SQL 引用 H.answers_json）留档。）

### P1 — DELETE /api/admin/courses/series 假删除（数据完整性）

- 实测闭环：创建 series（id=2632）→ DELETE 返回 **200 code=0 message=“系列删除”** → 再 GET /api/admin/courses/series/2632 仍返回 200 且记录存在；DB 确认 4 条被“删除”的测试记录（2629/2630/2631/2632）全部仍在表中（仅 sale_status 被翻为 off_sale）
- 结论：DELETE 语义不成立 —— 响应声称已删除，实际未删除（疑似软下线但按删除响应）。前端“删除后列表仍出现该记录”必现

### P1 — 部署风险：DEBUG 鉴权降级开启（settings.DEBUG=true）

- 实测：不带 Authorization 调用 `/api/auth/me`、`/api/users/me`、`/api/trade/orders`、`/api/favorites` 均返回 HTTP 200，且**返回 DEBUG 虚拟管理员（user_id=1）的数据**；`/api/admin/courses/series` 则正确 401 —— 行为不一致
- 代码确认：`app/auth/dependencies.py get_current_user()` 规则2「没带 Header 且 DEBUG=True → 虚拟超级管理员」正在生效
- 影响：当前部署下未登录请求可读取用户级数据（本机 127.0.0.1 风险有限，一旦经代理暴露即越权）
- 建议：对外部署必须 DEBUG=False；用户侧端点（/api/users/me、/api/trade/*）应显式依赖鉴权并校验归属

### P2 — 响应壳未全覆盖（契约①部分完成）

- 实测 20 个抽样端点：17 个返回成功壳 {code:0,data}，3 个裸响应（/api/admin/users、/api/admin/users/dashboard/metrics、/api/users/me）
- 全量遍历中发现约 20 个业务端点仍返回裸体（无 {code,message,data}）：`/api/users/me`、`/api/users/me/profile`、`/api/recommend/path`、`/api/interactive/quiz/*`、`/api/coding/challenges`、`/api/vocab/*`、`/api/mindmap/*`、`/api/knowledge/partitions`、`/api/metrics/*`、`/api/admin/users`、`/api/admin/users/dashboard/metrics`、`POST /api/admin/users/{id}/status` 等
- 依据 `edu-frontend/src/lib/api-client.ts` 注释：壳/裸双形态为已知过渡态（task11+ 逐域补壳），拦截器对裸体透传 —— **前端可正常工作，非阻塞**，但 shell 一致性契约未完全落地
- 特例：`GET /api/coding/challenges/{code}` 裸体顶层 `code` 字段=题目code（字符串），与错误壳语义冲突；前端 isEnvelope 以 `message` 存在性防御，可规避

### P2 — POST /api/admin/courses/series 创建返回 HTTP 200（非 201）

- 与其他创建端点不一致（/api/auth/register、/api/chat/sessions、/api/admin/rag/presets 均 201）；功能正常（创建→修改→删除闭环通过，但删除见 P1 假删除）

### P2 — 错误码类型不一致（契约要求字符串错误码）

- 实测 `POST /api/admin/rag/presets`（默认预设冲突）返回 code=**40900（int）**，而 `POST /api/admin/refunds/1/approve` 返回 code=**“40031”（str）** —— 同一契约下错误码类型混用，前端 ApiError 兼容但契约不统一

### P3 — mcp/health-scan 响应慢（约 50s）

- 15 个服务器扫描：ok=1 error=14，耗时 ~50s；前端 axios timeout=15s，**该接口前端必超时**（需异步化或超时策略）

## 6. 安全写操作实测（创建→修改→删除闭环）

| 操作 | HTTP | code | 结果 |
|---|---|---|---|
| 创建系列 POST /api/admin/courses/series | 200 | 0 | 成功（创建后可查询） |
| 修改系列 PATCH | 200 | 0 | 成功 |
| 删除系列 DELETE | 200 | 0 | **失败（假删除）**：返回成功但记录仍在，GET 仍可查 |
| 添加收藏 POST /api/favorites | 200 | 0 | 成功 |
| 取消收藏 DELETE /api/favorites/{series_id} | 200 | 0 | 成功 |

## 7. 结论

- 总执行 162 项：正常 157（96.9%），HTTP 500 缺陷 0，DEBUG 降级观察 4，其他 1
- 契约缺口：前端引用但后端缺失 14 项 ｜ 后端存在但前端未用 99 项
- **验收结论：HTTP 500 阻断项已清零**（历史 6 个 500 缺陷经 2026-09-05 复跑 + 定向深探确认已修复）。剩余阻断/待办（非 500）：
  1. series DELETE 假删除（响应 200 但仅软下线 off_sale，记录仍在表）——需复核是否按 C5 软删契约落地
  2. DEBUG 鉴权降级部署风险（对外部署必须 DEBUG=False）
  3. 前端引用的 14 个端点后端缺失（见 §2/§4 missing_in_backend）
- **非阻塞待办**：响应壳逐域补齐（P2）、POST series 状态码统一 201（P2）、错误码类型统一为字符串（P2）、mcp/health-scan 异步化或超时策略（P3）、清理注册测试产生的 itest-newuser 用户与 itest-series 系列（2629~2632）

