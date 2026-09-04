# W2+ 优化批次收口（P0→P3 全量）— 20260904

> 编排者自动执行批次（用户授权自动审批 + 长时间自动执行）。全部经独立子 agent（强制消费 ponytail/tt/harden/review 资产）+ 编排者独立复验 + 逐项 commit。

## Commit 链（feature/opt-waves，倒序）

| commit  | 内容                                                 | 独立复验                   |
| ------- | -------------------------------------------------- | ---------------------- |
| 0c8d7e6 | **P3** task39 压测 / task35 Neo4j 图谱诊断 / task34 kb重建 | 复验 edu\_knowledge=2628 |
| d48735f | **P2** task114 W1C4 注册自动登录 + task114/115 契约收尾(0改动) | regSubmit 改动核查         |
| e86e7b8 | **P1-3** task32 评测集 5→30, BGE-M3 rank\@1=1.0       | result.json 30条全命中     |
| 37192df | **P1-1+P1-2** sort=popular + 视频章节CRUD              | curl 200/422 实测        |
| 94471c2 | **P0-2** task98 counts机构口径 + tests白名单门禁            | verify.py tests exit0  |
| 99fdc56 | **P0-1** task37 91失败→17 (idempotency body bug)     | 文件内容核验                 |

## 已闭环任务

- P0-1 task37(83→17)、P0-2 task98(机构口径+17项白名单)

- P1-1 热门榜 sort=popular(销量降序,422→200)、P1-2 视频章节CRUD(404→200)

- P1-3 task32 记忆召回评估集 5→30条, BGE-M3 rank\@1=1.0/recall\@3=1.0

- P2-1 W1-C4 注册自动登录(register无token→auto login→角色跳转)、P2-2 task114/115(0改动,有3项需决策)

- P3-1 task39(真实P95 50c=4.5s达标/100c=7.3s超标,连接池饱和指纹; Redis gap)、P3-2 task34(kb重建2647→2628走loader)、P3-3 task35(Neo4j连通但图谱空,APOC缺失,3项决策)、P3-4 task69(历史已完工已commit,非未开工)

## 需产品决策 / 待办（新登记）

1. **task35 3决策**：装APOC?/补种子范围?/type\_map标签口径?
2. **task34**：user\_1私有分区4条被重建丢弃(已备份 task34-user-partition-backup.json 可回滚)；verify.py user\_memory常量9≠80假阴性待修。
3. **task39**：Redis就绪后单独验收真Redis项；P95治理(池扩容/多worker/列表缓存待Redis)未做产品改动。
4. **P2-2**：旧烟测脚本断言已撤销page\_meta、前端src/ 冻结实现page\_meta?兼容声明，待清理。
5. **环境 gap**：Redis 6379 本机+192.168.85.101 均不可达（阻塞 task39 真Redis）。

## 说明

- Redis 不可达已如实登记，未造假真Redis命中/削峰数字。

- backend app 源码大量 untracked 为既存状态（历史分支丢失 14 分支悬空，工作区为唯一事实源），非本轮引入。

- 本批报告均含"资产消费证据"段 + agent×skill×workflow 矩阵。

