# R 批次:前端全页面重设计方案(执行平台=Gemini,去 AI 味+双端风格对齐)

> 触发:用户 2026-09-12 Gate A 签收回收站原型时提出——①管理端与用户端风格不一致需对齐 ②全页面(用户端+管理端)大幅整改去 AI 味,整改执行交由 Gemini ③本方案=R 批次计划,与 A(演示)/B(组件化)/C(单库)构成完整阶梯。
> 定位:R 是"视觉与体验层"的重做,产物 = 新 HTML 原型 + 冻结 token;实施与 B 批次 React 化合并调度(R 出原型 → B 的 Refine/TanStack 承接实现)。**不改 A 批冻结契约,不动页面接线逻辑**(原型携带真实数据形状,接线代码平移)。

## 1. 现状病灶(为何必须重做)
| 病灶 | 实证 |
|---|---|
| 双端风格不一致 | 管理端 8 页与用户端 15 页各自内联 CSS,导航壳经 `aihub-topnav-fix` 多轮 !important 覆盖叠加,同 token 不同观感 |
| AI 味设计(TT §6.3 红线) | 存量页含:千篇一律图标+标题+正文卡片网格、Hero 大数字指标模板、玻璃拟态/渐变滥用风险点、装饰性 sparkline 残留 |
| 23 页各自为政 | 同一组件(表格/弹窗/badge)23 份拷贝,改一处要动 23 文件(C15 批判的视觉面) |

## 2. 铁律(全部沿袭,不新造)
1. **AI Slop 十二条红线**(TT §6.3)一票否决;可机验 6 项(硬编码 hex/通用字体/纯黑白/弹性缓动/layout 动画/渐变文字)用 `frontend-quality-gate.mjs` 过 Gate。
2. **双 Gate 不豁免**:每页 HTML 原型 → 用户 Gate A(APPROVED)→ token 冻结 + 截图基线 → PARITY_CHECK → React 实施 → Gate B(机验)。原型未 APPROVED,任何框架代码不得开工。
3. **真实数据**:原型一律携带 curl 实测的数据形状与量级,禁空数据/MOCK。
4. **C-01 派单制**:Gemini 是执行平台之一;每 task 完工报告 + 编排者独立实证(渲染截图/机验脚本/断言复现),不采信自述。
5. **token 单一事实源**:`design-tokens.json` 冻结后,任何页面不得出现未登记 hex/字体/圆角/阴影(机验)。

## 3. Gemini 接入方式(三选一,按可用性降级)
| 方式 | 说明 | 适用 |
|---|---|---|
| a. `gemini` CLI 非交互(`gemini -p "<开工prompt>"`) | 编排者直派,产物落工作区 | 本机已装并可用 |
| b. 用户手动中转:编排者产出开工 prompt 包(必读清单+任务 GWT+守则+报告模板),用户贴给 Gemini(Web/App),产物文件回贴工作区 | 无 CLI 时的标准路径 | 兜底 |
| c. 降级:编排者派本端子 agent 执行同一 prompt | Gemini 不可用 | 应急(如实登记 SWITCHED_PLATFORM) |
每 task 开工包含:必读文档清单(设计规范+该页现状+冻结 token)+GWT+硬性守则(AI Slop 红线/真实数据/全交互态)+完工报告模板(必含"资产消费证据"+"AI Slop 自检 12 条逐条结论")。

## 4. 批次与排序
| 批 | 内容 | 产出 | Gate |
|---|---|---|---|
| R0 风格定调 | Gemini 产出 3-5 个互斥风格变体(对标品类:在线教育/学习工具,非 SaaS 后台);每变体=风格 prompt+1 页样张 | 用户选定 1 个 → `design-tokens.json` 冻结+样张截图基线 | 用户签收 |
| R1 学生线原型(7 页) | courses/course-detail/learning/chat/dashboard/achievements/me(+community 合并批) | 每页 HTML 原型(全交互态) | 逐页 Gate A |
| R2 管理线原型(7 页) | admin-dashboard/courses(+回收站)/users/questions(+detail)/rag/mcp(+course-detail)——**统一对齐 R0 token,消灭双端不一致** | 每页 HTML 原型 | 逐页 Gate A |
| R3 实施(与 B 合并) | admin 域走 Refine(主题=token 映射,B0 已选型);学生域 React+TanStack;PARITY_CHECK 门机验(token diff=0+截图接近度) | React 页面 | Gate B |
排序理由:先定调再批量,避免逐页风格漂移;管理端第二波(用户端先立基准,管理端"对齐"才有锚);实施最后,原型全签收后 React 一次铺开。

## 5. 验收(每页)
1. 机验:`frontend-quality-gate.mjs` 全 PASS(硬编码 hex=0/通用字体=0/纯黑白=0/弹性缓动=0/layout 动画=0/渐变文字=0)+ `prototype-parity-check.mjs`(tokenDiff=0)。
2. 渲染实证:CDP 多视口截图(375/768/1280/1440)+零 console 错误+真实数据渲染断言。
3. 人工:用户 Gate A 主观签收(AUDIT LOG 状态机:SUBMITTED→APPROVED/REJECTED,返工 FIX-R{n} 回读历史轮次)。
4. 强制批判:R1/R2 每批收口跑竞品对标批判(≥3 条带 URL+日期),登记 tracker。

## 6. 风险与对策
| 风险 | 对策 |
|---|---|
| Gemini 单次上下文有限 | 一页一 task,开工包≤200 token 摘要+具名文件路径 |
| AI Slop 高发(生成式默认审美) | 机验门前置+开工包附 12 条红线清单+报告强制逐条自检 |
| 重设计期间 A 批页面还要用 | R 产物全部落 `*-proto.html` 新文件,存量页冻结不动;R3 实施才替换 |
| 风格返工循环失控 | 每页返工≤2 轮(FIX-R1/R2),仍不过 → 风格定调回炉,不为单页特例 |
| 双端 token 漂移 | tokens.json 唯一来源;PARITY 机验兜底 |

## 7. 与现有计划的合并
- R0/R1 可与 A 批第四波并行(纯原型零生产代码);R2 在 A 收口后开;R3 即 B 批次的实施载体(B1/B2/B3 的 GWT 不变,输入原型换成 R 批产物)。
- C15 批判(双端结构性浪费)由 R+B 联合闭环:R 消灭 23 份 CSS 拷贝(单一 token 源),B 消灭 23 份接线 IIFE(组件化)。
