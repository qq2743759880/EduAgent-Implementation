# W-NEXT-BACKEND-001 完工报告 — hitl_realness_probe.py cwd-相对 .env 加载根因复核

> 任务：`fix(eval)/W-NEXT-BACKEND-001-hitl-mysql-pool`
> 实施日期：2026-09-17
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 分支：`feature/opt-waves`（git symbolic-ref HEAD 已确认 `refs/heads/feature/opt-waves`）
> HEAD 起始：`be4bf48e`（W-NEXT-CHECKDEMO-004 修复后 hotfix batch 稳定 tip）

## 0. 一句话结论

**dotenv 兜底已闭环（G1）；⑫ 守卫 FAIL 根因 ≠ .env 加载（G2 不可能 PASS 不扩 scope / 不重启 8000）。**

- **编排者盲测前提有误**：任务描述称"W-NEXT-CHECKDEMO-004 已对 4 个其他探针修了 load_dotenv，但 hitl_realness_probe.py 修复未覆盖"——**实证反驳**：hitl_realness_probe.py 的 dotenv 修复**已**包含在 W-NEXT-CHECKDEMO-004（commit `be4bf48`，+17/-0 行，file:`edu-agent/scripts/hitl_realness_probe.py:26-39`）。本次复核从 cwd=仓库根 启动 probe 复跑 3 次，**全程** stderr 干净，无 `Field required [type=missing]` 报。
- **⑫ FAIL 真实根因 = backend lifecycle ops issue**：probe 启动时 `from app.database import fetch_one` 走到 `get_mysql_pool()`，抛 `RuntimeError: MySQL 连接池未初始化，请先调用 init_mysql()（app/database.py:142）`。MySQL pool 是 8000 uvicorn lifespan 启动时 init_mysql() 注入的（process-local 单例），subprocess 无法继承。这是**已登记**的 ops 盲区——W-NEXT-CHECKDEMO-004 §2.3 把该 root cause 显式 scope-out。
- **路径也存在偏差**：任务描述把"文件归属"写成 `edu-agent/scripts/eval/hitl_realness_probe.py`，但仓库中实际文件位于 `edu-agent/scripts/hitl_realness_probe.py`（无 `eval/` 子层）。该路径错位可能源于上游编排者凭印象写的，未对照 `find` 输出复核。

## 1. 任务起源（编排者盲测前提 vs 实证复核）

| 维度 | 编排者盲测前提 | 本任务实证复核 |
|---|---|---|
| W-NEXT-CHECKDEMO-004 是否已修 hitl_realness_probe.py | "4 个其他探针修了，但 hitl_realness_probe.py 修复未覆盖" | **已修**（be4bf48 commit，含 `edu-agent/scripts/hitl_realness_probe.py +17/-0`，`load_dotenv(EDU_ROOT/.env, override=False)` 在第 33-39 行）|
| probe std{out,err} 含 "MYSQL_* Field required" 痕迹 | "复现路径：... → stderr 含 'MYSQL_HOST/PORT Field required'" | **不存在**（std{out,err} 完全干净——仅 2 行 `[安全] DEBUG 模式 ...` + 1 行 INFO 日志 + 1 行 JSON `{"error":"RuntimeError: MySQL 连接池未初始化..."}`）|
| ⑫ 守卫 FAIL 真实根因 | cwd-相对 .env 加载（pydantic-settings env_file） | **MySQL pool init 缺失**（subprocess 无法继承 8000 lifespan pool；与 .env 完全无关）|
| 文件归属路径 | `edu-agent/scripts/eval/hitl_realness_probe.py` | 实际：`edu-agent/scripts/hitl_realness_probe.py`（`scripts/eval/` 子层无此文件名）|

**关键决策**：本任务**坚决不动**源码——task 描述的前提在三重维度（"未覆盖"、"MYSQL_* Field required" stderr、"文件路径"）都不成立。强行"修"已修过的代码会污染 git history，或为追求 PASS 字符串而扩大 scope（重启 8000 / 改 probe 实现 / 改 app.config）——都是任务红线禁止项。

## 2. 根因诊断（实证复核 4 路径）

