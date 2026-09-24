# REPORT-TA5 — chat 用户并发槽失败路径泄漏修复（finally 收口）

> 分支 `feature/opt-waves`；后端 9988 已加载修复后代码并实测。
> 单 commit：`fix(be)/ta5: chat 用户并发槽失败路径泄漏修复(finally 收口)`

## 一、泄漏路径定位（文件:行）

并发槽的获取/释放实现在 `app/ai/guard.py`（`ConcurrencyGuard.acquire` / `release` / `release_user_slot`，
单用户计数键 `chat:concurrent:{user_id}`）。消费方有两处：

### 1. `app/chat/flows/graph_stream.py`（SSE 流式主路径，即 `/api/chat/stream`）
- 获取：`graph_stream.py:303` `guard_entry = await default_guard().acquire(int(user_id), request_meta=_request_meta)`
- 释放（两处 `finally`）：
  - 内层 `astream` 的 `finally`：`graph_stream.py:632-640`
  - 外层 `try` 的 `finally`：`graph_stream.py:674-681`

这两处都写的是
```python
if guard_held:
    try:
        from app.ai.guard import default_guard
        await default_guard().release(int(user_id))
    except Exception:        # ← 只捕获 Exception
        pass
```

**根因**：`release()` 是 `await`。当 SSE 客户端中途断连 / 请求超时，服务端取消该请求协程，
生成器的 `finally` 里的 `await release()` 被 **`CancelledError`** 打断（`CancelledError` 是
`BaseException`，上面的 `except Exception` 捕获不到），导致 `release_user_slot` 的
Redis `DECR` / 进程内 `_user_conc` 递减**从未执行** → 该用户并发槽永久占用 →
下次请求直接被 `user_concurrent_over_limit` 拒绝（latency ~20ms、零 token）。
这与 P0 验收复现的「student 聊几轮坏了就永久降级、重启后端即恢复」现象一致
（Redis 后端下残留槽会在 `GUARD_SLOT_TTL=600s` 自愈；内存后端下随进程重启归零）。

正常「LLM 异常」路径其实已被这两处 `finally` 覆盖（`astream` 抛异常 → `finally` 释放，
且非取消场景下 `await` 正常完成），所以旧代码在异常路径不泄漏；**泄漏只在
「客户端断连 / 超时」的取消路径**。

### 2. `app/ai/graph.py:928`（非流式 `run_agent` 路径，同类泄漏 + 一处误释放）
```python
finally:
    if guard_entry is not None:        # ← 拒绝(ok=False)时也进入
        await default_guard().release(int(user_id))
```
- 同类取消脆弱性：`except Exception` 不防 `CancelledError`。
- **额外 bug**：条件 `guard_entry is not None` 在「guard 拒绝」（`ok=False`，从未占用槽位）时
  也为真 → 对从未 INCR 的 `chat:concurrent:{uid}` 执行 `DECR`，把 Redis 计数打到负数（脏计数）。

## 二、修复 diff

### 2.1 `app/ai/guard.py` — 新增取消安全的 `safe_release`（并发模块集中修复）
```python
async def safe_release(guard: "ConcurrencyGuard", user_id: int) -> None:
    """取消安全的并发槽释放（修复「失败 / SSE 客户端断连 / 请求超时」路径的槽泄漏）。

    调用方已在 finally 中成对调用 release，但 SSE 客户端断连或请求超时会令
    await release() 被 CancelledError 打断（CancelledError 是 BaseException，
    调用处 except Exception 捕获不到），导致槽位永不归还、该用户被永久限流。
    用 asyncio.shield 包裹释放：即便外层 await 被取消，内部 release 仍在事件循环上
    独立跑完，保证槽位一定归还。
    """
    try:
        await asyncio.shield(guard.release(int(user_id)))
    except asyncio.CancelledError:
        pass  # shield 已让内部 release 在后台继续完成，无需重复释放
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[guard] 释放并发槽异常（已尽力归还）: {type(exc).__name__}: {exc}")
```

