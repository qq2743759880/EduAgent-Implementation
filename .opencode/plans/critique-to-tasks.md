# 批判落实专项规划（Critique → Concrete Tasks）

> 建立：2026-08-28 ｜ 用户指出：批判文档生成但未落实到具体修改任务
> 原则：每条未闭环批判 → 一个具体可执行的修改任务（文件/模块/验收指标）
> 承接：critique-backlog-tracker.md 的扩展（覆盖生产级改造任务批判）

## 一、生产级改造任务未闭环批判 → 修改任务

### task-T1 批判（3 条未闭环）
| 批判 | 具体修改任务 | 落点文件 | 验收指标 |
|---|---|---|---|
| ① DB 枚举 ALTER 未执行 | **执行** `refactor_sql/task-T1-add-status-enum.sql`，并纳入发布流程 | MySQL mcp_tool_call_log | MANUAL_GUIDE/REJECTION_LIMIT 落库成功，无 try/except 吞错 |
| ② TOOL_FALLBACK_MAP 备用工具未注册 | 注册 calculator/search_knowledge 到 mcp_tool，或接子代理降级检索 | mcp_tool 表 + executor.py | 第 3 步 switch_tool 命中真实注册工具，非"未注册自然走指南" |
| ③ LLM 改写 args 仅窗口 | **窗口内实测** `TOOL_RETRY_LLM_REWRITE` 真实改写；或增强规则改写（参数名映射） | executor.py `_rewrite_args` | 窗口内真实改写成功 ≥1 例；规则改写映射表 ≥5 组 |

### task-S1 批判（3 条未闭环）
| 批判 | 具体修改任务 | 落点文件 | 验收指标 |
|---|---|---|---|
| ① HITL_ENABLED 默认 False 未启用 | 运维灰度启用：.env 设 HITL_ENABLED=True（先 exec_command/refund），补真实拦截实测 | .env + executor.py | exec_command/refund 真实拦截，未批准零执行 |
| ② hitl_approval 表未建 | **执行** `refactor_sql/task-S1-create-hitl-approval.sql` | MySQL hitl_approval | 建表成功，四审计字段可写 |
| ③ sweep 无定时挂接 | 接入后台调度（对齐 task-M1 memory_worker 模式） | service.py start_memory_worker | sweep_expired_pending 定时触发，过期 pending 自动拒绝 |

### task-R1 批判（3 条未闭环）
| 批判 | 具体修改任务 | 落点文件 | 验收指标 |
|---|---|---|---|
| ① fp16 批量噪声 | 评估 fp32 批处理或阈值校准（排序敏感场景） | reranker.py `rerank_pairs` | fp32 模式噪声 <1e-4；排序稳定 |
| ② sidecar 未部署 | 部署 uvicorn 8601 + 模型预热 + RERANK_SIDECAR_ENABLED=True 灰度 | 部署脚本 + rerank_service/main.py | sidecar /health 200，主链路走 sidecar |
| ③ Redis 队列可选 | 高峰流量评估后启用 RERANK_QUEUE_REDIS=True | queue_adapter.py | Redis 队列削峰生效，队满走降级不 500 |

### task-G1 批判（3 条未闭环）
| 批判 | 具体修改任务 | 落点文件 | 验收指标 |
|---|---|---|---|
| ① retry.py 未接真实调用点 | 接入 classify_error + next_backoff 到 generator.py/agent.py 实际重试路径 | generator.py + agent.py | 真实 429 触发指数退避；超时线性重试 |
| ② 60s 窗口边界 | task39 压测复测评估令牌桶 | guard.py TokenBudgetGuard | 令牌桶平滑，边界突发不超 |
| ③ 预估兜底 2000 | 强制 request_meta 传入，降低 ESTIMATE_DEFAULT_TOKENS 依赖 | guard.py `estimate_request_tokens` | 无 request_meta 调用告警；预估更精确 |

### task-O1 批判（3 条未闭环）
| 批判 | 具体修改任务 | 落点文件 | 验收指标 |
|---|---|---|---|
| ① 埋点调用点未全接入 | memory/executor/compaction 用 record_* 一行接入 | memory/service + executor + compaction | 四类事件真实产出到 OTel，trace 可查 |
| ② OTLP 非 protobuf | 接入 opentelemetry-exporter-otlp-proto-http（需真实后端） | otel/exporter.py | OTLP protobuf 投递成功 |
| ③ 跨实例聚合 | 接入 Prometheus/OTLP 后端 | metrics.py | 多实例指标聚合 |

