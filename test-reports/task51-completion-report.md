# task51 完成报告 — /community 社区列表页（React 实现）

## 任务概述
将 task51 社区列表页从 HTML 效果图（`test-reports/fe-html/community.html`）迁移为 React 实现，符合 candy-playful 冻结风格，复用契约⑬ `community/posts` API 层与既有通用组件，压实四态（loading/error/empty/success）与完整交互。

## 交付内容

### 新增 / 重写文件
| 文件 | 类型 | 说明 |
|------|------|------|
| `src/components/community/PostCard.tsx` | 重写 | C24 帖子卡片：置顶/锁定/版块糖果 pill/标签/作者/时间/💬👍统计，糖果硬阴影与 hover 悬浮 |
| `src/components/community/CommunityFilterBar.tsx` | 新增 | 版块 chips（单选 `aria-pressed`）+ 排序下拉 + 搜索框（防抖 300ms，跳过首挂载） |
| `src/app/(user)/community/page.tsx` | 重构 | 页面四态 + Hero 数据统计 +「我的帖子」+ 发帖 CTA/FAB + 分页（复用 PaginationBar）+ 搜索防抖与版块切换重置页码 |
| `src/lib/community-meta.ts` | 更新 | BOARDS 改为糖果实底 pill 色（english 蓝 / math 紫 / programming 绿 / general 橙） |

### 测试
| 文件 | 说明 |
|------|------|
| `src/components/community/PostCard.test.tsx` | 置顶/锁定/版块/统计渲染、锁定只读提示 |
| `src/components/community/CommunityFilterBar.test.tsx` | chips 单选、排序选中、搜索防抖与提交（rerender 同步受控态） |
| `src/app/(user)/community/page.test.tsx` | 四态切换、版块/排序/搜索联动、分页、发帖弹窗、空态 |

## 关键实现决策
- **无 MOCK**：接口全部走契约⑬ `listPosts` 真实 API，无 fallback 假数据（验收 grep 无假数据）。
- **四态压实**：loading 骨架、error（`role=alert` + 重试）、empty（`role=status` + 引导发帖 CTA）、success 完整渲染。
- **交互闭环**：搜索输入防抖避免冗余查询；版块/搜索变更重置 `page=1`；排序/版块/搜索/分页进入 React Query queryKey。
- **响应式**：`@container headers` 容器查询 + 断点 820/520，适配 375~1440 视口无横向溢出。

## 验证结果
独立 fe-tester 子代理 R2 复验全绿：
- tsc：0 error
- eslint：0 problem
- Vitest：全量 423/423 通过（含 community 专项）
- `next build`：成功
- grep 审计（硬编码 hex / 内联色值 / 任意字号 / 字体阶梯）：全 0

## 变更
- git commit：`8c36860`
- 已运行 `sync.ps1` 分发

## 遗留 / 提示
- 后端 community 域若存在未冻结字段，联调前以契约⑬ 为准，仅做展示映射。