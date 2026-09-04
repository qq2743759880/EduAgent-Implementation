# W1-批判3 — 死链扫描未门禁化：完工报告

- 任务：W1-C3（scan-deadlinks.mjs 挂进 W4(task123) 检查单 + L4 全量回归跑一次 + 接受"静态扫描+变量拼接人工走查"口径）
- agent：W1-批判3 执行子 agent ｜ skill：ponytail + tt ｜ workflow：W1-C3 框架承接（C-17）
- 日期：2026-09-04 ｜ 未 commit（遵守开工单纪律）

---

## 1. 资产消费证据 + agent×skill×workflow 矩阵

**资产消费证据（先消费后动手）**：
- **ponytail**（`C:\Users\Administrator\.agents\skills\ponytail\SKILL.md`）：阶梯「复用>新建/最小」约束下，本批**零新增代码、零新建 CI 系统**——只做三件事：写口径注释（改 1 处头注释）、挂检查单条目（改 1 行段）、跑一次工具。不建回归 harness、不加运行时代码。SS 判定为最小可行。
- **tt**（`C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 回传/验收 + §5.4 L4/里程碑 gate）：工具头注释即「口径固化」，检查单挂载即「回归门固定条目」，本报告即 §5.2 要求的完工回传（只传路径引用）。
- **自检**：读 tool 现状→试跑→置口径→挂检查单→复跑验证→人工走查注记；无修复假阴性需求，如实记录"无需白名单"。

**agent×skill×workflow 矩阵**：

| 维度 | 取值 |
|---|---|
| agent | W1-批判3 执行 agent（N=1 单平台模式，串行承接） |
| skill | `ponytail`（最小实现护栏）+ `tt`（§5.2 回传 + §5.4 里程碑/L4 gate） |
| workflow | W1-C3 框架承接：工具口径注释 → task123(deploy/README) 检查单挂载 → 本批实跑 → 人工走查盲区注记 |

---

## 2. 现状 → 口径注释 → 检查单挂载点 → 本次扫描输出

### 2.1 scan-deadlinks.mjs 现状
- **实际路径**：`test-reports/scan-deadlinks.mjs`（task110 一次性脚本；注意与任务描述 `edu-frontend/public/scan-deadlinks.mjs` 不同——该路径不存在）。
- **可独立跑**：`node test-reports/scan-deadlinks.mjs` 无参数、无输出文件需求，退出即打印统计。✅ 试跑成功。
- 现有能力：href / location 跳转 / 模板串提取 + 归一化（去 ${}、query、hash）→ 判定目标文件是否存在。已含对 `${...}` 与 `?` 的剥离，故 community-post 历史"伪孤立页"误判已经在 normalize 层规避。

### 2.2 口径注释（已写入工具头，`scan-deadlinks.mjs` 12–22 行）
在工具头注释新增「口径（W1-批判3 承接，C-17）」块，固化三点：
1. **定位**：本工具=静态孤立页/死链门禁（仅判「目标文件是否存在」），回归固定条目。
2. **盲区（非运行时巡检）**：静态扫描对变量拼接跳转（`"/x.html?"+id`、`location.href=...+"?"+id`）无感知 → 可能把仅动态可达页（如 community-post.html 详情页）误判为孤立/死链 = 假阴性，须人工走查社区/详情 ID 动态链路；运行时被禁用，不请求真实 URL。
3. **exception 规则**：如需排除已知动态拼接页或加白名单，在工具内维护一行 whitelist 正则；当前无需白名单（本次 0 死链、0 假阴性）。

### 2.3 检查单挂载点（已挂 deploy/README.md）
仓库内无独立「L4 全量回归」检查单文档；「task123 检查单」即 `deploy/README.md` 的「DEBUG=False 部署前必跑检查单（task123，出包前必跑）」（task123 计划「改动点5」+ 完工报告明确挂载点）。故挂在其中有据：
- 文件：`deploy/README.md`，LoadLine 97–101，在 4) metrics 鉴权项后**新增固定条目 `# 5) 死链扫描`**：
  - 命令：`node test-reports/scan-deadlinks.mjs`
  - 期望：末行 `=== 死链总数: 0 ===`
  - 注明 W1-C3/C-17、L4/里程碑回归固定条目、快照落到本报告、盲区人工走查提示。

### 2.4 本次扫描输出（本批实跑）
```
=== 扫描: 20 个 html ===
[修复前] 死链/可疑项(ok=false): 空
正常链接统计(ok=true): 208 条
... 20 文件均 dead=0 ...
=== 死链总数: 0 ===
```
- **结果：通过**（0 死链 / 0 假阴性）。
- **community-post 人工走查注记**：`community.html` 通过 `window.location.href = "/community-post.html?post_id=" + card.dataset.post` 动态拼接跳转详情页——目标文件存在于 public（scanner 判定 ok=13），但 `post_id` 各取值是否都有对应数据非静态可判，已进检查单人工走查提示，属已知盲区（非本次缺陷）。

### 2.5 假阴性修正 / 白名单
- 当前**无假阴性**（0 条 dead），无需修正、无需加白名单（exception 规则已以注释形式预留，避免过度设计）。

---

## 3. 死链清单结论

- **全站 20 个静态页无硬编码死链**（208 条有效链接全部目标存在），可作 W4/L4 里程碑回归的干净基线。
- **已知盲区**（诚实登记，不伪报）：变量拼接/运行时拼接跳转（社区详情、练习等含 ID 的动态跳转页）不在静态判定范围，需随功能联调人工走查；本工具不具备也不假装是运行时巡检。
- 检查单固定条目已就位，后续里程碑/L4 回归只需重跑 `node test-reports/scan-deadlinks.mjs` 并核对 `死链总数: 0` 即可。

---

## 4. 改动文件清单（未 commit）
| 文件 | 改动 |
|---|---|
| `test-reports/scan-deadlinks.mjs` | 工具头注释新增「口径（W1-批判3）」块（12–22 行），无逻辑改动 |
| `deploy/README.md` | task123 检查单新增固定条目 `# 5) 死链扫描`（97–101 行） |
| `test-reports/critique-W1C3-completion-report.md` | 本完工报告（新建） |