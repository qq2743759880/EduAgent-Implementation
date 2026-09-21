# REPORT-REWORK-FEAT-WIRE-V2 — 返工令 5 项（P0-1~P0-6）完工报告

- 分支：`feature/opt-waves`（对账一致）；全部未 push；分项独立 commit（5 个）
- 必读输入已消费：`test-reports/ORCH-AUDIT-feat-wire-v2.md` 全文（6 个 P0 锚点逐项落地）
- 工具链沿用：`scripts/gates/_shared.mjs` CDP（Token 注入/截图/网络差分），脚本与证据在 `test-reports/feat-wire-v2/`

## Commits

| commit | 内容 |
|---|---|
| 22169b9 | fix(be) P0-1+P0-6 记忆链路（槽位语义+召回最新优先+同步抽取+治理三核闸） |
| a74ea59 | fix(fe) P0-2 答后记忆反馈条 |
| 6c721d4 | fix(fe) P0-3 83 委托元素点击差分（3 处真死链当场修） |
| e4dad35 | fix(fe) P0-4 100MB 全链+失败注入+可重试 UI |
| 4aa7bff | feat(admin) P0-5 会话审计只读视图 |

---

## P0-1 + P0-6（一起修，记忆链路）✅

**四层修复**（后端 6 文件）：
1. **槽位 update 语义**（append-only 达成）：`ingest.detect_memory_slot/slot_like_patterns`（名字槽位=user_name）+ `event_persistence.close_slot_heads`（同槽位旧 HEAD **仅 valid_to 盖章**——不 UPDATE 内容、不追加 delete 事件）+ `store.write` 落库即关同槽位旧实体并同步删向量。
2. **召回同槽位最新优先**：`store.recall` 同槽位多条命中只留最新（id 最大）+ **3 倍过采样**——修掉 audit"45 秒后随机换名"的隐藏根因：治理只盖 SQL 章后，死向量仍占满 top_k 再被 HEAD 过滤清空 → 召回假空。
3. **提取前置（5 秒验收的机制）**：`memory/service.sync_extract_and_write` 在 chat `build_finalize` 内**同步**规则抽取并立即写库（done 帧前完成，毫秒级）；LLM 深抽取仍走异步队列且 `skip_rule_extract` 防同 content 重复入库；`MEMORY_SYNC_EXTRACT_ENABLED` 可配置降级。
4. **演示账号治理三核闸**（`d06-governance.py` + `d06-vector-cleanup.py`）：9 条冲突记忆（4 组旧名+「我的名字」+「什么名字」误报+「改成 999999」残留）全量备份 → valid_to 盖章（更新行数=备份行数 9/9）→ 模式 HEAD 残留=0 → 幂等重跑 0 变更；Milvus 死向量补删 14/14。

**验收（编排者可复现：`node test-reports/feat-wire-v2/r-p01-verify.mjs`，双跑通过）**：
```
A 会话「我叫返工验收员5040，请记住我的名字」→ done 帧 memorized=[整句,用户名字：返工验收员5040]
→ B 会话（A 完成后 ~2s 提问）「我叫什么名字？」→ 答「你叫返工验收员5040。」RECALL_HIT: true
DB 终态：名字槽位 17 行历史、恰好 1 个 HEAD（用户名字：返工验收员5040），其余全 valid_to 盖章
```
- 提取延迟说明：记忆在 **A 的 done 帧时刻已可召回**（同步落库），B 提问间隔≥0s 即可答对；A done 总时长含 LLM 流式（本轮 43s 属模型侧波动），非记忆链路延迟。
- pytest：`tests/test_memory_slot_semantics.py` 5 用例（盖章 append-only 断言/召回最新优先/同步落库/开关降级）；回归子集 **199 passed**（TEST_BASE=9988；另修 `test_course_domain.py` BASE 支持 TEST_BASE 覆盖——该文件此前硬编码已死的 8000）。

## P0-2 答后反馈条 ✅
- done 帧新增 `memorized: [...]`（同步抽取落库成功时）→ chat.html AI 气泡尾部渲染「💾已记住：…」绿条（无落库不显示）。
- **踩坑修正**：`renderStream(true)` 是整体 innerHTML 重写，反馈条先追加会被抹掉——改为渲染后追加（doneMemo 缓存）。
- 验收截图：`shots/r-p01-session-a-memobar.jpg`（绿条可见，黏土主题）。

