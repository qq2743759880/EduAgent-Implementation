# task17 完成报告 —— 清单外页面"不翻车"巡检（favorites / practice / my-cohorts / refund）

> 批次：reshape-a A 批 · P6 前提：只保不翻车，**不接新功能**。禁 Playwright，按派单允许的替代路径「node 最小 DOM 桩 + 静态机检」独立实证。
> 结论先行：发现并修复 **2 个运行时 ReferenceError 级缺陷**（其一为登录态真实功能死 UI 的 P0）+ **2 处死跳转** + **演示态 15 枚死按钮诚实禁用**；favorites.html 完全健康零改动。

## 1. 逐页巡检结果表

| 页面 | JS 运行时错误 | 死跳转/死按钮 | 登录守卫 | 接线状态 | 处置 |
|---|---|---|---|---|---|
| **favorites.html** | 无（3 脚本块 new Function 全过；no-undef PASS） | 无（分页/卡片/空态按钮全部有绑定；站内链接全部存在；无裸 href="#"） | ✅ 无 token → `EAPI.buildLoginUrl` 跳登录（L164）；分页/错误/空态三态齐 | ✅ 已全量接线（GET /api/favorites 分页壳 + 卡片真实跳 course-detail?id=） | **零改动** |
| **practice.html** | **P0：`bindQuestion(t)`（原 L1112）调用从未定义的函数** → 登录态真实复习会话 renderQuestion 中断，选项/提交/下一题绑定全丢=首题即死 UI。DOM 桩复现：`ReferenceError: bindQuestion is not defined` | 死链：面包屑 `href="#"`（L459）；演示态死按钮：错题演示表「重做」×4、会话演示条「结束复习/上一题/下一题」 | 未登录→演示态+「演示数据」角标（task122 模式，属既定设计非缺陷）；登录态全量真实（task120） | ✅ 已接线（wrong-book/quiz/vocab/recall 全真实） | **修 3 类**（见 §2） |
| **my-cohorts.html** | 无（5 块语法全过；no-undef PASS） | 死链：面包屑 `href="#"`（L313）；演示态死按钮 ×10（静态卡「继续学习/课程详情/售后」×2 组、「查看证书/写评价/再次报名」、「查看退款」均无绑定——登录态会被 task105 真实卡片整体替换，仅未登录演示态可达） | 未登录→保留演示数据+角标（task105/122 既定模式，L587/671）；登录态 `GET /api/enrollments/me/cohorts` 三 Tab 真实过滤 | ✅ 已接线 | **修 2 类**（见 §2） |
| **refund.html** | **P1：守卫 IIFE 调用未定义的 `flash`**（原 L216/220）→ 非 student 角色访问或 auth/me 失败时 `ReferenceError: flash is not defined`，且其后的跳转 setTimeout 永不注册=页面卡死。DOM 桩复现（admin 角色桩）：错误实抛 | 无死链/死按钮（wire() 全绑定：两表单/分页/撤销/订单联动；gnav 无，返回链接 dashboard.html 存在） | ✅ 三段守卫（无 token 跳登录 → auth/me 须 role=student 否则跳回 → auth/me 失败跳登录），但被 flash 缺陷炸断 | ✅ 已接线（refunds/orders/after_sales 全真实，task66） | **修 1 类**（见 §2） |

## 2. 改动清单（最小修复，全部在允许文件范围内）

