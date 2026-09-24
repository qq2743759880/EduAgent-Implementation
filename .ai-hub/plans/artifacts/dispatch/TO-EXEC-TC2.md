# TO-EXEC-TC2 — 盲测 B10-B12（yy · P2）

> 分支 `feature/opt-waves`。承接 `AUTO20/blind-test-queue.md`（B1-B9 已验）队列，新增三场景并执行。**服务重启只准用仓库根 `start-eduagent.cmd`；禁在执行者会话内 run_in_background 起服务（会随会话退出被杀）。** 禁 Playwright；UI 层用 CDP。

## 三个盲测场景（owner 口径=以用户能感知的现象为准，非接口字段）

| ID | 场景 | owner 口径判据 |
|---|---|---|
| B10 | 流式 UI 双端 | React `/chat` 与静态 `chat.html` 各 3 次：肉眼可见逐字渐进（非转圈后整段弹出）；CDP 时间线佐证 distinctTextLens 多值 |
| B11 | 黄条视觉 | 照手册话术「帮我把《Python 入门》这门课收藏起来，并简述你会怎么处理」3 次：黄条可见（role=alert 黄底）；截图 3 张哈希互异 |
| B12 | HITL 卡 | admin 对话建课 3 次（零 ID）：卡弹出→approve 落库/另 2 次 reject 零落库；DB 只读断言系列码计数 |

## 工作项

1. 三场景各执行 3 轮，证据落 `test-reports/blind-b10-12/`（CDP json+截图）。
2. 队列状态机更新：`AUTO20/blind-test-queue.md` 追加 B10-B12 行（PENDING→PASSED/FAILED+证据路径）。
3. 任一场景 3 轮未全过 → 停手上报（附复现脚本与最小差证），**禁自行改代码**（那归返工单）。

## 铁律

- 域：test-reports/blind-b10-12/ + 队列文件一节 + 报告。零代码改动；DB 只读；token 运行时注入禁落盘。
- 不 push；单 commit：`test(blind)/tc2: 盲测 B10 流式/B11 黄条/B12 HITL 卡(owner 口径 3×3)`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TC2.md`：9 轮判定表+证据清单。

## owner 验收口径

Given owner 亲手操作三场景各一次，Then 现象与盲测判定一致（逐字渲染/看到黄条/卡后同意出课拒绝不出课）。