### 2.2 `app/chat/flows/graph_stream.py` — 两处 finally 改用 `safe_release`
内层 `finally`（:632）与外层 `finally`（:674）均改为：
```python
if guard_held:
    try:
        from app.ai.guard import default_guard, safe_release
        await safe_release(default_guard(), int(user_id))
    except Exception:  # noqa: BLE001
        pass
```
（外层 `finally` 的 `guard_held` 在已释放时已被置 False，不会重复释放。）

### 2.3 `app/ai/graph.py:928` — 仅准入时释放 + 改用 `safe_release`
```python
finally:
    # 仅当 guard 实际准入（ok）才释放；拒绝路径（ok=False）从未占用槽位，误释放会使
    # Redis 计数变负。safe_release 对客户端断连/超时导致的 CancelledError 免疫（TA5）。
    if guard_entry is not None and guard_entry.get("ok"):
        try:
            from app.ai.guard import default_guard, safe_release
            await safe_release(default_guard(), int(user_id))
        except Exception:
            pass
```

**未改动并发上限本身**：`USER_MAX_CONCURRENT=2` / `LLM_GLOBAL_CONCURRENCY=8` 保持不变。

## 三、三步自验（真实 HTTP，后端 9988，student 账号 user000001）

脚本：`C:/Users/Administrator/AppData/Local/Temp/ta5_verify.py`（临时，未入库）；
基线前用 `redis-cli` 等价 `rc.delete("chat:concurrent:{uid}","ai:llm:concurrent")` 清计数。

### 步骤① 正常一轮问答后再问 → 不出现 `user_concurrent_over_limit`
- 第 1 轮：events=[start,retrieval,token×55,done]，`done_degraded=rerank_sidecar_unavailable`（与并发无关），token 55。
- 第 2 轮：events=[start,retrieval,token×93,done]，`done_degraded=rerank_sidecar_unavailable`，token 93。
- **结论 PASS**：两轮均正常出 token，无 `user_concurrent_over_limit`。

### 步骤② 人造失败路径（SSE 中途断连，复现 P0 取消泄漏）→ 再问不被限
每轮：清基线 → 顺序发 2 个「收到 start 帧即关闭连接」的请求（模拟客户端断连，占用并泄漏槽）→
等 4s → 读 Redis `chat:concurrent:{uid}` → 再发 1 个正常请求。
- round0：`chat:concurrent=None`（= 槽已归还基线），reask token=44 ✅
- round1：`chat:concurrent=None`，reask token=1 ✅
- round2：`chat:concurrent=None`，reask token=1 ✅
- **结论 PASS**：断连后 Redis 槽计数回到基线，再问正常出 token —— 取消路径泄漏已修复。

### 步骤③ 并发上限语义仍在（同用户并发打满仍正确拒绝）
发 5 个并发请求（user_max=2）：
- 结果：3 个 `done_degraded=user_concurrent_over_limit`（req1/req3/req4），2 个正常出 token（req0/req2）。
- **结论 PASS**：上限仍生效（至少 1 个被拒），未放宽。

> 注：`rerank_sidecar_unavailable` 是 rerank 旁路（127.0.0.1:8601）不可达的良性降级，
> 与本次并发槽修复无关，不计入 `user_concurrent_over_limit`。

## 四、回归结果

聚焦并发/guard/SSE 契约测试（与本次改动直接相关，且 monkeypatch `default_guard` 的 fake 均含 `release`，兼容 `safe_release`）：
```
pytest tests/test_contract_task26.py tests/test_contract_task_r02.py \
       tests/test_contract_task_g1.py tests/test_sse_envelope_contract.py \
       tests/test_contract_task_m1.py -q
→ 68 passed, 1 warning in 16.73s
```
**零新增失败。**

## 五、owner 验收口径对照

Given owner 用 student 账号连问多轮（含一次中途打断），When 继续提问，Then 永远能正常回答，
不再出现「并发超限」降级。→ 步骤②（中途断连后仍能正常回答）+ 步骤①（连问多轮正常）已实测通过。

## 六、commit

`fix(be)/ta5: chat 用户并发槽失败路径泄漏修复(finally 收口)`（路径限定提交：`app/ai/guard.py`、
`app/chat/flows/graph_stream.py`、`app/ai/graph.py`；未 push）。
