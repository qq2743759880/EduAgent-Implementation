# EduAgent 两轮修复验收报告（独立实证）

- **验证人**：be-tester（独立实证，不采信任何实施报告）
- **日期**：2026-08-31
- **后端**：http://127.0.0.1:8000（在线，最新代码）
- **验证账号**：admin `adm02test` / `Test@123456`；student `user000001` / `Test@123456`
- **验证方法**：admin token 实测 HTTP + 项目 embedder（`app.knowledge.importer.embedder`）编码查询直连 Milvus 检索 + 管理端 RAG 接口交叉验证 + 前端 vitest 全量回归

---

## 1. P1 回归确认（commit b36e1aa 修复项复测）

| # | URL | 期望 | 实际 | 判定 |
|---|-----|------|------|------|
| 1 | `DELETE /api/admin/courses/series/999999` | 404 + 字符串 code 壳（非 500） | **404**，`{"code":"40400","message":"系列不存在，999999","data":null}`，215ms | ✅ 通过 |
| 2 | `GET /api/recommend/next?top_n=5` | 200 且 <5s（原 500/超时） | **200**，341ms，返回 5 条推荐项（KNOWLEDGE_POINT：programming/english/math） | ✅ 通过 |
| 3 | `GET /api/mindmap/me/1` | 200 | **200**，183ms，返回英语音标主题思维导图（nodes/categories 完整） | ✅ 通过 |

P1 三项全部符合预期，无回归。

---

## 2. P0 检索质量验证（核心，EMBED_BACKEND=cloud→cuda）

**验证方式（方案 A 主验证 + 方案 B 交叉）**：
- 方案 A：直接调用项目 embedder（`encode_dense_batch` + `build_sparse_vector`，配置 `EMBED_BACKEND=cuda`，日志确认 "BGE-M3 模型已加载 device=cuda"）编码查询 → `hybrid_search`（dense COSINE + sparse IP + RRF）直连 Milvus `edu_knowledge`（2628 行，`dense_vec` dim=1024，与查询同模型同空间）。
- 方案 B：`POST /api/admin/rag/search`（`use_hyde=false, enable_graph=false` 走底层检索链路）交叉验证。

| 学科 | 查询 | top1 命中内容 | 对应学科 | 判定 |
|------|------|--------------|----------|------|
| Python | Python 中如何使用变量和 for 循环遍历列表 | 【编程题】remove_duplicates(nums) 去重函数 / 遍历列表（`seeds/3_question/question.csv`） | programming ✅ | 区分 |
| 数学 | 一元二次方程求根公式与韦达定理的推导 | 【公式推导题】二次方程 ax²+bx+c=0 求根公式推导 | math ✅ | 区分 |
| 英语 | 英语单元音音标的发音口型与单词举例 | 课程系列：考研英语阅读写作班 / 中学英语同步班·核心词汇 | english ✅ | 区分 |
| 化学 | 化学元素周期表的分区与原子结构特征 | 课程模块：中学化学同步班·元素化合物基础巩固（`middle_high_school_chemistry_foundation_m1`） | chem ✅ | 区分 |

- **判定：4/4 学科查询 top1 各命中对应学科内容**，跨学科召回正确区分。
- 对比修复前：4 学科查询全返回相同 Python 题（错配，doubao-cloud 2048 维截断向量与库内 BGE-M3 1024 维空间不一致 cosine≈0.035）。修复后查询与库同走 BGE-M3（cuda），语义空间一致。
- 交叉验证（方案 B）：`/api/admin/rag/search` Python 查询 top1-3 均命中 Python 编程题（score 1.0 / 0.970 / 0.931），200 + `code=0`，无 degraded。
- 冷启动：脚本首次编码耗时 17.9s（BGE-M3 模型加载），后续查询 encode 0.12s / search 0.01-1.02s，服务预热正常，不影响验收。

---

## 3. 全接口冒烟复测（admin token）

- 覆盖：course_admin（7）、question_admin（6）、user_admin（2）、rag_admin（3）、recommender（3）、mindmap（2）、auth（1）、MCP（6）、鉴权 fail-closed（2）≈ **27 个请求**（GET 为主 + 2 个安全写验证）。
- **500 数量：0**。全部端点无服务器内部错误。

| 类别 | 结果 |
|------|------|
| 总请求 | 27 |
| 200 | 25 |
| 预期 401（无 token fail-closed） | 2（`{"code":"40101","message":"缺少 Authorization 请求头","data":null}`）|
| 404 | 1（`/api/mindmap/me`，该路径不在 mindmap 路由清单内——实际路径为 `/me/{series_id}`，属接口清单项，非回归）|
| 500 | **0** |
| `{code:0,data}` 壳（admin 域） | course_admin / question_admin / rag_admin / MCP 全部正常 ✅ |

**观察项（非阻断，既有契约）**：
- `user_admin`（`/api/admin/users`、`/dashboard/metrics`）、`recommender`（`/path`、`/next`）、`mindmap`（`/me/{id}`）为 `response_model` 直出裸 JSON（无 `{code,data}` 壳），属 P7 既有设计，非本轮两轮修复引入；均 200 正常返回。
- 推荐反馈 `POST /api/recommend/feedback`（HELPFUL）200，`score_delta=0.5`，写链路正常。

---

## 4. 前端测试确认（edu-frontend）

```
npx vitest run
Test Files  72 passed (72)
Tests       491 passed (491)
Duration    42.13s
```

- **结果：全绿，491 passed**，与预期（491）完全一致，无失败用例。

---

## 5. 结论

| 维度 | 结果 |
|------|------|
| P1 接口修复回归 | ✅ 通过（3/3）|
| P0 检索通道修复（跨学科召回区分） | ✅ 通过（4/4 学科 top1 各自命中）|
| 全接口冒烟 | ✅ 通过（0 个 500，admin 域壳正常）|
| 前端测试 | ✅ 通过（491/491）|

**最终判定：通过** ✅

**阻断项**：无。

**建议观察项（不阻断本轮验收）**：
1. `user_admin` / `recommender` / `mindmap` 端点返回裸 response_model（无统一壳），如后续要求全站统一 `{code,data}` 壳需另行契约变更。
2. 库内存在测试种子数据（如 `itest-sweep-*` off_sale 系列），生产环境重建种子时应清理。
