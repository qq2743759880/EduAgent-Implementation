# task119 — learning 学习动线（/api/study/* 接入）

- 域：FE ｜ 平台：trae ｜ 波次：W3 ｜ 依赖：task101、task103（入口已建）；契约依赖 X1 修正（纯前端改路径，无后端变更）
- 文件：`learning.html`

## 目标
救活从未执行的 learning 注入，实现真实学习闭环：大纲 → 课次播放/资源 → 打点 → 完成态。

## 证据
- audit §X1：前端调 `GET /api/learning/sessions/{sid}`——后端**无此路由**，实际是 `GET /api/study/sessions/{id}`（domains/learning/router.py:50）；路径正则永不匹配致注入从不执行（L3191）。
- 可用契约：`GET /api/study/courses/{series_id}/outline`（StudyOutline：模块/课次/进度）、`GET /api/study/sessions/{session_id}`（资源过滤+transcode_status）、`POST /api/study/sessions/{session_id}/complete`、`POST /api/progress/video/tick-batch`（VideoTickBatchIn：play_session_id/session_id/ticks[]≤200）。
- audit §1.1：转码提示/演示控件为纯静态。

## 改动点
1. 取参改 `EAPI.pageId`：`learning.html?cohort_id=&session_id=`（task103 入口已传）；进入先按 cohort 取 series 再拉 outline 渲染侧栏大纲（模块→课次树 + watch_ratio 进度）。
2. 课次区接 `GET /api/study/sessions/{id}`：视频资源按 transcode_status 显示播放或"转码中"提示；作业/考试入口按资源类型显示。
3. 播放打点：video timeupdate 每 30s 攒 tick，`POST tick-batch` 批量上报（事件类型/position/rate 按 VideoTickBatchIn 实测）；页面卸载前 flush。
4. "标记完成"接 `POST complete`，完成后大纲树该课次打勾、watch_ratio 刷新。
5. 演示控件（假播放条等）在无 token 时保留演示态，有 token 时全部切换真实数据。

## GWT 验收
- Given 已报名 student（DB 有 enrollment），When 从课程详情"去学习"进入，Then 大纲渲染该班次真实模块/课次且当前课次高亮。
- When 播放视频 30s+，Then Network 可见 tick-batch 请求且 progress/dashboard 学习时长增长（对照 curl）。
- When 点"标记完成"，Then outline 该课次状态更新并持久（刷新后仍在）。
- 机验：`grep -c "api/learning/" learning.html` = 0；打点批量 ≤200 tick 断言。

## 风险
- 视频 URL 的访问鉴权（access 端点）若返回签名地址，前端不得缓存过期 URL——按响应实测处理；打点失败静默重试 ≤2 次后丢弃并 console.warn（不阻塞播放）。