## P0-3 83 个 delegated 元素点击差分 ✅
- **三轮扫描**（初扫 → 文本精确匹配重测修"querySelector 首个匹配"错位 → 修复 MutationObserver document-start 时序（documentElement 为 null 致观察器全挂、mut 恒 0 的测量假阴性）后重测）。
- **终判**（`matrix/delegated-differential.json`）：83 = **47 wired**（26 网络/导航证据 + 21 DOM 变异证据）+ **13 disabled-by-design**（分页边界/未选班次）+ **14 prototype-honest**（admin-users-refine-proto 为零 script 孤儿静态稿，页内已公示「纯静态原型·零 script·不发请求」）+ **3 fixed-this-rework**。
- **3 处真死链当场修 + CDP 复验**：
  1. admin-rag-upload 审计分页 cur 按钮 → 补绑定 `refreshRagAudit(ragAuditPage)`（复点触发刷新实证）
  2. admin-mcp 调用日志页码按钮 → 补绑定 `loadLog()`（复点日志刷新实证）
  3. admin-question-detail 选项删除按钮 → `window.delOpt` 已定义但渲染后**从未绑定** → renderOpts 后补 onclick（注入内容→点×→内容清除实证；最少 4 行为设计守卫）

## P0-4 ≥100MB 全链 + 失败注入 ✅
- **可重试 UI**（admin-course-detail.html）：分片级自动重试（同分片最多重发 2 次，轨迹入时间线）+ 失败态「↻ 重试上传」按钮（`S.uploadFile` 保留原文件，点击整链重传）。
- **CDP 实测**（`r-p04-verify.mjs`，ffmpeg 生成 114,069,910B ≈108.8MB / 22 分片）：
  ```
  阶段1 Network.setBlockedURLs 阻断 upload-chunk → 分片0 自动重试 2 次（时间线 bad 轨迹）
        → 错误态「已自动重试 2 次，可点下方重试整链」+ 重试按钮截图（r-p04-fail-retry-ui.jpg）
  阶段2 解除阻断 → 点重试 → 69%→100% → finalize→bind→转码完成（r-p04-retry-done.jpg）
  落盘：data/media/videos/VID-20260921-D6F0193A.mp4 = 114,069,910B；同源 GET 200 video/mp4 全量
  ```
- 截图组：fail-retry-ui / retry-progress / retry-done。

## P0-5 管理端会话审计只读视图 ✅
- **后端**（新 `app/admin/chat_audit/router.py`，main.py 注册）：
  - `GET /api/admin/chat-audit/sessions?user_id&page&page_size` → 裸分页 DTO；`GET /api/admin/chat-audit/sessions/{sid}/history?limit` → 只读历史；
  - 路由级 `require_role([UserRole.ADMIN])` **服务端角色硬校验**；纯只读（无写端点）；开发中自测发现并修正 LIMIT/OFFSET 参数序反置、Pydantic datetime 字段两处缺陷。
- **前端**：新 `admin-chat-audit.html`（审计用途红色横幅「只读·无任何修改删除能力·ADMIN 专属授权面」+ user_id 过滤 + 分页 + 历史抽屉，黏土主题）；8 个 admin 页 gnav 增「会话审计」入口。
- **pytest**（`tests/test_chat_audit.py` 5 passed）：student 列表/历史 403；分页壳+user_id 过滤不泄漏；admin 读学员历史；404 壳。
- **双角色 CDP 验收**（`shots/r-p05-audit-admin.jpg` / `r-p05-audit-history.jpg` / `r-p05-audit-student-blocked.jpg`）：
  ```
  admin：316 会话/20 行、审计横幅、历史抽屉实开（学员「我叫什么名字？」会话消息渲染）
  student：页面守卫跳转 dashboard + 直连 API 403 —— 隔离边界双侧实证
  ```

---

## 铁律对账
- user_memory_event append-only：全程只 valid_to 盖章（单测断言旧行内容原样保留、无 delete 事件追加）；无任何旧行内容 UPDATE；无物理删除。
- SQL 全参数绑定（治理脚本 LIKE 模式亦参数化）；后端修配 pytest（新增 test_memory_slot_semantics 5 + test_chat_audit 5）；回归子集 199 passed。
- 不 push；5 个分项 commit；报告本文件。

## 诚实披露
1. **8000 live 实例已坏**：全仓 live 契约测试默认 TEST_BASE=127.0.0.1:8000（端口迁移后无服务，看门狗多次重启未稳定）——本轮将该口径统一为可覆盖并默认指向 9988 跑通；编排者复跑回归请带 `TEST_BASE=http://127.0.0.1:9988`（或修复 8000 watchdog，属环境运维项，未擅动）。
2. P0-1 验收脚本中"A→B 间隔"打印值为 B 的回答生成时长（LLM 波动 7~42s）；5 秒口径的实际语义=A done 后 B 立即提问（脚本 ~2s）即答对，记忆可用性在 A 的 done 帧已达成。
3. A 会话内模型仍会自称"无写入记忆工具"（模型层认知），但平台侧同步抽取已落库且反馈条可见——非缺陷，如实登记防误判。
4. Mimosa 预扫描持续 `scanner_enobufs` fail-open（与上一单相同），本轮 commit 未经完整安全扫描背书，全量审计仍待重跑。
