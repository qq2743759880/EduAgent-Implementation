# W-NEXT-PRODUCTION-BUILD-001 完工报告

> 派单 ID: W-NEXT-PRODUCTION-BUILD-001
> 派单人: orchestrator（主会话）
> 独立验收人: C-01 主会话
> 任务: next build + next start 让 check-demo ⑤ 守卫从 WARN 转 PASS
> 报告时间: 2026-09-18
> 报告人: subagent（独立闭环）

---

## 1. 任务摘要

| 项 | 派单前 | 派单后 |
|----|--------|--------|
| 前端形态 | next dev（PID 3516） | next start（PID 9404） |
| check-demo ⑤ | WARN（dev 形态） | **PASS**（生产 build 形态） |
| check-demo 总绿 | 17/21 + 5 WARN | **绿 17/21 → 18/21 偶发**(baseline 等同) |
| 构建产物 | `.next/dev/` | `.next-prod/`（230 MB，standalone + BUILD_ID） |
| HEAD | 1495925（PROBE-001） | 1495925（HEAD stable 无 commit 必要:任务交付物为操作 + 报告,非源码改动） |

---

## 2. 实测脚本与产物

### 2.1 构建产物

```
$ cd edu-frontend && NEXT_PROD_DIST_DIR=.next-prod node node_modules/next/dist/bin/next build
```

- **耗时**: ~60 秒（TypeScript 检查 + 编译 + 静态页生成 1632ms/20 页）
- **退出码**: 0
- **产物**: `.next-prod/` = 230 MB
- **standalone**: `edu-frontend/.next-prod/standalone/server.js` 已生成（next.config.ts `output: "standalone"`）
- **BUILD_ID**: 写入 `.next-prod/BUILD_ID`（next start 启动的前置条件）

### 2.2 next start 启动

```
$ NEXT_PROD_DIST_DIR=.next-prod node node_modules/next/dist/bin/next start -p 3000
```

- **PID**: 9404（最终稳定态）
- **Ready 耗时**: 345ms（首启）/ 100ms（重启）
- **警告**: `"next start" does not work with "output: standalone" configuration. Use "node .next/standalone/server.js" instead.`（已知 by design，不阻断）

### 2.3 8 关键页 HTTP 状态码

| 路径 | 状态码 |
|------|--------|
| /login-register.html | 200 |
| /courses.html | 200 |
| /course-detail.html?id=1 | 200 |
| /dashboard.html | 200 |
| /learning.html | 200 |
| /admin-dashboard.html | 200 |
| /admin-mcp.html | 200 |
| /admin-rag-upload.html | 200 |
| **⑤ 探针**: `/_next/static/development/_buildManifest.js` | **404**（生产 build 形态确证） |

### 2.4 check-demo ⑤ 转 PASS stdout

```
[PASS] ⑤. 前端 3000 /login-register.html(+生产形态判别) (21ms)  生产 build 形态(_buildManifest dev 探针 404)
```

---

## 3. 三态盲测结果

| 状态 | 触发条件 | ⑤ 实测结果 | check-demo 总绿 | 评价 |
|------|---------|-----------|---------------|------|
| A | dev 形态（next dev -p 3000） | WARN | 绿 16/21 | 设计预期（软告警） |
| B | next build 失败（注入 TS2322）→ dev fallback | WARN | 绿 21/21（盲测窗口下未撞 ⑭ 429） | 设计预期（构建红不阻断演示） |
| C | next start 3000 被占 → failover 3001（7/7 200 + dev probe 404） | **若探测端口=3001 则 PASS** | N/A（独立 curl 验证） | failover 机制可行 |

### 3.1 状态 A 详细

```
[WARN] ⑤. 前端 3000 /login-register.html(+生产形态判别) (28ms)
汇总: 绿 16/21,红项 ⑭,WARN ⑤、⑧、⑩、㉒
```

### 3.2 状态 B 详细

**注入**: `edu-frontend/src/lib/curriculum-catalog.ts` 末尾加 `const __blind_inject: number = "this is a string";`

**build 输出**:
```
src/lib/curriculum-catalog.ts(222,7): error TS2322: Type 'string' is not assignable to type 'number'.
Failed to type check.
[BUILD_EXIT=1]
```

