# task99: 批量 auth 补生成（100K 用户登录可用）

> **类型**：ops/data ｜**执行工具**：Trae ｜**阶段**：P3（与 task10~15 并行）｜**工作量**：S
> **前置**：task07（数据冻结）+ task08（auth 现状确认）
> **来源**：task08-技术批判.md 批判②（P2）
> **性质**：数据补漏任务——不改生成脚本（避免重灌破坏冻结基线），对现有冻结数据补 auth

## 1. 问题背景（实证）

- `sys_user_auth` 仅 200 条（188 注册 + 3 测试账号 + 少量），`sys_user` 100003 条
- 生成脚本 layer1~4 只写 sys_user 不写 sys_user_auth（edu-data 源码确认）
- 影响：10 万生成用户无法登录 → 登录态功能/压测/E2E 无法用全量用户

## 2. 交付物

```
scripts/backfill_auth.py
├── 批量生成 sys_user_auth（bcrypt 预哈希，复用 restore_admin.py 哈希逻辑）
├── 参数：--limit N（默认 1000，可全量 --limit 100000）/ --role student
├── 账号策略：account + 默认密码（如 Test@123456）→ 写入 password_hash
├── 幂等：已存在的 user_id 跳过（INSERT IGNORE / ON DUPLICATE KEY）
└── 验证：抽样 10 个新 auth 登录成功（复用 task08 登录验证）
```

## 3. 实现规划要点

- 密码策略遵循项目约定：8+ 字符、大小写+数字+特殊字符（tech-source-audit + task00 安全约束）
- bcrypt 哈希（与 restore_admin.py 一致，禁止明文）
- 写入批次 5000/批（对齐 full 档批量参数）
- **不修改** edu-data 生成脚本（避免重灌）；若未来重灌 full 档需登录用户，则另行评估在 layer1 补写

## 4. 验收标准（Given/When/Then）

- Given 脚本执行，When 抽样 10 个新账号登录，Then 全部 200 + JWT role=student（GWT ①）
- Given 重复执行脚本，When 再次运行，Then 幂等（auth 记录数不翻倍、无唯一键冲突）（GWT ②）
- Given 全量执行（--limit 100000），When 统计，Then sys_user_auth ≈ sys_user 数量级一致（GWT ③）
- Given 未破坏冻结数据，When 重跑 verify_schema.py，Then 0 差异（回归 GWT ④）

## 5. 交接与记忆

- 完成 → 看板 task99=DONE → sync.ps1
- 注意：账号密码（默认 Test@123456 或自定义）必须写入报告，供 E2E/压测使用
