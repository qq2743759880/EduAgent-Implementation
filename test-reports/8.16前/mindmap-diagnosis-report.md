# 思维导图 Tab 视觉诊断报告（fe-visual-auditor）

- 日期：2026-08-14
- 目标页面：`http://localhost:3000/courses/1` →「思维导图」Tab
- 审查方式：后端 API 实测 + 前端代码对照 + Playwright 真实浏览器（chromium, 1280×800）
- 结论先行：**图谱渲染正常（canvas 非空、节点/边均绘制、无 console 错误），但「边」的关系类型与样式因字段不匹配而丢失 —— 与怀疑一致，FAIL**

---

## 1. 环境

- dev server：http://localhost:3000（Next.js 16 + Turbopack，`next dev`，本地已起未重启）
- 后端：http://127.0.0.1:8000（admin / Admin@12345）
- 实测账号：admin 登录成功
- 截图目录：`test-reports/screenshots/`
  - `test-reports/screenshots/diagnose-mindmap.png`（图谱渲染全貌）
  - `test-reports/screenshots/diagnose-mindmap-login-blocked.png`（dev server 跨域拦截时登录页卡死证据）

### 环境备注（不属业务 bug，但影响调试入口）
- 直接访问 `http://127.0.0.1:3000`（IP 形式）时，Next dev 会拦截 `_next/static/chunks/*` 请求：
  `⚠ Blocked cross-origin request to Next.js dev resource /_next/static/chunks/... from "127.0.0.1"`（见 edu-frontend/next-dev-orch.log）
  → 前端 JS 无法加载，登录页卡在「跳转中…」。
- 改用 `http://localhost:3000`（hostname 形式）后一切正常，本次实机验证均基于 localhost。

---

## 2. 数据与代码对照（根因）

### 2.1 后端实际返回（API 实测 `/api/mindmap/course/1`，无认证）
```json
"links": [
  {"source": "SER-EN-PHON", "target": "MOD-EN-PHON-VOWEL", "rel_type": "CONTAINS",
   "line_style": {"color": "#5B8FF9", "type": "solid", "width": 1.2}},
  {"source": "KP-EN-VOWEL-SINGLE", "target": "KP-EN-VOWEL-DOUBLE", "rel_type": "PREREQUISITE",
   "line_style": {"color": "#F6BD16", "type": "solid", "width": 2.0, "curveness": 0.2}}
]
```
- 课程 1 共 11 条边：7 条 `CONTAINS`（蓝 #5B8FF9 solid）、4 条 `PREREQUISITE`（琥珀 #F6BD16）
- 字段名：**snake_case** `rel_type` / `line_style`（edu-agent/app/mindmap/schemas.py MindMapLink）

### 2.2 前端读取字段（edu-frontend/src/components/curriculum/CourseMindmapView.tsx）
- L132 `relation: l.relation`
- L133 `lineStyle: l.lineStyle ?? {...}`
- L135-137 兜底：`color: l.relation === "PREREQUISITE" ? CHART_COLORS.warning : CHART_COLORS.muted, type: l.relation === "PREREQUISITE" ? "dashed" : "solid"`
- L77 tooltip：`关系：${p.data.relation ?? "关联"}`
- API 层（src/lib/api/curriculum.ts L267-270）**直接透传后端响应，无字段转换**

### 2.3 结论（代码级）
`l.relation` / `l.lineStyle` 恒为 `undefined` →
- 边 tooltip 恒显示 fallback「关联」（关系类型全部丢失）
- 边样式恒走兜底且因 `l.relation === "PREREQUISITE"` 恒 false → **全部 muted 灰实线**（PREREQUISITE 的 amber 语义丢失；后端给的 line_style 也完全未被使用）

---

## 3. Playwright 实机证据（1280×800，headless chromium）

