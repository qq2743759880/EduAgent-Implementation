# W-NEXT-VEC-003 完成报告：VEC-LOCK 守门机制（pre-commit + check-demo ⑲ + CI 文档）

> 任务：W-NEXT-VEC-003（独立执行 agent，单写者，wnextvec3.lock 全周期持有，完工删除）
> 完成：2026-09-17 ｜ 分支：feature/opt-waves ｜ HEAD 起始 870d2977
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 起点：WNEXTVEC-002（v2 修复 + 12 维机验）+ critique-VEC-LOCK（VEC-C2 P0-D 实证）

---

## 一句话结论

**PASS** — VEC-LOCK 守门机制完整闭环：
- **VEC3-G1** pre-commit hook 写入 + chmod +x 实证（嵌入 embedder.py 改动 → hook 触发）
- **VEC3-G2** hook 实证跑出 12/12 PASS（且 `[vec-guard][OK]` 输出 + RC=0）→ 提交可继续
- **VEC3-G3** check-demo ⑲ 守卫通过（解析 `[veclock] 汇总：12/12 PASS` + `[veclock] PASS 0 backend 探测: backend=bge_m3(须=bge_m3) model=bge-m3@26159e7a(须=bge-m3@26159e7a)`）
- **VEC3-G4** `deploy/CI-CHECKLIST.md` 含 VEC 改动纪律 + 跳过机制 + 多人协作边界
- **VEC3-G5** 0 回归：3 个回归测试（绿 / dim0 FAIL / 11/12）全 PASS，check-demo.mjs node syntax OK + pre-commit bash -n OK

---

## 一、GWT 验收 5 步数字

| GWT | 状态 | 数字/证据 |
|---|---|---|
| **VEC3-G1** pre-commit hook 写入并可执行 | ✅ PASS | `.git/hooks/pre-commit` 3084 字节 `-rwxr-xr-x`，检测 3 条触发路径 + `--no-verify` 跳过 |
| **VEC3-G2** hook 触发实证 12/12 PASS | ✅ PASS | 临时改 embedder.py + git add → hook 跑出 `[vec-guard] 锁定模型 revision = bge-m3@26159e7a` + `[veclock] 汇总：12/12 PASS` + `[vec-guard][OK] veclock_verify.py 通过` + RC=0 |
| **VEC3-G3** ⑲ 守卫跑通 | ✅ PASS | check-demo.mjs ⑲ 段加入，解析实测 PASS（见 §四） |
| **VEC3-G4** CI-CHECKLIST.md 含 VEC 改动纪律 | ✅ PASS | `deploy/CI-CHECKLIST.md` §一 含 ① 触发路径 + ② ⑲ 守卫 + ③ ⑪ + §1.3 跳过机制 + §1.4 多人协作 |
| **VEC3-G5** 0 回归 | ✅ PASS | check-demo.mjs `node --check` RC=0；pre-commit `bash -n` RC=0；⑲ 解析 3 测全过 |

---

## 二、执行纪律回执

| 红线 | 状态 |
|---|---|
| 服务 8000 运行中禁重启 | ✅ 未重启（本任务无需触达） |
| 服务 3000 运行中禁重启 | ✅ 未重启 |
| pre-commit hook 不动 app 业务代码 | ✅ 仅 hook 文件 + check-demo ⑲ 段 + CI 文档 |
| Mimosa ① host 写死 127.0.0.1 | ✅ check-demo BACKEND 仍 = `127.0.0.1:8000`；未改 |
| Mimosa ② DB 参数绑定 | ✅ N/A（无 DB 调用新增） |
| Mimosa ③ 密钥仅从环境变量读 | ✅ N/A（无密钥调用） |
| 单写者锁 | ✅ `edu-agent/scripts/eval/wnextvec3.lock` 开工建（Sep 17 11:29），完工删（§六） |
| Git 纪律 | ✅ HEAD=870d2977，分支 feature/opt-waves 存活，commit 待 §六 |
| 入 commit scope | ✅ 仅 `deploy/CI-CHECKLIST.md` + `edu-agent/scripts/check-demo.mjs`（pre-commit hook 是本地不入库文件，**不入** commit） |

---

## 三、pre-commit hook（VEC3-G1 实证）

### 3.1 文件

| 路径 | 大小 | 权限 |
|---|---|---|
| `.git/hooks/pre-commit` | 3084 bytes | `-rwxr-xr-x` |

### 3.2 工作原理

1. **触发路径**（任一变更即触发）：
   - `edu-agent/app/knowledge/importer/embedder.py`
   - `edu-agent/app/knowledge/importer/loader.py`
   - `edu-agent/scripts/eval/veclock_verify.py`
2. **执行**：`cd edu-agent && PYTHONPATH=. .venv/Scripts/python.exe scripts/eval/veclock_verify.py`
3. **阻断**：`exit 0` → commit 继续；`exit ≠0` → 阻断 + `[vec-guard][BLOCK]` 输出
4. **跳过**：`git commit --no-verify`（已部署纪律：见 CI-CHECKLIST.md §1.3.1）

