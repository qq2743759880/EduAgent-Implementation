# task-P1-git-baseline 完工报告

> 分支：`feature/opt-waves`　remote：`origin(EduAgent-Implementation.git)`　执行：TT P1-基建（backend 核心源码首次完整入库 + .gitignore 完善，消除源码改动不可 trace）

## 目标与范围
- 让 `edu-agent/` 后端核心源码在 git 中首次完整入库：`app/`、`tests/`、`scripts/` 源码 .py 与编排文件、`pyproject.toml`、`uv.lock`、`alembic/`、`docs/`。
- 完善 `.gitignore`，把一次性验证/探查脚本、本地运行输出、压测产物、第三方二进制、敏感配置（含凭据）全部隔离，绝不入库。
- 只做 git/ignore 基建，**零业务逻辑改动**；禁止 `git add -A`/`git add .`，逐路径精确 add 并核对 staged 清单。

## 资产消费证据
开工前真实读取/执行了以下资产：
1. `AGENTS.md`（工作区规则）— 实测启动/契约/关键教训；获悉仓库 commit 消息风格为 `前缀(opt)/主题: 描述`（如 `fix(opt)/L4-delete-500: ...`）。
2. 项目记忆 Hard Constraints（只读，工时/约束上下文）。
3. `edu-agent/.gitignore` 现状 — 已有 `.env/.venv/__pycache__` 等，缺一次性脚本/输出/压测/第三方二进制覆盖。
4. `.opencode/plans/task-agent-matrix.md` 上下文 — 供批判承接核对引用。

**自检发现并修复的问题**：
- `.gitignore` 本身从未入库（git status 一直 `??`），导致即便写了忽略规则也随 append 而不可 trace；本任务已把 `.gitignore` 一并提交。
- `alembic.ini` 内含明文本地 DB 口令（`root:123456@localhost`），属敏感配置 → **不提交**，改为 `.gitignore` 拒之（宁可保守不入）。
- `tools/redis/` 是 redis Windows 二进制发行包（exe/dll/pdb/dump.rdb），非源码 → `git add` 不包含，`/tools/` 忽略。
- 存量 `git ls-files edu-agent/app` 仅 115，实际 app 内 Python 共 271 → 未入库源码约 156 个文件，是 P1 主战场。

## 竣工实操
### .gitignore 变更点（`edu-agent/.gitignore`，三次提交逐步落库）
新增条目：
```
# 一次性验证/探查/冒烟/诊断/基准脚本（任意层级）
_verify*  _probe*  _smoke*  _diag*  _bench*  _t*
scripts/_*
# 一次性运行输出 / 验证结果
*_out.txt  verify_out.txt  smoke_out.txt  reverify_out.txt  pytest*_out.txt
*_results.json  *_result.json
# 覆盖率 / 压测(locust) / 打包产物
.coverage  .coverage.*  *.csv  locust_*.html  redis.zip  *.zip
# 第三方二进制运行目录（Redis Windows 发行包）
/tools/
# alembic 本地默认 DB URL 含明文口令(root:123456@localhost)，不入库
alembic.ini
# edu-agent 根目录一次性探针/检查/临时脚本（未匹配通用下划线模式者）
/_check*  /_tmp*  tmp_smoke_*
```
既有 `.env` 保持覆盖真实凭据，`.env.production.example`（纯占位模板）不入库、不 ignore（留待他任务）。

### staged 清单摘要（仅真实源码，未用 -A）
- `edu-agent/app/**`：新增 156 文件（ai/auth/chat/common/community/core/curriculum/domains(各业务域)/events/extensions/gamification/interactive/knowledge/middleware/mindmap/progress/recommender/routers/services/users 等；含 `_archived/question_admin` 存档代码以保可 trace）。
- `edu-agent/tests/**`：46 文件（契约测试 + 单元测试 + `performance/` 性能工具）。
- `edu-agent/scripts/**`：19 文件（check_models/check_p1_readiness/convert_to_safetensors/download_models/gen_schema/generate_review_doc/test_chunker/verify_p1_data/verify_task{30,31,vec} + `eval/` 编排 run_task29/verify_task32 等）。
- `edu-agent/alembic/**`：9 文件（env.py/README/baseline_schema.sql/versions 5 个迁移）。
- `edu-agent/pyproject.toml`、`edu-agent/uv.lock`、`edu-agent/docs/P0_知识复习手册.docx`。
- 合计 227 文件新增（+37419 行）。

