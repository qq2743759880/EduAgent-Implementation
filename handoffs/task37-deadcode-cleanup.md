# task37 GWT① 死代码清理 — 证据单

> 落点：task37（清理/文档/测试修复）｜类型：死代码删除
> 日期：2026-08-28｜执行者：后端+数据库开发者

## 1. 清理对象

`edu-agent/app/admin/course_admin/`（旧管理端课程模块，与 task12 落地后的
`edu-agent/app/domains/course_admin/` 并存，属历史残留）。

该目录含：`__init__.py`、`router.py`、`schemas.py`、`service.py`，其中
`service.py` 含 **39 处 `curriculum_` 引用**（即 GWT① 标注的「39 处 curriculum_ 引用」）。

## 2. 删除前核查（零外部依赖）

- 全仓 grep `app.admin.course_admin` / `admin.course_admin`（含 `.py`/`.yaml`/`.toml`/`.ini`）：
  除目录自身外 **零命中** → 无其它模块 import 它。
- `app/main.py` 仅 `include_router(app.domains.course_admin.router)`（**新**模块，task12 落地，不动）。
- `app/admin/__init__.py` 仅一句 docstring，无导出。
- 无任何 test 文件 import `app.admin.course_admin`。
- git 状态：该目录在 **当前 HEAD 从未被跟踪**（历史 19825b8/83a9531/62bc195 曾跟踪，
  后续已从索引移除，工作树残留为未跟踪游离文件）。因此删除为纯文件系统清理，无 tracked diff。

## 3. 执行

```
rm -rf edu-agent/app/admin/course_admin
```

## 4. 验收指标

| 指标 | 删除前 | 删除后 | 结论 |
|------|--------|--------|------|
| `curriculum_` 在 `app/`、`tests/` 的 `.py` 总命中 | 61 | 22 | ✅ 减少 39（即旧 course_admin 的全部引用） |
| 外部 import `app.admin.course_admin` | 0 | 0 | ✅ 无破坏 |
| 存活 `curriculum_` 引用归属 | — | `app/curriculum/*`（task11 308 重定向，有意保留）、`app/main.py`（308 路由注册）、`test_curriculum_service.py` | ✅ 均非死代码 |

> 说明：存活的 22 处 `curriculum_` 全部来自 `app/curriculum`（task11 旧路由 308 永久重定向兼容层，
> 仍由 `main.py:342` 显式注册，契约要求保留）及其测试，不在 GWT① 清理范围内，故未动。

## 5. 结论

GWT① 达成：`app/admin/course_admin` 旧死代码已删除，39 处 `curriculum_` 引用清零，
存活引用均为有意保留的 308 重定向层。无 import 破坏、无回归。
