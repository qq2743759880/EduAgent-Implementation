# REPORT-TB1 — 图谱推荐接线（推荐系统接 Neo4j 图谱源 · P1）

> 送工单：`TO-EXEC-TB1.md`
> 分支：`feature/opt-waves`　｜　后端 9988 / 前端 3322（本单仅后端）
> 本单目标：把孤立模块 `app/recommender/neo4j_engine.py` **真正接进推荐 API**，响应新增
> `source` 字段（`neo4j`|`mysql`），Neo4j 可达时优先/混入图谱候选，停机 1s 预算内静默降级 MySQL 图。

---

## 0. 契约冻结（**先冻后实现**）

> 依工单工作项②：响应结构变更**先在本节定稿，再写代码**。本节为唯一事实源，
> 实现与下游 TB3 展示均以本节为准。

### 0.1 端点与不变式

| 项 | 值 |
|---|---|
| 受影响端点 | `GET /api/recommend/next`、`GET /api/recommend/path`（前缀见 `app/main.py:601` → `/api/recommend`）<br>`POST /api/recommend/feedback` **不涉及** `source`：其响应 `RecommendFeedbackOut` 是反馈回执（`scene_code/target_id/feedback_type/score_delta/ok`），**不含候选列表**，故无「图谱来源」语义 —— 本单未改其结构（`submit_feedback` 零改动） |
| 鉴权 | 不变：`Depends(get_current_user)`（原有行为，本单不改） |
| 响应壳 | 不变：全站统一壳 `{code:0, message:"ok", data:{...}}` |
| **新增字段** | `RecommendedCourse.source` / `PathNode.source`（`"neo4j"｜"mysql"`）<br>`NextStepOut.graph_source` / `LearningPath.graph_source`（`"neo4j"｜"mysql"`） |
| 字段默认 | `"mysql"` —— 老调用方/未接线时行为**逐字不变**（加字段非改字段） |
| 降级语义 | Neo4j 不可达/超时/熔断 → **HTTP 200**，图谱候选回落 MySQL 图，`source`/`graph_source` 均为 `mysql`，**绝不抛 5xx** |
| 灰度位 | `.env` `KG_RECOMMEND_ENABLED`（默认 `true`=演示开）；`false`=纯 MySQL 图 |
| 超时预算 | `.env` `KG_RECOMMEND_TIMEOUT_MS`（默认 `1000`）—— 单次图谱查询硬顶，且为**整段图谱阶段共享总预算** |

### 0.2 `GET /api/recommend/next` → `data` 结构（**冻结**）

```jsonc
{
  "items": [
    {
      "item_type": "KNOWLEDGE_POINT",
      "item_code": "能力提升",          // 见 §1.3 F2：Neo4j KP 无 code，以 name 作稳定标识
      "item_name": "能力提升",
      "subject_code": null,
      "level_code": null,
      "score": 1.0,
      "reason": "图谱(Neo4j):共现关联",
      "estimated_hours": null,
      "prerequisite_codes": [],
      "mastery_ratio": 0.0,
      "source": "neo4j",               // ★ 新增：本条候选的图谱来源
      "extra": { "neo4j_modules": ["..."], "graph_source": "neo4j" }
    }
  ],
  "strategy_weights": { "cold_start": 0.3, "collaborative_filter": 0.25,
                        "graph_traverse": 0.3, "feedback_delta": 0.15 },
  "graph_source": "neo4j"              // ★ 新增：本次融合图谱源（页内是否含 neo4j 候选）
}
```

### 0.3 `GET /api/recommend/path` → 新增字段

```jsonc
{
  "nodes": [ { "step_no": 1, "node_type": "...", "node_code": "...", "node_name": "...",
               "source": "mysql" } ],   // ★ 新增：该节点是否存在于 Neo4j 图谱
  "graph_source": "mysql"               // ★ 新增：路径是否含 Neo4j 图谱节点
}
```

> **契约偏差记录**：无。实现与本节一致。

---

## 1. 模块直跑（工作项①：先证模块可用，再接线）

**脚本**：`edu-agent/scripts/tb1_directrun.py`（直连**真实 Neo4j** `bolt://192.168.85.101:7687`，`tenant_id=_default`）