### commit hash
- `084f795` chore(p1-infra): track backend core source in git（227 文件）
- `f930915` chore(p1-infra): add gitignore keeping temp/sensitive artifacts out of git
- `963e072` chore(p1-infra): ignore leftover root-level probe/temp scripts（+5 行）

### 敏感项 grep 结果（均为空）
- `git ls-files edu-agent | findstr /i "\.env"`：仅 `.env.example`（占位模板，正常），无真实 `.env`。
- staged 清单 grep `\.zip$|_out\.txt$|\.coverage|\.venv|__pycache__|_probe|_verify|redis`：**空**。
- `git ls-files edu-agent | grep \.zip$|\.venv|_out\.txt$`：**空**（评估数据如 `scripts/eval/*.json`、`adversarial_dataset.json` 已在此前差分 commit 入库，非丢失）。
- `git check-ignore edu-agent/.env` → `edu-agent/.env`（确认被忽略）。

### git ls-files 前后计数对比
- `edu-agent/app`：**115 → 272**（+157）。

## 独立实证验证（第 6 步逐条）
1. `git status --short`：edu-agent 下 `app/tests/scripts/alembic/pyproject/uv.lock/docs` 已无 `??` 残留；剩余仅出局项（`edu-agent/test-reports/*`、`.opencode/`、`.serena/`、`.env.production.example`）与根目录它类未跟踪项。根探针 `_check_import_task14.py`、`tmp_smoke_s1.py`、`alembic.ini` 均已落入 ignore。
2. `git log --oneline -1`：`963e072 chore(p1-infra): ignore leftover root-level probe/temp scripts ...`（本批最新），`084f795` 为源码基线提交，均已落 HEAD 链。
3. `git ls-files edu-agent/app`：272（115→272，+157），前 5：`app/__init__.py`、`app/_archived/question_admin/{__init__,router,schemas,service}.py`。
4. 收集确认：`python -m pytest tests/ --collect-only -q` → **509 tests collected, 31 errors during collection (11.07s)**。本 commit 为纯新增（零 modify），收集结果与入库前基线一致，未改坏代码（31 个 collection 错误为既有 import/环境依赖，如需 DB/向量服务/Milvus 联机的 test_core/test_contract_task_vec 等，属前置基线事实，非本任务回归）。

## 批判承接核对
- 本任务无追加载批判项，写"**无承接项**"，仅自查：
  - **误删被引用正确代码**：未删除任何文件，全是新增；`app/_archived/question_admin` 一并入库保留 trace。
  - **临时产物误入库**：staged 227 文件已逐条核对，无 `_verify/_probe/_smoke/_diag/_bench/_t`、无 `*_out.txt`、无 `.coverage`、无 `.zip`/`.csv`/`tools/redis`；敏感配置（.env / alembic.ini 明文口令）均不入库。
  - 留存隐患可见"遗留/风险"。

## 遗留/风险
- `edu-agent/.env.production.example` 与若干根目录/`edu-frontend` 探针、`deploy/` Dockerfile、`refactor_sql/` 等仍为未跟踪（不经本任务清理，属其它任务/根 .gitignore 范畴）；`edu-agent/.gitignore` 仅约束 edu-agent，仓库根级 `.gitignore` 尚未覆盖同理产物（如 `regression_out.txt`、`test-docs/*_out.txt`）。
- 31 个 pytest collection 错误为既有环境依赖，建议后续以一个独立可重放任务核对是否仅需 DB/向量服务即可转绿。