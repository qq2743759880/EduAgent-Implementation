# CI 检查纪律清单（CI-CHECKLIST）

> 维护：W-NEXT-VEC-003 起首次落地；改动需走契约变更单 + reviewer 双签。
> 工作区：`E:\stu\project\stu\EduAgent实施手册`
> 引用：`edu-agent/scripts/check-demo.mjs`（17 项门禁）、`edu-agent/scripts/eval/veclock_verify.py`（12 维 VEC 机验）

---

## 一、VEC-LOCK 改动纪律（P0 强制）

任何**改了 VEC-LOCK 核心代码**的 commit / PR / CI 流水线，**必须**满足以下全部三项，否则视为守门缺失，下游（HITL-FIX / RAG 写类工具真实写库 / 大批量知识库迁移）不得放行：

| # | 步骤 | 谁负责 | 触发条件 |
|---|---|---|---|
| **①** | pre-commit hook 跑 `veclock_verify.py`（12 维） | 提交者（本地） | 改动路径包含 `edu-agent/app/knowledge/importer/embedder.py` / `loader.py` 或 `edu-agent/scripts/eval/veclock_verify.py` 任一文件 |
| **②** | `node scripts/check-demo.mjs` ⑲ 守卫通过（12/12 + dim0 backend=bge_m3） | 演示前 / CI 流水线 | 同上（演示机环境就绪时） |
| **③** | ⑪ VEC-LOCK embed 一致性健康门通过（已有） | 演示前 | 同上（不动） |

### 1.1 pre-commit hook 工作原理

- 文件：`.git/hooks/pre-commit`（**本地文件，不入库**）
- 检测：`git diff --cached --name-only --diff-filter=ACMR` 中命中以下三条路径之一即触发：
  - `edu-agent/app/knowledge/importer/embedder.py`
  - `edu-agent/app/knowledge/importer/loader.py`
  - `edu-agent/scripts/eval/veclock_verify.py`
- 执行：`cd edu-agent && PYTHONPATH=. .venv/Scripts/python.exe scripts/eval/veclock_verify.py`
- 退出：`exit 0`（PASS）→ commit 继续；`exit ≠0`（FAIL）→ commit 阻断 + 输出 `[vec-guard][BLOCK]`
- 耗时：约 30~120s（依赖 BGE-M3 加载 + Milvus 11 维检索 + 黄金集 top-10）

### 1.2 check-demo ⑲ 守卫工作原理

- 探针：同 `veclock_verify.py`（与 hook 共源，单一事实源）
- 解析两项关键行：
  - `[veclock] 汇总：12/12 PASS`（必须等于）
  - `[veclock] PASS  0 backend 探测: ... backend=bge_m3(须=bge_m3) model=bge-m3@26159e7a(须=bge-m3@26159e7a)`（必须命中）
- 阻断规则：任一项不符即红阻断 exit 1（不降 WARN，因为 12 维是 VEC-LOCK 不可协商基线）

### 1.3 何时可跳过（且**只能现场手动**）

#### 1.3.1 hook 跳过

```bash
git commit --no-verify -m "..."
```

**纪律**：

- **仅限**以下场景：
  1. 真实在跑 W-NEXT-VEC-N 系列 v2 调试（已确定 12 维门槛会过，但 hook 卡住时）
  2. 紧急 hotfix：必须在 5 分钟内提交，否则生产事故
  3. BGE-M3 mmap 内存压力暂态失败（os error 1455），关其他 Python 进程释放内存后必须复跑 `veclock_verify.py` 再 commit
- **不得**跳过场景：
  - "我以为没事 12 维都过" → ❌ 必须 hook 实证通过
  - "时间紧" → ❌ 跳过 hook 等于绕过守门
- 每次 `--no-verify` 必须在 PR 描述里附：
  - `[skip-vec-hook]` 标签
  - 跳过理由（命中上面 3 条之一）
  - 事后跑 `veclock_verify.py` 的输出（`passed/total` + 后端 revision）

#### 1.3.2 check-demo ⑲ 跳过

**不允许**。

⑲ 守卫是演示机环境的事后守门，覆盖"已 commit 但环境漂移""多人共改未触发 hook"两类盲区。⑲ 没有 `--no-verify` 等价机制；如果 verify 跑不过，**必须修到 12/12** 才允许演示。