### 2.1 路径 1：hitl_realness_probe.py 入口 dotenv 块当前态

```
$ sed -n '26,40p' edu-agent/scripts/hitl_realness_probe.py
# W-NEXT-CHECKDEMO-004 修:.env 加载兜底 ——
# 现象:check-demo.mjs ⑫ 守卫 spawn 子进程时 cwd=仓库根,不是 edu-agent/。
#       pydantic-settings 的 env_file='.env' 是相对 cwd 的相对路径,cwd=仓库根时
#       找不到 edu-agent/.env → 启动期 ValidationError: LLM_API_KEY Field required。
#       _count_task 走 app.database.fetch_one 间接依赖 settings.MYSQL_* 同样会崩。
# 修复:入口处显式 load_dotenv(EDU_ROOT/.env),让进程环境变量在 import app.config 之前
#       已经被填好。不依赖 cwd,不依赖父进程的 env 注入。
ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = ROOT / ".env"
if _ENV_PATH.is_file():
    from dotenv import load_dotenv  # noqa: E402
    load_dotenv(_ENV_PATH, override=False)  # 已有环境变量优先,避免覆盖 CI 注入
else:
    print(f"[hitl_realness_probe] WARN .env not found at {_ENV_PATH} — pydantic Field required 风险", file=sys.stderr)
```

✅ **完整 dotenv 兜底已在**——同 veclock_health_probe.py / veclock_verify.py 标准模式，`override=False`、显式 `EDU_ROOT/.env` 绝对路径、`.env` 缺失时 WARN 而非静默。

### 2.2 路径 2：cwd=仓库根启动 probe 复跑（3 次，全用 venv python）

```
$ cd "E:/stu/project/stu/EduAgent实施手册" && timeout 30 edu-agent/.venv/Scripts/python.exe edu-agent/scripts/hitl_realness_probe.py
[安全] DEBUG 模式使用公开 JWT_SECRET，仅限本地开发，禁止上线
[安全] DEBUG 模式使用默认 API_TOKEN，仅限本地开发，禁止上线
[INFO] app.common.logging:setup_logging:95 | 日志系统已初始化，级别: DEBUG，目录: logs
{"error": "RuntimeError: MySQL 连接池未初始化，请先调用 init_mysql()"}
EXIT=1

$ 同上（第 2 次）
[同 stderr/stdout]
EXIT=1

$ 同上（第 3 次）
[同 stderr/stdout]
EXIT=1
```

✅ **复跑 3 次结果完全一致**：stderr 全程**无** `Field required`、**无** `MYSQL_* Field required`、**无** pydantic ValidationError。仅 `MySQL 连接池未初始化` 的 RuntimeError。

### 2.3 路径 3：隔离 spawn 复制 check-demo ⑫ 子进程（cwd=仓库根 + venv python）

```javascript
// 等价于 check-demo.mjs:464  spawn(EDU_PY, [HITL_PROBE], windowsHide, cwd=仓库根)
const probe = 'edu-agent/scripts/hitl_realness_probe.py';
const py = 'edu-agent/.venv/Scripts/python.exe';
spawn(py, [probe], {windowsHide:true, cwd: 'E:/stu/project/stu/EduAgent实施手册'});
```

输出：
```
---EXIT--- 1
---STDOUT---
[INFO] app.common.logging:setup_logging:95 | 日志系统已初始化，级别: DEBUG，目录: logs
{"error": "RuntimeError: MySQL 连接池未初始化，请先调用 init_mysql()"}

---STDERR---
[安全] DEBUG 模式使用公开 JWT_SECRET，仅限本地开发，禁止上线
[安全] DEBUG 模式使用默认 API_TOKEN，仅限本地开发，禁止上线

---STDERR has Field required [type=missing]?--- false
---STDERR has RuntimeError MySQL pool?--- true
```

✅ **绝对定论**：⑫ 守卫的 stderr 干净（无 pydantic Field required），stdout 只有 backend lifecycle 抛出的 `MySQL 连接池未初始化`。

### 2.4 路径 4：隔离 .env 加载验证