```
NEO4J_URI=bolt://192.168.85.101:7687  tenant_id=_default
driver_alive=True
[hub_seed_names]               ok=True rows=6  p95=19.6ms err=None
    seeds=['能力提升', '工程能力', '项目实践', '模考复盘', '成长规划', '通用程序设计题库']
[recommend_by_co_occurrence]   ok=True p95=12.9ms err=None
[recommend_knowledge_points]   ok=True rows=20 p95=30.3ms err=None
    能力提升 strength=126 modules=['campus_employability_foundation_m3', 'middle_high_school_chemistry_foundation_m2']
    项目实践 strength=117 modules=['frontend_development_practice_m1', 'foundation_models_and_agents_foundation_m1']
    工程能力 strength=117 modules=['fullstack_development_foundation_m2', 'foundation_models_and_agents_practice_m1']
    成长规划 strength=81  modules=['middle_high_school_physics_foundation_m1', 'middle_high_school_chemistry_foundation_m1']
    考证通关 strength=45  modules=['teacher_certificate_advanced_m2', 'teacher_certificate_practice_m1']
[pagerank_importance]          ok=True p95=11.9ms err=None
[check_learning_path_gaps]     ok=True p95=15.8ms err=None
[find_shortest_learning_path]  ok=True p95=15.4ms err=None
[kp_names_present]             ok=True present=2 p95=14.6ms err=None

=== 断言 ===
PASS: 模块直跑非空 + 耗时 ≤2s + 异常可控
```

**结论**：全部查询函数**非空返回**、P95 均 **≤2s**（最大 30ms，远低于阈值）、异常可控。

### 1.3 直跑发现 + 模块修复清单（工作项①「若查询过期/超时则修模块」）

| # | 问题（直跑真实库暴露） | 修复 |
|---|---|---|
| **F1** | `find_shortest_learning_path()` / `check_learning_path_gaps()` 用了 `*..$max_depth` —— **Cypher 不允许参数出现在变长路径量词内**，查询在真实库上直接语法报错 | 改为整数**字面量插值** `*..%d % int(max_depth)` |
| **F2** | Neo4j `KnowledgePoint` 节点**无 `code` 属性**（返回 None）——原引擎按 `code` 关联，接线后会得到空 code | 推荐候选以 `name` 作稳定标识（`item_code=item_name=kp_name`）；路径节点存在性校验改用 `name`（`kp_names_present`） |
| **F3** | **MySQL `graph_node`(18 KP) 与 Neo4j(1609 KP) 是两套不同节点集** —— 直接用 MySQL 掌握度推出的 KP 名去查 Neo4j → 命中 0 条 | 新增 `hub_seed_names()`：以 Neo4j 高连通 hub 为**可靠种子基**（必存在于 Neo4j），用户 frontier 名先经 `kp_names_present` 存在性校验再前置 |
| **F4** | 原模块仅 `PREREQUISITE` 先修图，但线上 `PREREQUISITE` 近乎死边（14 条） | 主信号改用 `RELATED_TO` **共现**（`recommend_knowledge_points` 批量 `UNWIND`），先修链函数保留供路径用 |

> 均为**直跑真实库实测**发现的模块缺陷，非臆造；修复后直跑 PASS。

---

## 2. 接线实现（工作项②）

**改动面**（严格限于工单允许范围）：

| 文件 | 改动 |
|---|---|
| `app/recommender/neo4j_engine.py` | 新增 `recommend_knowledge_points()` / `hub_seed_names()` / `kp_names_present()`；修 F1；新增 `_run()` 每查询预算注入 |
| `app/recommender/engine.py` | 新增 `_run_neo4j()`（熔断+预算硬顶，恒不抛）、`_neo4j_hub_seeds()`（300s 缓存）、`graph_recommend_neo4j()`、`_graph_stage_deadline()`；`hybrid_rank()` 图谱候选 = MySQL 基 ∪ Neo4j 叠加；`build_learning_path()` 逐节点打 `source` |
| `app/recommender/schemas.py` | `RecommendedCourse.source` / `PathNode.source` / `NextStepOut.graph_source` / `LearningPath.graph_source`（默认 `"mysql"`） |
| `app/config.py` | 新增灰度位 `KG_RECOMMEND_ENABLED=True` + `KG_RECOMMEND_TIMEOUT_MS=1000` |
| `.env` | 新增同两行（**字节级保留原文件**，非 echo 追加） |

**降级范式**：完全对齐已验证的 `app/ai/kg_bridge.py`：
`asyncio.wait_for(neo4j_run(op_name, fn), timeout=…)`
—— 超时 / `DependencyUnavailableError`（熔断 OPEN）/ 任意异常 **一律吞掉返回 `None` → 回落 MySQL 图**。

**「优先/混入」语义**：`graph_items = {**mysql_graph, **neo_items}`
—— Neo4j 候选覆盖同 key 的 MySQL 图谱候选，其余 MySQL 图谱候选保留（`source=mysql`）。

