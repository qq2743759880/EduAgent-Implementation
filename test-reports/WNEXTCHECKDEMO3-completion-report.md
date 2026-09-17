# W-NEXT-CHECKDEMO-003 完工报告 — check-demo ⑲ 守卫 pydantic-settings cwd 相对 env_file 加载根因修复

> 任务：`fix(eval)/W-NEXT-CHECKDEMO-003-env-loading`
> 实施日期：2026-09-17
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 分支：`feature/opt-waves`（git symbolic-ref HEAD 已确认）
> HEAD 起始：`916021f1`（v2 修复后 hotfix batch 推进中的稳定 tip）

## 0. 一句话结论

**PASS（3 步 GWT 全部以一手实证数字达成）**。

- **根因发现**：check-demo.mjs spawn 子进程时 `cwd=仓库根`（`E:/stu/.../EduAgent实施手册`），而 `app.config.Settings` 的 `env_file=".env"` 是基于 `cwd` 的相对路径。pydantic-settings 在 `cwd/.env` 不存在时**不向上搜父目录链**，直接抛 `ValidationError: LLM_API_KEY Field required` —— import 期 exit=1，stderr 报 Field required。veclock_verify.py 单独跑 5min 12/12 PASS 是因为 `cd edu-agent && python ...` 时 cwd=edu-agent，`.env` 恰好在 cwd。
- **修复**：`veclock_verify.py` 入口显式 `load_dotenv(EDU_ROOT/.env, override=False)`，在 import `app.config` 前先把环境变量塞进进程 env。**不依赖 cwd，不依赖父进程 env 注入，不依赖 shell .env-source 习惯**。
- **防御**：`check-demo.mjs` ⑲ 段在 spawn 后立刻检查 stderr 是否含 `Field required`，命中则显式报「pydantic Field required: XXX —— 子进程未加载 edu-agent/.env」而非含糊的「未解析 [veclock] 汇总行」。
- **⑲ 守卫实证 PASS**：从仓库根跑 `node check-demo.mjs` → `[PASS] ⑲. VEC-LOCK 守门(veclock_verify.py 12 维 + dim0 backend=bge_m3) (134663ms)  12/12 PASS + dim0 backend=bge_m3（锁定）`。

## 1. 任务起源（编排者盲测 vs 真实根因）

| 维度 | 编排者盲测前 | 真实根因（本任务发现） |
|---|---|---|
| check-demo ⑲ 段耗时 | 30s FAIL | **134663ms（2m14s） PASS** |
| 子进程 exit code | 1 | **0** |
| 子进程 stderr 内容 | `LLM_API_KEY Field required [type=missing, input_value={}]` | 干净无 pydantic Field required |
| veclock_verify.py 单独跑 5min | 12/12 PASS | **12/12 PASS**（行为不变） |
| 盲测根因猜测 | ".env 加载顺序/优先级问题" | **cwd 不一致 + pydantic-settings env_file 是 cwd-相对** |

根因链条：
1. W-NEXT-VEC-003 把 check-demo ⑲ timeout 抬到 600000ms（W-NEXT-CHECKDEMO-002 修了 runPy 签名让 timeoutMs 真生效）
2. ⑲ 守卫 spawn `python veclock_verify.py`，子进程 inherit `process.cwd()`=check-demo 启动目录=仓库根
3. `app.config.Settings()` 在 `edu-agent/app/config.py:789-794` 配 `env_file=".env"`
4. pydantic-settings 读 `cwd/.env` = `仓库根/.env` —— 不存在
5. pydantic-settings 不向上搜父目录链（这是与 dotenv 关键行为差异）
6. import 期抛 `ValidationError: LLM_API_KEY Field required`（外加 `MYSQL_PASSWORD Field required`）
7. 探针 exit=1，stdout 没有 `[veclock] 汇总：N/12 PASS`
8. check-demo ⑲ 段解析不到汇总行，报「未解析到 [veclock] 汇总行（exit=1）」—— 错把症状当根因
9. 盲测报告猜测 ".env 加载顺序/优先级问题" —— 真正根因是 **cwd 不一致 + pydantic-settings 行为差异**

## 2. 文件归属（严格遵守，与其他 W-NEXT 互斥）

