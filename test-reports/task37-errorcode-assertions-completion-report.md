# task37 批判项「task14/15 错误码断言」完工报告

> 执行 agent：task37-errorcode-assertions ｜ 日期：2026-09-04
> 类型：批判滞后任务闭环（错误码断言与权威一致核对）

## 1. 资产消费证据（assetConsumed）

| 资产 | 路径 | 消费内容 | 内核词/锚点 |
|------|------|----------|-------------|
| ponytail skill | `C:\Users\Administrator\.agents\skills\ponytail\SKILL.md` | 最小 diff、根因而非症状、YAGNI | 最小 diff / 无整数断言=无需改 |
| tt skill §5.2 | `C:\Users\Administrator\.agents\skills\tt\SKILL.md` §5.2 | 完工报告须含资产消费证据；验收独立实证 | assetConsumed / 完工报告 |
| review skill（review 簇） | `C:\Users\Administrator\.agents\skills\tt\vendor\review\SKILL.md` | 验证须记录可复现证据（pytest 实跑） | be-tester 实证 |

**自检发现**：两测试文件当前已无整数码断言、无与 error_codes.py 不一致的串码断言；无需修改测试代码（最小 diff = 空 diff）。自检无发现可修复的分析层问题。

### agent×skill×workflow 矩阵

| 项 | 取值 | 说明 |
|----|------|------|
| agent | task37-errorcode-assertions（本 sub-agent） | 执行；
| skill | ponytail（最小 diff）、review（验证）、tt §5.2（报告纪律） | 消费 |
| workflow | 单 agent 串行（N=1 退化模式） | 核实→对齐→pytest 实证→报告 |
| mcp | 无（不需要 MCP） | — |

## 2. 核实结果（权威 → 两文件断言逐条 → 修正）

### 2.1 权威（app/common/error_codes.py，契约① v1.1 字符串码，成功 code=0 int）

- AUTH_TOKEN_TYPE_MISMATCH=`40104`、AUTH_TOKEN_INVALID=`40101`、AUTH_TOKEN_EXPIRED=`40102`、AUTH_TOKEN_MALFORMED=`40103`、AUTH_TOKEN_MALFORMED=`40103`、AUTH_ROLE_INVALID=`40105`
- AUTH_ACCOUNT_EXISTS=`40912`、AUTH_LOGIN_FAILED=`40111`、AUTH_USER_DISABLED=`40312`、AUTH_USER_NOT_FOUND=`40413`

### 2.2 tests/test_auth_service.py（12 处断码断言）

逐条核对 `ei.value.code ==`：`40104/40101/40102/40103/40105/40912/40111/40111/40312/40312/40104/40413` —— **全部为字符串，且与 error_codes.py 完全一致，无整数码残留**。

### 2.3 tests/test_error_codes.py

- `e.code ==` 断言全部为字符串：`40310/40300/40410/40101/50002/40311` —— 均与来源一致（40310 COMMUNITY_POST_LOCKED、40300 FORBIDDEN、40410 COMMUNITY_POST_NOT_FOUND、40101 AUTH_TOKEN_INVALID、50002 DatabaseError 默认、40311 COMMUNITY_FORBIDDEN_UPDATE）。
- `_http_status_for_code("...")` 段映射断言为字符串串码，PASS。
- 非断码行：L86 `AppException(code=40000, ...)` 为**构造 int 码用于测 http 映射**（AppException 契约接受 str|int，`_http_status_for_code` 对 int 先转 str），非断言字符串/整数契约，不属于断错误，未改。

### 2.4 修正条目清单

**本次无修正**。批判观察的"字符串/整数码断言 bug"在这些测试文件当前实现中已不存在（判断为 task14/15 早前批次已收敛）。ponytail：无整数断言 → 不改，避免虚改。

## 3. pytest 实证结果（两文件全 PASS）

命令：`edu-agent\.venv\Scripts\python.exe -m pytest tests\test_auth_service.py tests\test_error_codes.py -v`

```
collected 33 items
tests/test_auth_service.py ............                            [ 69%]
tests/test_error_codes.py ............                             [100%]
============================= 33 passed in 6.65s ==============================
```

- test_auth_service.py：23 PASS
- test_error_codes.py：10 PASS
- 合计 33/33 PASS，无失败无报错。

## 4. 产品侧观察（非本任务修改范围，上报编排者）

1. **DatabaseError/LLMError 默认码未登记进 error_codes.py 单一事实源**：`app/common/exceptions.py` 中 `DatabaseError` 硬编码 `"50002"`、`LLMError` 硬编码 `"50001"`，二者在 `error_codes.py` 内无具名常量（error_codes.py 含 INTERNAL_ERROR=`50000` / SERVICE_UNAVAILABLE=`50300` / LLM_* 段 50011~50016，但无 50001/50002）。**这是单一事实源偏离**，非断错误、非契约违背（字符串串码），测试断言与 exceptions.py 一致故 PASS。建议后续将 `"50001"/"50002"` 抽为 error_codes.py 常量（如 `LLM_ERROR`/`DB_ERROR`）由 exceptions.py 引用，消灭第三套注册来源。
2. 效率不起冲突，不阻塞验收。

## 结论

- 两测试文件错误码断言已与 `error_codes.py` 权威一致（全部字符串串码、值精确匹配），无修正项。
- pytest 两文件 **33/33 PASS**。
- 无产品 error_codes.py 直接 bug；存在 DB/LLM 默认码未登记单一事实源的小口径偏离（建议项 4.1，非阻断）。