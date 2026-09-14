# dev-plan: EduAgent 重构批次 reshape-r v1.1(终审批判承接版)

> v1.0→v1.1:接受用户七条批判全量重排——评估基线前置 W0/R02 移出 W1 单独成波+双跑灰度/R03 迁移三问补设计/R23 降级实验并摘 KB 徽/漏接 P2 五条补入/TT §3§4§7 合规补齐。复扫核验:graph.py:785 thread_id、enqueue_turn 单输入、registry PROJECT_SKILLS 硬编码(注:AI_HUB 部分有 env 覆盖,批判引用已修正)均实证。

## 需求前提挑战
| # | Premise | Confirm |
|---|---------|---------|
| P1 | 三份冻结契约+SSE 契约重构期禁改;新契约只增不改旧 | agree |
| P2 | **测量先于手术**:W0 评估基线+双跑探针未冻结前,R02/R03 禁开工 | agree(终审缺陷①③承接) |
| P3 | 死代码=删除不留尸;R05 删旧路径的前置=双跑 diff 收敛,非仅 R02 验收 | agree(缺陷③) |
| P4 | KB 对标须语义对等:张冠李戴的徽章摘除(R23 重标注为"借鉴实验") | agree(缺陷⑤) |
| P5 | 禁 DB 直写;SQL 一律参数绑定;凭据只从 env;**服务端外发请求校验 host 拒 localhost/环回/私有地址**(Mimosa 硬约束,波及 webhook/外呼) | agree |
| P6 | 评估基线建立后即为回归门;**每任务派单前须有独立详档 tasks/taskRxx-*.md**(TT §3) | agree(缺陷⑦) |

4 问结论:Q1 为什么现在 三处 P0 断电+终审判定 v1.0 是"不建测量仪先动手术",必须先立测量 / Q2 现状 49 条审计+终审七缺陷,病灶行号复扫零漂移 / Q3 窄楔子 W0 两任务(基线+探针,1-2 天)→低风险抢修→R02 单波灰度→架构对齐;不做容器化/公网/前端大改 / Q4 未来适配 基线/探针/灰度框架为一切后续改动的永久测量设施,零废弃

## 任务分解(v1.1 波次)

### W0 测量仪(新增,R02/R03 之前必做;详档已生成 tasks/taskR20min/R20b)
**R20-min 评估基线冻结**(T3) 依赖:无。契约:**C-R-EVAL 提前至此冻结**(报告 JSON schema+阈值字段)。
- GWT:Given eval_set32;When 跑 hit_rate/mrr(口径对齐 LlamaIndex metrics.py);Then 基线 JSON 落仓库(contracts/rag-baseline-eval32.json)+阈值入配置;脚本 exit 0;**此后 R03/R02/R23 的一切对照以此为准,禁手动比对**。
**R20-b 双跑探针**(T3) 依赖:无。
- GWT:Given 100 条流式请求样本;When 同请求喂 run_agent_turn 与六节点图各跑一遍(离线批跑);Then diff 报告落盘(intent 分歧率/need_search 分歧率/docs 重合度/答案语义抽检),作为 R02 灰度收敛基准(P2-23 双规则分歧量化)。

