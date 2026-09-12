# task19 优化修改方案(承接 task19-技术批判.md)

> 承接关系:每条对应 task19-技术批判.md 表格一行;不改后端契约(凡涉接口变更一律走变更单);本文件只列可落地动作,不重复批判论据。

| 承接 | 修改项 | 具体方案 | 验收指标 | 建议落点 | 优先级 |
|---|---|---|---|---|---|
| T19-1 | 检索线降级开关 + pgvector 收敛最小验证启动 | ① chat/RAG 页在 Milvus 断链(错误码 50000/50301)时切换"知识库暂不可用"降级文案,LLM 直答保留;② C 阶段 pgvector 里程碑占位升级为可执行:写 `_perf_pgvector_vs_milvus.py` 对比脚本(2629 条×2048 维,检索 P95+召回@10) | 关 VM 状态下 chat 页出降级文案而非异常;对比脚本产出报告且召回差 <5% 时给出退役建议 | 降级开关=B 批前端任务顺带;pgvector=C 阶段(依赖部署窗口) | P1 |
| T19-2 | series/1 慢查询定位 + Redis 读缓存 | ① explain 定位 /api/series/{id} 8~16s 慢因(疑 cohort 聚合/N+1);② 复用 task39 缓存基建(已实证 322.6ms→5.3ms)对 series 详情/列表加短 TTL 缓存(60s,演示数据低变更频率);③ check-demo 增 series/1 P95 探测项 | 缓存后 /api/series/1 P95<500ms;check-demo 新增探测项绿 | 后端小改,建议 B 批前热修窗口(不动契约) | P1 |
| T19-3 | 错误契约:依赖不可用类目 + 脱敏 | ① error_codes.py 增 50301 DEPENDENCY_UNAVAILABLE,HTTP 503;② Milvus/Mongo/Redis 连接异常在中间层转译,message 脱敏("知识库服务暂不可用"),内部 detail 进日志;③ admin 知识库页按 503 渲染降级横幅 | 停 Milvus 后 /api/knowledge/partitions 返回 503+code 50301+无内网拓扑泄漏;pytest 契约用例 1 条锁行为 | 后端+error_codes,走小变更单(新增码不破坏存量) | P1 |
| T19-4 | B0 审计立即开工 + admin 聚合端点变更单 | ① B0 选型审计(Refine vs react-admin,含 DEMO spike 与 dataProvider 隐藏工作量)按 v3 计划启动,产出审计文档+选型冻结;② admin 仪表盘缺口(订单数/营收/热门课程榜聚合)立契约变更单进 B 契约,补 GET /api/admin/trade/overview;③ B3 验收沿用可证伪判据(代码量<静态页 1/3) | B0 审计文档冻结;B3 admin-users Refine 版代码量<静态页 1/3;聚合端点进 reshape-b 增补 | B0/B1a(B 批已规划,前置 task19 即本报告) | P2 |

## 执行顺序建议
T19-2(热修,演示前性价比最高)→ T19-3(半天,安全卫生)→ T19-4(B0 立即并行)→ T19-1 ①(降级开关随 B 批前端);T19-1 ② pgvector 维持 C 阶段窗口。