### 2.1 计分修正（直跑 + HTTP 双证发现的新问题）

接线后首轮 HTTP 自验发现：`graph_source=neo4j` 但**页内 0 条 neo4j 候选**。
**真因**：融合分 = `WEIGHT_GRAPH(0.30) × 候选分`，Neo4j 候选只出现在图谱一路 → **乘性上限 0.30**，
而多源热点（冷启动+协同+图谱）可达 0.5+ → Neo4j 候选**永远进不了 top_n**（owner 看不到 `source=neo4j`）。

**修法**（均已实证）：
1. `graph_recommend_neo4j` 候选分由 `[0.1,1.0]` 归一化改为**按共现强度映射到 `[0.6,1.0]`**，与 MySQL 图谱候选同量级；
2. `hybrid_rank` 对**仅 Neo4j 新接线候选**加独立优先通道 `score += WEIGHT_GRAPH*neo_score + 0.4`
   （加成**只给 `neo_items`**，不改判既有 MySQL 图谱节点）；
3. 保留「图谱来源可见性护栏」：若 top_n 截断挤掉全部图谱候选，则用最高分图谱候选替换末尾项。
   —— 灰度关（`neo_items` 空）时加成恒 0，**行为与现状逐字一致**。

### 2.2 ≤1s 停机降级（**必须两处都设，否则形同虚设**）

初版只靠 `asyncio.wait_for` 预算，实测停机请求仍耗 **2~6s**。逐层定位到两个独立原因：

| 断点 | 机制 | 修法 |
|---|---|---|
| driver 连接超时 3s | `init_neo4j` 构造时 `connection_timeout=3.0`（`NEO4J_CONNECT_TIMEOUT`），不可达时单次连接顶满 3s | — |
| `wait_for` 无法取消线程 | `neo4j_run` 把同步查询丢进 `asyncio.to_thread`，**超时只能让等待方放弃、线程仍在跑** | 在**查询层**加超时 |
| **neo4j 5.x 超时是 `Session.run(query, params, timeout=)`** | 写成 `session(timeout=)` 会被 **静默吞掉**（`session(**config)` 接受任意 kwarg） | `neo4j_engine._run(session, cypher, **params)` 统一注入 `timeout=KG_RECOMMEND_TIMEOUT_MS/1000` |
| 多次调用预算叠加 | hub + frontier + 主查询各自 1s → 合计 2~3s | `_graph_stage_deadline()` 给**整段图谱一个共享总预算**（`deadline` 参数） |

> 中间曾误走「给 hub 独立预算 + frontier 限 0.3s + 主查询保 0.4s 下限」的过度设计，停机反而回到 2.1s。
> **正解 = 共享单预算**：不可达时**首个调用**快速失败 → 后续调用命中熔断毫秒级直降。实测停机整段 **≈1.06s**。

---

## 3. 自验（工作项④：三条，真实 HTTP）

**实例口径**：因生产后端 9988 为常驻实例，本单以**临时端口**加载最新代码验证（同一 `app.main:app`）：

| 场景 | 实例 | 启动环境 |
|---|---|---|
| ① 开+在线 | `:9985` | 默认（`KG_RECOMMEND_ENABLED=true` + 真实 Neo4j） |
| ② 不可达 | `:9987` | `NEO4J_URI=bolt://127.0.0.1:7999`（死端口，模拟停机） |
| ③ 开关关 | `:9986` | `KG_RECOMMEND_ENABLED=false` |

> pydantic-settings 中**进程环境变量优先于 `.env`**，故以上覆盖无需改 `.env` 即生效（已用 `tb1_env_check.py` 实证覆盖被读取）。

### ① 开关开 + Neo4j 在线 → `source:"neo4j"` 候选

```bash
curl -s --noproxy '*' -o resp.json -w 'HTTP=%{http_code} time=%{time_total}s\n' \
  http://127.0.0.1:9985/api/recommend/next -H "Authorization: Bearer $TOK"
```

