# task121 · 面向编排者的复验清单（task117 交付独立复验）

> 目的：让编排者**不依赖执行者自述**、用可复跑命令独立验证 task117 的交付物是否真实成立。
> 方法学：TT 独立实证验收（B 级资产消费证据）+ trust-but-verify（只信可复现证据）。
> 关联交付：task117 完工报告 `test-reports/task117-completion-report.md`。
> 本清单由 task121 收尾"两者都做"产出 —— ① 本复验清单；② 运维坑可复用 skill
> `C:\Users\Administrator\.workbuddy\skills\eduagent-local-verification-ops\SKILL.md`。

---

## §0 范围与交付物

| # | 交付物 | 说明 |
|---|---|---|
| 1 | `edu-frontend/public/admin-courses.html` | 真实 CRUD 接线（写路径全改，消费 task116 C-C 软删契约） |
| 2 | `test-docs/t117_full.py` | 可复跑全链验收脚本（建→改→上下架→软删→回收站复查 + 40901/42200 + 清理） |
| 3 | `test-reports/t117_full_out.txt` | 14 PASS / 0 FAIL 原始实证 |
| 4 | `test-reports/task117-completion-report.md` | task117 完工报告 |
| 5 | `test-reports/task121-reverification-checklist.md` | 本清单（task121 ①） |
| 6 | `~/.workbuddy/skills/eduagent-local-verification-ops/SKILL.md` | 运维坑可复用 skill（task121 ②） |

**硬纪律履约**（应全部为 ✅）：只改 `admin-courses.html` ｜ 未切分支 / 未 commit ｜ 未改 `edu-api.js` ｜ 未用 Playwright。

---

## §1 前置条件

- 工作区：`E:\stu\project\stu\EduAgent实施手册`
- 后端 venv：`edu-agent/.venv/Scripts/python.exe`（已存在）
- 可用端口：本机 `8078`（避开托管旧实例 8000）
- 管理员账号：`adm02test` / `Test@123456`（脚本内置，勿改）
- **环境要点（详见运维 skill 坑 1）**：后端须 `MYSQL_HOST=127.0.0.1`，**不要**用 `192.168.85.101`（VM MySQL 拒 `root@192.168.85.1`）。

---

## §2 静态机验（无需起后端，先跑这三项）

在 `EduAgent实施手册` 根目录执行：

```bash
# 2.1 写路径无残留 alert 占位（期望 0）
grep -c "alert(" edu-frontend/public/admin-courses.html
#   → 期望输出：0

# 2.2 删除文案合规：含"下架"、显式"不会永久删除"、按钮"确认下架（软删）"
grep -n "确认下架（软删）\|不会永久删除\|可在回收站查看" edu-frontend/public/admin-courses.html
#   → 期望命中 L398/L399/L405 附近

# 2.3 内联脚本语法（提取 <script> 块逐个 node --check）
python - <<'PY'
import re, pathlib, subprocess, tempfile, os
html = pathlib.Path("edu-frontend/public/admin-courses.html").read_text(encoding="utf-8")
blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
ok = True
for i, b in enumerate(blocks):
    p = os.path.join(tempfile.gettempdir(), f"em_scr_{i}.js")
    open(p, "w", encoding="utf-8").write(b)
    rc = subprocess.run(["node", "--check", p]).returncode
    print(f"script#{i} rc={rc} len={len(b)}")
    ok = ok and rc == 0
print("SYNTAX_OK" if ok else "SYNTAX_FAIL")
PY
#   → 期望每个 script# rc=0，末行 SYNTAX_OK
```

**判定**：2.1=0 且 2.2 命中且 2.3 `SYNTAX_OK` → 静态机验 PASS。

---

## §3 起后端（环境要点见运维 skill 坑 1/2）

```bash
cd edu-agent
MYSQL_HOST=127.0.0.1 .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8078
```

- 就绪标志：`Uvicorn running on http://127.0.0.1:8078`。
- ❌ 若日志出现 `1130 Host '192.168.85.1' is not allowed to connect` → 你连到了 VM，
  改回 `MYSQL_HOST=127.0.0.1`（见 skill 坑 1）。
- 起在**后台**（新终端 / `run_in_background`）；跑完 §4 后用 PowerShell 停：
  ```powershell
  Stop-Process -Id (Get-NetTCPConnection -LocalPort 8078 -ErrorAction SilentlyContinue).OwningProcess -Force
  ```

---

## §4 全链行为复验（跑 t117_full.py）

```bash
cd EduAgent实施手册
edu-agent/.venv/Scripts/python.exe test-docs/t117_full.py
# 可选：T117_BASE=http://127.0.0.1:8078（默认即此）
```

**期望输出（关键行）**：

```
[PASS] 新建系列成功
[PASS] 列表立现新建行
[PASS] PATCH 改名成功
[PASS] 刷新后为新值
[PASS] 上架成功 / 状态=on_sale
[PASS] 下架成功 / 状态=off_sale
[PASS] 软删 message=系列已下架
[PASS] 默认列表已剔除软删行
[PASS] 回收站视图仍可见
[PASS] 重复编码 409/40901
[PASS] 非法字段 422/42200
[PASS] 清理：hard 删除成功
PASS=14 FAIL=0
```

**判定**：末行 `PASS=14 FAIL=0` 且脚本 exit=0 → 全链行为复验 PASS。
（原始输出可对照 `test-reports/t117_full_out.txt`。）

---

## §5 C-C 契约消费对照（前端 → task116 冻结单）

| 契约条款（task116） | 前端落点（应能在 `admin-courses.html` 中 grep 到） |
|---|---|
| §1.1 软删默认路径，message `"系列已下架"` | `doDelete()` 调 `EAPI.del("/api/admin/courses/series/"+id)`，**不带 `hard`**；toast 用返回 message |
| §1.1 严禁"永久删除" | 删除文案含"下架"、显式"不会永久删除数据"；前端**永不发 `?hard=true`** |
| §2 默认列表过滤 `sale_status!='off_sale'` | `loadSeries()` 渲染默认列表；软删后 `refreshList()` 复拉，行自动消失 |
| §2 `include_deleted=true` 回收站 | 软删行在回收站仍可见（§4 第 9 项实证） |
| §7.2 不新增 `yn` 列 | 前端不依赖 `yn`，仅读 `sale_status` |

**判定**：逐项能在代码/grep 中对应 → 契约消费 PASS。

---

## §6 残余缺口与未达标（诚实标注，非本任务范围）

- **筛选栏未接 API**：顶部筛选栏（关键词/交付/状态/排序）的 `onchange` 仍走演示层
  `render()`（mock `SERIES`），真实数据下切换筛选会回落演示数据。归后续 task。
- **未 commit**（遵守硬纪律）：如需入版控，编排者另行路径限定提交。
- **环境漂移已解决并沉淀**：MySQL 须 `127.0.0.1`（见 skill 坑 1），已据以实证，未动 8000 托管旧实例。

---

## §7 验收签字（编排者填写）

| 复验项 | 结果 | 备注 |
|---|---|---|
| §2 静态机验 | ☐ PASS / ☐ FAIL | |
| §4 全链 14 PASS | ☐ PASS / ☐ FAIL | |
| §5 契约消费 | ☐ PASS / ☐ FAIL | |
| 硬纪律履约 | ☐ 通过 / ☐ 违反 | |
| 交付物齐全（§0 六件） | ☐ 齐 / ☐ 缺 | |

编排者签字：__________  日期：__________
