# TO-EXEC-FIX-CMTINPUT — community-post 评论框一类之修（编排者已裁：批准修复）

## 背景（GATE-V2 全站终验唯一余红，25/275 唯一 FAIL）

`edu-frontend/public/community-post.html:349` 的 `#cmtInput` 未挂 `clay-input` class，placeholder 吃 UA 默认灰，对比度 4.37:1 < 4.5。GATE-V2 执行者按铁律停手上报，编排者裁定：**批准修复**（预计一个 class 之修）。

## 工作项

1. 实读 community-post.html:349 附近 `#cmtInput` 元素与页内其它输入框的 class 用法；为 `#cmtInput` 补挂 `clay-input`（若元素已有功能类，**只追加不替换**；确认不破坏 JS 选择器——`docs/dom-hooks-frozen.md` 该页节先核对 id/class 依赖）
2. 复验：`node scripts/gates/viewport-a11y-gate.mjs --page http://127.0.0.1:3322/community-post.html`（带运行时 token）→ contrast 全绿；顺跑 G6/G9 单页确认零回归；G3 全站 `--all --check` 确认钩子零漂移
3. 若 clay-input 挂上后布局异常（输入框几何变化触发 G6 route/交互红），停手上报，勿另造样式

## 铁律

只许改 `edu-frontend/public/community-post.html` 这一个文件的一处 class（+必要时该页 `.page-` 私有修正层，禁改 theme.css）；不 push；单 commit：`fix(fe)/community-post: #cmtInput 补挂 clay-input(G7 contrast 唯一余红清零)`；报告 `REPORT-FIX-CMTINPUT.md`（修复前后 G7 输出对比+G3 全站绿证据）。3322 需 dev 态在跑，token 走 `EDU_GATE_TOKEN` 运行时环境变量禁落盘。