| 检查项 | 结果 |
|--------|------|
| a. 图谱渲染 | ✅ canvas 582×440，非空（opaque 像素 17,932 / 256,080），节点 + 边均绘制 |
| b. 边 tooltip 关系类型 | ❌ 扫到 PREREQUISITE 边 tooltip：`KP-EN-CON-FRIC → KP-EN-CON-NASAL 关系：关联`（应为「先修」） |
| c. 边样式颜色 | ❌ 像素统计 amber=0（无 #f59e0b/#F6BD16 琥珀像素），gray≈2800（slate-400 #94a3b8 灰边存在）→ 边统一灰色实线，PREREQUISITE amber 丢失 |
| d. 控制台错误 | ✅ 0 errors / 0 page errors（业务页面无报错；初始 403 属 dev server 跨域拦截，hostname 修复后消失） |
| e. 截图 | ✅ `test-reports/screenshots/diagnose-mindmap.png` |
| 附：节点 tooltip | ✅ 正常（`英语音标入门（元音+辅音）类型：系列课程状态：未开始`）—— 仅边字段不匹配 |

补充：tooltip 触发方式说明——Playwright `mouse.move` 未能触发 ECharts 6 tooltip（事件通道差异），改用向 canvas 派发合成 `MouseEvent('mousemove')` 后正常命中节点/边 tooltip；文本证据可靠。

---

## 4. 发现分类

### [规格违背]（必须修正）
- `edu-frontend/src/components/curriculum/CourseMindmapView.tsx:132-138` — 边字段读 `l.relation` / `l.lineStyle`，后端实际返回 `rel_type` / `line_style`（edu-agent/app/mindmap/schemas.py:24-29），API 层未转换 — 期望：关系类型与样式正确呈现（tooltip 显示「先修/包含」、PREREQUISITE 边 amber 虚线） — 实际：tooltip 恒「关联」、边统一灰色实线（实机证实）
- 同一处影响的副作用：后端 `line_style` 中 PREREQUISITE 为 amber **solid**（#F6BD16 width 2.0），前端设计意图是 amber **dashed**——修复字段映射时需与后端/规格对齐线型（当前兜底写 dashed）。

### [浏览器行为错误]
- 无（页面渲染/交互无 JS 报错）

### [内容/文案]（建议修正）
- 边 tooltip 关系文案丢失（「关联」替代「先修/包含」）——随字段映射修复后自动恢复

### [主观建议]（不强制）
- 建议 API 层（curriculum.ts）增加字段归一化映射（rel_type→relation 等），或后端直接输出 camelCase，从源头避免同类问题；同时可在 CourseMindmapView 对缺失 relation 打 warning 日志便于排查
- 建议 next.config 配置 `allowedDevOrigins: ['127.0.0.1']`（若需支持 IP 访问调试），否则 dev 阶段 127.0.0.1 访问会触发 chunk 403

---

## 5. 判定

- **结论：FAIL**
- 阻塞项：
  1. 边关系类型字段不匹配（`rel_type` vs `relation`）→ tooltip 关系类型全部显示「关联」
  2. 边样式字段不匹配（`line_style` vs `lineStyle`）→ PREREQUISITE amber 语义丢失，边统一灰色实线

## 6. 机器可读结论

```json
{
  "taskId": "diagnose-mindmap",
  "result": "FAIL",
  "renderState": "canvas rendered OK (582x440, non-empty), nodes+edges drawn, 0 console errors",
  "edgeStyle": "unified gray solid (amber=0px, gray=~2800px); PREREQUISITE amber lost",
  "edgeTooltip": "relation type lost -> shows '关联' for PREREQUISITE edge (KP-EN-CON-FRIC -> KP-EN-CON-NASAL)",
  "rootCause": "field mismatch: backend rel_type/line_style (snake_case) vs frontend l.relation/l.lineStyle (camelCase), no transform in API layer",
  "screenshot": "test-reports/screenshots/diagnose-mindmap.png",
  "blockers": [
    "edge relation type field mismatch (rel_type -> relation)",
    "edge line style field mismatch (line_style -> lineStyle), PREREQUISITE amber dashed lost"
  ]
}
```
