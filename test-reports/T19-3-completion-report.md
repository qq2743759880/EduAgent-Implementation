# T19-3 完成报告：50301 DEPENDENCY_UNAVAILABLE + 错误响应脱敏

- 契约依据：`contracts/reshape-b.json` amendments T19-3（2026-09-12 用户签字）；派单 `.ai-hub/plans/dispatch-plan-reshape-b.md` §五
- 单 commit：`feat(b)/T19-3-50301-sanitize`（见文末 hash），**回滚 = `git revert <hash>`**
- 验证方式：离线 pytest（TestClient + monkeypatch，全程无 DB 直写）+ 8001/8002 临时 uvicorn 实例真 HTTP 前后对比（HEAD worktree vs 工作区，**用完即关**，未触碰在跑的 8000/3000/8003）

## 一、变更清单

| # | 文件 | 内容 |
|---|------|------|
| ① | `edu-agent/app/common/error_codes.py` | 纯增量 `DEPENDENCY_UNAVAILABLE = "50301"` + 值域表口径变更记录 v1.1→v1.2；`STATUS_TO_CODE` 不动（503→50300 通用映射保留，50301 仅在依赖点显式接线） |
| ② | `edu-agent/app/common/exceptions.py` | 新增 `DependencyUnavailableError(AppException)`：默认 message=「依赖服务暂不可用，请稍后重试」，**detail 恒 None**（data 恒 null 的根），http_status 可传 503/500 维持语义 |
| ② | `edu-agent/app/main.py` | `global_exception_handler` 脱敏：message 一律用户化（依赖型→50301 文案 / 其余→50000「服务内部错误，请稍后重试」），**data 恒 null（DEBUG 也不再回传 str(exc)）**，原始异常经 `logger.exception`（含堆栈）入日志；新增 `_is_dependency_exception` 保守分类器（内建连接/超时族 + 驱动库 MRO 根包 + 类名兜底 + MCP stdio spawn 签名 `stdio*`/`create_subprocess_exec 失败` + `CircuitOpenError`/熔断依赖信号，宁漏勿误） |
| ③ | `edu-agent/app/knowledge/routers/upload.py` | `GET/DELETE /api/knowledge/partitions`：原 `HTTPException(503,"Milvus 不可达，查询分区超时")` 与 `f"查询失败: {e}"`/`f"删除失败: {e}"` 直泄 → `logger.exception` + `DependencyUnavailableError(503/500)`；HTTP 状态码语义不变 |
| ④ | `edu-agent/tests/test_contract_50301_dependency.py` | 新契约测试 15 用例（下表） |

MCP spawn 失败同类接线说明：MCP 工具调用正常路径由 `executor._invoke_transport` 内捕转 `MCPToolTestResp(status=ERROR, error_message=...)`（200 数据载荷 + 审计落库，属 task33 行为，原始错误为运维必需，不在错误响应脱敏范围）；当 spawn/传输异常**逃逸到全局兜底**时，由 `_is_dependency_exception` 的 stdio 签名分支改判 50301（分类器单测 ④a 实证）。

## 二、pytest 结果

| 套件 | 结果 |
|------|------|
| `tests/test_contract_50301_dependency.py` | **15 passed**（4.76s） |
| 旧 50000 相关回归（test_error_codes / test_chat_stream_error / test_course_admin_json_columns / test_critique_round4） | **32 passed**（3.98s） |
| 全量 `tests/`（工作区，T19-3 后） | 73 failed, **819 passed**, 32 skipped |
| 全量 `tests/`（HEAD a1891b0 worktree 基线） | 81 failed, 796 passed, 32 skipped |
| 失败集合 diff | **after 73 条 ⊆ before 81 条，零新增失败**；基线独有 8 条（test_contract_mcp_health_async×7 + test_contract_middleware::test_login_success_format×1）系基线轮与临时实例/登录限流扰动同期所致的环境抖动，非代码因素 |

用例矩阵（15 例，全部通过）：
- ① 依赖端点契约：a 超时→50301+HTTP503；b 连接失败→50301+HTTP500+响应无类名/包名/host/路径（毒物文案断言）；c 删除分区连接失败→50301；d drop_partition False→404 分支不受影响
- ② 原始异常进 logger：loguru sink 等价 caplog 断言（原始文本含 host/路径入日志 + ERROR 级含堆栈；全局兜底同样入日志）——与"不进响应"形成对照
- ③ 普通错误不受影响：404→40400；非依赖→50000 且 **DEBUG=True 下 data 恒 null**（脱敏核心回归点）；STATUS_TO_CODE 503→50300 纯增量不变
- ④ 分类器：MCP spawn 签名 / 内建连接超时族 / 驱动库 MRO / 熔断依赖信号 / 逻辑异常不误判（宁漏勿误）
- 异常类形态：默认 message 用户化、detail 恒 None、http_status 可指定