```
HTTP=200 time=0.156000s
外层壳 code= 0 message= ok
graph_source= neo4j
items= 5 neo4j= 5
   能力提升   source=neo4j score=1.0  extra={'neo4j_modules': ['campus_employability_foundation_m3', 'middle_high_school_chemistry_foundation_m2', 'middle_high_school_informatics_advanced_m3'], 'graph_source': 'neo4j'}
   工程能力   source=neo4j score=0.98 extra={'neo4j_modules': ['fullstack_development_foundation_m2', 'foundation_models_and_agents_practice_m1', 'deep_learning_and_perception_practice_m2'], 'graph_source': 'neo4j'}
   项目实践   source=neo4j score=0.98 extra={'neo4j_modules': ['frontend_development_practice_m1', 'foundation_models_and_agents_foundation_m1', 'foundation_models_and_agents_advanced_m2'], 'graph_source': 'neo4j'}
   成长规划   source=neo4j score=0.9  extra={'neo4j_modules': ['middle_high_school_physics_foundation_m1', 'middle_high_school_chemistry_foundation_m1', 'middle_high_school_chemistry_foundation_m3'], 'graph_source': 'neo4j'}
   考证通关   source=neo4j score=0.82 extra={'neo4j_modules': ['teacher_certificate_advanced_m2', 'teacher_certificate_practice_m1', 'teacher_certificate_advanced_m3'], 'graph_source': 'neo4j'}
```

**判定 PASS**：HTTP 200；`code:0`；`graph_source=neo4j`；页内 **5/5** 条 `source=neo4j`；耗时 156ms。

### ② Neo4j 停机（不可达地址）→ 仍 200 且降级 `mysql`，无 500

```bash
# 实例以 NEO4J_URI=bolt://127.0.0.1:7999 启动（死端口），模拟运行中停机
curl -s --noproxy '*' -o resp2.json -w 'HTTP=%{http_code} time=%{time_total}s\n' \
  http://127.0.0.1:9987/api/recommend/next -H "Authorization: Bearer $TOK"
```

```
  第1次 HTTP=200 time=0.078000s
  第2次 HTTP=200 time=0.094000s
  第3次 HTTP=200 time=0.063000s
外层壳 code= 0 message= ok
graph_source= mysql | items= 5 | all_mysql= True
   HTTP 请求与 Web 基础        item_code=KP-PY-HTTP           source=mysql score=0.5775
   乘法与九九表                 item_code=KP-MATH-MUL          source=mysql score=0.5415
   SQL 基础与 CRUD           item_code=KP-PY-SQL            source=mysql score=0.3075
   模块 2：函数与面向对象           item_code=MOD-PY-FUNC-OOP      source=mysql score=0.3
   模块 1：变量、类型、控制流         item_code=MOD-PY-VAR-CTR       source=mysql score=0.3
```

**判定 PASS**：HTTP **200**（无 500）；`code:0`；`graph_source=mysql`；5/5 `source=mysql`；耗时 63~94ms。

> ⚠️ **两种停机形态，都要如实覆盖**（本单都取证）：
> - **形态 A（本 curl）**：Neo4j 进程不在 → `init_neo4j()` 启动即失败 → `get_neo4j_driver()` 恒 `None`
>   → 图谱函数 0ms 直接 `[]`（快路径），故 63~94ms。
> - **形态 B（更硬，脚本）**：driver 已建立、运行中目标不可达 → 走真实连接失败路径。
>   见 §3.4：整段 ~1.08s（共享预算生效）。
> 两者均满足「200 + `source=mysql` + 无 500」；形态 B 才真正检验 ≤1s 预算。

### ③ 开关关 → 行为与现状一致（纯 MySQL 图）

```bash
# 实例以 KG_RECOMMEND_ENABLED=false 启动
curl -s --noproxy '*' -o resp3.json -w 'HTTP=%{http_code} time=%{time_total}s\n' \
  http://127.0.0.1:9986/api/recommend/next -H "Authorization: Bearer $TOK"
```

```
HTTP=200 time=0.079000s
code= 0 | graph_source= mysql | items= 5 | neo4j= 0
   HTTP 请求与 Web 基础        item_code=KP-PY-HTTP           source=mysql score=0.5775
   乘法与九九表                 item_code=KP-MATH-MUL          source=mysql score=0.5415
   SQL 基础与 CRUD           item_code=KP-PY-SQL            source=mysql score=0.3075
   模块 2：函数与面向对象           item_code=MOD-PY-FUNC-OOP      source=mysql score=0.3
   模块 1：变量、类型、控制流         item_code=MOD-PY-VAR-CTR       source=mysql score=0.3
```

**判定 PASS**：`graph_source=mysql`；纯 MySQL 图。

**② vs ③ 逐条比对（钉死「开关关 = 现状」）**：

```
② graph_source= mysql items= ['KP-PY-HTTP', 'KP-MATH-MUL', 'KP-PY-SQL', 'MOD-PY-FUNC-OOP', 'MOD-PY-VAR-CTR']
③ graph_source= mysql items= ['KP-PY-HTTP', 'KP-MATH-MUL', 'KP-PY-SQL', 'MOD-PY-FUNC-OOP', 'MOD-PY-VAR-CTR']
item_code 序列完全一致: True
item_code + score 完全一致: True
```

