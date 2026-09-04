# 遗留项 1 完工报告 — Series JSON 列写侧序列化修复

- 任务：EduAgent 优化期遗留项 1（tt 工作流 A 级：BE/数据完整性/契约）

- 执行 agent：本执行 agent（串行编排下退化为单 agent 模式，N=1）

- 日期：2026-09-04

- 状态：修复完成，契约测试全绿（未 commit，验收通过后由编排者统一提交）

## 1. 资产消费证据段（必填）

本任务为 A 级（BE/数据完整性/契约），开工 prompt 列了 3 个必调资产，均在实际改动**之前**用 Read 真实消费：

| 资产路径                                                            | 是否读                                       | 消费到的方法论                                                                                                                                                                                         | 落在哪几行改动                                                                                                                           |
| --------------------------------------------------------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `C:\Users\Administrator\.agents\skills\harden\SKILL.md`         | ✅ 读过全文                                    | 「Input Validation & Sanitization / 边界加固」：`_json_or_null` 对 None / 已 str / list 三种类型分别安全序列化（None → NULL，list→dumps，str 保持）；「Automated testing / 集成测试 error scenarios」：契约测试覆盖 500→200、400、null 边界 | `series_repo.py` 顶部 `_JSON_COLUMNS` 常量 + `_json_or_null()`（14-25 行）；insert 三列调用（117-119 行）；update 循环内调用（131-132 行）                |
| `C:\Users\Administrator\.agents\skills\tt\SKILL.md`             | ✅ 读过全文（§5.2 回传机制/验收纪律 + §5.3/§5.4 契约独立验收） | 契约冻结纪律：不采信报告、须**独立实证**（真实 HTTP 直连 8000 + DB round-trip）；完工报告须含「资产消费证据」段（本文即按 §5.2/§5.3 格式落盘）；真实 token 鉴权（防 DEBUG 虚拟管理员降级绕过）                                                                     | `test_course_admin_json_columns.py` 全程：login 取真实 access\_token + Bearer 头；断言 200 `{code:0}` 与 data 三列 round-trip；测试名/断言按 GWT 语义命名 |
| `C:\Users\Administrator\.agents\skills\tt\vendor\sdlc\SKILL.md` | ✅ 读过全文                                    | 「BMAD-METHOD：plan→develop→review→summarize」工程主干：改动只限授权文件（repository 单层），只补写侧、不改 schemas 契约；review 阶段以契约测试为「独立验收」证据                                                                              | 改动范围收敛：仅 `series_repo.py` + 新增 1 测试文件；不改 `schemas.py` 的 `List[str]` 契约                                                            |

> 自检（critique 三视角，tt §5.2 竣工自检要求）：
>
> - 边界：None / 已 str / list 三型全覆盖，未破坏普通字段（update 循环内仅对 `_JSON_COLUMNS` 命中才序列化）。
>
> - 读←→写对称：写侧 `_json_or_null` 与读侧 `service._parse_json_columns`（json.loads）配对，round-trip 一致。
>
> - 契约：未改 schemas.py 字段定义（保持 `Optional[List[str]]` 正确语义）。
>
> - 自检无发现需修的问题。

## 2. agent × skill × workflow 矩阵

| 维度       | 取值                                         | 说明                                           |
| -------- | ------------------------------------------ | -------------------------------------------- |
| agent    | 本执行 agent（N=1 单平台串行模式，tt §5.0 退化路径）        | 只做遗留项 1，不扩范围                                 |
| skill    | `harden`（边界加固）+ `sdlc`（BMAD 工程主干）          | 均随包/本机真实存在，开工前 Read 消费                       |
| workflow | `tt` 契约冻结纪律（§5.2 独立实证验收 / §5.4 契约不 drifft） | 契约 immutability：schemas 未动；验收靠真实 HTTP 实证而非自述 |

## 3. 根因 → 修复 → 实证闭环

### 3.1 根因（编排者已定位，本 agent 复现确认）

`series_repo.py` 的 `insert`/`update` 把三个 JSON 列（`target_learner_identity_codes` 等）的 `list` 值直接塞进 SQL 参数元组；底层 `asyncmy cur.execute` 对 `list` 抛 `Argument 'val' has incorrect type (expected tuple, got list)` → 全局异常 → 500 `{code:"50000"}`。读侧 `service._parse_json_columns` 已正确，仅写侧缺序列化。

**改动前（关键片段）**：

```python
# insert
data.get("target_learner_identity_codes"), data.get("target_learning_goal_codes"),
data.get("target_grade_codes"), ...
# update
for key, val in data.items():
    set_clauses.append(f"{key} = %s")
    args.append(val)          # list 直接进参数 → asyncmy 500
```

### 3.2 修复（改动后关键片段）

`app/domains/course_admin/repository/series_repo.py`：

```python
import json
_JSON_COLUMNS = ("target_learner_identity_codes", "target_learning_goal_codes", "target_grade_codes")

def _json_or_null(val):          # None→NULL；str 保持；list/其它→dumps（与读侧 json.loads 对称）
    if val is None:
        return None
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)

# insert 三列改为 _json_or_null(data.get(...))
# update 循环内：
args.append(_json_or_null(val) if key in _JSON_COLUMNS else val)   # 不破坏普通字段
```

- 未动 `schemas.py`，`List[str]` 契约保持不变。

- 仅改授权文件 `series_repo.py`（+21/-3 行），新增 1 契约测试文件。

### 3.3 独立实证（真实 HTTP 直连 127.0.0.1:8000，admin 登录取真实 token）

新增 `edu-agent/tests/test_course_admin_json_columns.py`，3 用例全真实 HTTP：

| 用例                                              | 断言                                                                                      | 结果                       |
| ----------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------ |
| `test_create_with_json_list_columns_roundtrip`  | POST 含 `["C1","C2"]/[G1]/[GR1,GR2,GR3]` → `200 {code:0}` 且 data 三列 round-trip `==` list | **改造前 500 → 改造后 PASSED** |
| `test_patch_update_json_list_columns_roundtrip` | PATCH 更新三列为 list → `200 {code:0}` round-trip list                                       | **改造前 500 → 改造后 PASSED** |
| `test_create_with_null_json_columns`            | 三列显式 null → `200 {code:0}` round-trip `None`                                            | PASSED                   |

> 复现实证（改造前旧代码进程）：`POST/PATCH ... 实际 500 {'code': '50000', 'data': "Argument 'val' has incorrect type (expected tuple, got list)"}`，与根因完全一致。
> 重启后端加载新代码后：`3 passed in 29.84s`（全部 200 且 round-trip 断言通过）。

**结论**：创建/更新含 list 字段的 series **不再 500**，三 JSON 列读写对称、round-trip 正确，契约首尾一致。

## 4. 验收提示

- 后端当前以新代码运行在 8000（本 agent 重启）；虽重启自证通过，验收方仍可按 tt §5.4 独立复跑 `pytest edu-agent/tests/test_course_admin_json_columns.py`。

- 未 commit；等待编排者统一提交。

