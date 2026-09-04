# EduAgent 优化修改 dev-plan（任务总纲）v1.0

> 日期：2026-09-02 ｜ 证据：`audit-20260902.md` ｜ 范围决策：`prd-optimization-v1.md`
> 编号从 task101 起，避开既有 v3.4 总计划（task00~99）与已冻结的 task61。每任务独立详档见 `tasks/taskNN-*.md`；派发前详档必须存在且带 GWT 全文。

## 需求前提挑战（dev-planner Step 0）

前提表（任一被推翻 → 回需求澄清，本表随任务推进维护）：

| # | 前提 | 影响 | 状态 |
|---|---|---|---|
| P1 | 架构不变：fe-html 静态页 + 8000 FastAPI，本期不迁框架 | 全部前端任务形态 | 用户痛点即前端缺陷，默认成立 |
| P2 | 契约权威仍是后端 schemas.py；"对接"只补前端不改契约——但本期含 3 项**经冻结流程的契约修正**（C-A/C-B/C-C） | task114/115/116 | 需用户确认 D1/D2/D3（PRD §5） |
| P3 | 优先级 = 动线阻断 > 契约错位 > 安全 > 功能完善 > 卫生 | 波次排序 | 默认成立 |
| P4 | task61 沿用既有编号与已冻结契约⑥，不新立任务 | W2 | 看板 READY，成立 |
| P5 | 验收纪律：接口 requests/curl+pytest 独立实证；前端结构断言+截图视觉；禁 Playwright | 全部验收 | AGENTS.md 教训②，成立 |
| P6 | 多平台可用（探测到 7 平台）；平台不可用时退化为单平台串行+换视角复验，任务不裁剪 | 派单 | detect-platforms 2026-09-02 实测 |

四问结论：①为什么现在——8-31 全量接入后"能看不能用"，动线断裂阻塞一切演示/验收；②现状方案——演示数据兜底掩盖断点，须以真实数据为主线；③窄楔子——W0 四个 P0（壳客户端+动线）先行交付；④未来适配——契约统一（C-A/B）为多端复用与后续框架迁移铺路。

---

## 任务总表（5 波次 × 22 任务）

图例：域 FE=前端 / BE=后端 / MIX=前后端；类型 契约=触发契约冻结；依赖=完成依赖（严格等 DONE），其余为契约依赖（契约验收即解锁）。

### W0 动线阻断修复（P0）

| 任务 | 域 | 一句话 | 详档 |
|---|---|---|---|
| task101 | FE | edu-api.js 壳客户端加固（401 判定/非 JSON/超时/BASE 可配/logout/redirect） | tasks/task101-eduapi-hardening.md |
| task102 | FE | 两个 admin 详情页 SyntaxError 修复 + 全站统一 `?id=` 取参工具 | tasks/task102-admin-detail-syntax.md |
| task103 | FE | 课程动线打通：卡片可点→detail?id=→cohort→learning 入口；真分页 page_meta | tasks/task103-course-flow.md |
| task104 | FE | chat.html 双绑定清理 + 新建会话接 POST /api/chat/sessions + done 壳解包 | tasks/task104-chat-conflict.md |

### W1 契约对齐与守卫（P1）

| 任务 | 域 | 一句话 | 详档 |
|---|---|---|---|
| task105 | FE | 学生端字段对齐：achievements/admin-dashboard no-op 修复、dashboard/me 字段按后端 schema 重对（X2/X3，关联 D4） | tasks/task105-student-fields.md |
| task106 | FE | 管理端表格列错位 ×4 修复（保留操作列）+ admin-mcp 过时契约注释更正与字段核验（X6） | tasks/task106-admin-tables.md |
| task107 | FE | admin-questions.html 真实接入（banks/questions 列表+详情+导入预览/执行） | tasks/task107-admin-questions.md |
| task108 | FE | 登录注册完善：注册接 API、Enter 提交、`?redirect=` 回跳、全站登出按钮 | tasks/task108-auth-logout.md |
| task109 | FE | 管理端角色守卫：admin-*.html 校验 role，非 admin/manager 重定向 | tasks/task109-admin-guard.md |
| task110 | FE | 动线杂修：死链 `/admin/courses/{id}`→`admin-course-detail.html?id=`、doBack、community-post 入口链接、my-cohorts 选择器 | tasks/task110-nav-misc.md |

### W2 安全与契约统一（BE 先冻结，FE 跟进）

| 任务 | 域 | 一句话 | 详档 |
|---|---|---|---|
| task113 | BE | 安全加固包：award 角色限制、payment mock 回调收敛、quiz correct 不下发、metrics 鉴权、memory 前缀入中间件、40021 拆分 | tasks/task113-be-security.md |
| task114 | BE+契约 | 响应壳统一：recommender/mindmap/interactive/users-me 纳入 ok() 壳 + users/me 字段冻结（X7，关联 D1/D4）→ 冻结 **C-A** | tasks/task114-be-shell-unify.md |
| task115 | BE+契约 | 分页统一（课程域 page_meta→全站 DTO，D2）+ chat SSE error 事件补发 → 冻结 **C-B** | tasks/task115-be-pagination-sse.md |
| task116 | BE+契约 | 系列删除语义落定（L2，D3）→ 冻结 **C-C** | tasks/task116-be-delete-semantics.md |
| task117 | FE | admin-courses CRUD 真实接线（保存/上下架/删除按 C-C；依赖 task116 DONE） | tasks/task117-fe-admin-courses-crud.md |
| task61 | FE | RAG 控制台上传 Tab（沿用既有编号；契约⑥已冻结：admin 上传/tasks/partitions） | tasks/task61-rag-upload-tab.md |