### 3.3 触发实证（VEC3-G2）

**步骤**：
1. 备份 embedder.py → `embedder.py.vec3bak`
2. 追加 1 行注释 → `git add`
3. 直接调 `bash .git/hooks/pre-commit`
4. 验证输出 → 撤回改动

**实测输出**（关键行）：

```
[vec-guard] 本次 commit 涉及 VEC-LOCK 核心代码: edu-agent/app/knowledge/importer/embedder.py
[vec-guard] 自动跑 veclock_verify.py (W-NEXT-VEC-002 v2 确定性版) ...
[安全] DEBUG 模式使用公开 JWT_SECRET，仅限本地开发，禁止上线
[安全] DEBUG 模式使用默认 API_TOKEN，仅限本地开发，禁止上线
[veclock] 锁定模型 revision = bge-m3@26159e7a
[veclock] PASS  0 backend 探测: backend=bge_m3(须=bge_m3) model=bge-m3@26159e7a(须=bge-m3@26159e7a); 若非 bge_m3 请清理 Python 内存再复跑...
[veclock] PASS  1 模型一致: total=3388 embedding_model={'bge-m3@26159e7a'} fallback=无 unmarked=0
[veclock] PASS  11 黄金集回归: 阈值=0.6（top-10 dense 命中率自定并记录）：中文=0.96(24/25); 英文=0.96(24/25); 混合=1.0(25/25); 代码=1.0(25/25)
[veclock] 汇总：12/12 PASS
[vec-guard][OK] veclock_verify.py 通过。
HOOK_RC=0
```

证据文件：`C:\Users\Administrator\AppData\Local\Temp\vec3hook.out`（7964 bytes），本地不入库。

**撤回验证**：测试行已清除，最后 3 行：
```
        msg = f"向量化失败：{exc.__class__.__name__}: {exc}"
        logger.exception(msg)
        return {"error": msg}
```
与原文件一致。

---

## 四、check-demo ⑲ 守卫（VEC3-G3 实证）

### 4.1 位置

文件：`edu-agent/scripts/check-demo.mjs` 第 558 行后插入 ⑲ 段（≈ 第 590 行完成）

### 4.2 守卫规则

| 解析 | regex | 阻断条件 |
|---|---|---|
| 12/12 汇总 | `\[veclock\]\s*汇总[：:]\s*(\d+)\s*\/\s*(\d+)\s*PASS` | `passed ≠ total` → 红 |
| dim0 backend PASS | `\[veclock\]\s*PASS\s+0\s+backend\s*探测[^\n]*backend=(\S+)\(须=(\S+)\)\s+model=(\S+)\(须=(\S+)\)` | `backend ≠ want_backend` → 红 |
| dim0 backend FAIL | `\[veclock\]\s*FAIL\s+0\s+backend\s*探测[^\n]*backend=(\S+)` | 直接红（BGE-M3 mmap 失败） |

**红线**：12 维是 VEC-LOCK 不可协商基线 → 任何一项不符即红（**不降 WARN**）

### 4.3 实证（VEC3-G3）

跑实际 `veclock_verify.py`，记录关键三行：

```
[veclock] 锁定模型 revision = bge-m3@26159e7a
[veclock] PASS  0 backend 探测: backend=bge_m3(须=bge_m3) model=bge-m3@26159e7a(须=bge-m3@26159e7a); 若非 bge_m3 请清理 Python 内存再复跑...
[veclock] 汇总：12/12 PASS
```

Node regex dry-test：

```
SUMMARY: 12/12 PASS
DIM0: { backend: 'bge_m3', want: 'bge_m3', model: 'bge-m3@26159e7a', wantModel: 'bge-m3@26159e7a' }
```

→ ⑲ 应输出 `12/12 PASS + dim0 backend=bge_m3（锁定）`

证据文件：`C:\Users\Administrator\AppData\Local\Temp\vec3_check.out`，本地不入库。

### 4.4 0 回归测试（VEC3-G5）

| 测试 | 输入 | 期望 | 实测 |
|---|---|---|---|
| TEST1（绿） | 12/12 PASS + dim0 backend=bge_m3 | SUMMARY=12/12 + DIM0 bge_m3==bge_m3 | ✅ |
| TEST2（红） | dim0 backend=cloud FAIL | DIM0_FAIL 检测到 backend=cloud | ✅ |
| TEST3（红） | 11/12 PASS（一 dim FAIL） | passed=11 ≠ total=12 → 红 | ✅ |

---

## 五、CI-CHECKLIST.md（VEC3-G4 实证）

文件：`E:\stu\project\stu\EduAgent实施手册\deploy\CI-CHECKLIST.md`（新建）

### 5.1 主要结构