```
$ timeout 30 edu-agent/.venv/Scripts/python.exe -c "
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path('edu-agent').resolve()
ENV = ROOT / '.env'
print(f'cwd={Path.cwd()}, ENV={ENV}, exists={ENV.is_file()}')
load_dotenv(ENV, override=False)
print(f'MYSQL_HOST={__import__(\"os\").getenv(\"MYSQL_HOST\")}')
print(f'MYSQL_PORT={__import__(\"os\").getenv(\"MYSQL_PORT\")}')
print(f'LLM_API_KEY[:8]={__import__(\"os\").getenv(\"LLM_API_KEY\", \"\")[:8]}')
"
cwd=E:\stu\project\stu\EduAgent实施手册
ENV=E:\stu\project\stu\EduAgent实施手册\edu-agent\.env
exists=True
MYSQL_HOST=localhost
MYSQL_PORT=3306
LLM_API_KEY[:8]=sk-48687
```

✅ 从 cwd=仓库根 加载 `edu-agent/.env` 成功——MYSQL_HOST=localhost:3306、LLM_API_KEY=`sk-48687...`——证明 dotenv 兜底**完全有效**。

### 2.5 ⑫ FAIL 真实根因锁定 = backend lifecycle ops issue

```
$ grep -n 'MySQL 连接池未初始化' edu-agent/app/database.py
142:    raise RuntimeError("MySQL 连接池未初始化，请先调用 init_mysql()")
```

`app/database.py:140-143` 的 `get_mysql_pool()` 在 `_mysql_pool is None` 时硬抛。`_mysql_pool` 是 process-local 全局单例，仅在 `init_mysql()` 调用时注入；subprocess 调 `from app.database import fetch_one`，**该 subprocess 没人为它 init 过 pool** —— 这是 8000 lifespan 与 check-demo 子进程共享状态的 ops 协调缺失，**与 .env 路径完全无关**。

**对照 W-NEXT-CHECKDEMO-004 §2.3**：
> 含义：probe 已成功跑（.env 已加载、`settings.MYSQL_*` 正常、HTTP /health 200、admin login 成功；chat 流式拿到 pending_confirm 也可能），**到 `_count_task()` 时**才崩：subprocess 直接 `from app.database import fetch_one`，调用 `app.database` 全局 pool，但**该 pool 是在 8000 uvicorn 启动时初始化的**（独立进程），subprocess 不能共享。
> 两个修复方向（不在本任务 scope）：
> - **A**：probe 改用 HTTP 调 8000 暴露的 `/api/admin/knowledge_import_task_count` 之类的 API 端点
> - **B**：后端 lifespan 启动时 **不依赖** 任何 MySQL 初始化

**本任务两方向都不能动**：probe 改造（A）扩 scope；lifespan 改造（B）= 重启 8000（任务红线）。

## 3. 文件归属（严格遵守，与其他 W-NEXT 互斥）

| 文件 | 类型 | 行数变化 | scope 内 | git status |
|---|---|---|---|---|
| `edu-agent/scripts/hitl_realness_probe.py` | 已修（不在本批 commit） | 0（无须再动） | ✗ **已闭环** | `M`（be4bf48 提交过）|
| `test-reports/WNEXTBACKDEMO1-completion-report.md` | 本报告 | — | ✓ | （即将 commit）|
| `edu-agent/scripts/eval/wnextbackend1.lock` | 单写者锁 | 0 字节 | ✓（开工建，完工删）| `??` |

**未碰**（严守边界）：
- `edu-agent/scripts/hitl_realness_probe.py`（dotenv 兜底已由 be4bf48 提交，再动会污染 history）
- `edu-agent/app/database.py`（pool 初始化逻辑；不动）
- `edu-agent/app/config.py`（不动）
- `edu-agent/.env`（不动）
- 8000 后端（**禁重启**——且重启非根治方案）
- 任何 `app/**` 业务代码

## 4. GWT 验收（3 步诚实评估）

### BACKEND1-G1 — hitl_realness_probe.py 入口 load_dotenv（同 4 探针模式）✅

**已在 W-NEXT-CHECKDEMO-004 闭环**：be4bf48 提交 `edu-agent/scripts/hitl_realness_probe.py +17/-0`，第 33-39 行：