### W1 低风险抢修(R02 已移出)
**R01 记忆 worker 通电**(T2) + **R01-b 记忆输入侧修复**(并入 R01 范围,P2-13 承接):enqueue_turn 改收 messages(含 assistant 回复,mem0 式最近 10 条上下文),worker 抽取输入从单 query 升级为对话窗。GWT 增:Given 一轮含问答的 chat;Then user_memory 行的内容同时覆盖用户偏好与助手事实性陈述。
**R04 MCP 调用修复+真测试**(T3) + **R04-b 落库脱敏**(并入 R04,P3-23/24 承接):mcp_server.env_json/http_headers_json 落库掩码;call_log args/result 敏感字段(密钥/手机号模式)脱敏。GWT 增:Given 造一个含 fake-key 的 header;Then DB 与 API 响应均不可见明文。
**R06 md5 修复 / R07 伪向量+IDOR**:同 v1.0。
**R03 chunk 唯一化+迁移**(T3+T1) **前置:W0 基线冻结**。v1.1 补三问设计:
- 写入策略:**一次性锁定窗口迁移**(上传任务队列暂停+拒绝新导入,窗口内只读;切换后新写全走新 ID;窗口预计分钟级,2631 行)。禁在线双写(重复召回风险即缺陷④所指)。
- schema 可行性:开工首步探查 Milvus 版本对存量 collection 加 scalar 支持;不支持→**dynamic field 承载新字段**(免全量重嵌;重建 collection 仅作最后手段并单独上报)。
- **canonical hash 输入=contextualize 之前的原始 chunk 文本**(契约写死;contextualize 前缀不参与 hash,杜绝将来开启导致 ID 漂移)。
- GWT(替换 v1.0 手动对照):迁移后重跑 R20-min,**hit_rate/mrr 相对基线偏差 ≤2%**(机验,超阈值=迁移回滚)。
**R08 skill 路径可移植**(T2,新增,P2-12 承接):PROJECT_SKILLS 硬编码绝对路径→env 驱动(SKILLS_PROJECT_DIR,缺省相对仓库根);AI_HUB_SKILLS_DIR 已有 env 保留。GWT:清空 env 后容器式相对路径启动,skill 扫描数>0;node --check/pytest 过。

### W2 R02 单独成波(带电换心脏,全灰度)
**R02 流式进图**(T3) 范围(v1.1 明示=重写而非抢修):执行体切 graph.astream+stream_mode 桥接 SSE 五事件+guard 移植+**TTFT 预算**(P2-17 承接:start→retrieval 间隔打点,新路径不得劣化超阈值,超了先优化图内快路径再灰度)。
- **R02-c thread_id 语义修复**(并入 R02,P2-8 承接):匿名请求不再共享 `task24-{user_id}`(graph.py:785)——每请求生成独立 thread_id 或强制 session_id;历史不串线。GWT:同用户两笔匿名请求,checkpoint key 不同且互不可见对方历史。
- **R02-b 双跑灰度**(缺陷③承接):STREAM_VIA_GRAPH=on 时同请求异步旁路双跑新旧路径(不影响响应延迟),diff 对 W0/R20-b 基线;**连续 N 天/千条差异收敛 <5%(intent/docs/答案三指标)才允许进 W3 删旧路径**;灰度报告每日落盘。
- 契约:C-R-SSE 沿用冻结禁改。GWT:task104 契约全绿+checkpoint key 实证+TTFT 打点报告+灰度 diff 报告四件齐。
- P2-9 修复顺带:flows/agent.py 重写时 plan 变量作用域修正(USE_AGENT_LOOP=False 不再 UnboundLocalError,单测覆盖)。

### W3 架构对齐(前置:双跑收敛)
**R05 删旧路径**(T2/T3) 前置:**R02 灰度收敛达标**(非仅 R02 验收)。GWT 增:删除后灰度探针复跑零引用旧路径,全量 pytest 零新增失败。
**R10 状态通道+引用回填 / R11+R11-F HITL / R13 停止条件 / R15 权限门+ACI**:同 v1.0;R15 设计升级见 PRD §5 v1.1(五层防御+确定性策略优先)。
**R12 LLM 工具决策接管**(T3) v1.1 增:**决策超时预算**(LLM 路由超时 N 秒→规则路由 fallback,防 TTFT 劣化);GWT 增:注入假慢 LLM,超时后按规则路由完成请求且延迟有界。

### W4 评估观测收口
**R21 faithfulness / R22 CI 门禁 / R24 trace JSONL**:同 v1.0。
**R23 三因子重排+真 HyDE**(T3) **降级为实验任务**(缺陷⑤承接,摘 KB 徽):[F-C02-005] 公式语义与文档检索不对等(课件无 importance 语义、知识无时效性),重标注为"借鉴实验";交付=**A/B 对照报告**(开关开 vs 关,各跑 eval_set32,以 R20 基线判收益),**无收益不默认启用**;真 HyDE 同框架实验。

## 契约冻结顺序(v1.1)
**C-R-EVAL(W0 最先)**→C-R-CHUNK(R03 前)→C-R-ACI(R15 前,R04 凭草案)→C-R-HITL(R11 前)。C-R-SSE 复用既有。冻结后禁改走变更单。

