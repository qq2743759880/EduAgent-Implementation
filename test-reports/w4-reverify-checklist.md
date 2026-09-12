# W4 复验门清单（P2-11 / P2-15）

> 落点来源：critique-backlog-tracker.md 末尾 P2-11「四任务真实探活缺位被标 PASS」、P2-15「DONE 口径混淆——两轴修正」。
> **两轴 DONE 口径**：代码侧 DONE（task19 达成）≠ 演示侧 DONE（本清单全绿前，**不得进 B 批实施**）。
> 建立日期：2026-09-12（H 热修波）。复验通过后在本文件登记日期与证据链接。

## 一、复验门定义（5 道，按序）

| # | 门 | 内容 | 判定 |
|---|-----|------|------|
| G1 | VM 在线 | VMware 虚拟机 192.168.85.101 可达（Milvus 19530 / Mongo 27017 / MinIO 9000 / Neo4j 7687） | 四端点全部连通 |
| G2 | Docker Desktop → Redis | 本机 Docker Desktop 运行且 Redis 容器 up（`docker start <redis容器>`；当前容器未跑=降级） | `redis-cli ping` → PONG；`GET /health/detail` redis=ok |
| G3 | check-demo 8/8 | `edu-agent/scripts/check-demo.mjs` 八项：①Milvus ②Redis ③Mongo ④8000 health ⑤3000 首页 ⑥登录链路 ⑦关键页 200×N ⑧advisory:DEBUG 虚拟管理员探测 | ①~⑦ 全 PASS；⑧ 按 P1-8 应升 FAIL 语义（待接线，见"待办"） |
| G4 | L6 RAG 链路 | 检索链路（BGE-M3 embedding→Milvus→rerank→chat 引用）live 打靶 | 检索返回真实引用、P95 达标（WAVE 批已实证） |
| G5 | P2-11 四项 live 复验 | task16 优惠券 / task17 订单 / task06 视频 3MB 链路 / task18 演示检查单——四任务此前"真实探活缺位被标 PASS"，须在演示机全绿后逐项重打 | 四项各自契约打靶全过并留证据 |

## 二、执行步骤

```text
1. G1  开 VMware → curl/ping 192.168.85.101:19530/27017/9000/7687（或跑 check-demo 看①③）
2. G2  开 Docker Desktop → docker ps 找 redis 容器 → docker start <name>
       → docker exec <name> redis-cli ping == PONG
       → GET http://127.0.0.1:8000/health/detail 中 redis=ok
       （注意：Redis 恢复后，进程级快断窗最长 30s 内仍降级直通，等一个探测周期再测）
3. G3  node edu-agent/scripts/check-demo.mjs → 八项结果截图/存档
4. G4  RAG 打靶：POST /api/chat/stream（query 含知识库检索预期）→ retrieval 事件真实引用；
       或复用 WAVE 批脚本 test-reports/WAVE-critique-indep-acceptance-report.md 的 R 组用例
5. G5  四项逐个重打：
       - task16：登录 user000001 → GET /api/coupons（unused）→ POST /api/trade/coupon/receive
       - task17：创建订单（真系列真班次）→ 列表/详情 6 态筛选（演示库用真数据，禁再留 pending 残留）
       - task06：learning.html 分片上传 3MB→finalize→bind→GET /media 200（已有真实链路，重打确认）
       - task18：跑 check-demo.mjs 即 G3（本项与 G3 合并判定，但需在 G1/G2 全绿的"真实环境"下跑）
6. 全部通过 → 本文件登记复验日期 + 证据路径 → 宣告"演示侧 DONE" → 才可进 B 批
```

## 三、判定总则

- 任一门红 → 演示侧 DONE 不成立；红项按 check-demo 的"一句话处置"处理后**整门重跑**（不许跳项）。
- G3 在 Redis/VM 降级态跑出的 PASS **不算数**（探活缺位正是 P2-11 批判点）——必须在真实全绿环境跑。
- 复验过程产生的新测试数据须即用即清（H2b `scripts/cleanup_demo_residues.py` 口径），不得再欠账。

## 四、当前进度（2026-09-12，H 热修波收口时点）

| 门 | 状态 | 证据/说明 |
|----|------|-----------|
| G1 VM | **✓ 在线**（当日实测） | 8001 临时实例 lifespan：Milvus/Mongo/MinIO/Neo4j 全 `ok`（2026-09-12 17:05 启动日志） |
| G2 Redis | **✗ 未过**（容器未跑，降级态） | `init_redis: Error 22 ... 拒绝网络连接`；H1a 快断窗生效中（限流/缓存毫秒级降级，不阻塞请求路径） |
| G3 check-demo 8/8 | **✗ 未过**（最近记录 5/8，task19 批判当日） | Milvus/Mongo 随 VM 恢复后需重跑；Redis 待 G2；⑧ 升 FAIL 语义待接线 |
| G4 L6 RAG | **✓ 已过**（WAVE 批独立实证） | `test-reports/WAVE-critique-indep-acceptance-report.md`（R 组） |
| G5 四项复验 | **✗ 未开始** | 等 G1+G2+G3 全绿后执行（P2-12：现状由执行 agent 开工前 grep/curl 核实） |

## 五、门上待办（复验前须接线的小项）

- [ ] check-demo ⑧ 升 FAIL 语义（P1-8 配套：后端启动硬门禁已由 H1b 落地，检查单探测项语义从 advisory WARN 改 FAIL）
- [ ] G5 四项打靶脚本落盘 `test-reports/`（复用既有契约测试风格：真实 HTTP + 唯一前缀 + teardown）
