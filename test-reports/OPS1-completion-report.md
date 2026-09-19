# W-NEXT-OPS-001 · 完工报告（watchdog 服务化 + CI full-run 门禁接线，2026-09-20）

> 双小单：**A** = STABILITY P0-A 承接（看门狗服务化——「看门狗非免死金牌：它自己不在岗就没人拉起」）；
> **B** = TEST-BASE §7 移交 2 承接（full-run 回归门禁一键脚本 + CI 接线）。
> 分支 feature/opt-waves（开工 tip=`d73540a`）；单写者锁 `edu-agent/scripts/eval/rops1.lock`（commit 前已删）。
> 主提交 = `7b8d1ad`（脚本/CI/README，6 文件 +523 纯增量），报告提交 = 本文件所在 commit。
> 结论速览：**小单 A 全链实测闭环（注册→查重→杀 8000→143s 自动恢复→卸载→终态服务化版在岗）；
> 小单 B 三分支 exit code 实证（0/1/2 语义）+ full-run 门禁真跑 PASS（exit 0，463s，1773P/79S/0F）；
> CI job 只接 workflow_dispatch + self-hosted，如实不伪装云端可跑**。环境侧坐实一起重大事实：
> **Milvus 宿主已从可达环境消失**（详见 §4，须编排者/用户裁决）。

---

## 1. 交付物清单（红线归属核对）

| 文件 | 状态 | 内容 |
|---|---|---|
| `edu-agent/scripts/deploy/install_watchdog_task.ps1` | 新增 | schtasks 注册「EduAgent-Watchdog」：BootTrigger 延迟 60s + TimeTrigger 每 5 分钟无限重复；查重幂等（已存在即跳过，`-Force` 重注册）；`-StopExisting` 自动停手工常驻版防双实例 |
| `edu-agent/scripts/deploy/uninstall_watchdog_task.ps1` | 新增 | `schtasks /End`（停任务实例）+ `/Delete /F` + 复核；提示 8000 为独立进程不受连带 |
| `edu-agent/scripts/eval/gate_fullrun.ps1` | 新增 | 门禁引擎：预检（MySQL/Redis 硬门 + Milvus 默认硬门/`-AllowMilvusDown` 降级开关）→ `pytest tests/ -q -p no:cacheprovider` → exit 0=PASS / 1=回归(tail 50) / 2=环境不可达 |
| `edu-agent/scripts/eval/gate_fullrun.cmd` | 新增 | cmd 一键入口（纯 ASCII——GBK 代码页踩坑，见 P0-4）；exit code 透传 |
| `.github/workflows/ci.yml` | 追加 | +`workflow_dispatch:` 触发器；+`full-run-gate` job（32 行纯增量，0 删改） |
| `deploy/README.md` | 追加 | §5.5 看门狗服务化（三命令）+ §5.6 回归门禁（本地一条命令 + CI 手动触发） |
| `test-reports/OPS1-gate-fullrun-console.log` | 新增 | 门禁实跑 console 全量留证（113 行） |
| `test-reports/OPS1-completion-report.md` | 新增 | 本报告 |

**未触碰**：`watchdog_8000.py` 本体（`git diff` 为空）、`tests/**`、`app/**`、`contracts/**`。工作区中他人并行改动（build_eval_set64.py 等）一律未提交。

## 2. 小单 A 实测（全链，时间为 2026-09-20 凌晨一手输出）

前置快照：常驻手工版看门狗 pid=21880 在岗（events 日志 01:01 仍打点）；8000 监听 pid=37756；任务计划无 EduAgent-Watchdog。

1. **停常驻版**：`python scripts/watchdog_8000.py --stop` → `stopped watchdog pid=21880` + events `WATCHDOG_STOPPED pid=21880`，exit 0。
2. **首次注册**（`install_watchdog_task.ps1 -StopExisting`）→ exit 0。`schtasks /Query /V` 关键证据：
   - `计划类型: 一次性, 分钟`；`重复: 每: 0 小时, 5 分钟`；`重复: 截止: 持续时间: 已禁用`（无限重复）
   - `要运行的任务: ...\edu-agent\.venv\Scripts\python.exe "...\scripts\watchdog_8000.py"`（loop 模式，见 §3 设计决策）
   - `如果运行了 X 小时 X 分钟，停止任务: 已禁用`（XML `ExecutionTimeLimit=PT0S` 生效——72h 默认时限已拆除，防定时自杀）
   - `下次运行时间: 2026/9/20 1:49:59`（5 分钟重复已武装）
