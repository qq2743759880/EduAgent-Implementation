# TO-EXEC-TB1 — 图谱推荐接线（yy 十点修复 · P1）

> 分支 `feature/opt-waves`；后端 9988 / Neo4j bolt://192.168.85.101:7687 在岗；`KG_EXPAND_ENABLED=true` 已生效（chat 检索第四通道已在用 Neo4j）。开工令自包含。

## 背景

owner 批评"缺图谱路必须修复"。现状：Neo4j 数据在（约 116.7 万 KP / 2854 Course）、driver 在（`app/database.py` `get_neo4j_driver`）、chat 检索侧 `kg_bridge.py` 已激活；**但推荐系统是孤儿模块**——`neo4j_engine.py`（真 Neo4j 查询代码）零接线，推荐 API 三端点（path/next/feedback）只用 MySQL 图。前提 P5 裁定：**先单测该模块直跑，坏了修模块再接线**。

## 工作项

1. **模块直跑先测**：不接线状态下用脚本直调 `neo4j_engine.py` 的查询函数（真实 Neo4j），断言返回非空、耗时 P95 可接受（≤2s）、异常可控。若查询过时/超时：修模块（如索引缺失、查询语句与现 schema 不匹配），记录修了什么。
2. **接线**：推荐 API 增加 Neo4j 图谱源——路径/下一课推荐响应新增 `source` 字段（`"neo4j"|"mysql"`），Neo4j 可用时优先/混入图谱候选；**Neo4j 停机必须降级 MySQL 图不报错**（超时熔断 ≤1s 内回退）。响应 schema 变更在本报告「契约冻结」小节先冻结再实现（下游 TB3 要展示）。
3. **开关**：`.env` 加 `KG_RECOMMEND_ENABLED=true`（默认 true=演示开；false=纯 MySQL 图）。**.env 编辑纪律：字节级保留（python rb/wb 或 surrogateescape+newline=''），禁 echo 追加**（历史事故：HITL_ENABLED 曾被 echo 粘进注释行）。
4. 自验：① 开关开——推荐响应含 `source:"neo4j"` 候选（curl 实测 + DB/图谱对照）；② 停 Neo4j（或临时改不可达地址验降级，验完还原）——响应仍 200 且 `source:"mysql"`，不抛 500；③ 开关关——行为与现状一致。

## 铁律

- 域：`app/recommender/`（或推荐模块实际路径）、`neo4j_engine.py`、新开关一行 `.env`。禁碰 `kg_bridge.py`/chat 检索链、`app/chat/`（TA5 在改并发槽）、前端（TB3 后接）。
- 简历措辞「三路融合」的修订**不在本单**（TC1 统一处理），勿改简历/手册。
- 不 push；单 commit：`feat(be)/tb1: 推荐系统接 Neo4j 图谱源(source 标注+停机降级+KG_RECOMMEND_ENABLED)`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TB1.md`：直跑证据、契约冻结小节、三条自验 curl 证据、模块修复清单。

## owner 验收口径

Given 演示环境，When owner 在前端看课程推荐，Then 推荐结果来自图谱（响应可见 source=neo4j）；拔掉 Neo4j 再点，推荐照样出（降级不报错）。