## TT 合规补齐(缺陷⑦承接)
- §3 详档:每任务派单前生成 tasks/taskRxx-*.md(W0 两份已随本版生成);**派发协议=编排者出交接 Prompt→用户转交执行 agent→完工后编排者独立复验**(用户裁定 2026-09-13,与历史矩阵 v1.3 同源);§4 开工 prompt 具名 skill/资产路径;§7 验收批判含竞品 URL+日期(见上批与 reshape-a 批判 4/4 URL 机验先例)。
- **review-gate 含金量声明(终审 D)**:其 PASS=文档格式合规(标题/占位/子段检查),不校验 GWT 可机验性/依赖闭环/URL 可达——方案正确性的首次真实验收=W0 两份数字(基线 JSON+双跑分歧报告),此前一切 PASS 仅为格式门。
- **Mimosa 出处(终审 E)**:Mimosa=本 ZCode 环境的安全扫描插件(mcp mimosa-security-scan+其 PreToolUse hook"生成前安全约束",本会话 hook 注入原文可溯)。PRD 引用的"SQL 参数绑定/SSRF host 校验/凭据仅 env"即其注入约束,非杜撰代号;追溯路径=会话 hook 输出+插件本体。

## 终审五问闭环(v1.1 补丁,2026-09-13)
- **A1 双跑统计洞**:temp=0 确定性强制+自跑稳定性预验;门槛指标收窄为 intent/docs 两项;答案抽检 30% 仅报告不入门槛(已改 taskR20b v1.1)。
- **A2 golden 现状**:编排者核实——build_eval_set32.py 在(golden=题目 chunk 自身 chunk_id,自动生成),**eval_set32.json 从未落盘**;W0 首步=跑生成器+5 条抽检,工期含此项。**新发现洞**:R03 改 chunk_id 会使冻结 golden 全量失配→基线 golden 双键(chunk_id+doc_sha256),迁移须输出 old→new id_map(入 C-R-CHUNK)。
- **B 迁移语义钉死**:C-R-CHUNK 契约加一句——"迁移=从 Milvus 读旧 chunk.content→计算新 ID→upsert 改 PK+scalar,**不重新 parse/chunk**(chunk 边界不变,向量原地)"。
- **C 五层防御拆任务**:①凭证 env/落库脱敏→R04-b ②**guard 三桩点(工具前/LLM 前/输出前)→新增 R15-b(W3)** ③权限门/HITL→R15/R11 ④沙箱容器级→**登记 C 批次占位 task-C-sandbox(tracker 可查),不入本 plan** ⑤审计→R24(+R04-b 脱敏)。
- **D 灰度门槛不留空**:R02-b 五条件推荐值入 C-R-EVAL 草案——**千条样本/连续 3 天/intent 分歧<5%/docs Jaccard>0.9/P95 TTFT 不劣化超阈值(阈值=旧路径实测+10%)**,五条全过才进 W3 删旧路;用户可调禁留空。

## 规划自审
### CEO 范围自审
- finding1:W0 前置使首交付延迟 1-2 天。处置:接受——终审判定无基线的后续验收皆可造假,W0 是信任成本不是工期成本;W0 与 R01/R04/R06/R07 可同波并行(互不依赖),实际零延迟。
- finding2:双跑灰度"连续 N 天"与开发节奏冲突。处置:N 可调(最少=千条样本收敛即达标),阈值与样本量入 C-R-EVAL 配置,用户可裁。
### Eng 架构自审
- finding1:R02-b 旁路双跑消耗双倍 LLM 配额。处置:旁路仅跑至 intent+docs 层(不重复生成答案,答案语义抽检 10%);配额护栏入灰度配置。
- finding2:Milvus dynamic field 承载 scalar 的过滤性能未知。处置:W1 探查步含 nprobe/filter 性能基准(对 R20 基线),不达标再评估重建。confidence: medium(新增依赖:双跑收敛的实测达成率;已设阈值闸与回退)。
### Design 体验自审
- finding1:TTFT 预算可能卡死 R02 上线。处置:阈值先实测旧路径分布再定(P50/P95 各+10% 容差),不设拍脑袋常数。
- finding2:灰度期间旁路失败不得污染用户路径。处置:旁路异常静默计数,不进主响应。
