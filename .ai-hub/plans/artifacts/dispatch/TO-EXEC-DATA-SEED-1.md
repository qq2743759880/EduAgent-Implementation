# TO-EXEC-DATA-SEED-1 — 种子数据外链占位本地化（favorites 封面 ×5 + me 头像 ×1）

## 背景与裁定（编排者验收 PACK-A 时批）

种子数据的 `cover_url`/`avatar_url` 指向不可达的 `cdn.example.com`，前端 `<img>` 渲染裂图（G8 local-assets 依赖数据面，前端行为层禁碰不能修）——**数据修正**，走 DB 变更三核闸。

## 工作项

1. 只读盘点：`SELECT id,cover_url FROM course_series WHERE cover_url LIKE '%cdn.example.com%'`（表/列名以实读 schema 为准）+ 用户头像同查；确认影响行数（预估 5+1）
2. 本地占位资源：用 theme.css 色系（moss/sky/peach 等表面色）生成 6 张 SVG 占位图落 `edu-frontend/public/assets/seed/`（封面 800×450、头像 200×200，含课程名文字），或复用仓库已有合规图片
3. **DB 变更三核闸（铁律，缺一不可）**：
   - 闸① 备份：变更前 `SELECT ... INTO OUTFILE` 或 mysqldump 相关行落 `deploy/backups/seed-<date>/`，行数留档
   - 闸② 变更：UPDATE 仅限受影响行（WHERE id IN (...) 精确清单），UPDATE 后行数与备份一致断言
   - 闸③ 幂等：同脚本重跑零变化（WHERE 已带新值条件）+ 前端复验：GET /api/favorites 的 cover_url 均为本地路径 + G8 单页跑 favorites/me 绿
4. 禁直写原则例外说明：本单是**数据订正**不是业务写——仍禁绕过 service 直插新业务行；UPDATE 既有种子行属数据订正，走三核闸即为合规通道

## 铁律

禁 push；单 commit：`fix(data)/DATA-SEED-1: 种子外链占位本地化(三核闸:备份+行数一致+幂等)`；报告 `REPORT-DATA-SEED-1.md`（备份路径/影响行数/前后对照/幂等证明/复验输出）。