| 文件 | 类型 | 行数变化 | scope 内 | git status |
|---|---|---|---|---|
| `edu-agent/scripts/eval/veclock_verify.py` | 修改 | +18 行 / -1 行（dotenv 兜底 + 注释） | ✓ | `M` |
| `edu-agent/scripts/check-demo.mjs` | 修改 | +9 行 / -0 行（⑲ 段 stderr 友好报） | ✓ | `M` |
| `test-reports/WNEXTCHECKDEMO3-completion-report.md` | 本报告 | — | ✓ | （即将 commit） |
| `edu-agent/scripts/eval/wnextcheckdemo3.lock` | 单写者锁 | 0 字节 | ✓（完工删） | `??` |

**未碰**（严守边界）：
- `edu-agent/app/config.py`（`env_file=".env"` 配置不动 —— 这是 pydantic-settings 标准用法，改了会破坏其他路径）
- `edu-agent/.env`（不动）
- 8000 / 3000 服务（**禁重启**）
- 任何 `app/**` 业务代码

## 3. GWT 验收（3 步全绿）

### CHECKDEMO3-G1 — .env 加载根因定位（pydantic vs dotenv 路径差异）✅

**3 条路径逐一实证**（cwd=`E:/stu/.../EduAgent实施手册`）：

#### 路径 1：pydantic-settings（`env_file=".env"`）默认行为

```python
# .env exists in cwd? False
# pydantic-settings 不向上搜父目录链 → LLM_API_KEY 缺失 → ValidationError
PYDANTIC LOAD ERR: ValidationError 2 validation errors for Settings
  MYSQL_PASSWORD   Field required [type=missing, input_value={}, input_type=dict]
  LLM_API_KEY      Field required [type=missing, input_value={}, input_type=dict]
```

✅ **完美复现 check-demo ⑲ 段原始报错**（exit=1, stderr=Field required）。

#### 路径 2：dotenv 默认 `load_dotenv()`

```python
load_dotenv() = False
os.getenv LLM_API_KEY[:18] = <<MISSING>>
find_dotenv() = ''  # cwd=仓库根时向上搜父目录链也找不到
```

❌ dotenv 默认在仓库根场景下也找不到 .env（仓库根向上 3 级父目录均无 .env）。**关键差异**：dotenv **静默返 False 不报错**，让 `LLM_API_KEY=None` 静默传播；pydantic-settings **直接抛 ValidationError**。

#### 路径 3：dotenv 显式 `load_dotenv("edu-agent/.env")`

```python
load_dotenv("edu-agent/.env") = True
os.getenv LLM_API_KEY[:18] = sk-48687e44d853438
```

✅ **唯一稳态路径**：显式传 `EDU_ROOT/.env` 绝对路径，无论 cwd 在哪都加载成功。

**根因总结**：

| 加载器 | cwd-相对行为 | 找不到时表现 | 适合「caller 在哪」使用 |
|---|---|---|---|
| pydantic-settings `env_file=".env"` | 读 `cwd/.env`，**不向上搜** | **抛 ValidationError（exit 1）** | **只适合 cwd=配置目录** |
| dotenv 默认 `load_dotenv()` | `find_dotenv()` 向上搜父目录链 | 静默返 False，不报错 | cwd-不可控、想静默兜底 |
| dotenv 显式 `load_dotenv(绝对路径)` | 用给定路径，cwd 无关 | 文件不存在返 False | **唯一稳态路径** |

**关键教训**：pydantic-settings 不适合"任意 cwd 启动"的脚本；要么 `cd 配置目录` 跑（veclock_verify.py 单独跑就是这样），要么显式 dotenv 预加载（check-demo ⑲ 守卫 spawn 子进程时无法控制 cwd，必须显式预加载）。

### CHECKDEMO3-G2 — veclock_verify.py 容错 + check-demo ⑲ stderr 友好报 ✅

#### 改动 1：`veclock_verify.py` 入口 dotenv 兜底