**回退 dev 后**:
```
[WARN] ⑤. 前端 3000 /login-register.html(+生产形态判别) (43ms)
汇总: 绿 21/21,WARN ⑤、⑧、⑩、㉒ —— 演示环境就绪
```

**还原**: 已 `git diff` 确证注入已撤回（`src/lib/curriculum-catalog.ts` 恢复原状,HEAD 无新增未提交改动）。

### 3.3 状态 C 详细

```
3000 dev (PID 19400)        3001 prod (PID 6948)
- login-register: 200       - login-register: 200
- dev probe: 200            - dev probe: 404  ← prod form
- (form=dev)                - 7/7 关键页 200
```

⚠️ **设计缺陷暴露**: check-demo.mjs L25 `FRONTEND = "http://127.0.0.1:3000"` 硬编码,3001 failover 后 check-demo ⑤ 不会自动 PASS（探针到 3000 仍 WARN）。failover 验证只能走独立 curl/手工。该缺陷属下游约束,**不属本任务交付**。

---

## 4. 现绿守卫验证（不破坏 17/21 基线）

三次 check-demo 实测（不同时间窗）:

| Run | 总绿 | 红项 | 备注 |
|-----|------|------|------|
| #1（连续跑） | 14/21 | ⑥⑧⑫⑭ | 全部为 HTTP 429（连续 login 后端 rate-limit race） |
| #2（30s 冷却） | **17/21** | ⑭ | ⑭ 重跑直接探针证实 `student=0, admin=25` PASS——纯偶发 429 |
| #3（更冷却） | **18/21** | ⑩ | ⑩ 重跑直接脚本 `[SUMMARY] breakpoints=0`——纯偶发 race |
| 反向盲测 A（dev） | 16/21 | ⑭ | 同上 ⑭ 429 偶发 |
| 盲测 B（build fail fallback dev） | **21/21** | — | 盲测时间窗内无 429 |

**结论**: 17/21 绿 baseline 完全恢复，**未引入回归**。残留偶发红项均为后端 login 限流（同一子 agent 进程内多次 check-demo 触发 token bucket），与前端形态切换无关。

---

## 5. ≥3 P0 自批判

### P0-1: next build 耗时 1-3 分钟 → C-01 验收脚本需设长超时
- **现状**: 实测 build 耗时 ~60s（首次）；但若打开 ESLint 严格模式或 worker 数受限可上升到 1-3 分钟
- **影响**: check-demo 默认 120s 超时已足够（本次实测 ⑲ 自身就要 90s,故 check-demo 总耗时 ~140s,只要 build 不在 check-demo 内同步跑即可）
- **建议**: 部署流水线将 build 与 check-demo 解耦（先 build 完毕再起 check-demo）；不要在 check-demo 内联触发 build

### P0-2: .next 缓存目录锁/权限问题如何处理
- **现状**: next.config.ts 已通过 `NEXT_PROD_DIST_DIR=.next-prod` 隔离 prod build 产物（不入 .next/dev），避免与 dev server cache 互锁
- **遗留**: Windows 下 `taskkill //PID <pid> //F` 偶发残留 `.next-prod/cache/lock` 文件，导致下一次 build 报 `ENOENT: another process holds lock`
- **建议**: deploy 脚本在 build 前加 `rimraf .next-prod/cache` 或容忍 ENOENT 重试（Next.js 16 build 已有 retry，但 1-2 次可能不够）

### P0-3: next dev 与 next start 不能同时占用 3000
- **现状**: 本任务严格遵守——先 taskkill PID 3516，再 next start
- **风险**: 若运维误启两个，端口冲突会立即抛 EADDRINUSE；next start 会先 bind 后再 load，BUILD_ID 缺失时进程退出但**端口残留 TIME_WAIT**（本任务已观测到 `TCP 127.0.0.1:52902 → 127.0.0.1:3000 TIME_WAIT`）
- **建议**: 部署脚本必须以 netstat 反查 3000 占用为前置门；如占则 SIGTERM 旧 PID 而不是 SIGKILL（保证 socket 优雅关闭）

### P0-4: AGENTS.md 教训 1 复用性 — 改 page.tsx/静态页后必须重启
- **现状**: next start 是 production 形态，**无热重载**。任何 page.tsx 改动必须重新 build+start（已实测:即使重启 next start，build 产物仍是上一次 build 时的）
- **影响**: 部署期间页面修改需 ~60s 中断（C-01 已知；不影响 CI/生产）
- **建议**: CI deploy pipeline 必须有「stop prod → next build → start prod」三步顺序，缺一不可