如确属 verify 探针本身故障（极罕见，需要独立子 agent 验收），走 `deploy/CI-CHECKLIST.md` 变更单流程。

### 1.4 多人协作边界

| 场景 | 守门机制 |
|---|---|
| A 改了 `embedder.py` → 触发自己 hook → commit | ✅ 单独守门 |
| A 改了 `embedder.py` → B 改 `loader.py` → 共用 PR | ❌ A/B 各自 hook 只验证自己改的瞬间。建议合并前 rebase 后再 push，由 CI ⑲ 收口 |
| A 改了 `loader.py` → hook PASS → 演示机 BGE-M3 内存吃紧 ⑲ FAIL | ⑲ 阻断演示，需释放内存后复跑 ⑲ |

---

## 二、其他门禁现状（不动，备查）

| # | 名称 | 文件 | 阻断规则 |
|---|---|---|---|
| ① | Milvus socket | check-demo ① | 连通 |
| ② | Redis ping | check-demo ② | PONG |
| ③ | MongoDB socket | check-demo ③ | 连通 |
| ④ | 后端 /health | check-demo ④ | status=ok |
| ⑤ | 前端登录页 + 形态判别 | check-demo ⑤ | 200 + 生产 build |
| ⑥ | 登录链路 admin+student | check-demo ⑥ | role 正确 |
| ⑦ | 8 个核心 html 200 | check-demo ⑦ | 全 200 |
| ⑧ | DEBUG 虚拟管理员漏洞 | check-demo ⑧ | 三分支 |
| ⑨ | 抽验页 admin-users-refine-proto | check-demo ⑨ | 200 |
| ⑩ | 契约对账（FE-BE-CONTRACT） | check-demo ⑩ | 断点=0 且在用未冻结=0 |
| ⑪ | VEC-LOCK embed 元数据 | check-demo ⑪ | 全=锁定 BGE-M3 revision |
| ⑫ | HITL 真实性 | check-demo ⑫ | confirm 续流无 42200 |
| ⑬ | MCP 三态门 | check-demo ⑬ | audit_ok + builtin_logged + redacted |
| ⑭ | 内部可见性 | check-demo ⑭ | student=0 + admin>0 |
| ⑮ | Redis 部署对账 | check-demo ⑮ | PASS/WARN 红 / FAIL_ENV_MISSING 红 / ENV_BLOCKED WARN |
| ⑯ | 8000 lifecycle 健壮性 | check-demo ⑯ | start+stop×5 无 CancelledError |
| ⑰ | MCP 跨权限门对账 | check-demo ⑰ | audit_checked≥17 + 5新对账行 + chat AST 链 + JSON |
| **⑲** | **VEC-LOCK 守门（12 维 + dim0 backend）** | **check-demo ⑲** | **12/12 PASS + backend=bge_m3 必中** |

---

## 三、变更单流程（本清单自身修改）

| 触发 | 路径 |
|---|---|
| ① 阈值变更 | `edu-agent/scripts/eval/veclock_verify.py` THRESHOLDS 字典（需 reviewer 双签 + 报告 §4.1 goalpost moving 表登记） |
| ② ⑲ 守卫规则变更 | `edu-agent/scripts/check-demo.mjs` ⑲ 段（需 reviewer 双签 + 新增/调整须配报告） |
| ③ 触发路径增删 | `.git/hooks/pre-commit` 同步更新 `deploy/CI-CHECKLIST.md`（需 reviewer 双签） |
| ④ CI 跳过规则扩展 | `deploy/CI-CHECKLIST.md` §1.3（需编排者批准，跳过门槛属红线变更） |

---

## 四、上线纪律（部署 checklist）

- [ ] 上线前必须 `node scripts/check-demo.mjs` 全绿（17 项门禁 100% PASS，WARN 不计绿）
- [ ] DEBUG 模式必须是 false（教训 6 + check-demo ⑧ 三分支）
- [ ] `.env` EMBED_BACKEND 必须与 `config.py` 默认值一致（教训 7 + ⑪ 探针）
- [ ] 改动 VEC-LOCK 核心代码后，hook 必须实证通过；不可 `--no-verify` 跳过
- [ ] ⑲ 守卫必须 12/12 PASS + dim0 backend=bge_m3 必中（不接受 WARN）

---

## 五、给编排者的盲测衔接

