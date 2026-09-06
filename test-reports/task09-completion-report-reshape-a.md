# task09 完工报告（reshape-a 批次）：achievements.html 成就激励·清零演示数据全量真实接线

日期：2026-09-06 ｜ 执行：fe-html 接线 agent ｜ 计划：`.ai-hub/plans/dev-plan-reshape-a.md` A 批次 task09
GWT：Given 学生登录态；When 打开 /achievements.html；Then 徽章/积分/排行全走真实 gamification API，无 MOCK 行，空态诚实（新用户可能无徽章）。
commit：`28a5eab`（fix(reshape)/task09）

## ① 改动清单（edu-frontend/public/achievements.html，+224/−356）

**清零的 MOCK/演示痕迹（全量，共 7 类）**：
1. 排行榜 6 行演示数据（Adm02Test 12,850/小豆芽/勤奋小海豚/阳光学习员/早起鸟/持之以恒 + 我的排名"第 1 名 · 12,850 分"）→ 清空，由 `/api/gamification/rankings` 真实渲染；
2. 积分总览演示值（Lv.5 · 进阶学咖 / 2,330 分 / Lv.5→Lv.6 进度 33%）→ 清空，由 `/api/gamification/me/points` 渲染；
3. 积分流水 6 条演示流水（发布回帖+2/练习满分+10/徽章奖励+30/每日登录+5/学习时长−0/发布帖子+5）+ 硬编码分页器 → 清空，由 recent_logs + logs_total 驱动；
4. 徽章墙 8 张演示卡（社区之星/坚持到底/初学乍练/互动达人/满分学霸/连胜王者/社区贡献/时间管理）+ "已解锁 3/8" → 清空，由 `/api/gamification/me/badges` 渲染（已得/未得状态诚实）；
5. 演示控制器：body `data-st="ok" data-show=""` 全局演示态 + `[data-st=privacy]`/`body[data-show=empty-log]` 演示 CSS + 空的"演示控制绑定已随 respbar 一并移除"脚本块 + `.demo-note` 演示样式 → 全部移除，替换为**三区块独立状态机**（rank/points/badges 各自 data-st=loading/ok/empty/error）；
6. task122「演示数据」未登录角标脚本 → 移除，替换为**诚实登录引导卡**（隐藏三区块 + 登录 CTA，`EAPI.buildLoginUrl` 站内 redirect）；
7. 默认日榜高亮与脚本强制周榜不一致的闪烁 → HTML 直接默认周榜（与初始拉取口径一致）。

**接线增强**：错误态重试按钮按区块各自重查真实接口（原为死按钮）；`esc()` 对 user_name/badge_name/note 等后端文本做 HTML 转义；`next_milestone` 后端原文展示（去掉原正则 `replace(/^下一目标：/)`）；my_rank 不在 top 内时"我的积分"独立展示；source=ZSET 时隐藏"实时"角标（原演示恒显）；单页流水隐藏分页器；无任何 `alert(`/`.match(`。

## ② curl 实测证据（2026-09-06，真实 HTTP，字段以此为准非页面注释）

| 端点 | 实测关键字段（user000001） | 结论 |
|---|---|---|
| GET /api/gamification/me/badges | `{total:8, unlocked_count:3, next_milestone:"下一目标：📚 勤学苦练（进度 150/600，25%）", items:[{badge_code,badge_name,rarity:COMMON/RARE/EPIC,unlocked,unlocked_at,progress_current:150,progress_required:600,progress_pct:25.0,reward_points}]}` | 壳 data 直取 ✓；徽章/积分/排行均在 contracts/reshape-a.json 冻结清单（hash 30aeddbe）✓ |
| GET /api/gamification/me/points?page=1&page_size=10 | `{total_points:314→321(活库), level_no:1, level_title:"萌新", level_min:0, next_level_min:500, level_progress_pct:62.8, logs_total:15→17, recent_logs:[{point_type:BADGE_BONUS/COMMENT_CREATE/POST_CREATE, delta, balance_after, note, created_at}]}` | 分页壳 page=2 复验返回 7 条 ✓ |
| GET /api/gamification/rankings?scope=WEEKLY&dimension=POINTS&top_n=10 | `{scope, dimension, snapshot_date:"2026-09-06", top:[{rank_no,user_id,user_name,metric_value,level_no,is_myself,badge_count}], my_rank:{rank_no:2,...}, source:"ZSET"}` | **my_rank 不在 top 内**（top[0] metric 15 vs my 7）→ 页面独立展示我的排名 ✓ |
| 同上 ALL_TIME/STUDY_MIN | top 含 is_myself:true 行，metric_value=150 分钟 | 双维度真实切换 ✓ |