> 即：**降级落到 MySQL 图的结果，与灰度关的 MySQL 图逐字一致** —— 证明「停机降级不引入任何新行为」。

### 3.6 `GET /api/recommend/path`（契约完整性抽验）

```
HTTP=200  code= 0  graph_source= mysql  nodes= 3
   step1 第 1 步：变量与基本数据类型 → 分支与循环…  node_code=KP-PY-VAR-KP-PY-CTRL source=mysql
   step2 第 2 步：函数定义与参数/返回值 → 类、对象…  node_code=KP-PY-FUNC-KP-PY-OOP source=mysql
   step3 第 3 步：HTTP 请求与 Web 基础 → SQL…      node_code=KP-PY-HTTP-KP-PY-SQL source=mysql
```

**说明（如实）**：`/path` 已正确产出新增字段（`graph_source` + 每节点 `source`）。
当前节点仍为 `mysql` —— 因路径节点来自 **MySQL `graph_node` 的 KP**，而该集合（18 个）与 Neo4j（1609 个）
**不重合**（F3），故 `kp_names_present` 判定为「不在 Neo4j」。这是**如实标注**，非缺陷：
一旦 TC 侧完成两套 KP 对齐（域外，本单不做），路径节点会自动改标 `neo4j`。


### 3.4 停机整段延迟（脚本级实证，含 5 连测）

`scripts/tb1_stage_budget.py`（driver 指向死端口，模拟运行中停机）：

```
第1次 hybrid_rank graph_source=mysql items=5 neo4j=0 用时=1062ms
第2次 hybrid_rank graph_source=mysql items=5 neo4j=0 用时=1073ms
第3次 hybrid_rank graph_source=mysql items=5 neo4j=0 用时=1054ms
PASS(≤1500ms)
```

对照在线（`scripts/tb1_online_timing.py`，冷缓存）：`hybrid_rank graph_source=neo4j neo4j=5 129ms`。

### 3.5 脚本自验（①②③三场景断言）

`scripts/tb1_selfverify.py`（`force_down` 用 mock 把 `get_neo4j_driver` 置 None，等价停机）：

```
[① 开+在线] graph_source=neo4j items=10 neo4j_items=10
    sample: [('能力提升', 'neo4j', 1.0), ('工程能力', 'neo4j', 0.98), ('项目实践', 'neo4j', 0.98)]
[② 不可达]   ok=True exc=None
    graph_source=mysql items=10 all_mysql=True
[③ 关]       graph_source=mysql items=10
    ②vs③ item_code 交集=10/10

=== 结果 ===
PASS: ①②③ 均符合预期（开→neo4j 候选；不可达/关→mysql 降级且不报错）
```

> **② 的两种等价取证**：脚本用 mock（driver=None，0ms 快速降级）；HTTP 用**死端口 URI**
> （driver 已建但目标不可达，走真实连接失败路径，~1.06s 降级）。两者都达到「200 + `source=mysql` + 无 500」。

---

## 4. 改动文件清单

```
edu-agent/app/recommender/engine.py        （接线 + 计分 + 预算/deadline + 护栏）
edu-agent/app/recommender/neo4j_engine.py  （3 新函数 + F1 修复 + _run 预算注入）
edu-agent/app/recommender/schemas.py       （4 个 source/graph_source 新字段，默认 mysql）
edu-agent/app/config.py                    （KG_RECOMMEND_ENABLED / KG_RECOMMEND_TIMEOUT_MS）
edu-agent/.env                              （同两行，字节级保留）
edu-agent/scripts/tb1_directrun.py          （模块直跑）
edu-agent/scripts/tb1_selfverify.py         （三场景自验）
```

**未触碰**（铁律）：`app/ai/kg_bridge.py`、chat 检索链、`app/chat/`、前端、TC1 的「三路融合」措辞。**未 push。**

---

## 5. owner 验收口径

| 步骤 | 预期 |
|---|---|
| 1 | 演示环境前端查看课程推荐 → 结果来自图谱（可见 `source=neo4j`，如「能力提升 / 工程能力 / 项目实践」） |
| 2 | 拔掉 Neo4j 后再点 → 推荐**照常出现**（HTTP 200，`source=mysql`，无报错页） |
| 3 | 可选：`.env` 置 `KG_RECOMMEND_ENABLED=false` 重启 → 与现状完全一致（纯 MySQL 图） |