### W3 功能完善

| 任务 | 域 | 一句话 | 详档 |
|---|---|---|---|
| task118 | FE | community 交互闭环：点赞/评论/发帖接 API、版块 chips 联动 board_code、列表→详情链接 | tasks/task118-community.md |
| task119 | FE | learning 学习动线：改调 /api/study/*（X1）、大纲渲染、tick-batch 打点、complete | tasks/task119-learning.md |
| task120 | FE | practice 完整接入：quiz next/submit 真判分（摆脱 correct 依赖）、vocab、错题表 | tasks/task120-practice.md |
| task121 | FE | me 资料编辑接 PUT profile + dashboard 快捷入口接真实跳转 | tasks/task121-me-dashboard.md |

### W4 卫生与流程收尾

| 任务 | 域 | 一句话 | 详档 |
|---|---|---|---|
| task122 | FE | 工程卫生包：HMR 残留/演示控制器/body 重复属性/假封面/假分页/错误 toast 统一（O5） | tasks/task122-hygiene.md |
| task123 | MIX | 流程收尾包：task43 核对、落错分支 commit 归属、itest 种子清理、critique-backlog-tracker 同步、DEBUG=False 部署检查单 | tasks/task123-process-closeout.md |

### 依赖图（关键边）

```
task101 ─┬─→ (所有 FE 任务的基建，先行合入)
task102/task103/task104  （W0 可全并行）
task105~110 （W1 可全并行，均依赖 task101 合入）
task113 → task120（correct 移除后 practice 判分必须已走后端）
task114 → C-A 冻结+验收 → task105 字段对齐复核、task107/106 admin 消费面回归
task115 → C-B 冻结 → task103 分页、task106 表格复核
task116 → DONE → task117
task61 独立（契约⑥已冻结）
task122/task123 收尾，等各波次合入
```

### 统一验收基线（每任务 GWT 共同项）

- **Given** 服务以 `DEBUG=False` 启动于 8000，**When** 执行该任务验收命令，**Then** 无 500；接口类任务以真实 HTTP + 数据库/响应实测为准；前端类任务附渲染截图。
- 每任务独立 commit（`feat(opt)/taskNN-*`），完工报告落 `test-reports/taskNN-completion-report.md`，含"实际调用证据"段。

---

## 规划自审（派单前三视角，CEO→Eng→Design）

### CEO 范围自审

- **Finding**：管理端 CRUD 全是 alert 占位（audit §1.1），若本期只修"展示错位"不接 CRUD，管理端在用户眼里仍是"半成品"，与"功能未完善"的原始诉求不符。
- **处置**：已增 task117（admin-courses CRUD 接线）并以 C-C 契约冻结护航；admin-users 角色管理、题目编辑写入列入 W3 后评估（本表 task107 只做读+导入）。范围拒绝项：不做 task78~91 批量管理页（非目标）。

### Eng 架构自审

- **Finding**：响应壳双轨 + 双分页壳若不统一，前端每个消费点都要写双解析，且 OpenAPI 无法推导统一客户端；这是后续一切前端任务的重复税。
- **处置**：task114/115 提前到 W2 冻结 C-A/C-B，前端消费方回归纳入同波次；**confidence 0.75**——风险在 137 端点消费面普查不全，缓解：冻结前 grep 前端全部取值点 + `interface_acceptance_final.py` 全量回归 + 每域灰度合入。
- **Finding 2**：task113 移除 quiz `correct` 字段可能破坏仍在用本地判分的前端页（practice.html 四题型本地判分）。
- **处置**：依赖边 task113→task120（先接真判分再移除字段，或同 PR 内完成）；验收含 grep `correct` 前端消费=0。

### Design 体验自审

- **Finding**：三个体验断点贯穿全站——错误被 `catch(function(){})` 静默吞（用户无任何反馈）、无登出按钮（登录态成"死状态"）、表单 Enter 原生提交刷新丢状态。
- **处置**：task101（统一错误事件/回调）、task108（登出+Enter+redirect）、task122（toast 统一）承接；本期不新设计页面，HTML gate 不适用，但所有改动页纳入渲染截图视觉验收。

---

## 机器校验

- 本计划通过 `node $SKILL_DIR/scripts/review-gate.mjs --plan .ai-hub/plans/dev-plan.md` 校验（含前提挑战/规划自审实质区块）。
- 派单前每任务详档落盘 `tasks/taskNN-*.md`；契约任务派发前置 `contractMode:'frozen'` 检查（handoffs/taskNN-contract.md 存在才开工下游）。
