# task122 — 工程卫生包（前端）

- 域：FE ｜ 平台：trae ｜ 波次：W4 ｜ 依赖：各波次合入后收尾（避免与在途任务同文件冲突）
- 文件：全站 22 页散点清理

## 目标
O5 卫生达标：演示残留清零、错误可见、非法 HTML 修复——让站点从"演示态"干净过渡到"产品态"。

## 证据
- audit §P2：login-register.html:2904 演示控制器残留；chat.html respbar 演示状态条；admin-rag-upload.html:293 body class 属性重复 8 次；me.html×8/learning.html×4/login-register.html×4 残留 `import('/@vite/client')` HMR 脚本（生产 404）；courses.html 假封面（task103 已清）；全站 `catch(function(){})` 静默吞错。

## 改动点
1. 移除全部 HMR 残留模块脚本（grep `/@vite/client` = 0）。
2. 移除/条件化演示控制器与演示状态条（无 token 时的演示态**保留**——这是设计内的静默降级，只清"开发工具残留"）。
3. body 重复 class 属性合并为单个。
4. 错误可见性：页面级静默 catch 全部接 task101 的 onError → 统一 toast（3s 自动消失 + console.error），`grep -c "catch(function(){})"` = 0。
5. 演示数据兜底统一加"演示数据"角标（未登录可见区块），避免真实/演示混淆——与 AGENTS.md 教训④的静默降级策略不冲突（显式标注）。
6. 杂项：`<html lang>` 缺失补齐、重复 id 检查清零。

## GWT 验收
- 机验：`grep -rc "/@vite/client" *.html` 全 0；`grep -rc "catch(function(){})"` 全 0；`grep -c "class=.*class=" admin-rag-upload.html` = 0（脚本断言 body 标签单 class）。
- Given 后端停机，When 打开 dashboard/community 页，Then 出现 toast 错误提示而非无声失败；恢复后刷新正常。
- 渲染截图走查 22 页无布局崩坏（结构断言 + 视觉验收双轨）。

## 风险
- 移除 demo 绑定可能影响"未登录演示态"页面 → 回归口径：无 token 打开每页不报错且显示演示数据 + 角标。
