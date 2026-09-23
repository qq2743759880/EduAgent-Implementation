# TO-EXEC-TA4 — 遗留测试数据清理（yy 十点修复 · P0 · 含 owner 过目停止点）

> 分支 `feature/opt-waves`。本开工令自包含。**本单有一个硬停止点：清理清单必须先交 owner 过目，未获批准不得执行任何删除/软删。**

## 背景

owner 实测反馈：管理端 RAG 调优控制台与 MCP 管理页「体验非常差，很多测试时遗留的无效数据」。演示面被测试残留污染。先例：T14 已用三核闸清理过 12 个 MCP 测试 server。

## 工作项

### 阶段 A：盘点（可立即开工）

只读扫描，产出《遗留数据清理清单》，逐项含：位置（库.表 / Milvus collection / Redis key 前缀）、判定为测试残留的依据（命名模式如 test/demo/seed 前缀、时间窗、与演示必要数据的冲突面）、行数、建议处置（软删/保留）、软删后对演示功能的影响评估。

扫描面（只读）：
- MySQL 3306：`question` 及题目关联表的脏数据（owner 点名「题目脏数据」）、RAG 相关表、knowledge/document 类表、`session_asset`/`session_video` 占位域**不在本次范围**（owner 未解冻，禁碰）。
- Milvus（192.168.85.101）：RAG 测试 collection（对照生产在用的 BGE-M3 collection，按命名与行数判别；先 `list_collections` + 各 collection 行数）。
- Redis 6377（**必须带 `docker exec` 前缀**，容器与 prisma-ai 共享——只清本项目 key 前缀，动前先列清单）。
- MongoDB（192.168.85.101）：三集合里的测试样例。

### 阶段 B：硬停止点

清单写盘 `.ai-hub/plans/artifacts/dispatch/TA4-清理清单.md`，**停手上报**，由 owner 过目批准。未获批准前阶段 C 禁止执行。

### 阶段 C：执行（仅获批准后）

- **三核闸**（每批次缺一不可）：① 执行前备份（mysqldump / pymilvus 导出 / RDB 片段，备份文件落 `deploy/backups/` 并在报告登记路径+大小）；② 软删后行数与备份记录一致性核对；③ 幂等性——重跑同批清理不产生二次变化。
- 软删优先（对齐项目既有软删口径），硬删仅限明显测试垃圾且 owner 清单里明示同意的项。
- 清理后回归：管理端 RAG 控制台与 MCP 页（`edu-frontend/public/admin-rag*.html`、`admin-mcp*.html`）重新加载，断言演示面无测试残留且正常数据仍在；跑 `scripts/gates/dom-hook-inventory.mjs --all --check` 确认 DOM 钩子零漂移（aria 快照随 DB 数据漂移的页按 G9 豁免口径处理，不硬刷绿）。

## 铁律

- 禁碰：`session_asset`/`session_video`、生产业务数据、`user_memory_event`/`user_memory`、代码文件（本单零代码改动）。
- SQL 一律参数绑定；禁 `DROP TABLE`/`TRUNCATE`；禁 reset Milvus collection（除非清单明示+owner 批准）。
- 不 push；阶段 C 后单 commit：`chore(db)/ta4: 遗留测试数据清理(三核闸,清单经 owner 批准)`（如零代码/零文件改动则仅交报告）。
- 与并行单 TA2（.env/手册）、TA1-3（chat.html/React chat）无文件交集。

## 报告

`.ai-hub/plans/artifacts/dispatch/REPORT-TA4.md`：清单要点、停止点时间线（提交清单时刻/批准时刻——批准由 owner 经信使传达）、每批三核闸证据（备份路径/行数核对/幂等复跑结果）、清理后两页回归证据。编排者将抽验备份可恢复性与行数。

## owner 验收口径（GWT）

Given 清单已经 owner 过目批准，When owner 打开管理端 RAG/MCP 页，Then 看不到测试残留数据，原有真实数据完好；备份文件可指认。
