# W-NEXT-STABILITY-001 收口报告（WNEXTSTABILITY1-completion）

- 任务：8000 uvicorn「无声死亡」取证收口 + 看门狗落地收尾
- 执行：W-NEXT-STABILITY-002（收口 agent，2026-09-19 08:25~08:40）
- 承接：前任 W-NEXT-STABILITY-001 全部产出已由编排者收殓为 commit `3bd799f`（分支 feature/opt-waves，收口时 HEAD）。本批**不重做取证**，只做收口四步：报告 / 看门狗重启 / commit / 回执。
- 取证素材：`git show 3bd799f`（watchdog_8000.py 388 行 + test_watchdog_8000.py 166 行 + check-demo.mjs FIX 追加）+ `edu-agent/logs/watchdog_8000_events.log`（含 2 次实弹全记录）+ 暂停快照（编排者交接）。

---

## 1. 三死亡结论表（四起事件 → 三条结论）

| # | 时刻 | 现象 | 根因 | 关键证据 | 排除项 |
|---|------|------|------|----------|--------|
| ① | 09-18 22:37 | 整机崩溃 | **整机异常重启**（Kernel-Power 41）+ torch_cpu.dll 0xc0000005 WER | Windows System 日志 Kernel-Power 41；WER 记录 torch_cpu.dll 访问违限 | 非 OOM（Event 2004=0）、非 GPU TDR（Event 4101=0）、非 uvicorn 优雅退出（死亡实例零 shutdown 日志） |
| ② | 09-19 00:07 | 8000 无声消失 | **外部 TerminateProcess 硬杀**（killPort 工具链 / taskkill /F /T / agent 会话 job 清理；actor 不可归因） | 无 WER、无 shutdown 日志、进程瞬间消失+端口立即释放 | 非 OOM/非 GPU/非 uvicorn 生命周期 |
| ③ | （同②窗） | r20b 探针记录的"又一次死亡" | **②宕机延续误记**——r20b 探针 in-process，把②造成的不可达误记为独立死亡 | 探针与②同进程，②死后探针必然连败 | 独立死亡事件不存在 |
| ④ | 09-19 04:52 | 8000 无声消失 | **同②：外部硬杀**（killPort 工具链家族） | 同②证据形态（零 WER/零 shutdown 日志/瞬杀） | 非 OOM/非 GPU/非 uvicorn 生命周期 |

**总根因**：①为整机级异常（含 torch_cpu.dll 崩溃 WER，触发整机重启）；②④为外部管理动作硬杀（killPort 工具链，actor 不可归因）；③非独立事件。**四起无一例可归因于应用层代码**——OOM（System 日志 Event 2004=0）、GPU TDR（Event 4101=0）、uvicorn 优雅/异常自退（死亡实例零 shutdown 日志）全部排除。结论：不可根除外部杀因 → **看门狗兜底**（本批已落地）。

## 2. 看门狗设计（3bd799f 已落地，本批零代码改动）

文件：`edu-agent/scripts/watchdog_8000.py`（388 行，仅 stdlib，Windows 优先）

- **探活**：每 `--interval`(30)s GET `/health`，须 200 且 `{"status":"ok"}`；连接拒绝/超时/非 ok 均计失败
- **触发**：连续 `--threshold`(3) 次失败 → netstat 反查 8000 LISTENING PID → `taskkill /F` 清僵尸监听 → 拉起 uvicorn
- **拉起三级降级**：DETACHED+NEW_GROUP+**BREAKAWAY**（脱离 job object，防会话结束连带杀）→ DETACHED+NEW_GROUP → `cmd /c start "" /B`（AGENTS.md 启动命令原样兜底）；stdout/stderr 追加 `logs/watchdog_8000_restart.log`
- **防重入**：`logs/watchdog_8000.pid` + 命令行含 `watchdog_8000.py` 校验（uvicorn 自身不算）；`--force` 抢占、`--stop` 停止
- **防风暴**：`--cooldown`(90)s 冷却窗；恢复成功记 `HEALTH_RECOVERED`
- **可观测**：事件日志一行一事立即落盘（`logs/watchdog_8000_events.log`）；每 10 轮采样内存基线（RSS/sysmem/CUDA）
- **辅助模式**：`--once`（单次判读，验收用）/ `--baseline`（内存+CUDA 基线）
- 测试：`edu-agent/tests/test_watchdog_8000.py` 10 用例（Monitor 连败/冷却/重置、pid 防重入 3 态、netstat GBK 解析、--once 退出码、探活契约），**不发真实网络请求**
- check-demo.mjs ④ FIX.backend 已追加 watchdog 判读提示并引用本报告路径（3bd799f diff）

## 3. 实弹证据（2 次真实演练，事件日志原文）

事件日志 `edu-agent/logs/watchdog_8000_events.log` 中两次完整 RESTART 循环（演练=人为杀 8000，看门狗真实检出并拉起）：

