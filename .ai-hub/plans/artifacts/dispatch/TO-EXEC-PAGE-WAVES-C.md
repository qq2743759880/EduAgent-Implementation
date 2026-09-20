# TO-EXEC-PAGE-WAVES-C — 逐页重塑包 C：管理端 10 页（批款=全黏土 C）

## 使命（1 天工期主干，Gate A 已批款+底座已验收）

按已批款风格（黏土拟物；**admin 黏土浓度=C 全黏土**——用户裁定覆盖 clay-light 预案）重塑 10 个管理页。**每页独立 commit**，每页门禁全绿才算完成。

## 你的页面（只许碰这 10 个文件）

`edu-frontend/public/` 下：admin-dashboard / admin-courses / admin-course-detail / admin-questions / admin-question-detail / admin-users / admin-users-refine-proto / admin-courses-recycle-proto / admin-mcp / admin-rag-upload（.html）

## 必读资产（开工前实读）

同 PACK-A 清单（方案 §3.1 黑名单+Gate A 批款块、theme.css 令牌冻结、dom-hooks-frozen.md 你 10 页节、icon-inventory.md、rollback-drill.md），另加：

- `edu-frontend/_prototypes/clay-gatea/admin-c.html` —— 风格基准（批款款 C）
- **全黏土下的可读性红线**：G7/G9 是唯一裁判——若某数据表格全黏土后出现对比度/溢出红且页内修正层救不回，按 theme.css 已备的 `clay-light` 降级类降该区块（不是降整页），并在报告逐条记录降级点；救不回且 clay-light 也红的 → 停手上报，勿硬凑
- **图表/富文本容器**（若你页有）按方案 §7.5：容器底色继承令牌、调色盘映射六表面色+coral、禁默认蓝紫

## 管理端门禁特别说明

- 管理页基线采集需运行时授权（G7/G9 网络态注入）：`$env:EDU_GATE_TOKEN`/`EDU_GATE_REFRESH_TOKEN` **只在当前 shell 内存提供，禁写入任何文件/日志/报告**；编排者验收时会用 admin 账号自取
- 管理端 admin 守卫三段（无 token 跳登录→auth/me 校验角色→失败跳登录）属行为层，**禁动**

## 每页工序

同 PACK-A 六步（接入 `theme.css?v=7fed87f` 统一版本 → emoji 换 sprite → 清 G6/G7/G9 存量债（admin-users-refine-proto 长文本适配是登记债）→ 六门全跑 → 单页 commit `style(fe)/<page>: clay 重塑+门禁绿(PACK-C)`）。

## 铁律

同 PACK-A 全部条款。报告写 `REPORT-PAGE-WAVES-C.md`（同 PACK-A 结构，另加 clay-light 降级点清单若有）。
