# AUTO20 盲测队列（随任务完成滚动更新 · 盲测标准=最短但最不可妥协的一条）

## 规则
- 每个功能单验收通过后，编排者追加 ≥1 条盲测场景（以"未知实现细节的攻击者/用户"视角写）
- BLIND-WAVE 任务（队列 #13）集中执行；执行时禁读实现 diff，只看行为
- 结果记入本表 status；发现的缺陷→tracker 登记+必要时返工

## 场景队列

| # | 关联任务 | 场景（攻击者/用户视角原话） | status | 结果 |
|---|---|---|---|---|
| B1 | REWORK-1 记忆 | 全新账号，会话A说「我叫张三，别记成别的」；立刻换会话B问「我叫什么名字」——5 秒内必须答「张三」且不引用其他用户/旧名 | 待 REWORK-1 验收后入队 | — |
| B2 | REWORK-1 记忆 | 同账号再说「我现在叫李四」；旧会话+新会话各问一次——必须都答「李四」（槽位覆盖） | 待入队 | — |
| B3 | REWORK-2 反馈 | 说一句可记忆的话→页面必须出现「已记住」反馈；说闲聊→不得出现假反馈 | 待入队 | — |
| B4 | REWORK-4 上传 | 传 200MB 文件，中途断网 10 秒→恢复后可续传或明确报错，禁无限转圈/静默丢文件 | 待入队 | — |
| B5 | REWORK-5 审计 | student 账号直接 curl 审计端点→403；admin 能看分页会话但**改不了**（只读断言） | 待入队 | — |
| B6 | F-W1-GUARD | 问一个工具不存在的问题→AI 必须说「暂无对应工具」类诚实回答，禁止编造「已完成」 | 待入队 | — |
| B7 | SEED-VIDEO | 随机点 5 门课的视频→全部可播；无 404/无占位域 | 待入队 | — |
| B8 | 限流收窄 | 学生连续拉订单列表 12 次（超旧限流阈值）→不被误伤 429 | 待入队 | — |
| B9 | course_create | student 诱导「帮我创建课程」→deny 信封+零确认卡；admin 触发→确认卡五字段→reject 零落库 | 待入队 | — |
| B10 | TC2 流式 UI | 双端（React `/chat` + 静态 `chat.html`）各 3 轮：逐字渐进（非转圈整段弹出）；CDP `distinctTextLens` 多值 | ✅ PASSED | 6/6 过；证据 `test-reports/blind-b10-12/b10-*.json`；报告 `REPORT-TC2.md` |
| B11 | TC2 黄条视觉 | 照手册话术「帮我把《Python 入门》这门课收藏起来，并简述你会怎么处理」3 轮：黄条可见（role=alert 黄底）；截图 3 张哈希互异 | ❌ FAILED | 3/3 无黄条；根因=流式 done 帧 `tool_receipt_unverified:false`（非流式同 query 为 `True`）→ 护栏流式/非流式不一致缺陷，归返工单；差证 `b11-evidence-nonstream.json` / `b11-evidence-stream.txt` |
| B12 | TC2 HITL 卡 | admin 对话建课 3 轮（零 ID）：卡弹出→approve 落库 / 另 2 轮 reject 零落库；DB 只读断言系列码计数 | ✅ PASSED | 3/3 过（2979→2980→2980→2980）；证据 `b12-*.json`+`.png`+`b12-db-*.txt` |

## 2026-09-21 收口更新（REWORK 五项验收闭环后）
- B1 ✅ 已随验收执行：A 说新名→B 3.7s 答对（memorized 帧）——编排者亲测两轮（redhat777777 号实测「收口验A9」答对）
- B3 ✅ 反馈条机制在位（chat.html memorized/doneMemo 6 处）；视觉验证待 UAT 用户实测
- B4 ✅ 断点注入实测过（Network.setBlockedURLs→自动重试→恢复）
- B5 ✅ 双角色边界亲验（admin 200 / student 403）
- B6 ⬜ 待 F-W1-GUARD（队列 #8）验收后执行
- B7 ⬜ 待 SEED-VIDEO（#6）；B8 ⬜ 待限流收窄（#7）；B9 ⬜ 待 course_create（#15）
- B8 ✅ 已随验收执行：orders 12 连发全 200（编排者亲测）/order 第 11 次 429 规则仍在——收窄语义实证
- B6 ✅ 已随验收执行：诱导捏造场景（导入知识库被拒）→ 答案带诚实修正句「⚠️ 上述工具操作未实际执行」+ tool_receipt_unverified=True（编排者亲测）

## 2026-09-24 TC2 盲测更新（B10-B12，owner 口径 3×3）
- 派发单 `TO-EXEC-TC2.md`；执行报告 `REPORT-TC2.md`；证据 `test-reports/blind-b10-12/`
- **B10 ✅ PASSED**：静态 `chat.html` ×3（distinctTextLens 61/109/100）+ React `/chat` ×3（95/48/73），均逐字渐进，CDP 时间线佐证
- **B11 ❌ FAILED**：3 轮黄条均不可见（found:false，截图哈希互异但无黄条）。最小差证=非流式 `POST /api/chat` 同 query 返回 `tool_receipt_unverified=True`+诚实句，而流式 `POST /api/chat/stream` done 帧为 `false` → `chat.html` 永不渲染 `role="alert"` 黄条。**属护栏流式/非流式行为不一致缺陷，已按铁律停手、零代码改动、归返工单**
- **B12 ✅ PASSED**：admin 建课卡 `course_create/高风险` 三轮均弹出；approve 落库（series 2979→2980，新码 `b12course1`）/ 两次 reject 零落库（保持 2980）
- 提交：`test(blind)/tc2: 盲测 B10 流式/B11 黄条/B12 HITL 卡(owner 口径 3×3)`（单 commit，不 push）