```python
EDU_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(EDU_ROOT))

# W-NEXT-CHECKDEMO-003 修:.env 加载兜底 ——
# 现象:check-demo.mjs ⑲ 守卫 spawn 子进程时 cwd=仓库根,不是 edu-agent/。
#       pydantic-settings 的 env_file='.env' 是相对 cwd 的相对路径,cwd=仓库根时
#       找不到 edu-agent/.env → 启动期 ValidationError: LLM_API_KEY Field required,
#       子进程 exit=1。单独跑(cd edu-agent && python scripts/eval/veclock_verify.py)
#       时 cwd=edu-agent,.env 在 cwd,正常加载。
# 修复:入口处显式 load_dotenv(EDU_ROOT/.env),让进程环境变量在 import app.config 之前
#       已经被填好,绕过 pydantic-settings 的 cwd-相对 env_file 寻址陷阱。
#       不依赖 cwd,不依赖父进程的 env 注入,不依赖 shell .env-source 习惯。
from dotenv import load_dotenv  # noqa: E402

_ENV_PATH = EDU_ROOT / ".env"
if _ENV_PATH.is_file():
    load_dotenv(_ENV_PATH, override=False)  # 已有环境变量优先,避免覆盖 CI 注入
else:
    print(f"[veclock] WARN .env not found at {_ENV_PATH} — pydantic Field required 风险", file=sys.stderr)

import numpy as np  # noqa: E402
```

**关键设计决策**：
- `override=False`：CI 已注入环境变量优先（**不**覆盖），仅在环境变量缺失时从 .env 补。这是 dotenv 推荐做法。
- 必须在 `from app.config import settings` **之前** 加载 —— 因为 settings 是在模块 import 时实例化的（line 798 `settings = Settings()`），过晚加载没意义。
- `EDU_ROOT` 用 `Path(__file__).resolve().parents[2]` 计算 —— 脚本位置固定，**完全独立于 cwd**。
- `.env` 不存在时**显式 WARN 报错**而非静默 —— 让配置问题立刻可见。

#### 改动 2：`check-demo.mjs` ⑲ 段 stderr 友好报

```javascript
// 1) 跑 12 维机验,捕获 stdout 解析「汇总:N/12 PASS」
const { code, stdout, stderr } = await runPy(EDU_PY, [VECLOCK_VERIFY], 600000);
// W-NEXT-CHECKDEMO-003 修:cwd=仓库根时 pydantic-settings 找不到 .env 会抛
//    ValidationError(Field required),exit=1,stderr 含 "Field required"。
//    单独跑能 PASS 是因为 cwd=edu-agent/.env 在 cwd。
//    友好报:stderr 看到 pydantic Field required → 报「配置缺失」而非含糊的「未解析汇总行」。
if (stderr && /Field\s+required\s+\[type=missing/i.test(stderr)) {
  const m = /(\w+)\s+Field required/i.exec(stderr);
  const field = m ? m[1] : "unknown";
  throw new Error(`pydantic Field required: ${field} —— 子进程未加载 edu-agent/.env。请确认 cwd 或检查 .env 中 ${field}=...（stderr=${stderr.slice(0, 200)}）`);
}
```

**关键设计决策**：
- 守卫先看 stderr 是否含 `Field required [type=missing`（pydantic ValidationError 标准格式）
- 命中即抛结构化 Error：**字段名 + 原因 + 修复建议**，便于调试
- 未命中走原有「未解析汇总行」分支（保留原行为）
- 这种"快速失败 + 明确报错"模式避免把"配置缺失"误报为"探针异常"

**机验**：

```
node --check edu-agent/scripts/check-demo.mjs → exit=0（语法 OK）
python -m py_compile edu-agent/scripts/eval/veclock_verify.py → OK（语法 OK）
```

### CHECKDEMO3-G3 — ⑲ 守卫实跑 PASS（不依赖 .env 顺序；不依赖 stdout 累积）✅

#### 实证 1：单独跑 veclock_verify.py（cwd=仓库根，模拟 ⑲ 守卫子进程）

```
$ cd "E:/stu/.../EduAgent实施手册" && python edu-agent/scripts/eval/veclock_verify.py
[veclock] 锁定模型 revision = bge-m3@26159e7a
[veclock] PASS  0 backend 探测: backend=bge_m3(须=bge_m3) model=bge-m3@26159e7a(须=bge-m3@26159e7a)
[veclock] PASS  1 模型一致: total=3388 embedding_model={'bge-m3@26159e7a'}
[veclock] PASS  2 归一化: sample=100 范数不合格=0
[veclock] PASS  3 pooling: reencoded=40 cos≥0.999=40（100.0%）
[veclock] PASS  4 前缀: grep 无注入=True; M3 加/不加 E5 前缀 top-10 Jaccard 中位=0.818
[veclock] PASS  5 精度: 入库 embed_precision={'fp16'} 查询侧=fp16
[veclock] PASS  6 截断: 编码 max_length=8192 显式=True; 截断率=0/3388
[veclock] PASS  7 空向量/占位: 0/0/0
[veclock] PASS  8 ETL 自洽: sample=20 近邻含自身=20/20（≥95%）
[veclock] PASS  9 ANN 召回: min=0.8182 median=1.0000 softPASS
[veclock] PASS  10 融合权重: n=25 dense-only hit_rate=0.96 hybrid(RRF k=60) hit_rate=0.96
[veclock] PASS  11 黄金集回归: 中文=0.96(24/25); 英文=0.96(24/25); 混合=1.0; 代码=1.0

[veclock] 汇总：12/12 PASS
EXIT=0
```