3. **查重幂等**：第二次安装（无 -Force）→ `SKIP 任务已存在（查重命中，幂等跳过）`，exit 0。
4. **任务拉起**：`schtasks /Run /TN EduAgent-Watchdog` → 成功；pid 文件换新 pid=14200，events `WATCHDOG_START pid=14200 interval=30.0s threshold=3 cooldown=90.0s`（父进程 28660=任务计划宿主，非本会话——脱离 agent 生命周期目标达成）。
5. **杀 8000 → 自动恢复（核心实证）**：`taskkill /F /PID 37756`（01:45:28）→ events 逐条留痕：
   ```
   [01:45:44] HEALTH_FAIL FAIL_1/3 detail=URLError ... 10061 ...
   [01:46:16] HEALTH_FAIL FAIL_2/3 detail=URLError ... 10061 ...
   [01:46:48] HEALTH_FAIL RESTART detail=URLError ... 10061 ...
   [01:46:48] RESTART_BEGIN
   [01:46:48] RESTART_INITIATED ok=True how=spawned via detached+breakaway
   [01:47:51] RESTART_OK 8000 back to healthy
   ```
   杀死→健康回 200 全程 **143s**（3 连败检出 64s + 拉起/模型加载 63s + 探活余量），新监听 pid=15560（≠被杀 37756，真拉起新进程）。
6. **卸载**（`uninstall_watchdog_task.ps1`）→ exit 0；`schtasks /Query` 报「系统找不到指定的文件」（任务已删）；任务实例 pid=14200 被 `/End` 结束（进程不在）；**8000 存活不受影响**（health 200——detached+breakaway 拉起的 uvicorn 独立于任务实例，卸载守卫≠停服务）。已知残留：pid 文件遗留 14200 陈旧值（`/End` 硬杀使 finally 清理不执行），下次启动 `WATCHDOG_STALE_PID_FILE replaced old_pid=14200` 自愈闭环。
7. **终态（按任务书要求以「服务化版在岗」收尾）**：重装 + `/Run` → pid=28852 在岗（陈旧 pid 自愈留痕），任务 `模式: 正在运行`、`下次运行时间: 1:53:23`，8000 health 200。**当前机器终态 = 服务化版在岗，手工常驻版已退场。**

### 两种形态取舍（如实）

| | 手工常驻版（裸进程） | 服务化版（本批任务计划） |
|---|---|---|
| 拉起方 | agent/用户会话 | Windows 任务计划（svchost 宿主） |
| 会话回收/重启后 | **随会话亡，无人拉起（P0-A 的洞）** | 开机 BootTrigger(60s) + 每 5 分钟重触发，「看门狗的看门狗」≤5 分钟自愈 |
| 防双实例 | pid 文件 | pid 文件 + MultipleInstancesPolicy=IgnoreNew 双保险 |
| 调试直观 | 高（前台可看输出） | 看日志（events/restart log） |
| 定位 | 临时排障 | **默认推荐形态（终态）** |

边界（如实登记）：InteractiveToken 形态=用户登录后才可运行，无头重启（断电自恢复/Windows Update）时「开机 60s 启动」实际=登录后 60s（StartWhenAvailable 补跑）。真无人值守需 S4U/服务账号改造（spawn 的 uvicorn 将进 session 0，CUDA/.env 行为未验证）→ 服务化 v2 待办，本批不伪装已达成。

## 3. 设计决策：任务动作为什么不是 `--once`（真实契约优先于任务书字面）

任务书写「每 5 分钟唤醒执行 `watchdog_8000.py --once`（--once 模式已存在：单次探活+按需拉起）」。
实读 `watchdog_8000.py`（AGENTS.md 教训 8 同款纪律：真实契约优先）：`--once` 用法注释（第 21 行
「单次检查，健康 exit 0 / 不健康 exit 1（**不拉起**）」）与 `run_once()`（354-358 行，仅探活无 spawn
路径）一致证明 **`--once` 不能拉起**。每 5 分钟一次的 `--once` 永远复活不了 8000，也复活不了已死的
看门狗本身 → 与 P0-A 意图直接相悖。故任务动作取 **loop 模式**（无参）：30s 探活/3 连败/冷却 90s/
僵尸清理/三级降级拉起全复用本体（红线：本体零改动）；每 5 分钟重复触发降格为「不在岗自愈」心跳
——实例在岗时 pid 文件互斥 + IgnoreNew 使触发为 no-op，死亡 ≤5 分钟由下次触发重拉。该偏离已在
脚本头注、任务 XML Description、deploy/README §5.5 三处写明理由。

