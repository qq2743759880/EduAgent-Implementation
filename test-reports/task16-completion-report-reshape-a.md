# task16 完成报告 —— 课件/作业/考试诚实降级占位（决策 D4：不留任何假按钮）

> 批次：reshape-a A 批 · 派单 prompt 硬性守则全遵守（只动资源入口范围/禁改后端与 contracts 与 edu-api.js/禁 MOCK/禁 alert 新增/禁 Playwright）
> 结论先行：**两页均无需处理（无代码改动）**——盘点实证：课件/作业/考试假入口在管理端原型的接线批已移除，学生端从未放置；视频入口真实且健康。D4「诚实降级、不留假按钮」在两页已处于满足态，按 task16 规则「若某页根本没放资源入口（可能只放了视频按钮），则无需加——如实报告」执行。

## 1. 盘点清单（grep + 读码核实，非凭注释）

### 学生端 edu-frontend/public/course-detail.html（1277 行）
| # | 资源入口/按钮 | 现状 | 判定 |
|---|---|---|---|
| 1 | 班次卡「去学习」（.go-learn，每班次一枚） | 真实：登录 → `GET /api/study/courses/{sid}/access` 鉴权 → `GET /api/study/courses/{sid}/outline` 取首课次 → 跳 learning.html（L672-704，task103 接线） | ✅ 视频入口真实，保持 |
| 2 | 课件入口 | **不存在**（`grep 课件/courseware/homework/exam/quiz/asset/资料/下载` 全零命中） | ✅ 无假按钮，无需处理 |
| 3 | 作业入口 | 不存在（同上） | ✅ |
| 4 | 考试入口 | 不存在（同上） | ✅ |
| 5 | 课程大纲 Tab | task04 已清 mock（MODULES 置空，L424-426），呈现诚实空态「课表暂未在此页展示」 | ✅ 无假数据 |
| 6 | 报名/领券/收藏/写评价 | 非资源入口（task04/05 域）：报名 `POST /api/trade/order`（Idempotency-Key）、领券 `POST /api/trade/coupon/receive`、收藏 `POST /api/favorites`、评价 GET/POST 全真实 | 不在本任务范围 |

### 管理端 edu-frontend/public/admin-course-detail.html（911 行）
| # | 资源入口 | 现状 | 判定 |
|---|---|---|---|
| 1 | 课次行「资源」列 `.res-4` | **现仅渲染一枚真实「▶ 视频」按钮**（L663：`<div class="res-4"><button class="video" data-vid=...>▶ 视频</button></div>`），打开视频面板走 `GET /api/admin/courses/sessions/{id}/assets` + 分片上传 4 端点（fe985a8 实测接线） | ✅ 视频入口真实，保持 |
| 2 | 课件/作业/考试按钮 | **当前代码未渲染**。原型（快照 test-reports/fe-html/admin-course-detail.html L453/470）曾有 4 入口且 3 枚无绑定假按钮；接线批 commit **fe985a8**（fix(reshape)/mcp+video+course-detail）已将其移除，仅保留真实视频 | ✅ 假按钮零存量，无需占位 |

### 后端端点实证（占位理由复核，防"误占位"）
- `edu-agent/app/domains/course_admin/router.py`：资源域仅 `GET /sessions/{session_id}/assets`（L209）+ 视频分片 4 端点（init-chunked L254 / finalize-chunked L276 / bind-session L284 / upload-chunk PUT）；**无课件/作业/考试的创建或挂载端点**。
- `session_repo.py` L80-81：session_exam / session_homework 等子表存在于删除防护名单，说明数据模型有位但路由层未开放 → 与页面注释「无 sessions/{id}/assets 活跃端点（对课件/作业/考试而言）」一致。
- contracts/reshape-a.json：endpoints 列表同样仅含视频域端点 → **前端加 disabled 占位按钮没有可指向的后端语义，保持现状即最诚实**（若加占位按钮反而与「只修不增」P2' 纪律冲突）。

## 2. 改动清单
- **代码：零改动**（两页 course-detail.html / admin-course-detail.html 均未动——无入口可降级，无需加占位）。
- 文档：本报告。

## 3. 资产消费证据
1. **dev-plan-reshape-a.md**：task16 GWT（点击显示"后端未实现·后续上线"诚实占位，不留假按钮；视频入口保持真实）+ P2'（A 批只修不增）+ P6（清单外只保不翻车）——本案 GWT 前件为空（无入口可点击），按"无需加"分支收口。
2. **contracts/reshape-a.json**（hash 30aeddbe）：endpoints 全量核对，课件/作业/考试域零端点 → 占位无契约依据。
3. **原型快照** test-reports/fe-html/admin-course-detail.html L451-471：证明原型曾有 3 枚无绑定假按钮（历史基线），与当前 L663 单视频按钮对照，演变由 git 历史 fe985a8 实证。
4. **后端源码** course_admin/router.py + session_repo.py（行号见上）：资源域端点面实证。
5. **真实 HTTP 探活（诚实登记环境限制）**：对 3000/8000 服务 curl 探活在本 agent 沙箱内全部连接拒绝（127.0.0.1/localhost/192.168.85.101 均试，netstat 无监听面；服务进程存在但网络不可达；遵禁令未重启）→ live 探活证据缺位，该限制不影响本任务结论：结论全部来自静态代码、git 历史与后端源码的确定性事实，非运行时采样；task18 检查单跑通后可一键补证。

## 4. 批判承接核对段
| 批判/决策 | 本任务落点 | 核对 |
|---|---|---|
| 决策 D4「诚实降级：不留任何假按钮」 | 盘点证明假按钮存量=0（管理端 3 枚已于 fe985a8 移除；学生端从未有）；拒绝"反向新增 disabled 占位按钮"（那是新 UI，违反 P2' 只修不增，且无后端契约语义） | ✅ D4 已满足态，不回退 |
| 技术批判「页面注释≠契约，实测为准」（教训 8 同源） | 管理页头注释写「资源 4 入口…占位提示」，实测 res-4 仅渲染视频按钮——以代码+git 历史为准记录，未沿注释臆断 | ✅ |
| 「占位样式复用 muted/disabled 类」约束 | 因零改动未触发；登记：若后续后端开放课件域端点，res-4 可复用 `.res-4 button` 体系扩展，禁新造样式 | ✅ 预留不预做 |

## 5. 三视角自检
- **Eng（工程）**：零代码改动 = 零回归面；结论链每一环（grep 零命中 / L663 单按钮 / fe985a8 历史 / 后端无端点）可独立复核，无"凭感觉"。遗留观察（不在本任务范围，登记不修）：学生端 course-detail 静态评价面板的 `onclick="alert(未登录…)"`（L549）是 task04 保留的降级底座，评价 Tab 点击即被 loadReviews 真实面板整体替换，仅在加载间隙理论可达——建议后续批判批收口，本任务不越资源入口边界。
- **Design（体验）**：学生端用户看不到任何指向不存在的课件/作业/考试 UI（无期望即无失望，诚实）；管理端管理员只看到可用的视频入口，不会有灰按钮暗示"即将可用"的错误预期（disabled 占位反而制造错误承诺）。
- **CEO（演示故事）**：演示动线"视频真实可播 + 课件/作业/考试不出现"完全成立；若演示官被问"课件在哪"，答案是后端确无该域端点（可指本报告 §后端实证），不踩"点了没反应"的翻车雷。

——task16 收口：无代码变更，仅本报告；后续 task17 报告另附。