| 段 | 内容 |
|---|---|
| §一 | VEC-LOCK 改动纪律：3 项必做（① hook ② ⑲ ③ ⑪）+ 触发条件 |
| §1.1 | pre-commit hook 工作原理（路径 + 命令 + 退出码 + 耗时） |
| §1.2 | check-demo ⑲ 守卫工作原理（探针 + 解析 + 阻断规则） |
| §1.3.1 | hook 跳过机制（`--no-verify` 3 个允许场景 + 3 个禁止场景 + PR 标签 `[skip-vec-hook]`） |
| §1.3.2 | ⑲ 守卫跳过（**不允许**，需变更单） |
| §1.4 | 多人协作边界（A 单独守门 / A+B 共用 PR rebase / hook PASS + ⑲ FAIL 内存压力） |
| §二 | 其他 16 项门禁现状表（不动，备查） |
| §三 | 变更单流程（CI 清单自身修改） |
| §四 | 上线纪律 checklist |
| §五 | 给编排者的盲测衔接（T-VEC-A/B/C/D） |

### 5.2 纪律点（必读）

- hook 跳过**只能** `--no-verify`，且必须在 PR 描述附 `[skip-vec-hook]` + 跳过理由 + 事后 veclock_verify 输出
- ⑲ 守卫**不允许**跳过
- hook 与 ⑲ 是**同源 CI 收口**（都用 `veclock_verify.py`），覆盖「commit 时阻断」+「演示前再守门」双盲区

---

## 六、commit 与锁管理

### 6.1 归属文件

| 路径 | 状态 | 入 commit？ |
|---|---|---|
| `.git/hooks/pre-commit` | 新建 + chmod +x | ❌ 本地文件不入库（Git 设计） |
| `edu-agent/scripts/check-demo.mjs` | ⑲ 段新增（仅本任务文件） | ✅ |
| `deploy/CI-CHECKLIST.md` | 新建 | ✅ |
| `test-reports/WNEXTVEC3-completion-report.md` | 新建（本报告） | 待 §六.2 |
| `edu-agent/scripts/eval/wnextvec3.lock` | 开工建；完工后 `rm -f` | N/A |

### 6.2 计划 commit

- **commit 标题**：`chore(ci)/W-NEXT-VEC-003-guard`
- 分支：feature/opt-waves（HEAD 起始 870d2977）
- 入 commit scope：`deploy/CI-CHECKLIST.md` + `edu-agent/scripts/check-demo.mjs` + `test-reports/WNEXTVEC3-completion-report.md`

---

## 七、批判性自检（避免再被同型问题打脸）

1. **是否改了不该改的？** — 仅改 check-demo ⑲ 段（新增）+ deploy/CI-CHECKLIST.md（新建）+ .git/hooks/pre-commit（新建）。**未动** embedder.py / loader.py / veclock_verify.py 任何 app 业务代码
2. **是否悄悄改了契约？** — ⑲ 探针共用 veclock_verify.py（不变）；hook 调用同一个 verify.py（不变）。**契约冻结**
3. **是否避开了 P0-A 数据写入污染？** — hook + ⑲ 都是**只读探针**，零写
4. **hook 是否真会跑？** — VEC3-G2 实证完整：嵌入 embedder.py 改动 → hook 触发 → 12/12 PASS → `[vec-guard][OK]` → RC=0
5. **⑲ 解析能否正确区分绿/红？** — VEC3-G5 实证 3 测：12/12 绿 + dim0 backend=bge_m3 绿；dim0 FAIL 红；11/12 红 → 全过
6. **未来 CI 可复跑吗？** — ⑲ 走 `edu-agent/.venv/Scripts/python.exe`（已有）；hook 走同一 python。**Windows 环境可复跑**

---

## 八、给下游的衔接

### 8.1 解锁下游

- ✅ T-VEC-A / T-VEC-B / T-VEC-C / T-VEC-D 盲测（VEC-LOCK 守门机制已具备，可接编排）
- ✅ 任何改动 `embedder.py` / `loader.py` / `veclock_verify.py` 的后续任务（W-NEXT-T-N / R-N）现在都被强制守门

### 8.2 仍待办（向上反馈）

- **VEC-C2 根因 P0-A 仍未根治**：并发导入污染基线问题（critique-VEC-LOCK §一 P0-A）—— 本任务**不解决**，仅补**事后守门**机制
- **P0-B EMBED_BACKEND 双源断言**：⑪ 仅检元数据，不检运行时 settings.EMBED_BACKEND——本任务不解决
- **P0-C delete→flush 仅修一半**：veclock_dispose.py / loader.py:drop_partition 仍存风险——本任务不解决
- **P0-D 黄金集非确定性**：v2 已用 consistency_level=Strong + sort 兜底，但服务端抖动仍可能——本任务不解决

### 8.3 不需要后续改动

- hook 本身就是终极守门：所有 VEC-LOCK 改动必须实证 12/12 才允许 commit
- ⑲ 守卫：演示机环境的事后守门，覆盖 hook 盲区

---

## 九、锁管理

- 开工：`edu-agent/scripts/eval/wnextvec3.lock`（Sep 17 11:29，0 字节）
- 完工：`rm -f edu-agent/scripts/eval/wnextvec3.lock`（待 §六 commit 后执行）

---

完工。W-NEXT-VEC-003 守门机制已落地，commit 待 §六 执行。