修复记录：初跑 13/15——`TestClient` 默认 `raise_server_exceptions=True` 会把全局兜底生成的 500 响应以 ExceptionGroup 重抛，client fixture 改 `raise_server_exceptions=False`（要验证的正是 handler 响应体）后 15/15。

## 三、脱敏前后对比样例（同输入、同环境实证）

### A. 全局兜底 handler 直探（DEBUG=true，同一毒物异常喂 HEAD 与工作区）

```
输入：ValueError("内部秘密报错 C:\secret\path.py host=192.168.85.101")
BEFORE(HEAD) → 500 {"code":"50000","message":"服务内部错误，请稍后重试",
                    "data":"内部秘密报错 C:\secret\path.py host=192.168.85.101"}   ← 泄漏
AFTER        → 500 {"code":"50000","message":"服务内部错误，请稍后重试","data":null}

输入：ConnectionError("pymilvus.exceptions.MilvusException: connect 192.168.85.101:19530 failed")
BEFORE(HEAD) → 500 {"code":"50000",...,"data":"pymilvus.exceptions.MilvusException: connect 192.168.85.101:19530 failed"}  ← 泄漏
AFTER        → 500 {"code":"50301","message":"依赖服务暂不可用，请稍后重试","data":null}
日志侧（两版一致）：logger.exception 完整堆栈落日志（console/log 文件可见）
```

### B. 真 HTTP（GET /api/knowledge/partitions，MILVUS_URI=http://127.0.0.1:19999 拒连，adm02test 真 JWT）

```
BEFORE(8002, HEAD a1891b0)：
  GET    HTTP 500 {"code":"50000","message":"查询失败: <MilvusException: (code=2, message=Fail connecting to server on 127.0.0.1:19999, illegal connection params or server unavailable)>","data":null}
  DELETE HTTP 500 {"code":"50000","message":"删除失败: <MilvusException: ...127.0.0.1:19999...>","data":null}   ← 类名+host 直泄 message
AFTER(8001, 工作区)：
  GET    HTTP 500 {"code":"50301","message":"依赖服务暂不可用，请稍后重试","data":null}
  DELETE HTTP 500 {"code":"50301","message":"依赖服务暂不可用，请稍后重试","data":null}
HTTP 状态码语义不变（500/500；503 分支由 pytest ①a 实证 HTTP 503 维持）。
```

### C. 正常路径不回归（8001 接真实 Milvus 192.168.85.101:19530）

```
GET /api/knowledge/partitions → HTTP 200 {"code":0,"message":"ok","data":{"total_partitions":2,
  "partitions":[{"name":"_default","row_count":2631},{"name":"course_public","row_count":2}]}}
```

## 四、旧断言测试受影响面

- 全仓 grep `50300`/`Milvus 不可达`/`partitions`/`50000`：旧测试中"Milvus 不可达"仅为 `skipif` reason 文案，partitions 端点无旧断言测试，50000 断言（4 文件 32 用例）语义未变——**无需按新契约更新任何旧测试**，实测全量回归零新增失败佐证。

## 五、范围判定与残留观察（不阻塞收口）

1. `app/rerank_service/main.py:78` `HTTPException(503, str(exc))`：**不改**——8003 独立验证服务（非前端用），detail 为主应用降级链的机读契约（AC4），非用户面错误响应。
2. `upload.py` 上传路径 `HTTPException(500, f"文件落盘失败：{exc}")` 与 413 `str(exc)`：413 为业务校验用户面文案（不改）；500 落盘失败混合本地磁盘/MinIO 异常，非本次点名的 Milvus/MCP 两类，且改成 50301 会把真实 bug 误标为依赖问题——登记为残留观察项，建议后续任务以「依赖分类前置判定」方式收敛。
3. `app_exception_handler` 的 DEBUG detail 回传为既有业务 AppException 设计（受控业务文案非原始堆栈），新 50301 类 detail 恒 None 不受影响。

## 六、回滚

```
git revert <本 commit hash>   # 5 个代码/测试文件 + 本报告同 commit，revert 即完整回滚
```