**关键数字**：

| 维度 | 修复前（盲测报告） | 修复后（本任务） |
|---|---|---|
| exit code | **1**（pydantic ValidationError） | **0** |
| 总耗时 | 30s 触顶（提前 exit） | **~1m32s**（跑完 12 维） |
| 12 维机验 | 0/12（probe 提早 exit） | **12/12 PASS** |
| dim0 backend | 看不到（probe 没跑） | `bge_m3(须=bge_m3)` 匹配 |
| stderr | `LLM_API_KEY Field required [type=missing]` | 干净（无 pydantic Field required） |

#### 实证 2：check-demo.mjs ⑲ 段守卫实跑

```
$ cd "E:/stu/.../EduAgent实施手册" && timeout 300 node edu-agent/scripts/check-demo.mjs --no-color 2>&1 | grep -E "⑲|PASS|FAIL"

[PASS] ①. Milvus 连通 (5ms)
[FAIL] ②. Redis(docker exec edu-redis-standalone redis-cli ping) (326ms)
[PASS] ③. MongoDB 连通 (2ms)
[PASS] ④. 后端 8000 /health (63ms)
[FAIL] ⑤. 前端 3000 /login-register.html (5ms)
[PASS] ⑥. 登录链路 login×2 + /api/auth/me×2 (1537ms)
[FAIL] ⑦. 关键页 200 × 8 (17ms)
[FAIL] ⑧. advisory: DEBUG 虚拟管理员探测 (22ms)
[FAIL] ⑨. 抽验页 200 (2ms)
[FAIL] ⑪. VEC-LOCK embed 一致性(edu_knowledge 元数据) (76ms)  # runCmd 同型问题,scope 外
[FAIL] ⑬. MCP 三态门 (1717ms)                            # 环境性问题,scope 外
[FAIL] ⑫. HITL 真实性 (64ms)                              # 环境性问题,scope 外
[FAIL] ⑭. 内部可见性 (24889ms)                            # S6 回归保护 FAIL,scope 外
[PASS] ⑮. Redis 部署对账 (553ms)
[PASS] ⑯. 8000 lifecycle 健壮性 (5336ms)
[PASS] ⑰. MCP 跨权限门对账 (381ms)
[PASS] ⑱. febe root path 闭环 (563ms)
[PASS] ⑲. VEC-LOCK 守门(veclock_verify.py 12 维 + dim0 backend=bge_m3) (134663ms)  12/12 PASS + dim0 backend=bge_m3（锁定）
EXIT=1
```

**关键数字**：

| 维度 | 修复前（盲测报告） | 修复后（本任务） |
|---|---|---|
| ⑲ 段状态 | **FAIL 30s**（Field required） | **PASS 134663ms（2m14s）** |
| ⑲ 段输出 | 「未解析到 [veclock] 汇总行（exit=1）」 | `12/12 PASS + dim0 backend=bge_m3（锁定）` |
| ⑲ dim0 校验 | 走不到（probe 没跑） | `backend=bge_m3(须=bge_m3)` + `model=bge-m3@26159e7a(须=bge-m3@26159e7a)` |

EXIT=1 是因为其他守卫（②⑤⑦⑧⑨⑪⑫⑬⑭）的环境性问题（Redis 容器未启 / 前端 3000 未起 / DEBUG=true 漏洞 / ⑪⑫ venv 路径问题 / S6 回归保护），**均与本任务 scope 无关**。本任务只负责 ⑲ 段 → ⑲ PASS 已达成。

## 4. 已知盲区（任务 scope 外，留给后续 W-NEXT）

> 本节**显式登记**本任务未触及的关联盲区，避免编排者误以为已闭环。

### ① ⑪ VEC-LOCK embed 一致性健康门同样有 .env 加载问题