```
[07:26:47] WATCHDOG_START pid=30488 …
[07:27:50] HEALTH_FAIL FAIL_1/3 … listener_pid=None
[07:28:22] HEALTH_FAIL FAIL_2/3 … listener_pid=None
[07:28:54] HEALTH_FAIL RESTART …
[07:28:54] RESTART_BEGIN → RESTART_INITIATED ok=True how=spawned via detached+breakaway
[07:29:00] RESTART_OK 8000 back to healthy          ← 演练①：杀→恢复 75.4s（30~90s 窗口命中）

[07:32:04] HEALTH_FAIL FAIL_1/3 …
[07:32:36] HEALTH_FAIL FAIL_2/3 …
[07:33:08] HEALTH_FAIL RESTART …
[07:33:08] RESTART_BEGIN → RESTART_INITIATED ok=True how=spawned via detached+breakaway
[07:33:14] RESTART_OK 8000 back to healthy          ← 演练②：杀→恢复 80.5s（30~90s 窗口命中）
```

两次恢复时长 75.4s / 80.5s（杀→/health 回 200），均命中设计窗口（检出 3×30s + 拉起冷启动）。三级降级第一级 `detached+breakaway` 两次直接成功。

## 4. 内存基线（OOM 假说弱化）

| 采样时刻 | 8000 PID | RSS | sysmem | CUDA used/total (MiB) |
|---|---|---|---|---|
| 07:25:57（重启前实例） | 16060 | 2,547,420K（2.43GB） | 80% | 6017 / 8188 |
| 07:31:32（演练①重启后） | 4524 | 3,926,404K（3.75GB） | 78% | 3040 / 8188 |
| 07:36:45 | 28308 | 3,771,512K（3.60GB） | 78% | 3031 / 8188 |
| 07:41:46 | 28308 | 3,772,060K（3.60GB） | 68% | 2581 / 8188 |
| 08:30:08（本批基线） | 2808 | 3,581,000K（3.42GB） | 90% | 3122 / 8188 |

口径：RSS 2.43~3.75GB、CUDA 2.5~6GB/8GB。**重启后 RSS 反而更高（2.43→3.75GB）且无单调增长**——OOM 假说弱化（死亡与内存水位无相关性）。注意 08:30 采样 sysmem=90%，整机内存压力偏高属环境常态，与 8000 单进程 RSS 无因果。

## 5. 承接验证（本批复跑实证）

- **单测复跑**：`.venv/Scripts/python.exe -m pytest tests/test_watchdog_8000.py -v` → **10 passed in 5.20s**（Python 3.11.15 / pytest 8.4.2，Windows-10-19044），与暂停快照 10/10 一致，零回归。
- **check-demo FIX**：`git show 3bd799f -- edu-agent/scripts/check-demo.mjs` 确认 FIX.backend 追加「无声死亡史→watchdog --once 判读→常驻看门狗」提示+本报告路径引用。
- **watchdog 代码**：本批**零改动**（无缺陷需要小修），红线遵守。

## 6. 本批看门狗重启（在岗证据）

前任实例 pid=30488 于 07:41:46 后事件断流，08:25 核查：无进程、pid 文件已消失、事件日志无 WATCHDOG_STOPPED/EXIT 行 → **非正常退出**（外部杀/会话连带杀，属死亡②④家族再现——恰好反证看门狗必要性）。本批重启：

- 08:29:37 拉起，spawner 三级链第一级 `detached+breakaway` 成功（Popen pid=19080 为 venv launcher，实际解释器 pid=21880 写 pid 文件——uv 管理 python 的 launcher→解释器两级结构，kill 目标以 pid 文件为准无歧义）
- **pid 文件**：`edu-agent/logs/watchdog_8000.pid` = `21880`
- **进程在岗**：PowerShell `Get-Process -Id 21880` 存活，CommandLine=`…python.exe scripts/watchdog_8000.py`（防重入标记命中）
- **事件日志**：`[08:29:37] WATCHDOG_START pid=21880 interval=30.0s threshold=3 cooldown=90.0s` + `[08:30:08] BASELINE pid=2808 rss=3581000K sysmem=90% cuda_used_total_mib=3122, 8188`（新 BASELINE 行）
- **连续 2 次探活 200**：`--once` ×2（间隔 31s）均 `health=OK detail=ok listener_pid=2808`；8000 生产实例零接触（未重启，仅探活）
- **自主循环在岗证据**：08:34:08 事件日志出现看门狗自主第 10 轮采样 `BASELINE pid=2808 rss=3581452K sysmem=88% cuda_used_total_mib=2831, 8188`（非人工触发，RSS 与 08:30 基线一致=稳定无泄漏迹象），且零 HEALTH_FAIL

## 7. 零误报窗状态（如实登记）

前任 30 分钟零误报窗**未走完**（至暂停时事件日志零误报，07:26:47~07:41:46 在岗窗内无 HEALTH_FAIL 误触发）。本批 08:29:37 重启后在岗观察误报 0，**正式 30 分钟零误报窗由运维侧累计**（判定口径：事件日志无「非演练 HEALTH_FAIL→RESTART」行即零误报；演练/真实死亡触发的 RESTART 不计误报）。

## 8. 承接核对：8000 中止根因排查移交项 = 本批承接收口

