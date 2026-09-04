<!-- 镜像登记：权威 tracker 在 .opencode/plans/critique-backlog-tracker.md，本文件为 review-gate 机验镜像 -->
| # | 批判（来源） | 级别 | 修复措施 | 落点任务 | 验收指标 | 状态 |
|---|---|---|---|---|---|---|
| C-15 | W1批判1 401静默刷新缺失（taskW1-技术批判.md） | P2 | edu-api.js single-flight refresh+重放1次 | task122 | 过期场景跳登录率→0 | DONE(203a1e5) |
| C-16 | W1批判2 守卫8份拷贝（taskW1-技术批判.md） | P2 | 抽edu-guard.js单点化 | task122 | 内联grep=0,引用=8 | DONE(203a1e5) |
| C-17 | W1批判3 死链扫描未门禁（taskW1-技术批判.md） | P3 | 挂task123检查单+L4回归 | task123 | 里程碑跑通0死链 | DONE(123框架承接) |
| C-18 | W1批判4 注册两步式（taskW1-技术批判.md） | P3 | C-A评估register返回token | task114讨论项 | 采纳则curl含token | DONE(d48735f 注册即登录) |
