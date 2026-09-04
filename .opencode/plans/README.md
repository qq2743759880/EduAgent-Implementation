# EduAgent 重构方案文档索引

> 数据权威：`E:\stu\project\stu\edu-data`（sql/edu.sql 66 表 + seeds + generate 脚本）
> 状态：**实施中（task00~06 已验收）** ｜ 计划版本：dev-plan **v3.2**（98 任务）

| 文档 | 角色 | 内容概要 | 供谁使用 |
|------|------|---------|---------|
| `edu-data-refactor-plan.md` | PRD + 修改规划（v2.0） | 背景/范围/FR 功能需求/数据库六类动作/后端模块表/前端页面清单/实施 P0~P9/风险回滚 | 全体（总纲） |
| `tech-source-audit.md` | **技术选型来源审计** | 每项选型=**参考来源（文献/网站/竞品）+ 自我批判（是否为最优解）+ 选用原因**；七节：后端栈/AI 架构/RAG-MCP/中间件/前端栈/前端设计/运维 | 任何技术决策前必查（无条目先补） |
| `doc-frontend-design-spec.md` | doc-frontend 设计规范（938 行） | 设计令牌（indigo 主色 hex 全量）/字体阶梯/间距/圆角/阴影/断点/图表色板；**18 页逐页规范**（布局草图+组件清单+交互+状态机+数据依赖）；HTML 原型审核流；跳转地图；红线规则 | fe-architect / fe-design-director / fe-spec-writer / fe-implementer / fe-styler |
| `doc-architect-tech-arch.md` | doc-architect 技术架构（753 行） | 模块化单体决策/四层架构/目录树；中间件（Trace/熔断/幂等/限流/缓存三防）；**AI 助手 orchestrator-worker 多 agent**（图节点/effort scaling/三层记忆+遗忘/compaction/Redis 防过载/tool 规则/CoT/token 优化/HITL）；RAG Contextual Retrieval 落地；MCP 描述审查 | sd-dev / sd-planner / 后端开发 |
| `dev-plan.md` | dev-planner 任务划分（**v3.2**，814 行） | **98 个任务（task00~task97）**：后端 60+（task00~39 + 管理端补全 70~77b/88/89 + AI 修订 92~97）/ 前端 40+（task40~69 + 78~91）；总览表 + GWT 验收 + 依赖图 + **执行顺序章节（A 数据主线→B 底座→C 交易域→D 知识库重建前移→E AI 修订+实现→F 管理端→G 前端滚动解锁→H 收尾）** + 契约冻结①~⑭ + 风险清单 + 选型审计引用 | 全体（执行依据） |
| `orchestration-frontend-backend.md` | 前后端联调编排 | Trae(后端)/TraeWork(前端)/opencode(编排) 分工；任务执行排序总表；跨工具交接单机制（契约冻结→handoffs→看板）；并行窗口；时间锚点 | 编排者 + 双方开工必读 |
| `collaboration-protocol.md` | 三方对接守则 | 角色边界（越界上浮）；契约纪律（schemas.py 唯一权威）；AI-Hub 记忆分区（trae-projects/codex/project-handoff 看板）；同步节奏；开工检查单 | 双方每任务开工必读 |
| `task-agent-matrix.md` | 任务调度矩阵 | 5 类任务模板调度链；任务 × agent 链 × skill × workflow × MCP 全表；dev-standard.mjs 适配本项目调用参数 | 执行每个 task 时查表 |
| `kickoff-prompts.md` | 开工 Prompt **v2.1** | 发给 Trae / TraeWork 的两段可直接复制 prompt + 编排者配合动作（含 AI 修订必读） | 开工时复制 |
| `self-critique-ai-agent-vs-competitors.md` | **AI 助手自我批判**（vs Claude Code/TraeWork/Cursor） | 9 维度判定达不到竞品水平；**3 结构性缺陷**（子代理共享 state/无 skill 机制/MCP 描述进前缀毁缓存）+ 5 工程差距；证据=竞品官方文档实抓 | AI 修订任务（task24~33/92~97）必读 |
| `ai-agent-revision-plan.md` | **AI 8 项修订计划**（R1~R8） | R1 子代理独立上下文/task92、R2 skill runtime/task93+94、R3 MCP 延迟加载认证重连/task95、R4 context editing/task96、R5 缓存监控/task97、R6 tree-sitter/task30、R7 显式记忆触发/task25、R8 harness 对比/task29 | AI 修订任务实施依据 |
| `admin-modules-completion.md` | **管理端补全方案**（v1.1） | M1 订单/M2 退款/M3 学员作答/M5 公告站内信/M6 工单申诉/M8 报表/M10 券/M11 CRM 详表 + task70~91 任务规划 | 管理端任务（task70~91） |
| `db-acceptance-principles.md` | **数据库验收 6 点原则**（用户定稿） | P1 先文档后脚本 / P2 精确断言== / P3 动态计算 / P4 CI 门禁 / P5 5 维度质量 / P6 口径漂移声明；可复用生产验收体系（verify.py）设计 | 所有数据库任务（task07 修复/task98/后续改表）验收设计必读 |
| `checkpoint-critique.md` | **Checkpoint 机制批判**（task06 复核） | 4 缺陷：无原子写（断电丢状态🔴）/层粒度非批次（批中断全量重跑🟠）/init 顺序（失败路径误判🟠）/并发双跑覆盖🔴；修复方案（os.replace/批级进度/SQLite 或 MySQL）；**本次不改（task06 复用度低），未来 agent 机制复用 checkpoint 时必须先按此优化** | 未来任何复用 checkpoint 的实现（含 AI 修订） |
| `html-rework-sop.md` | **HTML 页面返工 SOP**（v1.2：§〇 风格定调 gate + §2.1 工具命令速查） | 设计调用链执行手册：`frontend-design → prototype → colorize → polish → visual-validation → audit/critique` 六步细则（触发/调用/动作/出口标准）+ **§2.1 工具命令速查**（每步必跑 ui-ux-pro-max search.py --design-system/--domain style/color/stack + Playwright 截图 + grep hex 校验，含实测命令）+ 返工循环与 AUDIT LOG + 验收清单 + AI Slop 红线 + 失败模式止损；是 doc-frontend-design-spec §五 HTML 审核流中"返工"环节的可执行细则 | fe-* 每页 HTML 返工必读 |
| `tasks/taskNN-*.md` | **100 个任务详细文档** | 每个任务：GWT 验收全文 + agent 调度链 + MCP/skill 清单 + workflow 调用参数 + 前置/后置/联调节点 + 实现规划要点 + **选型依据引用** | 执行对应 task 时直接读取 |

