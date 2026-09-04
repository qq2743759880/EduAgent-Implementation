# 前后端联调编排方案（Trae 后端 ↔ TraeWork 前端 跨工具调度）

> 定位：解决"先做哪个 task、谁做、做完怎么交接"的编排问题。
> 工具分工：**Trae** = 后端/数据库开发者（跑 database/backend/rag/mcp/agent/ops 任务）；**TraeWork** = 前端开发者（跑 frontend 任务）；**opencode（当前）** = 编排者，负责跨工具调度、契约冻结发布、验收裁决。
> 依据：`.opencode/plans/dev-plan.md`（59 任务）、`doc-frontend-design-spec.md`、`doc-architect-tech-arch.md`。

## 一、执行工具总分工表（59 任务 × 工具）

| 工具 | 任务 | 说明 |
|------|------|------|
| **Trae**（后端/数据库） | task00~08、09~23、24~35、54、55、56、58 | 数据库 DDL、full 档重灌、后端全部域、AI 助手、RAG、MCP、知识库重建 |
| **TraeWork**（前端） | task36~53、57（E2E 前端部分） | API 客户端、UI 组件、18 页、E2E 页面链路 |
| **opencode**（编排者） | 全程 | 契约冻结、跨工具交接单、记忆同步、冲突仲裁、验收汇总 |

## 二、任务执行排序总表（含跨工具交接）

> 原则：**后端契约先行 → 前端消费契约**；后端任务按依赖链串行推进；前端页面任务在后端契约冻结后按页推进；每完成一个后端域立即解锁一批前端页面。

### 阶段 0：数据主线（Trae 独占，无前端依赖）

```
Trae task00(备份) → task01(66表DDL) → task02(删13表) → task03(sys_user+索引) → task04(任务表) → task05(diff校验)
  → task06(full档适配) → task07(重灌+校验) → task08(admin恢复+冒烟)
```
**编排者动作**：task08 完成后输出「数据基线冻结」通报（TraeWork 不参与本阶段，但需知悉字段权威 edu.sql 已落地）。

### 阶段 1：后端底座（Trae）→ 前端接口层（TraeWork）第一个交接点

```
Trae task09(core框架) → task10(响应壳统一+错误码) ──► 【契约冻结①：{code,message,data}】──► TraeWork task36(api-client解包)
Trae task11(课程域series) ──► 【契约冻结②：/api/series 5端点】──► TraeWork task38(课程中心) → task39(课程详情)
Trae task12(course_admin四级CRUD) ──► 【契约冻结③：admin/courses】──► TraeWork task47 → task48(管理端课程)
Trae task13(题库域) ──► 【契约冻结④：question/analysis_text】──► TraeWork task49 → task50(管理端题库)
Trae task14(progress/users修bug) ──► 【契约冻结⑤：/me接口】──► TraeWork task53(适配页组)
Trae task15(存量壳适配) ──► 并入契约冻结①复核
```

### 阶段 2：交易/售后域（Trae）→ 前端页面批（TraeWork）并行解锁

```
Trae task16(coupons/favorites) ──► TraeWork task41(优惠券页) + task45(收藏页)
Trae task17(order域) ──► TraeWork task42(订单列表)
Trae task18(payment域) ──► TraeWork task43(支付页)（依赖 task17+18 双契约）
Trae task19(refund域) ──► TraeWork task44(退款页)
Trae task22(tickets域) ──► TraeWork task46(售后工单+人工申诉)
Trae task20(enrollment) + task21(study) ──► TraeWork task40(我的班次) + task52(学习页)
Trae task54(RAG上传后端) ──► TraeWork task51(RAG上传前端)
```

### 阶段 3：AI/RAG/MCP 支线（Trae 独占，与前端并行互不阻塞）

```
Trae task24 → task25 → task26 → task27 → task28 → task29（AI 助手，前端 chat 页不依赖新契约）
Trae task30 → task31 → task32（RAG，不影响前端除 task51 外）
Trae task33（MCP 增强）
Trae task34 → task35（知识库重建，独立）
```

### 阶段 4：收尾

```
TraeWork task57(E2E回归，需全部后端上线) → Trae task55(旧代码清理) → task56(文档) → task58(压测+容灾)
```

## 三、跨工具交接单机制（关键操作者方案）