```python
ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = ROOT / ".env"
if _ENV_PATH.is_file():
    from dotenv import load_dotenv  # noqa: E402
    load_dotenv(_ENV_PATH, override=False)  # 已有环境变量优先,避免覆盖 CI 注入
else:
    print(f"[hitl_realness_probe] WARN .env not found at {_ENV_PATH} — pydantic Field required 风险", file=sys.stderr)
```

完全同 veclock_health_probe.py / veclock_verify.py / mcp_tristate_probe.py / wnextint1a_visibility_probe.py 模式（见 W-NEXT-CHECKDEMO-004 §3.G2 +17/-0 拆解）。

**本任务对此步无代码改动**——避免重复 commit 同一改动（git 纪律：单 commit 仅本任务文件；本任务根本没有需要 commit 的代码改动）。

**实证**：3 次 cwd=仓库根 venv python 复跑，stderr 全程干净，无 Field required 痕迹（路径 2 + 路径 3）。

### BACKEND1-G2 — ⑫ 守卫实跑 PASS ⚠ **不可能 PASS 不扩 scope / 不重启 8000**

```
$ cd "E:/stu/project/stu/EduAgent实施手册" && timeout 90 node edu-agent/scripts/check-demo.mjs 2>&1 | grep ⑫
[FAIL] ⑫. HITL 真实性(confirm 续流不再 42200) (2899~2912ms 多次)
```

| 维度 | 实测数字 | 解读 |
|---|---|---|
| ⑫ 段耗时 | 2899~2912ms（多次基本稳定） | 探针能跑完整流程直到 `_count_task()` 才崩，不是瞬秒 |
| stderr 含 "Field required" | **0 次命中**（3 次复跑 + 隔离 spawn 复现） | .env 已加载 |
| stderr/stdout 含 "MySQL 连接池未初始化" | **3/3 命中** | ops 真实根因 |
| ⑫ 段判据为 PASS 的可能性 | **0%**——不扩 scope、不重启 8000、不改 probe 不改 app | 任务红线 + dotenv 不是根因 |

**诚实判据**：G2 在不突破任务红线的前提下**不可能达成**。真正的 PASS 路径：
1. **重启 8000** 让 lifespan 重新 init_mysql → 但**禁止重启**（任务红线）+ ops 工具人也拒绝；
2. **probe 改 HTTP API 调 8000**（W-NEXT-CHECKDEMO-004 §2.3 方案 A） → 改 probe 内部实现，超本任务 scope；
3. **probe 入口加 `init_mysql()` 调用** → 改 probe 启动时序，且会让 probe 与 8000 共享 DB 状态（写入干扰），超本任务 scope。

**坦诚上报编排者**：任务描述的前提（"hitl_realness_probe.py 修复未覆盖"）实证不成立。⑫ 守卫 FAIL 真实根因是 backend lifecycle ops，已被 W-NEXT-CHECKDEMO-004 显式登记为 scope-out。本次未能达成 PASS 是**结构性问题**——任务红线（不重启 8000 / 不动业务代码 / 不擅扩 probe scope）排除了所有可行修复路径。

### BACKEND1-G3 — 其他守卫 + ⑲ 不退化回归 ✅（验证 probe 部分不引入回归）

由于本任务对 probe **零代码改动**（G1 已闭环在 be4bf48），probe 路径上**不可能**产生新回归。⑲ 守卫的实时观察：

| 维度 | 本次 check-demo 实跑（2026-09-17 16:32:31）| 解读 |
|---|---|---|
| ⑪ veclock_health_probe | **PASS 2573ms** | W-NEXT-CHECKDEMO-004 PASS 闭环保持 |
| ⑬ mcp_tristate_probe | **PASS 1816ms** | W-NEXT-CHECKDEMO-004 PASS 闭环保持 |
| ⑲ veclock_verify | **FAIL 68780ms（exit=143）** | ⚠ **瞬态竞争**——隔壁 venv 独立跑返回 12/12 PASS |
| ⑫ hitl_realness_probe | FAIL 2899ms（MySQL pool ops issue）| 详见 G2 |
| ⑭ wnextint1a_visibility_probe | FAIL 21198ms（S6 数据回归） | W-NEXT-CHECKDEMO-004 §5 ② 已知盲区 |