## 关键决策（用户已确认）
1. pf_bagu_kb 保留；2. 题目标签删除后重构；3. 响应壳全模块统一 `{code,message,data}`；4. 支持分夜跑批；5. **前端全部页面重建**（29 页，排除购物车/咨询，咨询改人工申诉），每页 HTML 原型→用户讲解修改点/给设计图→fe 返工迭代；6. full 档数据 + Redis 性能优化；7. Milvus/Neo4j 清除后用课程+题目重建；8. 管理端 RAG 新增通用文件上传入口；9. **技术选型必须注明参考来源+自我批判**（tech-source-audit.md）；10. 管理端补全 P0+P1 全做（M1~M11 → task70~91）；11. **AI 助手 8 项修订先于实施**（self-critique → task92~97 + task24~33 改造）；12. 执行顺序 A→H（知识库重建前移至 AI 之前）；13. **checkpoint 机制本次不改，未来复用必须按 checkpoint-critique.md 先优化**（原子写/批粒度/并发锁）。 15. **数据库验收 6 点原则**（db-acceptance-principles.md）：先文档后脚本/精确断言==/动态计算/CI门禁/5维度质量/口径漂移声明；task07 建表标准不改，后续数据库迭代验收按此设计；新增 task98 生产可复用 verify.py 框架。 14. **【最高优先级】任务验收强制技术批判+优化修改方案**（D:\.ai-hub\memory\task-review-critique-rule.md）：每个 task 验收必须产出 task{id}-技术批判.md（≥3 条，真实证据）+ task{id}-优化修改方案.md（可落地），任一缺失不得验收通过；从 task07 起执行。

## 调研依据（真实一手资料）
- Anthropic《Building Effective Agents》《Effective Context Engineering》《Multi-agent Research System》《Contextual Retrieval》官方工程博客
- 字节 CloudWeGo 官网（Kitex/Hertz/Sonic/Eino）
- 腾讯 PolarisMesh 官网（服务治理/熔断）
- LangGraph 官方文档（context7：checkpointer/Redis Store/HITL）
- MCP 官方（modelcontextprotocol.io）

## 风格定调 gate + HTML 效果图迭代流程（项目级前置 + 前端每页必经，29 页全量）
```
0 风格定调（首屏前必做）：问风格 → 无想法引导"对标品类"prompt → 实时搜主流/小众/Awwwards 获奖站 + ui-ux-pro-max → 出 N 个可复制 HTML 风格 Prompt → 用户选定 → 冻结（design-spec + design-tokens.json + STYLE frozen）→ 后续页面风格统一
1 doc-frontend 规范（缺失页先补规范）→ fe-* 产出 test-reports/fe-html/{page}.html（含交互态+内联 CSS）
  → 用户审核 → 用户讲解修改点或给出设计图 → fe-* 按讲解/图返工改 HTML → 再审核
  → 循环至用户签收 APPROVED → fe-implementer 写 React → fe-tester/fe-visual-auditor 验证
```

> **当前冻结状态（2026-08-19）**：风格 `candy-playful`（学中玩糖果色，用户指定 Duolingo 系）已在 task44 审核中定调并签收 → **已冻结**（doc-frontend-design-spec §风格定调 + design-tokens.json + globals.css + courses.html STYLE 标记）。后续页面统一糖果色，不再重问；换风格=重新走 gate。