> 每个契约冻结点，编排者（opencode）在 AI-Hub 交接区写入一份「契约交接单」，Trae 完成后写入、TraeWork 开工前读取。**Trae 完成后发现下一 task 需前端执行时，操作者方案如下**：

### 3.1 Trae 侧操作者流程（后端 task 完成后）

1. Trae 完成 taskNN 并验证（pytest/冒烟通过）
2. 在 `E:\stu\project\stu\EduAgent实施手册\.opencode\handoffs\` 写入 `taskNN-contract.md`，内容：
   - 已完成端点清单（路径/方法/请求示例/响应示例——真实 curl 输出）
   - 字段命名表（snake_case 全列）
   - 状态码/错误码清单（字符串错误码）
   - 未完成事项/已知缺口
3. 运行 `powershell -File D:\.ai-hub\sync.ps1` 同步记忆
4. 在 AI-Hub 交接状态文件 `D:\.ai-hub\memory\project-handoff.md` 标记 `taskNN: READY_FOR_FRONTEND`
5. 向编排者报告 → 编排者通知 TraeWork 开工（见 3.3）

### 3.2 TraeWork 侧操作者流程（前端 task 开工前）

1. 读取 `project-handoff.md` 确认依赖契约状态 = READY
2. 读取 `handoffs/taskNN-contract.md`（或后端模块代码 `edu-agent/app/domains/...` 的 schemas.py 作为字段权威）
3. 按契约写 API 客户端 + 页面（HTML 原型审核流：先 `test-reports/fe-html/{page}.html` → 用户审核给图 → 再写 React）
4. 发现契约不符 → 不自行改后端，写入 `handoffs/taskMM-discrepancy.md` 交给编排者仲裁 → 编排者决定改后端（Trae）还是改前端（TraeWork）
5. 完成后更新 `project-handoff.md` 标记 `taskMM: DONE` + 运行 sync.ps1

### 3.3 编排者（opencode）职责

- 维护 `D:\.ai-hub\memory\project-handoff.md`（唯一事实源）：59 任务状态看板（TODO/DOING/READY_FOR_FRONTEND/DONE/BLOCKED）
- 契约冲突仲裁：前端发现的契约问题 30 分钟内裁决（改后端=派单给 Trae；改前端=退回 TraeWork 附修正意见）
- 每日同步：Trae/TraeWork 记忆各自写入后跑 sync.ps1，编排者核对两侧 project_memory.md 不冲突

## 四、并行窗口（谁和谁可以同时干活）

| 窗口 | Trae 在做 | TraeWork 在做 | 前提 |
|------|----------|-----------|------|
| W-A | task09~15（后端底座） | task36 前的**规范准备**：读 doc-frontend-design-spec、搭 HTML 原型模板（test-reports/fe-html 模板文件） | 契约冻结①未发布前 TraeWork 不写正式代码 |
| W-B | task16~23（交易域）+ task24~35（AI/RAG） | task38~53 逐页（契约随发随做） | 每域契约冻结即解锁对应页 |
| W-C | task34~35（知识库重建） | 任意剩余页面 | 互不依赖 |
| W-D | task55/56（清理/文档） | task57（E2E） | 后端全部上线 |

## 五、关键时间锚点（按依赖推算的执行顺序示例）

```
D1  Trae: task00~02（备份+DDL+删表）
D2  Trae: task03~05（sys_user+索引+校验）+ task06 启动 full 档（夜间跑批）
D3  Trae: full 档继续跑（layers 3~7 分批）+ task09(core框架并行)
D4  Trae: task07 校验 + task08 admin 恢复 → 「数据基线冻结」
D5  Trae: task10 → 【契约冻结①】→ 通知 TraeWork 启动 task36
D6  Trae: task11 → 【契约冻结②】→ TraeWork: task36 完成后启动 task38
D7+ Trae: task12~15 连续 → TraeWork: task38/39 逐页 HTML 审核迭代
... 后续按 §三 交接单节奏滚动
```

## 六、接口契约权威源

- 后端字段权威：`edu-agent/app/domains/**/schemas.py`（Pydantic 模型 = 契约）
- 前端消费：`edu-frontend/src/lib/api/*.ts`（类型定义与 schemas.py 一一对应）
- 两端 diff 检查：每次交接前跑 `scripts/check-api-connectivity.mjs`（前端现有脚本）+ 新增 `scripts/contract-diff.py`（对比 schemas.py 与 api/*.ts 字段集，差异即阻断）
