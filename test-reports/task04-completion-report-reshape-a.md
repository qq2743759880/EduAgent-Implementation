# task04 完工报告（reshape-a 批次）：course-detail.html 学生端课程详情修复

日期：2026-09-06 ｜ 执行：fe-html 接线 agent ｜ 计划：`.ai-hub/plans/dev-plan-reshape-a.md` A 批次 task04
GWT：Given 真实 id → 详情+班次真实渲染；未登录报名入口跳登录；坏 id 诚实空态。
（注：`test-reports/task04-completion-report.md` 为历史批次同名报告，与本批无关，故加 `-reshape-a` 后缀）

## ① 改动文件 + 行数

- `edu-frontend/public/course-detail.html`：+111 / −65（git f70b06f），修复清单：
  1. **P0 根因修复**：wire 回调中 `COHORTS = items.map(...)` 对 **const 赋值抛 TypeError**，异常被 `.catch(showEmpty)` 吞掉 → **真实存在的课程（如 id=1）被误报"课程不存在"空态，hero 连同 h1 被顶掉**——即任务书"h1 空缺缺陷"根因。改为 `splice(0, length)` 原地替换（const 兼容）。
  2. **loading 收敛**：id 有效时立即 `applyState("loading")` 覆盖 mock 初渲（消除假课程名/假班次闪现）；重渲前先切回 success（修复引入的 loading 短路，自检发现并修掉）；同步清空 mock 班次+selected=0，任何失败路径不再回落 mock。
  3. **无班次守卫**：班次选中重算移出 `if(items.length)`；`summaryHtml`/`ctaText`/`cohortDetailHtml`/hero 班次区增加 c 空/COHORTS 空守卫（"暂无可报名班次"+CTA 禁用）。
  4. **MOCK 清零**：REVIEWS 假评价（米粒子等）、MODULES 假大纲（501~503，与真实班次 id 有碰撞风险）置空；评价 Tab 初始诚实空态、点击拉真（loadReviews 既有链路）。
  5. **假交互治理**：收藏心形由"本地翻转+alert"接真实 POST /api/favorites（幂等实测）+已收藏回显（GET 匹配）+已收藏再点诚实提示（取消路径实测为假删除，不做假交互）；大纲空态文案改"报名后可在学习页查看完整课表"；面包屑 `href="#"` 死链→courses.html，硬编码"编程/通用编程入门班"→真实一级分类/系列名回填。
  6. **字段错配**：bindLearn 的 outline 首课次 `ss[0].id` → `ss[0].id || ss[0].session_id`（实测字段为 session_id，原取值恒 undefined）。
  7. **无效 HTML**：cohortDetailHtml 模板中 `<></>` fragment 垃圾文本移除（浏览器会渲染出 "<>" 字符）。

## ② 资产消费证据

