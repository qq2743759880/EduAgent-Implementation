# TO-EXEC-TA8 — 探针与门禁假红修复（收尾小单）

> 分支 `feature/opt-waves`（开工前 `git log --oneline -3` 记基线）。三处工具层假红/漂移，均为 TC1/TA7 验收期实证发现，零业务代码改动。**服务重启只准用 `start-eduagent.cmd`。**

## 工作项

1. **⑯ lifecycle 假红**：`edu-agent` 下 lifecycle 探针 `:46` 用了未定义变量 `PROBE_PORT`（同函数 `:29` 是 `probe_port`），NameError 被 `except Exception: pass` 吞掉 → 健康检查恒假 → 空转 30s 被 kill → 指标全 0。修：改 `probe_port` + **except 收窄为 OSError**（禁裸吞）。修后跑一轮 lifecycle 验证产出真实指标（对照 `logs/lifecycle_real_*.log` 旧假红轮）。
2. **mcp_tristate_probe.py 默认端口漂移**：仍默认 8000（端口 2026-09-20 已迁 9988）→ 改 9988 并复跑确认真连。
3. **G7 parse() 支持 CSS Color 4**：`scripts/gates/viewport-a11y-gate.mjs::parse` 把 `color(srgb 1 0.9 0.87)`（分量域 0~1）按 0~255 读 → 近黑 → 假对比度比值（<2.0）。修：解析时识别 `color(srgb …)` 函数并按 0~1 域归一。修后 G7 `--all` 全站跑一遍，对照既有基线确认**只消假红、无新增红**（admin-infra 的页面侧实色规避可保留，不回改页面）；基线如需重冻结走 `--update-baseline` 并在报告说明。
4. 回归：G3 `--all --check` 零漂移；`node --check` 所有改动脚本语法过。

## 铁律

- 域：上述探针/门禁脚本 + （如基线重冻结）对应基线文件。禁碰业务代码、页面 HTML、`.env`。
- 不 push；单 commit：`fix(gates)/ta8: 探针假红修复(lifecycle PROBE_PORT+tristate 端口)+G7 CSS Color 4 解析`。
- 报告 `.ai-hub/plans/artifacts/dispatch/REPORT-TA8.md`：修前修后对照（假红轮 vs 真实指标轮；G7 全站前后计数）。

## owner 验收口径

Given owner 问"体检单 ⑯ 还红吗"，Then 答案基于真实健康检查（有指标）；G7 全站无 <2.0 的诡异比值。