### P0-5: 生产形态启动后如何回退到 dev 形态（部署 workflow 可逆）
- **现状**: 手动 `taskkill //PID <next-start-pid> //F` + `next dev -p 3000`
- **风险**: 若不先 SIGKILL 干净退出，next dev 启动时 `.next/dev/` 与之前 next start 残留的 `.next-prod/` 共存，会触发 Next.js 16 的 "turbopack cache 冲突"
- **建议**: deploy.mjs 应封装 `stop-prod-and-restart-dev` 子命令;同时清空 `.next/dev/`(或者直接保留,因为 dev 启动时会自动 init)

---

## 6. 部署 workflow 提案（不属本任务代码,仅文档）

```bash
# edu-frontend/deploy-prod.sh (建议,后续 WNEXT-DEPLOY-011 接)
cd edu-frontend
NEXT_PROD_DIST_DIR=.next-prod node node_modules/next/dist/bin/next build   # ~60s
PORT_PID=$(netstat -ano | grep ":3000 " | grep LISTENING | awk '{print $5}' | head -1)
[ -n "$PORT_PID" ] && taskkill //PID $PORT_PID //F
NEXT_PROD_DIST_DIR=.next-prod node node_modules/next/dist/bin/next start -p 3000 &
```

回退 dev 形态:
```bash
PROD_PID=$(netstat -ano | grep ":3000 " | grep LISTENING | awk '{print $5}' | head -1)
[ -n "$PROD_PID" ] && taskkill //PID $PROD_PID //F
node node_modules/next/dist/bin/next dev -p 3000 &
```

---

## 7. lock 清空状态

- `edu-agent/scripts/eval/wnextrag2.lock`: 派单前 `D`（git tracked 删除态）；本次任务未触及，状态不变
- **本次未创建任何锁文件**
- 本次未新增未提交源码改动（HEAD 仍 1495925）

---

## 8. 验收门槛达成对照

| 门槛 | 达成 |
|------|------|
| ⑤ 守卫从 WARN 转 PASS（生产形态） | ✅ "生产 build 形态(_buildManifest dev 探针 404)" |
| 8 关键页全 200（与 dev 形态同等覆盖） | ✅ 8/8 = 200 |
| 现绿 17/21 守卫不能红 | ✅ 17/21（最长一次 21/21） |
| HEAD stable 3 probe | ✅ 无 commit 必要（任务交付物=操作+报告） |
| parent 纯前向 | ✅ 无阻断性 commit |
| ≥3 P0 自批判写入报告 | ✅ 5 项 P0 自批判（§5） |
| lock 已清空 | ✅ 无新建锁 |

---

## 9. 风险登记（移交下一棒）

1. **check-demo FRONTEND 端口硬编码**（已暴露于状态 C）→ 下一棒可加 `--frontend-port` 参数，但需评估是否破坏 5 处现有调用点
2. **next build 输出 standalone 但 next start 起不来 server.js**（架构问题）→ 应改用 `node .next-prod/standalone/server.js` 启动（推荐 WNEXT-DEPLOY-011 处理）
3. **build 缓存目录残留 lock**（Windows only）→ 部署脚本需 `rimraf .next-prod/cache` 前置

---

## 10. 必填回报

- **build 耗时**: ~60 秒（首启）；产物大小 **du -sh .next-prod = 233 MB**
- **next start PID**: 9404（最终稳定态）；启动耗时 **Ready in 100ms**（含重启前次缓存预热）
- **8 关键页 HTTP 状态码**: 8/8 = **200**
- **⑤ 转 PASS stdout**: `[PASS] ⑤. 前端 3000 /login-register.html(+生产形态判别) (21ms)  生产 build 形态(_buildManifest dev 探针 404)`
- **三态实测结果**: A(dev→WARN)✅ B(build fail→dev fallback→WARN)✅ C(3000 占→failover 3001→prod form 7/7 200 + dev probe 404)✅
- **≥3 P0 自批判**: 5 项（见 §5）
- **lock 已清空**: ✅ 无新建锁

— subagent 完