# H 系列·独立复验包(一令可跑,2026-09-12 交付)

> 用途:任何人可随时独立复现 H 系列热修的全部验证,不依赖编排者自述。
> 前置:后端 8000 运行(edis/Milvus 状态不影响);工作区根执行。

## 一令复跑(全部)
```bash
cd edu-agent && .venv/Scripts/python.exe -m pytest tests/test_contract_p18_debug_gate.py tests/test_contract_series_restore_conflicts.py -q --no-header
```
预期:`7 passed`(P1-8 门禁 4 用例 + restore/hard 冲突 3 用例)。

## 分项手工验证(可选)
| 项 | 命令/操作 | 预期 |
|---|---|---|
| H1b 拒启实验 | `cd edu-agent && set ENV_NAME=prod && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8002`(cmd) | 启动即拒,exit≠0;8002 无残留 |
| H2a manager 403 | mgr01test 登录 → GET /api/admin/users?page=1 | 403 `40300 允许角色=['admin']` |
| H2a admin 对照 | adm02test 同端点 | 200,total≈100034 |
| H2a 页面行为 | manager 登录进 admin-users.html | 红横幅「仅 ADMIN 可用」+不发列表请求 |
| L2 性能 | admin token GET /api/admin/courses/series/1 计时 ×3 | <0.5s(健康栈实测 16-38ms) |

## 相关提交
41b5996(门禁)/ 0463da8(冲突测试+清理脚本)/ e7b53a2+36af61c(门禁合并单一真相)/ ed31f4d(manager 守卫)
## 已知非缺陷观察
O1 ENV_NAME 双声明已合并(e7b53a2);O2 两层门禁口径差已消除;O3 H1c 测试设计性残留 2 行(H2 脚本范畴)。
