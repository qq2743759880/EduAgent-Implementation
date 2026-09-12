# 契约审查包 reshape-a(草案 draft:true → 你逐条审后冻结)

> 审查方法:按你的真实业务场景走一遍,每行标 **同意/修改(写明场景)**。契约权威 = `edu-agent/app/schemas.py` + `error_codes.py` + 实测 curl;本包只列审查要点,不复制全文。冻结后执行期禁改,变更走变更单+重验收。
> 实测标记:✅=真实 HTTP 实测过(第一批+今日) / 🔎=今日只读探活过 / ✍️=写操作(未实际执行,审查重点)

## 0. 全局壳(最高优先级,错一处全盘错)
| 项 | 契约 | 实测 |
|---|---|---|
| 响应壳 | `{code:0, message:"ok", data:...}`;失败同形(code≠0 的字符串业务码) | ✅ |
| 分页壳 | 裸 DTO `{total, page, page_size, items}`(不再包一层 data 外壳) | ✅ |
| 登录 | `POST /api/auth/login` body=`{account, password}`(**不是 username**)→ `{access_token, refresh_token, token_type:"Bearer", expires_in, user:{user_id, account, role,...}}` | ✅ |
| 401 语义 | 过期/无效 → HTTP 401;前端单飞 refresh 后重放一次,再失败跳登录 | ✅ |
| 业务错误码 | `error_codes.py` 权威。演示线高频:40000 参数/42200 校验/40101 凭证/40300 越权/40400 不存在/40901~40907 唯一冲突(系列~视频)/50300 Milvus 不可达/50000 内部 | ✅(40903/40904 冲突实测过) |

## 1. 学生线
| # | 端点 | 要点(入参→出参) | 标记 |
|---|---|---|---|
| 1.1 | `POST /api/auth/register` | 注册(字段见 schemas);成功后需再登录 | ✍️ |
| 1.2 | `GET /api/series` | 筛选:学科/交付/价格/排序/关键词/分页 → 分页壳 items[系列卡] | 🔎 |
| 1.3 | `GET /api/series/{id}` | 系列详情 + 班次列表 | 🔎 |
| 1.4 | `GET /api/coupons` | 可领券列表,分页壳 | 🔎 |
| 1.5 | `POST /api/trade/coupon/receive` | 领券;重复领取→业务码提示 | ✍️ |
| 1.6 | 下单 | `POST /api/orders`(携带 cohort_id+coupon_receive_record_id)——**今日未探活,task01 补验后才接前端** | ✍️⚠ |
| 1.7 | `GET /api/enrollments/me/cohorts` | 我的班次(my-cohorts/learning 入口) | 🔎 |
| 1.8 | `GET /api/study/courses/{id}`、`GET /api/study/sessions/{id}` | 学习页课次/资源(learning) | 🔎(经 my-cohorts 跳转路径待联调) |
| 1.9 | `GET /api/progress/dashboard`、`GET /api/users/me/learning-summary` | 仪表盘两数据源 | 🔎 |
| 1.10 | `POST /api/chat/sessions`、`GET /api/chat/sessions`、`GET /api/chat/sessions/{id}`、`DELETE` | 会话 CRUD | 🔎 |
| 1.11 | `POST /api/chat/stream` | SSE!body=`{query, session_id, stream:true}`(字段是 query);事件 `start/retrieval/token/done/error`,token 累加 `j.delta` | ✅(历史实测) |
| 1.12 | `GET /api/community/posts`、`POST /api/community/posts`、`POST /api/community/posts/{id}/comments`(路径以联调为准)、评论/反应 | 分页壳一致;aria-pressed 反应 | 🔎/✍️ |
| 1.13 | `GET /api/gamification/me/badges|points`、`GET /api/gamification/rankings` | 成就三件套 | 🔎 |
| 1.14 | `GET /api/favorites`、`POST /api/courses/{id}/favorite`(取消同路径,以联调为准) | 收藏 | 🔎/✍️ |
| 1.15 | `GET /api/vocab/daily|progress`、`POST /api/vocab/recall`、`GET /api/interactive/quiz/*`、`POST /api/interactive/quiz/submit` | 练习域(practice 页,清单外只保不翻车) | 🔎/✍️ |
| 1.16 | `GET /api/users/me/profile`、`PUT /api/users/me/profile` | 个人资料读写 | 🔎/✍️ |

