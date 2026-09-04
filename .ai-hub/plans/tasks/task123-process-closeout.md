# task123 — 流程收尾包（跨域）

- 域：MIX ｜ 平台：traework（调研）+ codex（复验）｜ 波次：W4 ｜ 依赖：各波次合入后
- 文件：流程/git/DB/部署，无业务功能

## 目标
清偿流程债与部署安全门，让下一迭代从干净基线开始。

## 证据（对应遗留 L 编号）
- L12：task43 缺完工报告/HTML APPROVED 记录，验收状态待核对。
- L13：task37 前端两个 commit（e3a1636、5bfdda0）落错分支，归属未处理。
- L17：测试种子残留（itest-newuser、itest-series 2629~2632、itest-sweep-* off_sale）。
- L20：critique-backlog-tracker 清单滞后（多项已闭环未勾选；task32 段 4 项真实未做）。
- L1：DEBUG 鉴权降级为部署阻断项（auth/dependencies.py:80-127 虚拟管理员后门）。
- 另：17 个 staged 文件长期未提交（critique-p0 披露）；根目录杂项（=1、=ro 等）未清理。

## 改动点
1. task43 核对：补齐完工报告或按现状重新验收，看板状态改齐。
2. commit 归属：cherry-pick 或确认已被 592c926 基线覆盖后关闭事项，结论写入 handoffs。
3. 种子清理 SQL：生成并执行 itest-* 清理脚本（先备份受影响表）；生产重建清单同步 deploy/mysql-init.sql 备注。
4. tracker 同步：逐条核对 critique-backlog-tracker.md，已闭环项勾选并注 commit 依据；真实未做项（task32 段评估补强等）保持未勾并排期。
5. **DEBUG=False 部署检查单**：`.env` 核对、无 token curl /api/users/me 必须 401、X-Force-Role 头无效验证、/api/metrics 鉴权生效（依赖 task113）——检查单落 deploy/README.md，出包前必跑。
6. 工作区卫生：17 个 staged 文件归位提交或明确丢弃；根目录杂项文件清理进 .gitignore 或删除（逐项列出再动）。

## GWT 验收
- 看板（D:\.ai-hub\memory\project-handoff.md）中 task43/37 归属条目状态更新且有依据链接。
- DB 实证：`SELECT count(*) FROM users WHERE account LIKE 'itest-%'` = 0（测试库）。
- tracker 文件：无"已闭环但未勾选"条目（逐条复核记录）。
- 部署检查单：DEBUG=False 下 `curl -s /api/users/me`（无头）→ 401；带 X-Force-Role: admin → 仍 401；检查单进入 deploy/README.md。
- git status 干净度：无长期 staged 未提交文件。

## 风险
- 删除种子数据是不可逆操作：先 `mysqldump` 备份再执行，SQL 脚本入 refactor_sql/ 留档（项目已有该目录惯例）。

## task61 验收时登记的遗留清理件（2026-09-02）
- Milvus 测试向量残留：_default 分区（系统数据，不删）；user_1 分区 4 行（task61 测试文档向量）——删除被拒因「partition is loaded」，需先 release 再 drop（pymilvus 两行），生产重建时一并清理。
- 后端 venv 已补装 pdfplumber 0.11.10（编排者验收动作，使契约⑥的 pdf 支持真实成立）——部署清单 deploy/README.md 需加该依赖，归 task123 检查单。
- 用户种子头像假域名：users profile 种子 avatar_url 含 cdn.example.com（task121 验收时发现，与课程封面同源）——生产重建种子需替换或置空。