### 2.1 代码修复（3 文件，+28/-20 行）
| 文件 | 修复 | 性质 |
|---|---|---|
| `edu-frontend/public/practice.html` | ① 删除 `bindQuestion(t);` 调用（函数从未定义；实际绑定由其后的 SINGLE/JUDGE/MULTI/DRAG_SORT 分支完成，该调用纯冗余且致命）+ 注释说明 | P0 运行时错误修复 |
| | ② 面包屑 `href="#"` → `href="me.html"`（个人中心） | 死跳转修复 |
| | ③ 演示态死按钮诚实禁用：错题演示表「重做」×4、会话演示「结束复习/上一题/下一题」加 `disabled` + `title="演示数据 · 登录后可真实重做/进入真实复习会话"`（这些元素登录态下被 hideQuizDemo/wbDemoPanel 隐藏，禁用零风险；交互演示项——切题型/填空提交/判断——本就有绑定，未动） | 死按钮→诚实占位 |
| `edu-frontend/public/my-cohorts.html` | ④ 面包屑 `href="#"` → `href="courses.html"` | 死跳转修复 |
| | ⑤ 静态演示卡 10 枚死按钮 `disabled` + title（「售后/查看证书」等如实标注「演示数据 · …」/「后端未实现·后续上线」）；复用既有 `.btn:disabled` 样式（L119），**零视觉 token 改动**；登录态下网格被真实卡片整体替换，不受影响 | 死按钮→诚实占位 |
| `edu-frontend/public/refund.html` | ⑥ 守卫 IIFE 内补等价局部 `flash`（复用页面既有 `#flash` toast 元素与原样式语义——红/绿判据与 bootRefund 私有版逐字一致；**非 alert 新增**），使非 student 角色与 auth/me 失败路径恢复"诚实提示 + 1.2s 跳转"的设计行为 | P1 运行时错误修复 |

### 2.2 巡检工具（可复跑资产，随本 commit 入库）
- `test-reports/_task17_patrol_id_href.js` —— 四页 DOM id 交叉引用 + 站内 href 目标存在性 + 裸 `href="#"`/死锚扫描（剥 HTML 注释防误报）。
- `test-reports/_task17_patrol_undef_conclusive.js` —— no-undef 权威检查（ESLint v9 flat config，`-c` 显式指定防项目根配置覆盖）：**内置反证步骤**——先对修复前基线（动态定位 fix(reshape)/task17 提交取其父版，可 T17_REV 覆盖）的 practice/refund 跑同检查，必须捕获 `bindQuestion`/`flash` 两处 no-undef（证明检查器非空转），再对修复后四页跑必须全 PASS。

## 3. 实证记录（资产消费证据）

1. **语法**：四页 14 个内联脚本块 `new Function` 全过（修前修后均过——两处缺陷是运行时作用域/未定义引用，非语法）。
2. **DOM 桩复现（修前）**：node 最小 DOM 桩执行 refund 守卫 IIFE（EAPI 桩返回 role=admin）→ `unhandledRejection: ReferenceError: flash is not defined`（实锤）；practice renderQuestion 路径桩 → `ReferenceError: bindQuestion is not defined` + 绑定丢失后果说明。
3. **DOM 桩复验（修后）**：refund 守卫桩 → `flash message="当前角色 admin 无权访问退款中心，正在跳回学习端…"`、`flash visible=block`、`redirect setTimeout scheduled=true`、无异常。
4. **no-undef 反证闭环**（`_task17_patrol_undef_conclusive.js` 实跑输出）：
   - `基线 practice.html (pre-fix): 231:5 error 'bindQuestion' is not defined no-undef`
   - `基线 refund.html (pre-fix): 19:7 / 23:5 error 'flash' is not defined no-undef`
   - `FIXED favorites/practice/my-cohorts/refund: 全部 PASS`
   - 过程诚实记录：首轮 no-undef 检查显示"0 errors"系项目根 eslint.config 覆盖了我的临时配置（规则未生效、结果空转）——靠 HEAD 反证暴露并改用 `-c` 显式配置修复检查方法本身；v1 文本扫描器因正则字面量（`/[&<>"']/g`）误报已废弃，不做数。
