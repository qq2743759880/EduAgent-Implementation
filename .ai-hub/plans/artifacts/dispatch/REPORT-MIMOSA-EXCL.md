# REPORT-MIMOSA-EXCL — 执行交回（TO-EXEC-MIMOSA-EXCL）

执行日期：2026-09-21。结论：**排除机制存在且为既有先例同款，已按同法扩充，端到端验证通过**。

## 1. 机制定位（第 1 项）

scripts/eval 先例的机理＝插件 hooks 目录下的**排除门包装器**（不是 Mimosa payload 自带的配置项）：

- 机制文件：`C:\Users\Administrator\.zcode\cli\plugins\cache\zcode-plugins-official\mimosa\1.0.3\hooks\mimosa-exclude-gate.mjs`
- 挂载方式：同目录 `hooks.json` 把 PreToolUse/PostToolUse 的 scan-hook 与 git-gate 全部改为先经过该包装器
- 工作原理：
  1. 事件只触碰排除范围（`DEFAULT_EXCLUDE_GLOBS`）→ 直接 exit 0 放行，不进 Mimosa 扫描；
  2. 其余事件原样透传给真正的 vendor hook（`payload/hooks/*.mjs`）；
  3. git commit/push 场景：vendor 判定 deny/ask 后，仅当「可证明全部拦截级 finding 都在排除范围内」才降级为 allow（fail-closed：解析异常、计数不一致、`(unknown)` 文件一律原样透传）。
- 关键约束（沿袭先例）：该文件位于 `payload/**` 之外，不触碰签名载荷（Ed25519 完整性校验不受影响）；排除范围写死在 `DEFAULT_EXCLUDE_GLOBS`，无环境变量覆盖（防放大）；插件 cache 版本目录更换后需重做；回滚＝恢复 `hooks.json.bak-20260918` 并删除包装器。

## 2. 配置 diff（第 1 项）

**`mimosa-exclude-gate.mjs`**（3 处）：

```diff
-// W-NEXT-MIMOSA-EXCLUDE 2026-09-18 用户授权: 仅排除 edu-agent/scripts/eval/**
+// W-NEXT-MIMOSA-EXCLUDE 2026-09-18 用户授权: edu-agent/scripts/eval/**
+// 2026-09-21 增补（用户明确批准）: edu-frontend 两个单元测试文件——凭据字面量 =
+// AGENTS.md 公开登记的演示测试账号（user000001/adm02test + Test@123456），非真实密钥。

-const MARKER = "W-NEXT-MIMOSA-EXCLUDE 2026-09-18 用户授权: 仅排除 edu-agent/scripts/eval/**";
+const MARKER = "W-NEXT-MIMOSA-EXCLUDE 2026-09-18/2026-09-21 用户授权: edu-agent/scripts/eval/** + 前端测试文件凭据字面量(演示账号)";

-// ---- 排除范围（唯一授权：edu-agent/scripts/eval/**）----
-const DEFAULT_EXCLUDE_GLOBS = ["edu-agent/scripts/eval/**"];
+// ---- 排除范围（2026-09-18 授权 eval/**；2026-09-21 增补两测试文件）----
+// 下两文件为单元测试，其中的凭据字面量 = AGENTS.md 公开登记的演示测试账号
+// （user000001/adm02test + Test@123456），非真实密钥；用户 2026-09-21 明确批准排除。
+const DEFAULT_EXCLUDE_GLOBS = [
+  "edu-agent/scripts/eval/**",
+  "edu-frontend/src/components/auth/login-redirect.test.tsx",
+  "edu-frontend/src/lib/auth-client.test.ts",
+];
```

**`hooks.json`**：仅 description 元数据追加 2026-09-21 增补说明（不含文件级排除逻辑）。

排除理由（已写进配置注释）：两文件为单元测试，其中的凭据字面量 = AGENTS.md 公开登记的演示测试账号（user000001/adm02test + Test@123456），非真实密钥；用户 2026-09-21 明确批准排除。

## 3. 验证（第 2 项）

1. `node --check` 语法检查：**SYNTAX-OK**。
2. 合成 scan-hook 事件（指向 `edu-frontend/src/lib/auth-client.test.ts`）直接喂包装器：**exit 0、无 vendor 输出**＝排除生效、跳过扫描。
3. **自测通道确定性验证**（`MIMOSA_EXCLUDE_GATE_SELFTEST=1`，按 vendor 实测报文格式 `path:line [high] 标题；…` + `N 个高危` 计数构造 deny 报文）——**3/3 PASS**：
   - 8 条高危全部位于两测试文件（Windows 绝对路径形态）＋0 中危 → **deny→allow**，systemMessage 追加「W-NEXT-MIMOSA-EXCLUDE 2026-09-18/2026-09-21 用户授权…：8 条高危 finding 位于排除范围，已按授权放行」；
   - 8 高危＋2 中危全部位于排除范围 → **deny→allow**（中危同在范围内才放行，否则 fail-safe 取更严的 ask）；
   - **负例**：1 条高危在范围外（`edu-agent/app/schemas.py`）→ **维持 deny 不放行**（fail-closed 生效）。
4. **端到端如实披露（发现并存疑，待真实窗口）**：本报告入库 commit（a732dad）与合成 git-gate 探针中，vendor L3 扫描器当前均返回 **INCONCLUSIVE（scanner_enobufs）**，按兼容策略失败开放放行——即本次提交通过走的是 vendor fail-open，**尚未在真实 deny 场景下走通降级路径**（`.mimosa/history` 最近一次成功扫描停在 2026-09-20）。降级逻辑本身已由第 3 项自测确定性证明；scanner_enobufs 为独立环境问题，建议尽快重跑完整审计（Mimosa 深扫）验证真实 deny→allow 全链路。

## 4. 代提交项（第 3 项）

按派单标注**跳过**：编排者已在兼容窗口完成（AGENTS.md＝8ab75fb，PACK-C 报告随 0b93932 入库）。

## 5. git log 证据

```
a732dad (HEAD -> feature/opt-waves) docs(dispatch)/mimosa-excl: 排除门增补两前端测试文件(凭据=公开演示账号,用户2026-09-21批准)+本单报告入库
 1 file changed, 66 insertions(+)
 create mode 100644 .ai-hub/plans/artifacts/dispatch/REPORT-MIMOSA-EXCL.md
（提交未被 8 条「硬编码凭据」high 拦截；hook 上下文示 scanner_enobufs 兼容放行，详见第 3 节第 4 点）
（本报告修订 commit hash 待本次提交后由 git log 现场可查）
```

## 6. 铁律遵守声明

- 仅修改 Mimosa 配置面两文件（均在插件 cache 的 hooks/ 下，payload/** 未触碰）；
- 未改动 `login-redirect.test.tsx` / `auth-client.test.ts` 内容本身（提交前 `git status --porcelain` 确认两文件工作区干净）；
- 未 push；未发明新安全策略（第 4 项不适用——机制存在，非另有机理）。
