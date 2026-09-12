# 派发方案 reshape-b·第一波(2026-09-12,经用户终审有条件批准后编制)

> 用户条件逐条落实:§四 ①正式派发方案=本文 ②禁 DB 直写条款=所有开工单硬性守则第 1 条 ③a2 解耦=已裁定解耦并冻结 ④B0 维护判据=已入 tracker(2027-03 复核) ⑤B1 开工单两条已含 ⑥B2 按 B0 §5 修订定义 ⑦B3 拆 proto/impl+214 行判据 ⑧T5=B 批启动时编排者自跑 ⑨T19-3 并入 reshape-b 增补(变更单先行) ⑩R0 暂缓登记原因与解除条件。

## 一、关键决策(用户建议采纳)
| 决策 | 定案 |
|---|---|
| D-H3 | **A 方案并入 B3**:admin-users 权限对齐直接在 Refine 版实现(B3-proto 原型含权限口径);过渡期临时措施=对 manager 灰显导航例外入口(待 task109 GWT③ 签字后派,一行级小改,与 B1/B2 并行) |
| D-a2 | **a2 与数据事故解耦,立即冻结**(三条变更与帖删除/订单无因果;冻结文件 contracts/reshape-a2.json) |
| D-T19-3 | **并入 reshape-b 契约增补**:50301 DEPENDENCY_UNAVAILABLE+脱敏走变更单草案→用户签→实施(不独立派) |