5. **id/href 扫描**（`_task17_patrol_id_href.js` 实跑输出）：修复后四页 static/dynamic id missing=NONE、missing target pages=NONE、dead #anchors=NONE、bare href=#[ ]。
6. **契约消费**：favorites 分页壳 `{total,page,page_size,items}`、my-cohorts `GET /api/enrollments/me/cohorts`（enroll_status 枚举 active/completed/cancelled/refunded）、refund 三端点 `/api/refunds`、`/api/trade/orders?refundable=true`、`/api/trade/after_sales/ticket`——与 contracts/reshape-a.json endpoints 及各页头注释核对一致；本任务未新接任何端点（P6）。
7. **真实 HTTP 探活（诚实登记环境限制）**：3000/8000 curl 探活在本 agent 沙箱全部连接拒绝（127.0.0.1/localhost/192.168.85.101 均试，netstat 无监听面，遵禁令未重启）→ 登录态真实 API 回归与 CDP 加载截图缺位，建议 task18 检查单/全链路回归补跑；两处 P0/P1 修复的判据是确定性静态事实 + 可复跑 DOM 桩，不依赖该环境。

## 4. 清单外登记（不接线，P6 边界）
- 四页均**不是**"完全未接线只有演示数据"页：favorites/refund 全量真实，practice/my-cohorts 登录态全量真实 + 未登录演示态（角标）为 task105/120/122 既定模式——无需登记新页。
- practice 入口卡「开始回忆/去练习」两钮：登录态有真实绑定（滚动到真实区块），未登录演示态下惯性地无动作——**未禁用**（禁用会连带失效登录态绑定），由「演示数据」角标覆盖，登记为演示态已知行为，建议 React 阶段统一演示态按钮语义。
- practice 演示会话 `time_spent_sec: 12` 为 task120 既有固定上报值（真实端点真实提交，非假交互），不属死按钮，未动。
- my-cohorts 演示卡假数据（含假退款单号 RF20260812001）：demo 角标覆盖下属既定演示态，未动。

## 5. 批判承接核对段
| 批判/教训 | 本任务落点 | 核对 |
|---|---|---|
| 教训 9「参数提取禁用正则 match」 | 巡检中所有 id/参数核对走 id 集合比对与 URLSearchParams 语义，未引入路径正则 | ✅ |
| 教训 10「守卫三段不可少」 | refund 三段守卫本体健全，修复使其在非 student/失败路径真正走通（原被 flash 炸断=事实上的单点失效） | ✅ 修复后守卫才成立 |
| D4「不留假按钮」精神延伸到清单外页 | 演示态 15 枚死按钮诚实禁用（disabled+title），零 alert 新增、零假弹窗/假进度/假表单 | ✅ |
| P6「清单外只保不翻车」 | 未接任何新功能/新端点；favorites 零改动；演示态边界行为登记不修 | ✅ |
| 批判方法论「独立实证须可证伪」 | no-undef 检查器自身经 HEAD 反证证明非空转；两处 ReferenceError 均有修前桩复现 + 修后桩复验的对称证据 | ✅ |

## 6. 三视角自检
- **Eng（工程）**：修复均为最小 diff（删一行未定义调用 / 补一个等价私有函数 / 改两个 href / 加 disabled+title 属性）；未触碰 edu-api.js、edu-guard.js、contracts、后端；未新增全局符号（flash 为 IIFE 内 var，与 bootRefund 私有版隔离，无遮蔽风险——bootRefund 的 flash 在其自身闭包内解析）；my-cohorts 禁用按钮与 task105 真实注入无交互（注入按 `.grid` 整体替换 innerHTML）。
- **Design（体验）**：修复后演示态用户点死按钮得到的是禁用态+诚实 title（而非无响应），登录态用户获得可用的真实复习会话（P0 修复直接复活错题重做/专项练习核心动线）；refund 非 student 用户从"白屏卡死"变为"明确提示+自动跳回"；复用既有 disabled/muted 样式，无视觉 token 变更。
- **CEO（演示故事）**：演示动线涉及页中 practice（错题重做→真实判分→解析）此前在登录态首题即断——本修复消除该演示事故隐患；四页加载、守卫、跳转均"不翻车"；剩余已知项（演示态角标、time_spent_sec、course-detail 评价面板降级底座）均已登记且有归属，无隐形雷。

——task17 收口：3 文件修复 + 2 巡检工具 + 本报告，独立 commit。