- 读完 AGENTS.md（教训 2 禁 Playwright——本任务用 curl + node stub-DOM 渲染链模拟替代；教训 8 真实契约优先；教训 9 禁 match 取参——取参走 EAPI.pageId("id")，回归确认未动）。
- 读完 dev-plan task04 GWT、contracts/reshape-a.json（GET /api/series/{id}、/api/favorites、/api/study/courses/* 在冻结清单，hash 30aeddbe 未改）、edu-api.js 头部注释（pageId/buildLoginUrl/错误壳）。
- **自检发现并修掉**：①P0 const 赋值缺陷（复现后修）；②自己引入的 loading 短路（applyState("loading") 后 renderBody 直接渲染 loading，重渲前未切 success）——打点定位后修复；③openReviewForm 对注入后数据的双转义风险（esc 两遍显示失真，影响极小，登记不修）。

## ③ curl 实测证据（2026-09-06，GET/POST http://127.0.0.1:8000）

| # | 请求 | 实测响应摘要 |
|---|---|---|
| A | GET /api/series/1 | 200 壳内 series_name/description/categories[{category_name}]/min_price/max_price/cohort_count=2（详情渲染字段全部有真实来源） |
| B | GET /api/series/1/cohorts | 200 分页壳 total=2，items 含 cohort_name/sale_price/max_student_count/current_student_count/head_teacher_id/start_date（班次卡字段映射逐一对上） |
| C | GET /api/series/999999 | **HTTP 404** `{"code":"40400","message":"系列不存在或已下架"}` → 页面走诚实空态（场景2模拟断言通过） |
| D | POST /api/favorites `{"series_id":1,"favorite_source":"series_detail"}`（student token） | 200 `data.favorite_id=30010`；**重复 POST 幂等**返回同一记录 |
| E | DELETE /api/favorites/30010 | 200 `{"deleted":true}` 但**复查 GET 列表记录仍在 → 假删除**，故取消收藏不做假交互 |
| F | GET /api/study/courses/1/{access,outline}（student token） | 200；outline 的 session 字段名为 **session_id**（坐实 bindLearn 字段错配，已修） |
| G | GET /api/favorites（无 token） | 200 返回 user_id=1 数据——**DEBUG 虚拟管理员漏洞复现**（教训 6），前端 reviews/favorites 已按未登录降级设计，部署前 DEBUG=False 为硬要求（登记） |

**渲染链实证（node stub-DOM 四场景，替代被禁的 Playwright）**：
- 场景1 id=1 未登录：loading→真实渲染，h1="通用编程入门班·直播"、真实班次"202608期"、真实描述/分类标签、面包屑真名、mock 评价/大纲/班次零残留、无 `<></>` 垃圾、无误报空态；
- 场景2 id=999999：诚实"课程不存在"空态（回归确认任务 ③）；
- 场景3 id=1 登录态：同场景1 全绿 + 已收藏回显链路接通（stub 返回匹配记录）；
- 场景4 cohorts 接口失败：详情仍真实渲染，班次区/汇总/CTA 走"暂无可报名班次"守卫，无 mock 残留。
- 页内 4 个内联 script `node --check` 全部 SYNTAX_OK。

## ④ 批判承接核对

无承接项（tech-critique 未对 task04 登记承接条目）。

## ⑤ 自检三视角

- **交互态**：详情加载有 loading 骨架与文案；领券/评价/收藏均有 busy+disabled 防重复（reviewBusy/couponBusy/favBusy）；班次 RadioGroup 选择即联动价格汇总与 CTA。
- **边界**：坏 id/网络失败→诚实空态或错误态（不再误报"课程不存在"）；cohorts 失败/空→无班次守卫三处兜底；无 id→既有诚实空态回归通过；收藏分页外旧收藏可能漏判回显（登记）。
- **错误反馈**：下单/领券/评价/收藏失败均弹窗或行内展示后端原文 message；未登录操作按按钮语义跳登录并携带 redirect 原路返回。

## 遗留登记

- **3000 未运行**（实测 Connection refused，无监听进程；任务前提"3000 在运行"与实情不符）。改动全在 public/ 静态文件，服务直读盘、拉起即生效，未擅自启动服务（遵守禁重启纪律）。
- POST/DELETE /api/favorites 不在冻结 82 端点清单内，本次以 curl 实测（契约 authority 含"实测curl"）接入 POST，DELETE 因假删除未接入。
- 真实数据（series_name/cohort_name）经主脚本模板直出无 esc——XSS 面为管理端受信输入，与 courses.html 等存量页现状一致，统一收敛留 React 批次。
- GET /api/favorites 无 token 返回 user_id=1 数据系后端 DEBUG=true 虚拟管理员（教训 6），非本页缺陷；部署检查单必须含 DEBUG=False。
- 后端无学生端"班次课表"读取端点（详情页大纲 Tab 走诚实引导文案）；真实大纲在 learning 页经 /api/study/courses/{sid}/outline 呈现。
