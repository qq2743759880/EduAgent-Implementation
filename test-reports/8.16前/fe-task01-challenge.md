# 对抗性测试报告 fe-task01

## 第 1 次测试

### 判定：FAIL（一般 3 + 轻微 8；契约零漂移，无 BLOCKER）

- 测试时间：2026-08-13
- 测试方式：前端源码对抗审查 + 契约字段比对（后端 8000 未运行，以 edu-agent 源码 schema 为准）
- 落盘说明：本报告由主编排器依据 sd-challenger 会话完成的分析结论落盘（challenger 输出目录权限被拒，分析已 100% 完成）

---

### 问题清单

| # | 维度 | 严重度 | 位置 | 质疑 | 建议 |
|---|------|--------|------|------|------|
| 1 | 安全（self-XSS 面） | 一般 | PostEditor 预览内核 `@uiw/react-markdown-preview` 默认启用 `rehypeRaw`（node_modules 依赖实证；src/common.tsx:18 引入） | 帖子预览渲染作者自输入内容时允许 raw HTML 注入，构成 self-XSS 可利用面；旧报告「XSS 已防御」结论不完整（react-markdown 默认不渲染 raw HTML，但预览组件开启 rehypeRaw 后例外） | 预览与最终渲染统一走无 rehypeRaw 的配置；或显式关闭 rehypeRaw 并加白名单 |
| 2 | 错误处理（R-7 半达成） | 一般 | `src/lib/query-client.ts:8-24`（globalOnError） | 写操作失败仅 toast.error，无 console.error；红线要求「写操作失败必须 toast + console.error」——全局兜底层缺 console.error 分支 | globalOnError 补 console.error(error)；各 useMutation onError 保持双通道 |
| 3 | 功能（分页盲区） | 一般 | `src/components/community/CommentSection.tsx:47` | 回帖列表固定请求第 1 页 20 条，无分页 UI，>20 条评论不可达 | 补加载更多/分页控件（对齐后端分页契约） |
| 4 | 状态（错误态） | 轻微 | 积分/点数卡片 | 后端错误时积分显示 0，无错误占位区分「未加载」与「真实为 0」 | 区分 loading/error/empty 三态 |
| 5 | 文案 | 轻微 | 徽章/等级区 | 满级（next_milestone=null）文案矛盾（「下一里程碑」指向空） | 满级时显示「已满级」 |
| 6 | 硬编码 | 轻微 | achievements 页 | 「8 枚徽章」硬编码数量，后端新增徽章后漂移 | 用 unlocked_count/total 字段 |
| 7 | 错误处理 | 轻微 | 积分联动失败分支 | 后端积分联动异常被吞（无 toast/console.error） | 补错误透出 |
| 8 | 查询 | 轻微 | keyword 搜索 | 通配符 %/_ 未转义，LIKE 语义可能超集命中 | 转义 %/_ |
| 9 | 死分支 | 轻微 | rankings source 文案 | 「source」死分支文案存在 | 清理 |
| 10 | 风格 | 轻微 | 社区/成就多色 | 分功能多色（fe-task07 范围） | 归 fe-task07 收敛 |
| 11 | 文案 | 轻微 | 详情页 403 | 403 文案与「无权限」混用，语义混淆 | 明确文案 |

---

### 契约字段比对（前端 TS 类型 vs 后端 schema）

10 组逐字段比对 **零漂移**；`sort`/`board_code`/`scope`/`dimension`/`top_n`/`page_size` 枚举与后端 pattern 全一致；401/403/错误壳三线齐备（api-client.ts axios 拦截器 + 组件层 + toast 层）。

| 契约组 | 前端文件 | 后端 schema | 结论 |
|--------|---------|-------------|------|
| posts 列表/分页 | src/lib/api/community.ts | edu-agent/app/community/schemas.py | √ |
| 发帖 POST | 同上 | community/schemas.py | √ |
| 点赞/收藏/回帖 | 同上 | community/schemas.py | √ |
| badges | src/lib/api/community.ts | edu-agent/app/gamification/schemas.py | √ |
| points 流水 | 同上 | gamification/schemas.py | √ |
| rankings | 同上 | gamification/schemas.py | √ |

### 薄弱点核查（design-guide §7 相关项）

| # | 薄弱点 | 防御证据 file:line | 结论 |
|---|--------|-------------------|------|
| 1 | 静默吞错（R-7） | community.ts 写操作全部上抛 ApiError + 调用方 toast；但全局兜底缺 console.error（问题 #2） | 半达成 |
| 2 | 契约漂移 | 10 组零漂移 | 已防御 |

---

### 结论

无 BLOCKER。3 项一般问题（rehypeRaw / globalOnError console.error / 评论分页）与 8 项轻微问题进入修正环；契约零漂移，错误壳三线齐备，越权由后端 require_role 权威兜底。问题 #2（query-client.ts）与 #10（风格）跨 task，分别归 fe-task00 / fe-task07 处置。