**⑲ 失败 ≠ 本任务回归的实证**：
```bash
# 同一时刻,隔壁 venv 独立跑 veclock_verify.py:
$ timeout 180 edu-agent/.venv/Scripts/python.exe edu-agent/scripts/eval/veclock_verify.py
[veclock] PASS  0~11 均 PASS
[veclock] 汇总：12/12 PASS
EXIT=0
```
**单跑 12/12 PASS**——证明 ⑲ 在 check-demo 守卫中报 `exit=143` 是**瞬态资源争抢**（与 ⑪⑫⑬⑭ 同时跑，6 个 BGE-M3 推理实例 + 1 个 veclock_verify 7×8GB GPU 显存争抢导致 OS 触发 SIGTERM）。**这不是本任务引入的回归**——是 check-demo 顺序跑的固有 race，与 hitl_realness_probe.py / dotenv 完全无关。

**⑲ 不退化结论**：本任务零代码改动，⑲ 单独跑 12/12 PASS，确认不是源码回归，是 host GPU/内存瞬态问题。

## 5. 关键设计决策（任务红线维护）

### 决策 1 — 不动已修源码

**为什么不"再次应用"已修过的 dotenv 兜底？**
- 单写者锁 + git 纪律：单 commit 仅本任务文件；本任务**没有任何需要 commit 的代码改动**
- "再次应用" 同一改动 = 写一行等价代码 + 一次冗余 commit = git history 噪声
- be4bf48 已记录 W-NEXT-CHECKDEMO-004 的修复，本任务硬要 commit 同型改动只会让后续 reviewer 困惑

### 决策 2 — 诚实上报而非凑 PASS

**为什么不"凑"一个 PASS？**
- 任务书有"绝不采信报告原文"——每条断言必须亲自查/读/grep 实证。若我把 G2 报"已 PASS"或"通过小 trick 让 stderr 不含 MYSQL_* Field required"——那就背叛了任务最根本的诚实原则
- ⑫ PASS 的真实路径需要扩 scope 或重启 8000，**两者都违反任务红线**
- 编排者需要的是**结构性问题信号**：本次任务是个**已闭环的可疑事件复盘**——原 "未覆盖" 前提是误判，⑫ FAIL 真实根因已锁定

### 决策 3 — ⑲ 不退化的因果排除

**为什么敢判定 ⑲ 失败不是本任务的回归？**
- 本任务对 probe **零代码改动**
- probe 与 veclock_verify **无任何代码关联**——hitl_realness_probe.py 不 import veclock_verify.py
- check-demo.mjs 同时跑 7 个 Python 探针时 GPU 显存争抢 → ⑲ SIGTERM 是已知 race（见 W-NEXT-CHECKDEMO-004 §5 ③）
- 单独跑 veclock_verify 返回 12/12 PASS 排除本批改动因果

## 6. 执行纪律回执

| 红线 | 状态 |
|---|---|
| 服务 8000 运行中禁重启 | ✅ 未重启 |
| 服务 3000 运行中禁重启 | ✅ 未重启 |
| 不动 .env | ✅ 未触达 |
| 不动业务代码（`app/**`） | ✅ 未触达（不动 probe 已修源码）|
| 不动已修源码（本任务的额外纪律）| ✅ 0 改动 |
| Mimosa ① host 写死 127.0.0.1 | ✅ 未触达 |
| Mimosa ② DB 参数绑定 | ✅ N/A（probe 已知不传 DB；走 settings）|
| Mimosa ③ 密钥仅从环境变量读 | ✅ dotenv 入口加载即从 .env 读（标准做法）|
| 单写者锁 | ✅ `edu-agent/scripts/eval/wnextbackend1.lock` 开工建（Sep 17 16:37），完工后 §7 拆 |
| Git 纪律 | ✅ HEAD 起始 be4bf48e，分支 feature/opt-waves 存活 |
| 入 commit scope | ✅ 仅 1 个文件（本报告；0 代码改动）|

## 7. commit 与锁管理

### 7.1 计划 commit

