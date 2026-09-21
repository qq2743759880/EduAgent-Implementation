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
| **TO-EXEC-THEME-GATE** | 重塑底座：theme.css 定稿+Phosphor sprite+G3/G6-G9 门禁工具 | ✅ 闭环（7fed87f；编排者复核：HTML 零触碰/对比度亲算 8.84+5.43 吻合/sprite 30 枚零 emoji/G3 亲跑 PASS 25 页 1214 钩/325 截图实数/G8 硬失败语义 EXIT=1 正确；25 页实况纠偏 19 页口径被如实上报） | — |
| **TO-EXEC-PAGE-WAVES-A** | 逐页重塑包 A：学生端核心 8 页 | ✅ 闭环（8 页逐页 commit；编排者验收：G3 全站 PASS/G1 断点 0/learning G7 红=声明的 roving tabindex 豁免/主题字体 emoji 抽查过；变更单三条已裁：G7 聚合→GATE-V2、login G9 N/A→GATE-V2、seed 外链→DATA-SEED-1） | — |
| **TO-EXEC-PAGE-WAVES-B** | 逐页重塑包 B：学生端次级+chat 7 页 | ✅ 闭环（chat 补丁 52a28d7；自留档 after 证据 G6 6/0 全绿；achievements aria 漂移→GATE-V2 基线刷新） | — |
| **TO-EXEC-PAGE-WAVES-C** | 逐页重塑包 C：管理端 10 页（批款全黏土） | ✅ 闭环（10 页含 2 处 clay-light 降级点合规记录；零 API 页 N/A→GATE-V2；长文本债清零） | — |
| **TO-EXEC-GATE-V2** | 门禁第二批：radio/roving 聚合+settle+N/A 白名单+route-stable 形态钉死+console 诊断跟进 | **待派（三包验收沉淀）** | 中强模型 |
| **TO-EXEC-MIMOSA-EXCL** | 测试文件凭据排除（用户已批）+ AGENTS.md 勘误/PACK-C 报告代提交 | **待派（可并行）** | 中强模型 |
| **TO-EXEC-DATA-SEED-1** | 种子外链占位本地化（三核闸） | **待派（可并行）** | 中强模型 |

> 三包 25/25 页验收 PASS（G8 全站 dev 态+token 终态 0 failed）。三张后续单可并行带走。GATE-V2 验收后：全站 G6-G9 终扫 + G10 回滚实演 + UAT 十场景。
