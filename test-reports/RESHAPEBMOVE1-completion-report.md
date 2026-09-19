# W-NEXT-RESHAPEB-MOVE-001 完工报告（编排者亲自执行版——子 agent 出生即死(59s)后按新规接手，本报告交独立子 agent 审核）

- 执行者：编排者；审核者：待派独立子 agent
- 主体 commit：见 git log（接手前无 WIP——前任出生即死零改动）

## ① 任务
`POST /payment-notifications/channel`（PAY-GATE 062704a）语义归位：从 contracts/reshape-b.json（实为 MCP health-scan 契约，CANON-SYNC 披露错位）迁至 contracts/reshape-r-health.json 的 G3_trade_payment 组。用户裁定（四裁定之④）。

## ② 执行
1. **迁出 reshape-b.json**：endpoints 移除该端点；amendment PAY-GATE-346 原地标记 status=moved + moved_to + moved_at（留迁移溯源）；hash 重算=`677f038880d8…`（算法=sha256(json.dumps(去hash键,indent=2,sort_keys=True,ensure_ascii=False))，迁移前对现值复验 MATCH）。
2. **迁入 reshape-r-health.json**：G3_trade_payment 组+endpoints 增该端点（**root 路径原样**——实测路由无 /api 前缀，与 febe KNOWN_ROOT_PATHS/resolve_relative 解析兼容）；amendments 补 PAY-GATE-346 全链来源（062704a→CANON-SYNC e22a1c2→本归位）；hash 重算=`c9ccf7b670b5…`（同算法）。
3. **硬门实证（编排者亲跑）**：febe → `breakpoints=0 in_use_unfrozen=0 unfrozen_only=0 to_connect=72 frontend=144 backend=216 contracts=242 malformed=0`——**冻结效力迁移零损失**；febe 套件+pay 套件 60 passed；check-demo **绿 21/21+WARN ⑧⑩㉒**。

## ③ 过程登记
- check-demo 首跑 15/21（⑤⑦⑨ 红）=**3000 前端进程又死**（第 N 次自发死亡，fetch failed 全页）——重启生产形态（NEXT_PROD_DIST_DIR=.next-prod next start）后复跑 21/21。此死亡频率已由 STABILITY 看门狗覆盖 8000，**3000 无看门狗**——登记候选（下一批可扩 watchdog_3000 或并入现有脚本）。
- tests 侧 expected_ops（test_febe_contract_check.py:267）引用该端点于 NEXTJS_OPS 桶——canonical 桶未动，断言继续成立（60 passed）。

## ④ P0 自批判（4 条）
1. **端点路径双形态风险**：root 路径（无 /api）在 febe 的解析依赖 resolve_relative 兜底，后端离线时该条目会落 malformed（与姊妹 mock-notify 同型，CANON-SYNC P0-⑤ 已登记）——归位未消除此既有脆弱性。
2. **3000 无看门狗**：本次验收被前端死亡打断，同类问题重复出现才补——应主动扩防而非被动修。
3. **amendments 双文件同 id**：PAY-GATE-346 在 reshape-b（moved 标记）与 reshape-r-health（active）并存——溯源完整但消费方需按 status 过滤，未出机验。
4. 迁移未做契约消费方全扫（假设 febe 是唯一消费方——grep 证实，但未机制化）。

## ⑤ 移交
- watchdog_3000 候选（STABILITY 范式复用）
- 契约消费方清单机制化（febe 之外的解析者登记）