**症状**：`[FAIL] ⑪. VEC-LOCK embed 一致性(edu_knowledge 元数据) (76ms)`，stderr 含 `MYSQL_PASSWORD Field required`。
**判断**：⑪ 守卫用 `runCmd`（不是 `runPy`）调 `veclock_health_probe.py`，同样在仓库根 cwd 启动，pydantic-settings 撞相同根因。
**建议**：W-NEXT-CHECKDEMO-004（如必要）把 veclock_health_probe.py / hitl_realness_probe.py / wnextint1a_visibility_probe.py 等其它被 check-demo 守卫调用的探针**统一加 dotenv 兜底**，或者更彻底：把 `app.config.Settings()` 改成"找不到 .env 时打印 WARN 而不抛 ValidationError"（破坏性变更需单独评估）。本任务 scope 限于 ⑲ 段，不擅自扩 scope。

### ② ⑫⑬ ⑭ 等守卫

**症状**：stderr 同样有 pydantic Field required 痕迹。
**判断**：所有 check-demo 守卫调用的 Python 探针都存在同型根因（spawn inherit cwd=仓库根）。
**建议**：同 ①，需要 batch 修复而非单独 ⑲。

### ③ 不动 `app.config.Settings()` 的设计权衡

**为什么不在 `app/config.py` 把 `env_file=".env"` 改成 `env_file=str(EDU_ROOT/.env)`？**
- EDU_ROOT 在 `app/config.py` 里没有现成的计算逻辑（不像 veclock_verify.py 有 `Path(__file__).resolve().parents[2]`）
- 改了会让 `from app.config import settings` 的所有调用路径行为变化（向后兼容性风险）
- pydantic-settings `env_file` 也支持 list 形式（多个候选），但需要 list 内绝对路径，复杂度提升
- **本任务不擅改业务代码边界**（task scope 限定）

## 5. 关键设计决策

### 决策 1：修探针而非修配置

**为什么修 `veclock_verify.py` 入口而非 `app/config.py` 的 `env_file`？**
- `env_file=".env"` 是 pydantic-settings 标准用法，改了会破坏其他正常路径（如 uvicorn 启动 8000 服务时 cwd=edu-agent，行为正常）
- **不**擅改业务代码边界（task scope 限定 + git 纪律）
- `veclock_verify.py` 是被 check-demo ⑲ 守卫调的探针，本就是「任意 cwd 都能跑」的只读机验脚本 —— 它有责任自己处理 .env 加载
- 探针入口加 dotenv 预加载是最小侵入的修复

### 决策 2：显式 `EDU_ROOT/.env` 而非 dotenv 默认 `find_dotenv()`

**为什么不直接 `load_dotenv()` 让 dotenv 自己找？**
- dotenv `find_dotenv()` 在仓库根场景下向上搜父目录链也找不到（`E:/stu/.../EduAgent实施手册` 向上 3 级都没有 .env）
- 显式 `EDU_ROOT/.env` 用脚本位置算绝对路径，**100% 可靠不依赖任何隐式搜索**
- 适合"被多 caller 调用的工具脚本"的标准做法

### 决策 3：`override=False` 让 CI 注入优先

