# task103 — 课程动线打通（列表→详情→班次→学习入口）

- 域：FE ｜ 平台：trae ｜ 波次：W0 ｜ 依赖：task101（EAPI.pageId）；分页部分契约依赖 C-B（未冻结前先读 page_meta 兼容）
- 文件：`courses.html`、`course-detail.html`、`learning.html`（仅加入口，learning 完整接入归 task119）

## 目标
修复"课程列表→详情动线完全断裂"这一最严重的体验断点：卡片可点、详情页 id 正确、班次可见、有去学习入口。

## 证据
- audit §1.2-1：courses.html:583 课程卡 role=button 无 href 无 click；course-detail.html:748-749 id 恒回退 "1001"；learning.html 全站 0 入口。
- audit §X4：课程域分页壳 `{items,page_meta}` 与全站不同（过渡期按 page_meta 读 total/has_more）。
- audit §1.3-16：封面假域名 `cdn.example.com` 必 404；假分页 L639 翻页内容不变。

## 改动点
1. courses.html 课程卡改为可点（整体 click 或包一层 `<a>`），跳 `course-detail.html?id=${series_id}`；卡片补真实封面占位（后端无封面字段时用首字母色块，**禁止外网假域名**）。
2. course-detail.html 用 `EAPI.pageId("id")` 取参调 `GET /api/series/{id}` + `/cohorts`；Tabs 区块字段按 `SeriesDetail` schema 对齐（min_price/max_price/categories/cohort_count）。
3. 班次卡加"去学习"按钮：有 token 时先调 `GET /api/study/courses/{series_id}/access` 判权，通过跳 `learning.html?cohort_id=&session_id=`（首课次从 outline 取），未通过提示去报名（my-cohorts 空态一致）。
4. 分页接真：按 page_meta.total 渲染页码，翻页真实请求 `?page=n`。

## GWT 验收
- Given student token 与真实系列数据（DB 实证至少 3 个系列），When 从 courses.html 点击任一卡片，Then 详情页展示**该系列**名称/价格区间/班次列表（URL id 与渲染名一致，非 1001）。
- When 点击班次"去学习"，Then 已报名者进 learning 页；未报名者出现报名引导且不报未捕获错误。
- When 翻到第 2 页，Then Network 发出 `page=2` 且渲染内容变化；页码总数 = page_meta.total/page_size 向上取整。
- 机验：`grep -c "cdn.example.com" courses.html` = 0；全站无指向 `/admin/courses/`、`/learning/` 路径式死链（task110 复扫）。

## 风险
- 若 C-B 分页统一在后完成，此处 page_meta 读法需回归调整一次（已列入 C-B 解锁后回归清单）。