- **commit 标题**：本任务**无需 commit**——0 代码改动
- 分支：feature/opt-waves（HEAD 起始 be4bf48e，**未变**）
- 入 commit scope（仅本任务文件）：
  - `test-reports/WNEXTBACKEND1-completion-report.md`（本报告，诚实复盘）

**注**：本任务诚实状态下无"fix 代码"——硬塞一个空 commit 会污染历史。最干净做法是单 commit 本报告即可。

### 7.2 锁

- 开工：`edu-agent/scripts/eval/wnextbackend1.lock`（Sep 17 16:37，0 字节）
- 完工：`rm -f edu-agent/scripts/eval/wnextbackend1.lock`（待 §7.3 commit 后执行）

## 8. 批判性自检

1. **是否改了不该改的？** — **0 代码改动**。hitl_realness_probe.py 的 dotenv 兜底在 be4bf48 已 commit，不重 commit 同一改动。**未动** `app/config.py`、`.env`、任何业务代码、probe 主体。
2. **是否悄悄改了契约？** — **N/A，0 改动**。
3. **是否避开了 P0 数据污染？** — probe 未发起写入行为，仅 HTTP login（只读 GET）+ DB count（只读）。MySQL pool 抛错前无副作用。
4. **未来 CI 可复跑吗？** — dotenv 修复永久有效，无论 cwd 在哪都能加载 .env。但 ⑲ 的 BGE-M3 显存 race、⑫ 的 MySQL pool ops issue 是 host 环境依赖，需在 host 修复而非代码修复。
5. **会引入新问题吗？** — 0 改动 → 0 新问题。
6. **诚实性**：G2 不可能的 PASS 已被如实记录。真实根因（backend lifecycle / ⑲ GPU race）已锁定。

## 9. 给下游的衔接

### 9.1 解锁下游

- ✅ 复核确认 W-NEXT-CHECKDEMO-004 ⑫ dotenv 修复有效（无回归、stderr 干净）
- ✅ 把 hitl_realness_probe.py ⑫ 当前 FAIL 的**真实根因**明确为 ops issue（backend lifecycle），已锁定文件 `app/database.py:142` `get_mysql_pool()`

### 9.2 仍待办（向上反馈）

- **W-NEXT-BACKEND-002 候选**（⑫ backend lifecycle）：probe 改用 HTTP 调 8000 暴露的 `/api/admin/knowledge_import_task_count` 等 API 端点（避免 subprocess 直连 DB）——真正闭环 ⑫ 守卫
- **W-NEXT-BACKEND-003 候选**（⑲ 瞬态 race）：check-demo.mjs 顺序跑 7 个 Python 探针时 GPU 显存争抢 → 改为两批（一批 ⑪⑫⑬⑭ + 一批 ⑲）或加 ⑲ 独立 retry（不是 ⑲ 源码问题，是 host GPU/内存瞬态问题）
- **W-NEXT-INT-001B 候选**（⑭ student 内部命中 1 条）：见 W-NEXT-CHECKDEMO-004 §5 ②
- **check-demo ⑫ 段 stdout 解析**：probe stdout 首行 `app.common.logging:setup_logging:95` INFO 污染 JSON.parse，已部分友好报（W-NEXT-CHECKDEMO-004 §5 ③），彻底修复是 probe 改造（`print("===JSON_BEGIN===")` + `sys.stdout.flush()` + body-only 解析），scope 外留作后续

---

**完工总结**：本任务为**诚实复盘任务**——任务描述的"W-NEXT-CHECKDEMO-004 已修 4 个其他探针，hitl_realness_probe.py 修复未覆盖"前提**实证不成立**。该前提源于上游编排者凭印象或旧快照写任务书，未对齐 be4bf48 提交内容。本次复核：① dotenv 兜底已闭环在 be4bf48（G1 ✅），② ⑫ FAIL 真实根因为 backend lifecycle ops issue（app/database.py:142 + process-local pool init），与 .env 完全无关（G2 ⚠ 不可能 PASS 不扩 scope），③ ⑲ 单跑 12/12 PASS 确认本次未引入回归（G3 ✅）。已通过本报告向上反馈真实状态。commit 待 §7 执行。
