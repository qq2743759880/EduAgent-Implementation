# TO-EXEC-FEAT-WIRE — 25 页功能接线全面审计与补齐（用户直接指令：每一个能链接的接口都不遗漏）

## 背景（用户裁定，优先级最高）

用户实测发现新黏土页面存在"功能未实现"体感（截图：课程详情优惠券弹窗/课表占位）。经编排者核查：G1 门禁只保证「页面**已调用**的接口 ↔ 后端路由零断点」，**不覆盖「有按钮/功能但根本没接接口」的死端**。本任务补这个洞：逐页枚举全部交互元素→逐一验证接线→修复死接线。

## 任务 A：接线矩阵盘点（25 页全量）

对 `edu-frontend/public/*.html` 每一页枚举：全部 button / a[href] / form / tab / 弹窗动作 / 上传控件 → 三分类：

| 分类 | 判据 |
|---|---|
| **wired** | 点击触发真实后端调用（EAPI/(fetch) 到 /api/*，openapi.json 中存在该路由） |
| **dead** | 无 handler / handler 报错 / 调用了不存在的路由 / 调用后不渲染结果 |
| **placeholder** | 诚实占位（「即将上线」四态组件，预留接口登记表在册）——**不算缺陷但须登记** |

产出 `docs/feat-wire-matrix.md`：页 × 元素 × 分类 × 证据（选择器+实测行为）。

## 任务 B：dead → wired 修复（行为层施工，本单特批授权）

平时铁律「行为层禁碰」**本单解除**（用户直接指令），但仍受以下约束：

1. 只接线不重写：沿用页内既有 EAPI 模式与代码风格；**禁止重构无关代码**
2. 契约权威：`http://127.0.0.1:9988/openapi.json` + `schemas.py`/`error_codes.py`；响应壳 `{code:0,message,data}`；**发现后端缺端点→登记移交，禁自建后端**
3. **安全硬约束（Mimosa 生成前约束，违反=FAIL）**：任何服务端发 URL 请求处只允许 http/https、发请求前校验 host、拒绝 localhost/环回/私有/保留地址；如涉及写 SQL 的脚本一律参数绑定禁拼接
4. 已知必查项（用户实测点名）：课程详情页的 课表展示（报名后）/「去学习」链路 → learning 页课表与进度 / 课程评价(0) 提交与展示 / 思维导图按钮 / 优惠券领取与使用闭环（模板 71 库存已由编排者 100→500，领券应成功）/ 报名下单→支付(mock)→my-cohorts 全链
5. 视频播放链路专项：核实 `/media/videos/*` 是否有静态挂载可服务（后端 main.py 静态目录 or Next）——learner 页点播真实上传视频（如 VID-2026 开头的本地文件）能否播放；不能→定性（缺挂载 or 缺端点）登记移交
6. 双前端对账（信息性登记）：`edu-frontend/src/app`（React：(admin)/(user) 路由组，根路由 / = React 壳）vs static 25 页——产出一张「哪个入口是 React / 哪些功能只在 static」对账表入 docs/，不改 React 侧代码

## 任务 C：修复验证（每处修复逐条实证）

- 修复元素 CDP 真实点击实测：请求发出→响应→UI 渲染，截图留档 `test-reports/feat-wire/<page>/`
- G3 全站 `--all --check` 零漂移（接线改动若需新增 DOM 钩子→走钩子清单增量并 `--update-baseline` 该页，登记）
- G1 契约检查 exit 0；改动页 G6/G7/G9 单页复跑绿
- 每页独立 commit：`feat(fe)/feat-wire/<page>: <修复清单>`
- **placeholder 诚实化**：凡短期接不上的功能，统一改挂「即将上线」四态组件（§方案十二），禁止假按钮

## 铁律

public/ 25 页 + `docs/` + `test-reports/feat-wire/` 之外零触碰；theme.css 禁改（视觉已冻结）；后端零改动；不 push；开工前后 `git branch --show-current`=feature/opt-waves；报告 `.ai-hub/plans/artifacts/dispatch/REPORT-FEAT-WIRE.md`（矩阵+修复清单+每处证据+移交项：后端缺端点清单/视频挂载结论/React 对账表；含资产消费证据与批判承接段）。3322 dev 态在跑，token 走运行时环境变量。
