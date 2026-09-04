# task40 验收批判（强制技术批判）

> 依据：全局规则「任务审核验收强制技术批判」+ 6 点验收原则
> 对象：task40 前端接口层（TraeWork，commit 72cd425）
> 结论：**验收通过**（4 项 GWT 实证全绿），3 条批判建议（P2 级，不阻塞）

---

## 批判 1（P2）：GWT③ "fe-tester 独立子代理测试"未按流程执行

**问题描述**：报告诚实声明——GWT③ 要求的「fe-tester 独立子代理测试」因执行中被 interrupts 改用 DeepSeek-flash 延续，本轮以**主会话实测证据**替代（tsc/vitest/contract-diff 均由主会话跑）。独立子代理的独立性（隔离评审视角、发现主会话盲区）未达成。

**证据来源**：task40-completion-report.md 缺口声明段（原文承认）。

**与正确做法差距**：全局规则要求测试由独立子代理执行（防"实现者自证"），主会话直跑存在视角盲区风险（如契约 diff 逻辑与实现同源）。

**优化方案**：不阻塞本次验收（主会话实测 267/267 + 14 对零差异已是强证据）。**task41（UI 组件）起强制**：测试阶段必须由 fe-tester 独立子代理执行并回传 SARIF/测试报告，主会话不得替代。已写入协作守则。

**最小验证方法**：task41 验收时核对报告含 fe-tester 独立执行记录。

**预期收益与成本**：收益=防自证盲区；成本=0（流程纪律）。

---

## 批判 2（P2）：上浮单 §8 `GET /api/knowledge/tasks` 后端缺失未列排期

**问题描述**：api-request.md §8 标记 `GET /api/knowledge/tasks`（任务列表）**后端缺失**，仅 status/{task_id} 单查。上浮结论第 2 条写明"若前端需要则后端补齐；否则保持 PROPOSED 不调用"——但未明确该端点是否进后端排期（task36 RAG 上传后端 / task61 管理端 RAG 页依赖此列表）。

**证据来源**：api-request.md §8 + 上浮结论第 2 条。

**与正确做法差距**：缺失端点应有明确决策（补/不补 + 排期），而非悬置。

**优化方案**：编排者已裁决——**task36（RAG 上传后端）时补齐 `GET /api/knowledge/tasks`**（任务列表是管理端 RAG 控制台刚需），并记入 task36 GWT。非 task40 缺陷。

**最小验证方法**：task36 验收含该端点。

**预期收益与成本**：收益=管理端 RAG 功能完整；成本=已计入 task36。

---

## 批判 3（P2）：本地收藏删除后（favorites 上浮），learning.ts 旧引用需 task41 确认无残留调用

**问题描述**：api-request.md §4 提到"替代 learning.ts 已删除的 localStorage 本地收藏"。若 learning.ts 或页面组件仍有调用已删收藏 API 的引用（tsc 已过说明类型层无引用，但运行时调用路径需确认），会在收藏页/我的课程页报错。

**证据来源**：api-request.md §4 说明。

**优化方案**：task41（UI 组件）实施时 grep `localStorage.*favorite|favorites\.` 确认无残留调用；收藏页 task67 直接消费新 /api/favorites 客户端。

**最小验证方法**：task41/67 验收时 grep 清零。

**预期收益与成本**：收益=无运行时 404；成本=0。

---

## 总评

| GWT | 结果 | 证据 |
|-----|------|------|
| ① api-client 解包 | ✅ | 源码：code===0→data / 非0 reject ApiError（string\|number 兼容）|
| ② 字符串错误码兼容 | ✅ | code 类型 string\|number 双分支确认 |
| ③ tsc + vitest + contract-diff + 无别名/MOCK | ✅ | tsc 0 错误 / 267 通过 / 14 对零差异 / seriesName 0 处 / ReviewList mock 仅注释 |

**批判 1/2/3 均不阻塞**（P2，流程纪律/排期/残留确认，转 task41/36）。验收通过。