移交项出处：`.ai-hub/plans/artifacts/kickoff-HITL-FIX.md` 步骤3 **CR-T11-C（P2）**——"admin 直连 knowledge_import 后 8000 中止——查退出栈、是否 OOM/未捕获异常/资源耗尽；若复现定位根因修复，或登记为已知环境限制"。

**承接结论**：本批三死亡取证（§1）覆盖该移交项——观测窗内 8000 中止全部为外部因素（①整机崩溃+torch_cpu.dll WER；②④killPort 工具链外部硬杀；③误记），**无一例 HITL 写路径应用层崩溃**（OOM/GPU TDR/uvicorn 生命周期全排除）。按 GWT ②"不复现则登记触发条件待观察"登记：**触发条件=外部 killPort 硬杀与整机异常重启，与 knowledge_import 写路径无关**。HF-G3"写类路径重复触发 8000 稳定不中止"的防再断保障由看门狗常驻兜底：即使再遭外部硬杀，30~120s 内自动恢复（实弹 75.4s/80.5s 实证）。移交项就此收口。

## 9. P0 自批判（4 条，均如实登记不粉饰）

1. **P0-A 看门狗不是免死金牌**：它与被监护对象同受外部硬杀与会话 job 清理威胁。前任实例 30488 正是如此离岗（无 STOP/EXIT 事件、pid 文件被清理）。本批以 `detached+breakaway` 拉起已缓解（脱离本会话 job object），但 killPort/taskkill 类工具仍可杀。**根治=Windows 服务化（schtasks SYSTEM / 服务包装），未做，登记为移交项**。
2. **P0-B 误杀风险**：/health 只证端口+轻路径可用，3×30s 连败即 `taskkill /F` 监听者，不区分"拒绝连接/超时/5xx"。若实例只是慢（CPU 饱和、模型重载），看门狗会把"慢"强杀成"停"，并触发 BGE-M3 CUDA 冷启动（分钟级），最坏反而放大不可用。缓解现状：RESTART 前有 netstat 监听复核，但"监听但不响应"与"僵死"本质不可区分；零误报窗未走完（§7），无误杀概率数据。
3. **P0-C RESTART_OK 假绿**：spawn 后首个 /health 200 即记 RESTART_OK（实弹日志 RESTART_INITIATED→RESTART_OK 仅 5~6s），而应用冷启动模型加载远超 6s——/health 在模型就绪前已 200，RESTART_OK ≠ 业务就绪。若上层依赖 RESTART_OK 判定"恢复完成"会误判；真实恢复应以首个业务请求成功为准（未实现，登记）。
4. **P0-D 救不回时无升级通道**：三级降级 spawn 全失败或 60s 未回 200 仅记 `RESTART_PENDING` 文件日志，无告警外发（邮件/webhook/OTLP 告警）——"看门狗救不回"与"看门狗自身死亡"对运维均不可见，只能靠翻日志发现。与服务化（P0-A）一并登记为运维侧移交。

## 10. 资产消费证据（AGENTS.md 教训引用）

- **AGENTS.md「启动命令」**：`spawn_uvicorn` argv 严格按 `.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`（cwd=edu-agent）构造，第三级降级原样内置 `cmd /c start "" /B` 形态（watchdog_8000.py:162-184）。
- **AGENTS.md 关键教训 2（禁 Playwright、验收须独立实证）**：本报告全部证据为真实 HTTP 探活、真实事件日志、真实 pytest 复跑，无模拟旁证；实弹演练为真实杀-真实恢复。
- **AGENTS.md 教训 8（真实契约优先于页面注释）**：探活契约以 /health 真实响应 `{"status":"ok"}` 实测为准（urllib 直连验证），非任何注释口径。
- **check-demo.mjs 资产反哺**：④ FIX.backend 注入 watchdog 判读提示+本报告路径（3bd799f），demo 检查链与看门狗资产互通。
- **test-reports/ 报告惯例**：本报告落位 `test-reports/`（与既有 40+ 份 WNEXT* 报告同目录），供 check-demo FIX 引用闭环。

## 11. 遗留与移交

| 项 | 归属 | 状态 |
|---|---|---|
| 看门狗服务化（防外部硬杀根治） | 运维侧/后续批 | 未做（P0-A） |
| 正式 30 分钟零误报窗累计 | 运维侧 | 已登记口径（§7） |
| RESTART_OK→业务就绪判据 | 后续批 | 未做（P0-C） |
| 告警外发通道 | 后续批/OTLP 线 | 未做（P0-D） |
| 8601 sidecar 未起（进程内 CUDA 兜底） | 已知降级 | 非本批范围 |
| 8000 生产实例 | 运行中 pid=2808 | 本批零接触，健康 |

## 12. 红线自检

- 文件归属：本报告 + lock 删除（`edu-agent/scripts/eval/wnextstability1.lock`，前任遗留，内容 `pid=2229 … agent=W-NEXT-STABILITY-001` 已留档于本行）+ logs/ 下看门狗运行时产物（pid/事件日志，非提交物）。**未改 watchdog 代码**（无必要小修，无 diff）。
- 未触碰 app/**、contracts/**、edu-frontend/**；8000 生产实例零重启零配置变更。
