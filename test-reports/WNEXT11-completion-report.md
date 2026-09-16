# WNEXT11 完工报告 — Milvus 存量 internal 回填 + 生产 skill 根配置

> 拆解来源：`kickoff-WNEXT11-milvus-backfill.md`（W-NEXT-10 收尾）
> 执行角色：独立后端/数据工程师（单写者，锁 `edu-agent/scripts/eval/wnext11.lock`）
> 分支：`feature/opt-waves`
> 完成时间：2026-09-16

## 0. 结论速览

| 任务 | 级别 | 状态 | 关键证据 |
|------|------|------|----------|
| 任务一：存量 internal 文档 Milvus 回填（W-NEXT-10 遗留） | P1 | ✅ 已闭环 | 1789/1789 对账一致；student 原生 expr 0 命中；admin 可见；幂等重跑不翻倍 |
| 任务二：生产 EDUAGENT_PLATFORM_SKILL_ROOTS 配置 | P2 | ✅ 已闭环 | config 字段存在（默认空）；.env.example/README 有配置说明；报告含两形态行为对照 |

- **数据安全红线**：全程先只读核查 → 先备份（id 清单 + 标量快照）→ 幂等回填 → 验证，无备份直写。
- 服务 8000（PID 19120）未重启；验证用 8010 临时实例（临时实例因本机页面文件过小 embedding 降级，见 §3 说明）。
- 文件归属命中 kickoff「仅限」清单（scripts/eval/、config.py 仅新增字段、.env.example、deploy/README.md、本报告）。

---

## 1. 任务一【P1】存量 internal 文档 Milvus 回填

### 背景
W-NEXT-10 上线了「导入期 internal 打标 + 检索期 student 过滤」，但存量 `_default` 分区 1789/4417（40.5%）行**没有** `internal` 字段——此前靠**结果侧兜底**（每次查询再过一遍 `classify_internal`）。回填后 student 过滤可直接走 Milvus 原生 expr `internal != true`，更高效可靠。

### 方案与执行
按 kickoff 修法 4 步走，判定口径与 loader.py 导入期**逐字一致**：
```
classify_internal(source_file, raw_content or content)
（raw_content 无值时取 content——与 load_chunks L393-397 完全一致）
```

1. **只读核查** `_wn11_scan_backup.py`：query_iterator 扫 `_default` 全量，1798-… 用 `_has_internal` 探测行是否已带 `internal=true`。
   - `total_scanned=4417`，`internal_pred_count=1789 (40.5%)`，`already_tagged=0`，`pending_backfill=1789`
   - **与 W-NEXT-10 登记 1789 完全对账一致** ✅（占比 40.5% 不变）
2. **备份**（`deploy/backups/`，含时间戳）：
   - `wnext11_internal_ids_20260916_134605.json`（id 清单，1789 行，297KB）
   - `wnext11_edu_knowledge_default_scalar_20260916_134605.json`（`_default` 全量标量字段快照，不含向量，2.6MB）
3. **幂等回填** `_wn11_backfill.py`：**读全行（`output_fields=["*"]`）→ 就地加 `internal=True` → 全行 upsert 回 `_default`**。
   - 关键正确性：Milvus `upsert` 是**整行替换**，只传 `{id, internal}` 会清空 dense/sparse/content。对齐 R03 created_at 补入做法——全字段透传仅补 dynamic scalar，**不重嵌向量、不动 dense/sparse/content**。
   - 分批 200（与 loader.load_chunks 一致），失败可重入；写后 `internal==true` 计数带可见性重试。
4. **验证**（`_wn11_verify_expr.py`，Milvus 原生 expr）——见 §3。

### GWT 验收（逐项数字）

| GWT | 期望 | 实测 | 结论 |
|-----|------|------|------|
| ① 备份文件存在（id 清单 JSON） | `deploy/backups/wnext11_internal_ids_*.json` | `deploy/backups/wnext11_internal_ids_20260916_134605.json`（1789 行）+ 标量快照 | ✅ |
| ② 回填后 internal 计数对账一致 | `internal==true` 计数 = 清单数(1789) | `internal==true=1789` / `internal!=true=2628` / `total=4417`（互斥全覆盖） | ✅ |
| ③ student/admin 对照实测（原生 expr 路径） | student 0 命中 / admin 可见 | student（role='student' 原生 expr）internal=true **0** 条；admin（role='admin'）internal=true **10/10** 条全可见；default（不传 role）internal=true 仍可见=历史行为不破坏 | ✅ |
| ④ 幂等（重跑不翻倍） | 重跑计数不翻倍 | 重跑后 `internal==true` 恒 **1789**，`total_rows_after` 恒 **4417**（覆盖写，不翻倍） | ✅ |

> ③ 中 student 侧另有 W-NEXT-10 同款 HTTP 对照（`_wn10_http_probe.py`，8010 实例）：query `sys_user_auth 批量生成` / `task09 验收批判方案` / `知识库内部实现 task 报告` → student 均 **0** 内部命中。admin HTTP 侧因临时实例环境问题未采信（见下）。

---

## 2. 任务二【P2】生产 EDUAGENT_PLATFORM_SKILL_ROOTS 配置

### 背景
W-NEXT-10 的 F5-b 修复让 `registry.default()` 与开发机 AI-Hub 隔离（未配置时返回**空注册表**）。生产若不配 `EDUAGENT_PLATFORM_SKILL_ROOTS`，线上 `skill_node` 不再注入 dev-host skill body（平台实物能力仍由 `platform_capability_block` 注入，不受影响，但平台自有 skill 也不进）。