## 二、C1/C2/M1 剩余批判（各 2 条）

### task-C1
| 批判 | 具体修改任务 | 验收 |
|---|---|---|
| ② graph 未装配 feature flag | 编排层注入 anchor_round + llm 到 compact_node | 真实对话启用锚定+动态选片段 |
| ③ 冻结区超阈值 | 监测冻结区 token 占比，超阈值告警/降 ANCHOR_ROUND | 冻结区占比可观测 |

### task-C2
| 批判 | 具体修改任务 | 验收 |
|---|---|---|
| ② TOOL_DEFERRED_MODE 灰度 | 灰度观察决策准确率，必要时回退 False | 决策准确率对比报告 |
| ③ schema_registry 跨实例 | 接入 Redis 共享（task-M2 协同） | 多实例 schema 一致 |

### task-M1
| 批判 | 具体修改任务 | 验收 |
|---|---|---|
| ② SQL 未建表冒烟 | 执行 patch_memory_event.sql + 验证真实读写 | user_memory_event 真实读写 |
| ③ 容量上限硬编码 | config 增加用户级容量配置 | 按用户活跃度动态调整 |

## 三、早期任务批判（task07~17 等，归入既有落点）

| 落点任务 | 承接批判 |
|---|---|
| **task37（清理/文档）** | task12 死代码 course_admin(39 处 curriculum_)、task14 answers_json、task15 test_auth 断言、task13 脚本 bug、task09 crud 覆盖率、task11 匿名 500、task17 幂等 IncompleteRead |
| **task39（压测）** | task16 HTTP 层并发、task10 契约遍历、task08 manager 403、task-VEC 冷启动预热、task31 首载 10.9s |
| **task98（验收体系）** | task07 CI 门禁/口径漂移、task10 断言统一、91 项预存失败 |
| **task34（kb 重建）** | task30 raw 双份存储、task32 云端 rerank 重跑 |
| **task69（E2E）** | task42 登录态/redirect、task59 预览/题型边界、task57 章节联调 |

## 四、执行优先级

| 批次 | 任务 | 理由 |
|---|---|---|
| **P0 立即** | T1①③/S1①③/R1②/G1①（窗口内 LLM 实测 + 部署启用）| 真实链路验证，卡测试窗口 |
| **P1 本周** | T1②/S1②/R1①/G1②③/O1①/C1②/C2③/M1②③（DB 建表 + 埋点接入 + 配置化）| 功能完备 |
| **P2 随主线** | O1②③/R1③/C1③/C2② + task37/39/98（依赖主线进度）| 收尾增强 |

> 注：本规划已更新 critique-backlog-tracker.md 覆盖生产级改造批判；具体任务执行时逐条对照验收。
### task-A1（Harness 抽象，2026-08-28 验收追加）
| 批判 | 具体修改任务 | 落点文件 | 验收指标 |
|---|---|---|---|
| ① 预处理节点未纳入接口 | 作为 task-E1 接口扩展：skill/compact/context_edit 纳入 Harness 可选钩子 | harness/base.py | 自定义 harness 可覆盖预处理节点 |
| ② 反向依赖 graph | 真搬迁：节点函数搬入 SixNodeHarness 方法体，graph.py 退化为纯构建器 | harness/sixnode.py + graph.py | 单向依赖；task24 契约零回归 |
| ③ 未知 impl 无 fallback | build_harness 加 fallback 到 sixnode + log warning；启动校验 HARNESS_IMPL | harness/registry.py | 未知 impl 不崩溃，降级 sixnode |
| ④ 拓扑锁定硬断言 | 抽 EXPECTED_SIXNODE_TOPOLOGY 常量，启动 fail-fast 自检 | graph.py | 拓扑漂移启动即暴露 |
### task-E1（影子模式，2026-08-28 验收追加）
| 批判 | 具体修改任务 | 落点文件 | 验收指标 |
|---|---|---|---|
| ① 影子默认规则重排 | set_shadow_variant 注入真实 rerank 参数变体，窗口内跑线上影子 | retriever.py | 真实变体影子对比落库 |
| ② 金丝雀窗口未持久化 | task-O1 指标库落地 started_at 窗口状态 | canary.py + otel | 重启后窗口续期 |
| ③ 4 维 Judge 未校准 | 窗口内真实 LLM 跑 judge_answer_4d 校准维度权重 | llm_judge.py | 真实评分报告 |
