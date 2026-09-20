# 派单协议（2026-09-20 起，用户裁定：执行者=其他平台 agent，用户任信使）

## 流程（六步闭环）

```
① 编排者（ZCode）写开工令 TO-EXEC-<ID>.md（自包含，执行者零上下文可开工）
② 用户把开工令全文复制给执行者（其他平台 agent）
③ 执行者在本仓库开工 → 单 commit（禁 push）→ 写 REPORT-<ID>.md
④ 用户把 REPORT 全文（+若报告引用了 diff/输出摘要则一并）带回贴给编排者
⑤ 编排者逐断言独立验收（跑测试/curl/git log/DB 实测，不采信报告文字）
⑥ 全 PASS → 记闭环；任一 FAIL → 编排者写 REWORK-<ID>.md → 用户带回 → 回到 ②
```

## 命名与位置

| 件 | 路径 | 谁写 |
|---|---|---|
| 开工令 | `.ai-hub/plans/artifacts/dispatch/TO-EXEC-<ID>.md` | 编排者 |
| 完工报告 | 同目录 `REPORT-<ID>.md` | 执行者 |
| 返工令 | 同目录 `REWORK-<ID>.md` | 编排者 |
| 验收结论 | 记入 tracker（.opencode/plans/critique-backlog-tracker.md）+ 对话汇报 | 编排者 |

## 每张开工令内置的铁律（执行者必读，违反=返工）

1. 禁 DB 直写；契约权威=后端 schemas.py/error_codes.py；响应壳 `{code:0,message,data}`
2. API key 只存在于 .env，禁写入报告/日志/commit
3. 只动开工令列明范围的文件；开工前后 `git branch --show-current` 对账（必须 feature/opt-waves）
4. 单 commit 禁 push；commit message 按开工令给定文本
5. 报告每条断言必须附编排者可复现的确切命令与真实输出摘录；「资产消费证据」与「批判承接核对」两段必备
6. 文档/注释里的接口描述只是初稿，一切以实读代码为准；发现锚点不符以代码为准并报告差异

## 当前派单板（用户按序带走）

| ID | 任务 | 状态 | 建议平台档位 |
|---|---|---|---|
| TO-EXEC-AUDIT-W1 | WRITE1 favorite_add 反向审核（只读验收） | ✅ 闭环（fa693b4，编排者复跑 111 passed 复证） | — |
| TO-EXEC-EVALFREEZE-B1 | idx31 组命中放宽变更单 + V3 尺契约冻结（用户已批） | ✅ 闭环（5ffe658，编排者指纹复核：双跑一致/毒性隔离仅 idx31/基线零漂移/draft:false） | — |
| TO-EXEC-GATEA-CLAY | 前端重塑 Gate A：3 页 × 3 黏土变体 | ✅ 闭环+批款（33c2b20；用户挑款：chat=B / login=B 弃紫改绿黄 / admin=C；禁 emoji 图标） | — |
| **TO-EXEC-THEME-GATE** | 重塑底座：theme.css 定稿+Phosphor sprite+G3/G6-G9 门禁工具 | **待派（当前最高优先）** | 强前端模型 |
| （待出）PAGE-WAVES | 逐页批量开工令 ×3（Gate A 底座验收后按域包发出） | 排队 | — |

> 并行建议：单张待派。Gate A 挑款已完成；THEME-GATE 验收后编排者立即出 PAGE-WAVES 三单。