### 改动
1. **config.py** 新增 `EDUAGENT_PLATFORM_SKILL_ROOTS: str = ""`（默认空=安全缺省，不消费任何 skill 根）。含完整注释说明安全缺省语义。
2. **.env.example** 补 `EDUAGENT_PLATFORM_SKILL_ROOTS=` 配置项（含双形态说明）；头注字段计数同步更新 242→243 / 230→231 键 / 未注释 37→38。
3. **deploy/README.md** §3② 后新增「平台自有 skill 根配置」小节：两形态行为对照表 + 判定口径 + 安全边界（**不要**在生产指向开发机库）。

### GWT 验收

| GWT | 实测 | 结论 |
|-----|------|------|
| ① config 字段存在（默认空） | `settings.EDUAGENT_PLATFORM_SKILL_ROOTS == ''`；`SkillRegistry.default().count()==0`（未配置=空注册表，F5-b 隔离） | ✅ |
| ② .env.example / devel·README（deploy/README.md）有配置说明 | `.env.example` 含键+注释；`deploy/README.md` §「平台自有 skill 根配置」含两形态对照表 | ✅ |
| ③ 报告含两种形态行为对照 | 见下表 | ✅ |

### 两种生产形态行为对照（写入报告主体）

| 形态 | 配置 | `skill_node`（平台 agent 系统提示 skill 段）行为 |
|---|---|---|
| **不配**（默认空） | `EDUAGENT_PLATFORM_SKILL_ROOTS=` | 只注入 `platform_capability_block()` 实物能力清单（源自 `permission_gate.TOOL_CLASS_MAP`，8 个真实工具）；**不**注入任何开发机 skill（`list_directory`/`read_file` 等 dev-host 工具绝不出现），也不注入平台自有 skill |
| **配**（平台有自维护 skill 根） | 指向该目录（`os.pathsep` 分隔多根） | 在实物能力清单之外，额外把这批平台自有 SKILL.md 的 body 注入 `skill_context` |

安全边界：`default()` 只扫该变量指向根，`dev_default()` 仍扫开发机 AI-Hub——两者完全隔离；**误指向开发机 `D:\.ai-hub\skills` 会重新引入 dev-host 工具**，生产禁指。

---

## 3. 测试与验证说明

- **回填脚本**：`_wn11_scan_backup.py`（只读核查+备份）、`_wn11_backfill.py`（幂等回填）、`_wn11_verify_expr.py`（原生 expr 对照），均在 `scripts/eval/`。
- **验证方式**：Milvus 原生 expr（`internal==true` / `internal!=true` 计数、role 对照）不依赖 embedding/HTTP，稳健可靠。
- **8010 临时实例局限（非代码缺口）**：8010 启动时本机页面文件太小（`os error 1455`，WinError 页面文件不足）→ BGE-M3 本地模型加载失败 → embedding 降级 DashScope（15s+）→ 超过 Milvus 检索 8s 超时 → admin HTTP 检索降级返回空。因此 admin「可见」改用 **Milvus 原生 expr role 对照**验证（打 ③ 已证 admin 10/10 全部召回 internal 行），不依赖 HTTP。student HTTP 0 命中可作为旁证（student 走了同一 bug 无关的检索、结果 0 internal）。

### 复跑指引
```
# 只读核查+备份（幂等，可反复跑）
cd edu-agent && .venv/Scripts/python.exe scripts/eval/_wn11_scan_backup.py
# 幂等回填（须 --confirm）
.venv/Scripts/python.exe scripts/eval/_wn11_backfill.py --list "deploy/backups/wnext11_internal_ids_<时间戳>.json" --confirm
# 原生 expr 对照验证（student/admin/default）
.venv/Scripts/python.exe scripts/eval/_wn11_verify_expr.py
```

---

## 4. 交付物

| 文件 | 性质 | 说明 |
|------|------|------|
| `edu-agent/scripts/eval/_wn11_scan_backup.py` | 新 | 只读核查 + 备份（id 清单 + 标量快照） |
| `edu-agent/scripts/eval/_wn11_backfill.py` | 新 | 幂等回填 internal=true（全行透传仅补 scalar） |
| `edu-agent/scripts/eval/_wn11_verify_expr.py` | 新 | 原生 expr student/admin/default 对照验证 |
| `deploy/backups/wnext11_internal_ids_20260916_134605.json` | 新 | id 清单备份（GWT①） |
| `deploy/backups/wnext11_edu_knowledge_default_scalar_20260916_134605.json` | 新 | _default 标量快照备份 |
| `edu-agent/app/config.py` | 改 | 仅新增 `EDUAGENT_PLATFORM_SKILL_ROOTS` 字段（默认空） |
| `edu-agent/.env.example` | 改 | 补配置键 + 头注计数更新 |
| `deploy/README.md` | 改 | 补 skill 根两形态配置说明 |
| `test-reports/WNEXT11-completion-report.md` | 新 | 本报告 |

## 5. 向编排者报备（文件归属）

1. **config.py 仅新增字段**（`EDUAGENT_PLATFORM_SKILL_ROOTS`），未改任何既有逻辑；对上位 F5-b 的 `registry.default()` 零改动（本该变量即由 registry 直接读 `os.environ`）——新增 config 字段与 registry 读取**解耦**（registry 读环境变量而非 settings），两者行为一致（默认空→空注册表）。
2. **deploy/README.md 归属**：kickoff 明列「deploy 文档（配置说明）」在仅限清单内，本次仅补配置说明段落，未改既有章节。
3. **8010 临时实例环境局限**已登记（§3），不影响回填结论（回填正确性由 Milvus 原生 expr 实证，不依赖 HTTP/embedding）。