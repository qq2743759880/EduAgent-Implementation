# TO-EXEC-MIMOSA-EXCL — Mimosa 门禁排除（用户 2026-09-21 批准）+ 待提交收口

## 任务

1. **定位 Mimosa git 提交门禁的排除机制**并配置以下两个文件进排除（先例：edu-agent/scripts/eval/** 的排除此前已由 agent 配置成功——找到当时的机制，同法扩充）：
   - `edu-frontend/src/components/auth/login-redirect.test.tsx`
   - `edu-frontend/src/lib/auth-client.test.ts`
   - 排除理由（写进配置注释）：两文件为单元测试，其中的凭据字面量 = AGENTS.md 公开登记的演示测试账号（user000001/adm02test + Test@123456），非真实密钥；用户 2026-09-21 明确批准排除
2. **验证排除生效**：排除配置后提交一笔文档 commit 应不再被 8 条「硬编码凭据」high 拦截（此前 `git commit -m "docs(agents)/fe-start-fix..."` 被拦）
3. ~~代提交积压文档~~（已由编排者在兼容窗口提交：AGENTS.md=8ab75fb、PACK-C 报告已随 0b93932 入库——本项已完成，跳过）：
   - `AGENTS.md`（工作区已有未提交修改：前端启动命令勘误，`git diff AGENTS.md` 可见）
   - `.ai-hub/plans/artifacts/dispatch/REPORT-PAGE-WAVES-C.md`（未跟踪新文件，`git add` 即可）
   - 提交信息：`docs(agents)/fe-start-fix: 前端启动命令纠正(next dev 旧写法已废→node_modules 生产 start+.next-prod)+PACK-C 报告入库`
4. 若发现排除机制根本不存在（scripts/eval 先例另有机理），如实上报你的发现与建议方案，勿发明新安全策略

## 铁律

只动 Mimosa 配置面 + 上述两个文档文件的提交；**禁改任何业务代码/测试内容本身**（凭据改 env 化是另一个潜在任务，不在本单）；不 push；报告 `.ai-hub/plans/artifacts/dispatch/REPORT-MIMOSA-EXCL.md`（写明机制路径、配置 diff、提交是否通过、`git log -1` 证据）。