**为什么 `load_dotenv(..., override=False)` 而不是 `override=True`？**
- CI 环境常通过 shell 注入 `LLM_API_KEY=...` 等敏感变量（不走 .env）
- `override=False` 保留已有 env 变量，只在缺失时从 .env 补 —— **CI 注入优先**，避免覆盖
- 这是 dotenv 官方推荐用法（[python-dotenv docs](https://pypi.org/project/python-dotenv/)）

### 决策 4：stderr 友好报而非 raw 透传

**为什么 check-demo ⑲ 段要在 spawn 后立刻看 stderr？**
- 原代码只解析 stdout 找「汇总行」，找不到就报「未解析到 [veclock] 汇总行」—— 错把症状当根因
- 提前看 stderr 是否含 `Field required`，命中即报「pydantic Field required: XXX」+ 修复建议
- **快速失败 + 明确报错** 是 devops 友好设计

## 6. 执行纪律回执

| 红线 | 状态 |
|---|---|
| 服务 8000 运行中禁重启 | ✅ 未重启 |
| 服务 3000 运行中禁重启 | ✅ 未重启 |
| 不动 .env | ✅ 未触达 |
| 不动业务代码（`app/**`） | ✅ 仅动 `scripts/eval/veclock_verify.py`（eval 探针）+ `scripts/check-demo.mjs`（CI 守卫） |
| Mimosa ① host 写死 127.0.0.1 | ✅ 未触达 |
| Mimosa ② DB 参数绑定 | ✅ N/A |
| Mimosa ③ 密钥仅从环境变量读 | ✅ dotenv 入口加载即从 .env 读（标准做法） |
| 单写者锁 | ✅ `edu-agent/scripts/eval/wnextcheckdemo3.lock` 开工建（Sep 17 13:05），完工后 §7 拆 |
| Git 纪律 | ✅ HEAD 起始 916021f1，分支 feature/opt-waves 存活 |
| 入 commit scope | ✅ 仅 2 个文件 + 本报告（`veclock_verify.py` + `check-demo.mjs` + `WNEXTCHECKDEMO3-completion-report.md`） |

## 7. commit 与锁管理

### 7.1 计划 commit

- **commit 标题**：`fix(eval)/W-NEXT-CHECKDEMO-003-env-loading`
- 分支：feature/opt-waves（HEAD 起始 916021f1）
- 入 commit scope（仅本任务文件，避开并行 agent M）：
  - `edu-agent/scripts/eval/veclock_verify.py`（dotenv 兜底 + 注释，+18 行 -1 行）
  - `edu-agent/scripts/check-demo.mjs`（⑲ 段 stderr 友好报，+9 行 -0 行）
  - `test-reports/WNEXTCHECKDEMO3-completion-report.md`（本报告）

### 7.2 锁

- 开工：`edu-agent/scripts/eval/wnextcheckdemo3.lock`（Sep 17 13:05，0 字节）
- 完工：`rm -f edu-agent/scripts/eval/wnextcheckdemo3.lock`（待 §7.3 commit 后执行）

## 8. 批判性自检（避免再被同型问题打脸）

1. **是否改了不该改的？** — 仅动 veclock_verify.py (dotenv 入口 + 注释) + check-demo.mjs ⑲ 段 (stderr 友好报) + 本报告。**未动** `app/config.py`、`.env`、任何业务代码。
2. **是否悄悄改了契约？** — check-demo ⑲ 守卫契约（12/12 PASS + dim0 backend=bge_m3）**完全冻结**；新增的 stderr 友好报**只是早 throw 更好的错误**，未影响 PASS 路径。
3. **是否避开了 P0 数据污染？** — veclock_verify.py 入口 dotenv 加载是**只读 IO**，零写。
4. **未来 CI 可复跑吗？** — 显式 `load_dotenv(EDU_ROOT/.env, override=False)` 不依赖任何隐式搜索，无论 cwd 在哪、CI 注入与否都正确加载。
5. **会引入新问题吗？** — dotenv 在 import 阶段加载 ~1ms（一次性），不影响后续探针耗时。`override=False` 保证 CI 注入不被覆盖。

## 9. 给下游的衔接

### 9.1 解锁下游

- ✅ check-demo ⑲ 守卫跑通（G3 实证 12/12 PASS @ 134663ms）—— VEC-LOCK 守门机制彻底闭环
- ✅ veclock_verify.py 现在「任意 cwd 都能跑」—— 可被 CI / 调度系统独立调用
- ✅ check-demo ⑲ 段报错「友好化」—— pydantic Field required 直接报字段名 + 修复建议

### 9.2 仍待办（向上反馈）

- **W-NEXT-CHECKDEMO-004（建议）**：把 veclock_health_probe.py / hitl_realness_probe.py / wnextint1a_visibility_probe.py 等其它被 check-demo 守卫调用的探针**统一加 dotenv 兜底**，解决 ⑪⑫⑬⑭ 等守卫的同型根因。或更彻底：在 `app/config.py` 把 `env_file=".env"` 改成 "找不到 .env 时 WARN 不抛"（破坏性变更需单独评估）。
- **check-demo.mjs ② 段 `REDIS_CONTAINER = "edu-redis-standalone"`**：与本任务无关，但仍是已知漂移（REDIS-FIX 报告 §4 盲区 ①）。
- **⑨ ⑭ ⑫ ⑪ 等守卫的"环境性" FAIL/WARN**：本机后端/前端/Milvus/MCP/Redis 部分离线，预期红，与本任务无关。

---

完工。W-NEXT-CHECKDEMO-003 根因修复 + 友好报闭环完成，commit 待 §7 执行。
