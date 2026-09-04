# task104 — chat.html 双绑定冲突清理 + 会话创建接真

- 域：FE ｜ 平台：trae ｜ 波次：W0 ｜ 依赖：task101
- 文件：`chat.html`

## 目标
消除演示脚本与注入脚本双绑定导致的 TypeError 与数据覆盖，把"新建会话"接到真实 API。

## 证据
- audit §四-2：demo document 级委托 L590-595 与注入元素级监听 L675-682 同时命中 `.sess` → 点真实会话 `draw("history")` 读 `MESSAGES[realId]` undefined 抛 TypeError；`#newSession/#sideNew/#drawerNew/#hamb` 仍绑 demo 处理器，用演示数据覆盖真实列表。
- 无创建会话调用；注入气泡 `class="msg me"` 无对应 CSS（CSS 只有 `.msg.user`）。
- audit §X5：后端 `done` 事件 data 是嵌套壳 `{code:0,data:{...}}`（chat/router.py:268-273），需核验前端解包。

## 改动点
1. 隔离 demo 脚本：未登录（无 token）时才启用演示控制器；有 token 时解绑 document 级委托与 demo 按钮处理器，全部走注入路径。
2. "新建会话"接 `POST /api/chat/sessions`（body 可空），成功后会话列表头部插入并选中。
3. 气泡 class 统一为 `msg user`（或补 `.msg.me` CSS，取改动小者）。
4. 核验 SSE 解析：`token` 取 `j.token`？——后端实际字段是 `delta`（chat/router.py:247）！若前端取 `j.token` 则**流式内容全空**，此为本任务最关键核验点；`done` 按嵌套壳取 `j.data.*`；`error` 事件分支按 C-B 契约预留（后端暂不发）。
5. 会话重命名/删除：删除已接 DELETE，重命名若后端无端点则隐藏按钮（不做假功能）。

## GWT 验收
- Given student token，When 发送一条消息，Then 流式 token 逐字渲染（Network 可见 token 事件且 delta 非空被追加），完成后助手消息完整、session 入列表。
- When 点击任一真实会话，Then 加载该会话 `/history`，**控制台无 TypeError**；When 点"新建"，Then 列表新增空会话且后端 `GET /api/chat/sessions` 可见。
- Given 无 token，When 打开 chat.html，Then 跳登录（现有行为保持）。
- 机验：`grep -n "j.token\|j.delta\|j.data" chat.html` 输出与后端契约（task114 冻结的 SSE 字段）一致；`grep -c "msg me" chat.html` 与 CSS 定义匹配。

## 风险
- token/delta 字段是"审计发现的高危嫌疑"，**开工后第一步实测**：curl -N POST /api/chat/stream 抓真实事件流再定改法，禁止凭猜。