**独立实证（node DOM 桩 + 真实 3000 页面脚本 + 真实 8000 数据，无 Playwright）**：`verify_task09.mjs` 17 项断言全 PASS（期望值动态取自 API：徽章已得/未得渲染与进度、计数 3/8、积分 321、进度条 64.2%、流水首条 COMMENT_CREATE 余额 321、排行 top1 Adm02Test、我的排名第 2 名、快照日期、ZSET 角标隐藏、三区块 data-st=ok、分页显示、无 alert/match）；`verify_task09_notoken.mjs` 4 项全 PASS（loginGate 显示、三区块隐藏、redirect 站内、未登录零 API 调用）。页内 3 个内联 script `node --check` 全部 SYNTAX_OK；未重启 3000/8000。

## ③ 资产消费证据

- AGENTS.md 教训逐条对账：②禁 Playwright（用 node 桩+curl 独立实证）✓；⑧真实契约优先于页面注释（points 的 user_id/level_min/next_level_min、rankings 的 badge_count/level_no 均按 curl 实测补充）✓；⑨参数提取不走正则 match（scope/dimension 从 tab class 读取）✓；静态页注入模式保留（edu-api.js + IIFE + getToken 判断）✓。
- 读完 `.ai-hub/plans/dev-plan-reshape-a.md` task09 GWT；读完 `contracts/reshape-a.json`（gamification 3 端点在 verified_read_21 冻结清单，hash 30aeddbe 未动）；读完 `edu-frontend/public/edu-api.js` 头部注释（EAPI.get/store/buildLoginUrl 复用，未改）。
- 现状澄清：任务书说"4 处 EAPI 引用"，实际文件已含 task105 接线雏形（登录态覆盖渲染）——本任务按 GWT 补齐其未竟部分：演示兜底行/控制器清零、诚实空态、错误重试、转义，不重复造轮子。

## ④ 批判承接核对

- tech-critique/contract-review 未对 task09 登记专项承接条目；页面既有的 C4（respbar 演示工具条移除）、C7/C8（空态/错误态规范）在本任务收敛完成（原仅移除工具条但保留演示态 CSS 与兜底数据，本次彻底清零）。
- 诚实性承接 task03 先例（"mock 百分比属数据欺骗"）：排行/积分/徽章所有数值均来自真实 API，0 条流水显示诚实空态文案而非演示流水。

## ⑤ 自检三视角

- **交互态**：scope×dimension 8 组合点击即真实重查（loading 骨架过渡）；流水分页真实 page 重查（17 条→2 页，第 2 页 7 条实测）；错误态三区块独立重试；tab 切换失败不串区块状态。
- **边界**：新用户无徽章 → empty 态"还没有徽章"；某榜无数据 → empty 态"该榜暂无数据"；无流水 → 行内诚实空态+分页隐藏；my_rank=null → "未上榜"；满级（next_level_min 缺失）→ "🏆 已达最高等级"；未登录 → 登录引导且零 API 调用（防 DEBUG 虚拟管理员数据误读，教训⑥）。
- **错误反馈**：非 2xx/壳错误由 EAPI 抛错 → 区块 error 态 + 重试按钮 + `[EAPI]` console.error；所有后端文本经 esc() 转义防注入；不虚构任何数值。

## 遗留登记（不改视觉，按守则只登记）

- 徽章分类 tab（学习/成就/社交）为副标题文案，非筛选器；items 已含 category 字段，若后续要做分类筛选属新增交互（P6' 出原型审批），本任务未动。
- 排行"我的排名"行不在 top 列表内时用户无法看到自己在榜内的行——与后端 ZSET 契约一致（my_rank 独立返回），已诚实展示独立排名条。