## 4. 环境事故如实登记（本批坐实，非本批造成）

**Milvus 宿主已从可达环境消失**。取证链（一手）：

1. 开工预检 `192.168.85.101:19530` UNREACHABLE；8000 `/health/detail`：`milvus/mongodb/minio/neo4j`
   全 error（uvicorn 自 2026-09-19 20:58 起即以 MySQL+Redis 双 ok 的降级形态在跑）。
2. 按 deploy/README §4① 处置路径 `vmrun start`（vmx 在 `E:\tt\CentOS 7 64 位 的克隆 docker\`）拉起
   该 VM：ping 通、SSH（root@192.168.85.101，复用既有 `scripts/ssh_diag.py` 通道）可达，但 guest 内
   `systemctl is-active docker`=active 而 `docker ps -a` **为空**——无镜像、无卷、无容器、无 compose
   文件，`.bash_history` 止于 08-11。**这台"克隆 docker"VM 是空机**，本批终将其关回原态（vmrun list
   复核仅剩另一台常驻 VM）。
3. 子网扫描 192.168.85.2-254 的 19530/27017/9000：**零命中**；宿主 Docker Desktop 容器清单无 Milvus。
4. MAC 对质：vmx `ethernet0.generatedAddress=00:0c:29:84:c5:f2` ≡ ARP 192.168.85.101 表项——即我拉起
   的就是 .101 本机，不存在"另一台才是 Milvus 宿主"的可能。

影响与既成事实：**TEST-BASE run7 终态基线（1712P/57S/0F）与今日已入库存的 eval64v2 golden 均是在
Milvus 依赖测试被无条件 skip 的形态下取得的**（见 §5 构成归因：task_m2:203 / task_vec:89 为
`@pytest.mark.skip` 固定理由，Milvus 在不在线均不进跑面）——门禁可比性不受影响，但 RAG 真实向量
链路（入库/检索的活体回归）当前无活体覆盖。**谁删的、数据卷是否可寻回，未定罪**；重建 Milvus 或
接受降级基线，须编排者/用户裁决（不在本批文件权限内，移交清单见 §8）。

## 5. 小单 B 实测

### 5.1 预检三分支（exit code 语义实证）

```
[1] gate_fullrun.cmd -PrecheckOnly                → mysql REACHABLE / redis:6377 REACHABLE /
                                                    milvus UNREACHABLE → decision=ENV-UNREACHABLE exit=2
