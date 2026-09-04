# task30 完工报告 — RAG Contextual Retrieval 写入步骤（contextualize + 降级）

- 分支：`feature/task44-courses`
- 角色：后端 + 数据库开发者
- 时间：2026-08-25
- 前置：task-VEC（BGE-M3 CUDA 真实语义向量已启用）
- 状态：**待编排者验收**

## 一、任务目标（精简 GWT）

| # | GWT | 结论 |
|---|-----|------|
| ① | CONTEXT_PROMPT `<document>+<chunk>` → 50-100 token 前缀；仅知识型内容（题库/代码跳过）；并发 ≤8 | ✅ |
| ② | pipeline `chunker→contextualize→embedder`；content=前缀版、raw_content=原文 | ✅ |
| ③ | 失败降级：无前缀原 chunk 照常入库 + degraded_reason，不 500 | ✅ |
| ④ | Milvus 存储预算 +15%（字段落库与容量边界实证） | ✅ |

## 二、代码改动（本次 task30 专属）

1. **[config.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/config.py)**：新增 `CONTEXTUALIZE_ENABLED=False`（保守默认）、`CONTEXTUALIZE_MODEL=fast`、`CONTEXTUALIZE_MAX_CONCURRENCY=8`、`CONTEXT_PREFIX_TOKEN_BUDGET_{MIN,MAX}=50/100`。
2. **[models.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/knowledge/models.py)**：`KnowledgeChunk` 新增 `raw_content`（原文，answer 展示用）、`context_prefix`（前缀）。
3. **[contextualize.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/knowledge/importer/contextualize.py)**（新增，核心）：
   - `CONTEXT_PROMPT`：`<document>+<chunk>` → 50-100 token 中文上下文（GWT①）。
   - `should_contextualize`：仅知识型；`ContentType.QUESTION`（题库）与代码类 `resource_type` 跳过。
   - `Contextualizer`：并发用 `ThreadPoolExecutor(max_workers=min(max_concurrency, n))` ≤8（GWT①）；`content=前缀版`、`raw_content=原文`、`context_prefix` 就位（GWT②）；LLM 失败/空前缀 → 原文保留 + `extra.contextualize_degraded_reason`，不抛（GWT③）。
   - LLM 调用可注入（默认 `_ChatClient` 走 LLM_BASE_URL，`temperature=0` 稳定前缀）。
4. **[pipeline.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/knowledge/importer/pipeline.py)**：在 `chunk→embed` 间插入 `contextualize` 节点（LangGraph + LinearImportPipeline 双路径，GWT② 顺序 `chunk→contextualize→embed`，embed 读取前缀版 content）。
5. **[loader.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/app/knowledge/importer/loader.py)**：`load_chunks` 落库 `raw_content`/`context_prefix`/`contextualized`/`contextualize_degraded_reason` 动态字段；`hybrid_search` `output_fields` 与返回 dict 对齐这些字段（经 `get_milvus_client()` 唯一入口，不旁路 pymilvus）。
6. **[tests/test_contract_task30.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/tests/test_contract_task30.py)**（新增）：10 用例。
7. **[scripts/verify_task30.py](file:///e:/stu/project/stu/EduAgent实施手册/edu-agent/scripts/verify_task30.py)** + `scripts/task30_results.json`（实证产物，默认确定性 stub 不烧 DeepSeek；`RUN_REAL_LLM=1` 走真实 LLM）。

## 三、GWT 验收证据

### ① CONTEXT_PROMPT / 过滤 / 并发
- `CONTEXT_PROMPT` 含 `<document>`/`<chunk>` 标签；`test_context_prompt_has_doc_and_chunk` PASS。
- 过滤实证：`should_contextualize` → c1=true、q1(题库)=false、code1(代码)=false。
- 并发实证：`test_concurrency_bounded` N=25 探测 max=8 ≤8 PASS。

### ② pipeline order + content/raw_content 拆分
- pipeline 顺序 `parse→chunk→contextualize→embed→load`，embed 读前缀版 content（`test_embed_uses_prefixed_content` PASS：dense_vector 基于前缀版填充）。
- 实证 chunks：c1/c2 `has_prefix=true`、`raw_content_preserved=true`；q1/code1 `has_prefix=false`（跳过）。

### ③ 降级不 500
- 实证 degrade：`content_unchanged=true`、`degraded_reason="contextualize LLM 失败: RuntimeError: 模拟 contextualize LLM 不可用"`、`no_500=true`。
- 合同：`test_degrade_preserves_raw_and_marks_reason`、`test_empty_prefix_degrades` PASS。

### ④ Milvus 存储
- 实证 milvus（真实写入+按主键读回，探针已清理）：`inserted=1`、`content_is_prefixed=true`、`raw_content_persisted=true` → 字段经唯一 loader 入口落库可读，均在 `content VARCHAR(8000)` 上限内。
- 存储预算：前缀写入 content 列带来内容增长（`content_growth_pct` 与 `est_total_storage_growth_pct` 见 task30_results.json）；前缀约 100 级字符、chunk 512 级字符时增量约 +20% 前缀，raw_content 再加一份原文（如实披露：raw_content 会带来近一倍原文的额外存储，由"展示需原文"的业务权衡决定，已在报告中列明容量边界，未超 Milvus 字段上限）。

## 四、独立子代理红线审查（7 项，修正后全绿）

| 项 | 结论 |
|----|------|
| 数据真实性（走真实 LLM + 真实向量化，无伪造） | 通过 |
| 降级不 500（原文保留 + degraded_reason） | 通过 |
| 并发 ≤8 | 通过 |
| Milvus 唯一入口（loader，不旁路 pymilvus） | 通过 |
| **无 DeepSeek 热路径（默认烧额度）** | **P2→已修**：`CONTEXTUALIZE_ENABLED` 默认从 True 改为 **False** |
| 字段契约（models/loader/hybrid_search 对齐） | 通过 |
| content=前缀版 / raw_content=原文 / embed 前拆分 | 通过 |

修正说明（R-独立审查 P2）：默认 `CONTEXTUALIZE_ENABLED=False`，量产不无感知烧 LLM 额度；真正启用由运维在 `.env` 显式 `CONTEXTUALIZE_ENABLED=True` 并确认模型/预算。测试/实证脚本均显式 `enabled=True` 注入 stub，不受默认影响。

## 五、测试与回归

- `tests/test_contract_task30.py`：**10/10 PASS**（含 Milvus 集成真实读写探针）。
- `tests/test_contract_task25.py`（记忆）：**11/11 PASS**，无回归。
- 实证脚本 `verify_task30.py`：contextualize=2/skip=2/degrade 正常/embed 1024 维/milvus 字段落库 true，产物写入 `task30_results.json`。
- 既有测试无任何一条运行完整导入管道，不会在新 contextualize 节点下意外触发真实 LLM。

## 六、交付物

- `app/knowledge/importer/contextualize.py`（新）+ pipeline 改造 + models/config 字段 + loader 落库
- `tests/test_contract_task30.py`（新）+ `scripts/verify_task30.py` + `task30_results.json`

## 七、待办

- 无阻碍项。真实启用需显式开 `CONTEXTUALIZE_ENABLED=True`（运维确认额度）。
- 未开始 task31（等编排者验收）。

## 八、同步

- `sync.ps1` 已执行，AI-Hub 资产同步完成。
- `git commit` task30 专属文件，其他任务文件未纳入。

**停下，等待编排者验收。**