## 2. 管理线
| # | 端点 | 要点 | 标记 |
|---|---|---|---|
| 2.1 | `GET /api/auth/me` | 守卫第二段;role∈{admin,manager} 放行 | 🔎 |
| 2.2 | `GET /api/admin/users/dashboard/metrics` | 管理仪表盘 KPI(角色统计 715ms 慢查询已发现——审查项:演示可接受否?) | 🔎 |
| 2.3 | `GET /api/admin/users`、启停/详情(PATCH,路径联调定) | 用户管理(admin-users 页从纯原型接线,重灾区) | 🔎/✍️ |
| 2.4 | `GET /api/admin/questions/types`、`GET/PATCH/DELETE /api/admin/questions/questions/{id}`、`POST questions`、`POST banks`、`POST import-preview|import-execu​te` | 题库全链;分页壳一致 | 🔎/✍️ |
| 2.5 | 四级 CRUD(系列/班次/模块/课次)GET/POST/PATCH/DELETE 全套 | 软删 yn=0;冲突码 40901-40904;创建班次必填 head_teacher_id+institution_id(隐含系列);模块必填 stage_no/lesson_count/total_hours/起止日期;课次必填 session_no/title/teaching_date | ✅ |
| 2.6 | 系列回收站 `POST /api/admin/courses/series/{id}/restore` | 仅 off_sale 态可恢复 | ✅(契约测试) |
| 2.7 | 视频四件套 init/upload-chunk(PUT octet-stream)/finalize/bind + transcode-status | 上传会话 manifest 落盘重启安全;finalize 需登录身份(FK);白名单 mp4/mov/m4v/webm/mkv;≤10000 分片 | ✅(全链路 30000B 实测) |
| 2.8 | 章节 CRUD `GET/POST /api/admin/courses/chapters`、`PATCH/DELETE /chapters/{id}` | start_second<end_second 校验;DELETE 物理删 | ✅ |
| 2.9 | `GET /api/admin/courses/sessions/{id}/assets` | 课次资源(视频面板数据源;video 附带 session_video 记录) | ✅ |
| 2.10 | MCP 全套( servers CRUD/health/discover/health-scan/tools/tools-test/call-log ) | RBAC=仅 admin;health-scan 同步全量慢(EAPI.TIMEOUT_MS=120s) | ✅ |
| 2.11 | RAG: `POST /api/knowledge/admin/upload`(FormData 多文件)、`GET /api/knowledge/tasks`、`GET/DELETE /api/knowledge/partitions`、`GET /api/admin/rag/collections` | 白名单 md/txt/markdown/pdf/docx;≤200MB×50;_default 禁删;**依赖 Milvus 虚拟机开机(50300 降级提示)** | ✅ |

## 3. 审查决议所需的关键决策点(请逐条表态)
1. **下单链路(1.6)**:演示要不要走真实扣款/订单?现有库有订单/支付态数据,但「领取→下单→我的订单」我尚未实测——按"缺契约停下上报"规矩,task01 先补验再冻,你接受?
2. **管理仪表盘慢查询(2.2)**:metrics 715ms(角色统计 JOIN)。演示口径可接受?可接受→照常接;不可接受→登记 B 阶段优化,A 阶段加 loading 态。
3. **登录注册(1.1)**:注册成功后自动登录 or 跳登录页?现页面是二合一,建议注册成功→自动写入 token 跳 dashboard(体验顺)。你定。
4. **community 评论/反应 与 favorites 收藏 的写路径**:页面注释与后端路由存在命名漂移风险(教训 8),task01 以 curl 实测为准回填本表,漂移处走变更单。你接受这个处理顺序吗?
5. **✍️ 写端点的实测纪律**:所有 POST/PATCH/DELETE 在前端接线前于测试库实际执行过一遍(造真数据→验证→清理),你之前裁定过"接口验收须独立实证"——写操作也按此执行,确认?

> 逐条回复方式:全局壳+两域表格默认**按上表冻结**,异议行指出;第 3 节 5 个决策点必须逐条给结论(如 `1 接受 2 可接受 3 自动登录 4 接受 5 确认`)。全部收齐 → 冻结 `contracts/reshape-a.json`(hash 上看板)→ 开始批次派单。