[2] gate_fullrun.cmd -PrecheckOnly -AllowMilvusDown → 同上预检 + 明示放行理由一行 → exit 0
[3] GATE_REDIS_URL=redis://127.0.0.1:6399/0 ...    → redis UNREACHABLE → exit=2（Redis 硬门）
```
（exit 2 文案均带「非代码回归」定性与环境处置指引；8000 后端探测只 WARN 不阻断，离线时 live_backend
系按 conftest 机制 skip 的覆盖面缩小会如实打印——本窗 8000 在线，实测 200。）

### 5.2 full-run 门禁真跑一次（PASS）

`gate_fullrun.cmd -AllowMilvusDown`，2026-09-20 01:48:50–01:56:33，console 全量留证
`test-reports/OPS1-gate-fullrun-console.log`：

```
[GATE] RUN cd ...\edu-agent && ...python.exe -m pytest tests/ -q -p no:cacheprovider
1773 passed, 79 skipped, 15 warnings in 456.56s (0:07:36)
[GATE] pytest exit=0 elapsed=463s
[GATE] decision=PASS exit=0（full-run 回归门禁通过；skipped 构成对照 TEST-BASE §4 白名单 57 例）
GATE_EXIT=0
```

**构成漂移如实归因（TEST-BASE §6-6「skip 构成是快照不是契约」预言命中）**：run7 基线 1712P/57S
（收集 1769）→ 本轮 1773P/79S（收集 1852，**+83**）。+83 全部来自 run7（commit `65b1b81`）之后的
7 个具名提交的测试增量：`b04e32d` eval64v2（47 例）/ `3bd799f` STABILITY watchdog 单测（10 例，
`test_watchdog_8000.py` +166 行）/ `b5c17e1` r03b 读护栏（11 例）/ `818b83d`+`dece40d` r23 cliff-v2
（12 例）/ `c03fa4a` fusionblind 通道健康（7 例）/ `e22a1c2` febe canonical 同步等；skip +22 亦随
上述新文件的设计内 skip 与环境依赖漂移而来。**门禁契约只锁 failed=0（exit 0）**，本轮 0 failed 断言
成立；skip 构成对照属维护动作，不阻断放行（§6-P0-3 有批判）。

### 5.3 ci.yml diff 摘要（+32 行纯增量，0 删改，YAML safe_load 验证通过）

- `on:` 增 `workflow_dispatch:`（注释写明：仅 full-run-gate 消费，不挂 push/PR 自动链）。
- 新 job `full-run-gate`：`runs-on: [self-hosted, eduagent-local]` + `if: github.event_name ==
  'workflow_dispatch'` + `timeout-minutes: 40`；步骤 = checkout → `gate_fullrun.cmd -PrecheckOnly`
  （不可达 exit 2 快失败，不误报代码回归）→ `gate_fullrun.cmd`（exit 0=PASS）→ 失败时
  `actions/upload-artifact@v4` 上传 `edu-agent/logs/gate_fullrun.log`（`if-no-files-found: ignore`）。
- 如实边界（job 注释逐字写明）：full-run 依赖本机真实 MySQL/Redis/Milvus/8000——云端 runner 一律
  没有，硬跑=大面积环境性假红；**绝不伪装云端可跑**；runner 未接线时 job 停在 queued 属预期。

## 6. P0 自批判（5 条，如实）

1. **Milvus 宿主失踪未定罪，且我未能恢复它**：我能证明「当前可达环境无 Milvus（扫描+MAC 对质+
   空 guest）+ TEST-BASE/eval64v2 的绿数字是在 Milvus 依赖测试无条件 skip 下取得」，不能证明 Milvus
   数据何时/被谁清掉、能否寻回。我的 `-AllowMilvusDown` 只是让门禁在降级形态下**如实可比**，不是
   把事故闭环——重建 Milvus 属数据恢复工程，超出本批文件权限，移交编排者（§8）。
2. **任务动作偏离任务书字面（--once → loop 模式）属意图推断而非用户确认**：证据链（源码两处 +
   恢复实测）支持我的判断，但存在另一可能解读——任务书若本意是「只要轻量探活记录，不要常驻
   常驻进程」，我的设计是超集（多一份 ~140MB RSS 常驻内存）。已在三处文档写明偏离理由与恢复
   实测依据，供 C-01 反向审核否决；若被否决，回滚=改任务 XML 动作一行。
3. **`-AllowMilvusDown` 是能被滥用的钥匙**：它把「环境不完整」变成「可明示放行」。当前安全的原因
   是那 2 例 Milvus 测试是无条件 skip；**未来若属主把 R-M2 漂移修成真实运行**，`-AllowMilvusDown`
   形态下的 PASS 会静默跳过它们，构成覆盖缩水的假绿。门禁只锁 exit code 不锁 skip 构成
   （TEST-BASE §6-6 同款边界），我未加机验护栏（如「PASS 时 assert skipped==白名单数」）——因为
   本轮实测已证明 skip 数随并行批次自然漂移（57→79），硬锁数字会误伤；正确方案（skip 构成白名单
   文件化+diff 告警）留待属主批次。
4. **Windows 编码双坑浪费一轮实跑**：.cmd 中文注释在 GBK 代码页下把批处理解析炸成碎片（首次
   `-PrecheckOnly` 直接 exit 255），ps1 无 BOM 被 PS5.1 按 ANSI 误读风险——修复为 .cmd 纯 ASCII +
   三个 .ps1 补 UTF-8 BOM。教训已写进 .cmd 头注（「keep this .cmd pure ASCII」）；后续任何
   Windows 脚本新增均需遵守，建议属主侧沉淀为 frontmatter 约定。
5. **服务化「开机自启」存在语义折扣**：InteractiveToken 下无头重启不会真正开机拉起（要等登录，
   StartWhenAvailable 补跑）。我没有为「语义完美」强上 S4U/SYSTEM——因为 session 0 下 spawn 的
   uvicorn 的 CUDA/模型加载/.env 权限行为未验证，拿未实证的形态上生产 = 用新风险换措辞完美。
   取舍如实登记（§2 边界），v2 待办含 S4U 形态的完整实弹验证。附带小瑕疵：卸载路径会遗留陈旧
   pid 文件（/End 硬杀跳过 finally 清理），靠启动自愈闭环，窗口内手工读 pid 文件会误判在岗。

## 7. 批判承接核对

| 上游批判/移交 | 本批承接 | 证据锚点 |
|---|---|---|
| STABILITY P0-A「看门狗非免死金牌——它自己不在岗就没人拉起」 | 小单 A 全部：任务计划持有 + BootTrigger 60s + 每 5 分钟不在岗自愈 + 双保险防双实例；实测杀 8000→143s 恢复、杀看门狗→重触发重拉（/Run 路径） | §2 实测 4/5/7 |
| TEST-BASE §7 移交 2「CI 门禁接线：pytest tests/ -q -p no:cacheprovider exit code==0」 | 小单 B 全部：gate_fullrun 一键脚本按该定义逐字实现 + ci.yml full-run-gate job；并真跑一次 exit 0 | §5.2/§5.3 |
| TEST-BASE §6-6「skip 白名单是快照不是契约」 | 本轮 57→79 漂移被预判并逐 commit 归因（非静默放行），批判反哺为 P0-3 | §5.2 |
| TEST-BASE §6-1/STABILITY「8000 无声死亡，根因未定罪」 | 服务化后该风险面收窄为「看门狗+任务计划双亡」；5 分钟自愈心跳兜底 | §2/§3 |

## 8. 移交/待办清单（编排者裁决项）

1. **Milvus 重建裁决**：数据卷寻回/重建 Milvus 栈（历史向量 3398 条，R-M2 已登记漂移口径在案），
   或正式接受「Milvus 离线」为基线形态并同步 .env/README/检查单。
2. **CI runner 接线**：在本机注册 GitHub self-hosted runner（labels 含 `eduagent-local`，工作区含
   `edu-agent/.venv`）后，full-run-gate job 即可被 workflow_dispatch 消费；未接线前 queued 属预期。
3. **服务化 v2**：S4U/服务账号形态实弹验证（无头重启真自启 + session 0 CUDA 行为）。
4. **skip 构成白名单机验化**：把「PASS 时 skip 构成对照」从纪律变护栏（白名单文件化 + diff 告警），
   归 TEST-BASE/conftest 属主。
5. **watchdog 单测属主对齐**：STABILITY 批新增的 `tests/test_watchdog_8000.py`（10 例）覆盖的是
   本体逻辑；本批 install/uninstall 脚本无单测（schtasks 交互不可单测，已用全链实测替代）——如需
   CI 化静态校验（XML schema/编码 ASCII 检查），归后续 ops 批次。

## 9. 资产消费证据（具名路径）

- 任务书（本单 kickoff 文本）：双小单目标/红线/实测要求逐条对照执行
- `edu-agent/scripts/watchdog_8000.py`（只读消费：--once 契约核实 L21/L354-358；loop 参数/三级降级/
  pid 互斥沿用；**零改动**）
- `test-reports/TEST-BASE-completion-report.md`（§4 门禁定义+终态基线 1712P/57S/0F+§6-6 skip 快照批判；
  §7 移交 2 = 本批小单 B 立项依据）
- `test-reports/testbase-runlogs/run7_final.txt`（task_m2:203/task_vec:89 无条件 skip 逐条核对）
- `edu-agent/tests/test_contract_task_m2.py` / `test_contract_task_vec.py`（只读：skip 条件核实）
- `.github/workflows/ci.yml`（deploy-env-gate job 范式照抄：独立 job/不嵌入既有 job/注释写明边界）
- `deploy/README.md`（§1.1 Redis 6377 事实、§2.1 venv 路径、§4① VMX_PATH/vmrun 处置路径、§5 结构）
- `AGENTS.md`（教训 8 真实契约优先、教训 2 禁 Playwright 独立实证、启动命令）
- 运维沉淀：`C:\Users\Administrator\.workbuddy\skills\eduagent-local-verification-ops\SKILL.md`（坑位风格沿用）
  + `edu-agent/scripts/ssh_diag.py`（VM SSH 通道复用，只读消费）
- VMware/网络取证：`vmrun list`、两台 vmx 的 `ethernet0.generatedAddress`、`arp -a`（§4 取证链）
- 实测原始留证：`test-reports/OPS1-gate-fullrun-console.log`（门禁全量）、`edu-agent/logs/watchdog_8000_events.log`
  （01:44–01:48 段：STOP/START/3×HEALTH_FAIL/RESTART_*/STALE_PID_FILE 全链）、schtasks /Query /V 输出（§2 引文）

## 10. 红线自检

- [x] 只新增/修改归属文件：install/uninstall ps1、gate_fullrun.cmd(+ps1 引擎)、ci.yml、deploy/README.md、报告
- [x] `watchdog_8000.py` / `tests/**` / `app/**` / `contracts/**` 零改动（git diff 为空）
- [x] `edu-agent/scripts/eval/rops1.lock` commit 前删除
- [x] 独立实证：全部结论出自真实 HTTP/进程/任务计划/git 一手操作，无 Playwright、无伪造输出