| 盲测 ID | 前置 | 验证目标 |
|---|---|---|
| T-VEC-A | ⑲ PASS | 多角色检索一致性 |
| T-VEC-B | ⑲ + HITL-FIX PASS | 写类知识库 chat 链路 |
| T-VEC-C | ⑲ PASS | 并发导入下验收门有效性（hook + ⑲ 双源） |
| T-VEC-D | ⑲ + WNEXT10 | 跨租户越权 + EMBED_BACKEND 降级探测 |

---

完工。W-NEXT-VEC-003 报告：`test-reports/WNEXTVEC3-completion-report.md`。

---

## 六、禁碰清单纪律（W-NEXT-REDLINE-001 收口，2026-09-17）

> 起源：编排者盲测发现——历史 W-NEXT-* 任务常出现"误改禁碰区"（如 `app/config.py` / `app/database.py` / `app/main.py` 关键路径 / `contracts/reshape-r-*.json` 冻结契约 / `edu-agent/.env` / `deploy/docker-compose.yml` 等），单写者锁防不住"自己 task kickoff 误碰相邻关键文件"。
>
> 解决方案：**commit-time 阻断**——pre-commit hook 解析 commit message 的 `禁碰：<glob>` 段，与 `git diff --cached --name-only` 交集非空即阻断。

### 6.1 禁碰清单机制

- **入口**：`.git/hooks/pre-commit` B 段（VEC-LOCK 为 A 段，禁碰清单为 B 段，二者并存）
- **Helper**：`edu-agent/scripts/eval/pre_commit_forbidden.py`（std-lib only，支持 `fnmatch` + `**` globstar）
- **commit message 语法**（任选其一）：

```
禁碰：app/config.py, app/database.py
禁碰:app/config.py
forbidden-files: app/config.py, edu-agent/.env
forbidden: app/main.py
```

- **pattern 语义**（POSIX glob via fnmatch + globstar 扩展）：
  - `app/foo.py` 精确路径
  - `app/**` 子树（含 `app` 本身与 `app/x` / `app/x/y`）
  - `edu-agent/scripts/eval/*.py` 通配
  - `**/foo.py` 跨目录

### 6.2 阻断规则

| 场景 | 行为 |
|---|---|
| commit message 无 `禁碰：` 段 | hook 静默放行（不读其他 marker，避免误伤） |
| 有 `禁碰：` 段但 staged 文件无交集 | hook 静默放行 |
| 有 `禁碰：` 段 + staged 文件命中任一 pattern | **红阻断 exit 1** + 友好错误（命中文件 + 命中 pattern） |
| 跳过机制 | `git commit --no-verify`（hook 不被调用，是 Git built-in 唯一合法路径） |

### 6.3 合法使用 `禁碰：` 段的场景

1. **W-NEXT-* 任务明确要禁碰某区域**：在 kickoff / 变更单中显式登记，commit message 必带 `禁碰：` 段
2. **多人协作分片**：A 改 `app/foo.py` 时禁碰 B 的 `app/bar.py`，避免合并冲突
3. **冻结契约区**：改 `app/main.py` / `app/config.py` 时禁碰 `contracts/reshape-r-*.json`（契约冻结纪律）

### 6.4 严禁（违反即纪律违规）

| 严禁项 | 后果 |
|---|---|
| 用 `禁碰：` 段掩盖 commit 真实意图（如禁碰 `test-reports/` 隐藏未跑验收） | 编排者审计发现即回退 |
| 用 `--no-verify` 绕过禁碰清单而不写理由 | PR 描述必须附 `[skip-redline]` 标签 + 理由 + 事后变更单编号 |
| 把 `禁碰：app/main.py` 与 `feat: 改 app/main.py` 同 commit | 红阻断（自我矛盾） |
| 禁碰清单与 VEC-LOCK 触发同时不冲突 | ✅ 二者独立运行，触发其一即跑（pre-commit §B 在 §A 之后） |

### 6.5 变更记录

| 日期 | 事件 | 改动文件 | 关联任务 |
|---|---|---|---|
| 2026-09-17 | 首版落地（禁碰清单 hook + helper + CI-CHECKLIST 纪律章节） | `.git/hooks/pre-commit`（B 段）+ `edu-agent/scripts/eval/pre_commit_forbidden.py`（已存在）+ `deploy/CI-CHECKLIST.md` §六 | W-NEXT-CHECKDEMO-001（复跑 W-NEXT-REDLINE-001） |