## 二、任务池终表(优先级/前置/平台/资产/开工单)
| # | 任务 | 优先级 | 前置检查(逐条实测) | 平台 | A 级资产(具名) | 开工单 |
|---|---|---|---|---|---|---|
| B1 | health-scan 异步化+sessions 池复用 | **P0** | ①B1b 冻结 b6772f8d ✅ ②task19 收口 ✅ ③**测试用 MCP server 可用**=stdio-echodemo 已重建(p8_stdio_demo_server.py)+修复后健康 ok:true 实测 ✅ | ZCode Agent | TT mcp spec 批判条目(C18)/app/mcp/executor.py 池代码 | 本文档 §四-B1 |
| B2 | Refine 注入共享 queryClient+401 interceptor 收敛(骨架,**不接页面**) | **P0** | ①B0 冻结(Refine v5 headless)✅ ②task19 ✅ ③定义按 B0 §5 修订=本表定案 ✅ | ZCode Agent | .ai-hub/plans/tech-source-audit.md §5;edu-api.js(只读参考) | 本文档 §四-B2 |
| B3-proto | admin-users Refine 版 HTML 原型(新布局壳+权限口径) | P1 | ①P6'-③ HTML gate 生效 ✅ ②不依赖 B2 ✅ | ZCode Agent | P6' 条款;admin-users.html 现状(642 行=判据基数) | 本文档 §四-B3 |
| H3-temp | manager 导航例外入口灰显(过渡,一行级) | P1 | ⚠ **task109 GWT③ 签字待用户** | ZCode Agent | edu-guard.js | 签字后补 |
| B3-impl | admin-users Refine 版实施 | P1 | B2 ✅+B3-proto APPROVED+GWT③ 签字 | ZCode Agent | **C15 判据:Refine 版≤214 行(642/3),超=证伪回滚选型** | B3-proto APPROVED 后出 |
| T5 | w4-reverify 4 项(task16 点击/task17 四页/task06 视觉可播/task04 收藏写) | P1 | 演示机 8/8 ✅(今日实测) | **编排者自跑**(非派单) | check-demo.mjs/probe_one.mjs | B 批启动时执行并出报告 |
| T19-3 | 50301 DEPENDENCY_UNAVAILABLE+错误脱敏 | P2 | 变更单草案=本文 §五(待签) | ZCode Agent | error_codes.py | 签字后并入 reshape-b |
| R0 | Gemini 风格定调 | ⏸ | 用户发令(暂缓中;解除条件=B 批第一批完成+数据事故处置落档) | **Gemini** | frontend-redesign-plan-gemini.md | R0 发令时出开工包 |
| C | pgvector 收敛等 | ⏸ | 部署窗口 | — | 占位(P5') | — |

## 三、依赖图
```
第一批(并行,本轮派): B1 ────────────────┐
                      B2 ──► B3-impl ────┤(第二批)
                      B3-proto ──APPROVED┘
                      H3-temp(待 GWT③ 签字,可即插)
                      T5(编排者,B 批启动时)
变更单流: T19-3 草案 → 用户签 → reshape-b 增补 → 实施(第二批)
暂缓: R0(条件解除) / C 阶段(部署窗口)
```

## 四、开工单要点(派单时全文随单下发)
### 通用硬性守则(所有 B 批开工单第 1 条)
1. **禁 DB 直写**:执行者禁止对 MySQL/Milvus/Mongo/Neo4j 执行任何直接 INSERT/UPDATE/DELETE(P1-7 数据事故流程条款);一切数据操作必须经 API;需要测试数据→走对应 API 造数并在报告登记。
2. 契约冻结禁改;接口对不上→discrepancy 变更单上浮,不臆造。
3. 现状自证:开工前 curl/grep 核实与目标态的差距,差距过大先停下上报(P2-12 条款)。
4. 禁 Playwright;接口验证 curl/python;每任务独立 commit+完工报告(资产消费证据/批判承接核对/三视角自检)。
5. edu-api.js/fe-html 冻结只修不增(B 批新功能一律落 React 侧)。

### B1 专项
- 前置实证:测试 MCP server=stdio-echodemo(已重建),先 curl POST /api/mcp/servers/1/health 断言 ok:true 再开工。
- GWT 增补(用户要求):并发健康检查用例——50 并发 GET 轮询期间,health 检查之间互不干扰(池锁),无 500/超时交叉。
- 验收:单台 health P95<500ms(before≈5s);扫描期 50 并发不排队;旧同步端点 30 天兼容窗。

### B2 专项(B0 §5 修订定义)
- 范围=Refine v5 headless 注入**共享 queryClient**(B2 的 queryClient=B3 dataProvider 的 queryClient,杜绝双轨)+401 single-flight 收敛为 interceptor。
- **不接业务页面**;最小验证=临时 scratch 页(不入 git)证明 401 并发回归+零手写轮询。
- 401 逻辑迁移须保持 edu-api 现行为等价(single-flight 语义,回归用例沿用 W1-C1 场景)。

### B3-proto 专项
- 原型须含:权限口径(manager=只读横幅/ADMIN=全量;GWT③ 签字后终定)、列表+筛选+启停+编辑的全交互态、糖果 token 映射说明。
- **C15 判据入单**:B3-impl 的 Refine 版代码行数≤214(=admin-users.html 642/3),超→回滚 B0 选型。

### B1/B2/B3 依赖与交付
B1 交付=后端+pytest;B2 交付=前端数据层模块+scratch 验证;B3-proto 交付=HTML 原型(送 Gate A)。三者互不阻塞,并行派。

## 五、T19-3 变更单草案(并入 reshape-b 增补,待签)
- 新增错误码 `50301 DEPENDENCY_UNAVAILABLE`(依赖不可达的业务语义码,替代当前 500/50300 直泄);
- 错误响应脱敏:message 面向用户(「依赖服务暂不可用,请稍后重试」),原始异常入日志不入响应(现状:50000 响应曾带 str(exc),task19 §C-18 实证);
- 影响面:全局异常处理器+knowledge/mcp 等依赖型端点;兼容窗:无(纯增量码);
- 回滚:revert 单 commit。

## 六、登记补全
- B0 维护判据入 tracker:@refinedev/core 自 2026-09 起连续 6 个月零发版且阻塞级 issue 无人响应→触发备选预案(react-admin)评估;**复核日 2027-03**。
- task109 GWT③ 签字文本(待用户):「manager 完整可用 4 页(courses/course-detail/questions/question-detail);例外 4 处=users/mcp/dashboard 整页+rag collections 卡;例外处理=导航灰显+横幅/诚实空态」。
- 数据事故:帖删除定责暂停(用户裁定);「禁 DB 直写」条款即前述流程改进先行落地。
