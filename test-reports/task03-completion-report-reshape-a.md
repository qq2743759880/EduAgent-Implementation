# task03 完工报告（reshape-a 批次）：courses.html 课程中心全量接线·回归加固

日期：2026-09-06 ｜ 执行：fe-html 接线 agent ｜ 计划：`.ai-hub/plans/dev-plan-reshape-a.md` A 批次 task03
GWT：Given 真实课程库；When 筛选/排序/搜索防抖/分页；Then 全走真实 `/api/series` 参数，空态诚实。
（注：`test-reports/task03-completion-report.md` 为历史批次同名报告，与本批无关，故加 `-reshape-a` 后缀）

## ① 改动文件 + 行数

- `edu-frontend/public/courses.html`：+5 / −5（git 9767a28）
  1. `coverClass(id)`：`i%5` 改非负模 `((i%5)+5)%5`（t/p 两处）——修复末页小 id（实测 id=1/2/3）负索引产生 `cover--undefined` 封面丢样式；
  2. 删除 `const pct=(s.id*7)%100` 假进度及 meta 行中的假进度环 span（真实列表接口无进度字段，mock 百分比属数据欺骗）；
  3. XP 徽章改条件渲染：`s.xp!=null` 才渲染（真实 items 无 xp 字段，原恒渲染"+0 XP"假数据）。

## ② 资产消费证据

- 读完 AGENTS.md（教训 2 禁 Playwright 用 curl、教训 8 真实契约优先、教训 9 禁 match 取参——本页取参全部走 URLSearchParams/buildQuery，无违反点）。
- 读完 `.ai-hub/plans/dev-plan-reshape-a.md` task03 GWT；读完 `contracts/reshape-a.json`（GET /api/series 在冻结清单，hash 30aeddbe，未改契约）；读完 `edu-frontend/public/edu-api.js` 头部注释（EAPI.get/pageId）。
- **开工现状澄清**：任务书说"仅 2 处 EAPI 调用、筛选器是死的"，实际文件已是 task103 接真版本（fetchPage+buildQuery 走真实 `/api/series`）。本任务转为**逐参数独立实证 + 缺陷修复**，不重复接线。
- **自检发现并修掉**（3 处，见①）：封面负索引丢样式（末页必现）、"+0 XP"假徽章、`(id*7)%100` 假进度环。

## ③ curl 实测证据（GET http://127.0.0.1:8000/api/series，逐参数验证真实生效，非凭页面注释）

| 查询参数 | 实测 total / 首条 | 结论 |
|---|---|---|
| （基准）page=1&page_size=5 | 2628 / 信息学竞赛入门班·录播 | 分页壳 {total,page,page_size,items} ✓ |
| category=数学 | 216 / 高中数学专题突破班·面授 | 一级学科生效 ✓ |
| category=概率与统计方法 | 36 / 概率统计进阶班·录播 | 二级方向共享 category 参数生效 ✓ |
| delivery_mode=online_live | 1296 / 首条为直播 | 交付筛选生效 ✓ |
| keyword=信息学 | 12 | 搜索生效 ✓（页面 400ms 防抖后发真实请求） |
| price_min=2000 / price_max=2000 | 1716 / 912 | 价格区间生效 ✓ |
| sort=newest / price_asc / price_desc | 首条各不相同 | 排序生效 ✓ |
| keyword=zzzz不存在zzzz | total=0, items=[] | 空态诚实分支可触发（renderSuccess 空分支→"没有符合条件的课程"+重置按钮）✓ |
| 第 176 页（末页） | items ids=[3,2,1] | **坐实 coverClass 负索引缺陷**（已修）；sale_status 全为 on_sale（两页抽检），副标题"仅 on_sale"诚实 |

- 空态/卡片跳转：卡片 `href="course-detail.html?id=${s.id}"`，纯 href 无 JS 取参，无 match 正则。
- 页内 5 个内联 script `node --check` 全部 SYNTAX_OK；未重启 3000/8000。

## ④ 批判承接核对

无承接项（tech-critique 未对 task03 登记承接条目）。

## ⑤ 自检三视角

- **交互态**：chips/select/搜索防抖/翻页全部即时触发真实查询；查询中骨架屏+spin；查询失败 error 态+重试按钮（走 fetchPage 真实重查），EAPI 全局 toast 兜底。
- **边界**：末页小 id 封面样式（已修非负模）；cover_url 为 cdn.example.com 假域名时按既有 coverSrc 规则降级色块不破图；total=0 空态含"查看全部课程"复位出口。
- **错误反馈**：网络/接口错误有页面 error 态+EAPI 默认 toast，空结果文案区分"无匹配"与"该学科即将上线"，不虚构数据。

## 遗留登记（不改视觉，按守则只登记）

- Hero 区"连续打卡 7 天/Lv.5/1280 XP"与 xpFill 62% 动画为学中玩风格静态装饰（用户签收的视觉基准，P2 冻结），非课程数据接口，未动；若后续要求真实打卡/XP 数据，应接 `/api/progress/dashboard`+gamification 域（属 React 批次范围）。
- `.ring`/`.xp-badge` CSS 保留（视觉冻结），仅不再用假数据渲染。
