# EduAgent 前后端并行开发协调文档

> 创建时间：2026-08-16
> 后端开发：Trae（AI Agent）
> 前端开发：用户（TraeWork）
> 更新规则：每次接口变更或开发进展更新后，双方同步修改本文档

---

## 一、接口契约（API Contract）

### 1.1 响应壳规范

```json
// 成功
{"code": 0, "message": "ok", "data": { ... }}

// 失败
{"code": "AUTH_EXPIRED", "message": "登录已过期", "data": null}
```

- 前端 `api-client.ts` 拦截器自动解包 `data` 字段
- code 类型：`string | number`（兼容历史数字码）
- SSE 流式端点 `done`/`error` 事件内嵌统一壳

### 1.2 当前可用接口

| 方法 | 路径 | 用途 | 状态 |
|------|------|------|------|
| POST | `/api/auth/login` | 登录 | ✅ |
| POST | `/api/auth/register` | 注册 | ✅ |
| GET | `/api/auth/me` | 当前用户信息 | ✅ |
| GET | `/api/curriculum/series` | 课程列表 | ⚠️ 待迁移到 /api/series |
| POST | `/api/chat` | AI 问答（非流式） | ✅ |
| POST | `/api/chat/stream` | AI 问答（SSE 流式） | ✅ |
| GET | `/api/progress/dashboard` | 学习仪表盘 | ✅ |
| GET | `/api/gamification/ranking` | 排行榜 | ✅ |
| GET | `/api/admin/users` | 管理端用户列表 | ✅ |
| GET | `/api/admin/courses` | 管理端课程 | ⚠️ 待重构 |
| GET | `/api/admin/questions` | 管理端题库 | ⚠️ 待重构 |

### 1.3 待开发的接口（task 对应）

| 阶段 | 接口 | 预计完成 |
|------|------|---------|
| task11 | GET/POST `/api/series` | Phase C |
| task11 | GET `/api/series/{id}/cohorts` | Phase C |
| task17 | POST `/api/orders` | Phase D |
| task18 | POST `/api/payments` | Phase D |
| task20 | GET `/api/enrollments/me/cohorts` | Phase D |

---

## 二、数据模型约定

### 2.1 字段命名

- 后端：全部 `snake_case`（`series_name`, `cohort_id`, `sale_price`）
- 前端：TypeScript 类型定义使用 `snake_case`，删除全部别名兜底
- **禁止**：`series_title` / `seriesName` / `fallbackPrice` 等旧字段名

### 2.2 核心数据模型

```
series（课程系列）
├── series_cohort（班次）
│   └── series_cohort_course（班次模块）
│       └── series_cohort_session（课次）
│           ├── session_asset（资源：视频/课件/作业/考试）
│           ├── session_video（视频 + 转码状态）
│           └── session_video_chapter（视频章节）
├── coupon（优惠券）
├── order（订单）→ order_item
│   └── payment_record（支付记录）
└── service_ticket（工单）
```

---

## 三、开发进度同步

### 3.1 当前进度

| 阶段 | 任务 | 后端状态 | 前端状态 |
|------|------|---------|---------|
| Phase A | task00 备份 | ⬜ 待执行 | N/A |
| Phase B | task01~05 数据库 | ⬜ 待执行 | N/A |
| Phase C | task09~15 后端底座 | ⬜ 待执行 | N/A |
| Phase D | task16~23 业务域 | ⬜ 待执行 | N/A |
| Phase E | task24~32 AI/RAG | ⬜ 待执行 | N/A |

### 3.2 更新规则

1. 后端每完成一个 task，在此文档更新状态
2. 接口有任何变更（路径/参数/响应格式），**立即**更新本文档 §一
3. 前端开始开发某一页面前，**必须先确认**对应后端接口已就绪
4. 双方每天结束时同步一次进度

---

## 四、接口变更通知模板

当后端修改接口时，在本文档末尾追加：

```markdown
### 变更 2026-08-XX

**修改接口**：POST /api/xxx
**变更内容**：请求体新增字段 `xxx`（必填，string）
**影响前端**：/pages/xxx 页面需要传入新字段
**迁移方案**：前端在调用处添加 `xxx: "default_value"`
```

---

## 五、前后端并行策略

```
后端 task（Trae）              前端 task（TraeWork）
─────────────────────        ─────────────────────
task11 课程域接口就绪  ────→  task38 /courses 页面
task16~17 交易域就绪   ────→  task41~43 优惠券/订单/支付
task20 报名域就绪      ────→  task40 我的班次
task21 学习域就绪      ────→  task52 学习页
task22 售后域就绪      ────→  task46 工单页
```

**关键原则**：前端不等待后端全部完成，而是**后端每完成一个域，前端立即启动对应页面**。

---

## 六、测试账号

```
账号: testuser
密码: Test1234!
角色: admin
```

---

## 七、当前阻塞项

（无）

---

## 八、变更记录

| 日期 | 变更 | 操作人 |
|------|------|--------|
| 2026-08-16 | 创建协调文档 | Trae |