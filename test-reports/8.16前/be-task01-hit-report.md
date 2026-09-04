# be-task01 打靶报告：chat DELETE 软删（R-2）

- 时间：2026-08-13 13:39:19
- 环境：DEBUG=true（.env 判定），uvicorn 127.0.0.1:8000
- 结果：22/22 PASS
- 说明：DEBUG=true（交付基线）：无 Authorization 被虚拟 admin 兜底，未登录删除预期 200+软删生效；DEBUG=false 生产回归：未登录删除 401。

| # | 断言 | 结果 | 说明 |
|---|------|------|------|
| 1 | A1 /health 200 | PASS | 实际 200 |
| 2 | B1 DEBUG=true 未登录 DELETE → 200（虚拟 admin 语义） | PASS | 实际 200 |
| 3 | B2 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 4 | B3 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 5 | B4 行仍在（UPDATE yn=0，无物理 DELETE） | PASS | row={'session_id': 's_a07c99a005d2', 'user_id': 939, 'yn': 0} |
| 6 | B5 幂等：未登录重复 DELETE → 404 | PASS | 实际 404 |
| 7 | C1 学生 B 删 A 的会话 → 403 | PASS | 实际 403 |
| 8 | C2 错误壳 code=CHAT_SESSION_FORBIDDEN | PASS | body={"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话", "detail": {"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话"}} |
| 9 | C3 403 错误壳含 {code,message,detail} | PASS | keys=['code', 'detail', 'message'] |
| 10 | C4 越权删除未生效（DB yn=1） | PASS | yn=1 |
| 11 | C5 学生 A 删自己 → 200 | PASS | 实际 200 |
| 12 | C6 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 13 | C7 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 14 | C8 GET /sessions → 200 | PASS | 实际 200 |
| 15 | C9 已删会话从列表消失 | PASS | sess_a=s_f05b4dc6843b in list=False |
| 16 | C10 已删会话历史 → 404 | PASS | 实际 404 |
| 17 | C11 历史 404 错误壳 code=CHAT_SESSION_NOT_FOUND | PASS | body={"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_f05b4dc6843b", "detail": {"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_f05b4dc6843b"}} |
| 18 | C12 幂等：重复删除 → 404 | PASS | 实际 404 |
| 19 | D1 非 s_ 前缀 session_id → 404 | PASS | 实际 404 |
| 20 | D2 SQL 注入 payload → 非 500 | PASS | 实际 404（参数化 SQL 应安全） |
| 21 | D3 错误统一走 {code,message,detail} 壳 | PASS |  |
| 22 | D4 全链路无 500 | PASS | 共采集 9 个响应，均 <500 |

# be-task01 打靶报告：chat DELETE 软删（R-2）

- 时间：2026-08-13 13:40:07
- 环境：DEBUG=true（.env 判定），uvicorn 127.0.0.1:8000
- 结果：22/22 PASS
- 说明：DEBUG=true（交付基线）：无 Authorization 被虚拟 admin 兜底，未登录删除预期 200+软删生效；DEBUG=false 生产回归：未登录删除 401。

| # | 断言 | 结果 | 说明 |
|---|------|------|------|
| 1 | A1 /health 200 | PASS | 实际 200 |
| 2 | B1 DEBUG=true 未登录 DELETE → 200（虚拟 admin 语义） | PASS | 实际 200 |
| 3 | B2 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 4 | B3 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 5 | B4 行仍在（UPDATE yn=0，无物理 DELETE） | PASS | row={'session_id': 's_dbb7f3bfdf2b', 'user_id': 941, 'yn': 0} |
| 6 | B5 幂等：未登录重复 DELETE → 404 | PASS | 实际 404 |
| 7 | C1 学生 B 删 A 的会话 → 403 | PASS | 实际 403 |
| 8 | C2 错误壳 code=CHAT_SESSION_FORBIDDEN | PASS | body={"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话", "detail": {"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话"}} |
| 9 | C3 403 错误壳含 {code,message,detail} | PASS | keys=['code', 'detail', 'message'] |
| 10 | C4 越权删除未生效（DB yn=1） | PASS | yn=1 |
| 11 | C5 学生 A 删自己 → 200 | PASS | 实际 200 |
| 12 | C6 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 13 | C7 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 14 | C8 GET /sessions → 200 | PASS | 实际 200 |
| 15 | C9 已删会话从列表消失 | PASS | sess_a=s_f4cb5b21f222 in list=False |
| 16 | C10 已删会话历史 → 404 | PASS | 实际 404 |
| 17 | C11 历史 404 错误壳 code=CHAT_SESSION_NOT_FOUND | PASS | body={"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_f4cb5b21f222", "detail": {"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_f4cb5b21f222"}} |
| 18 | C12 幂等：重复删除 → 404 | PASS | 实际 404 |
| 19 | D1 非 s_ 前缀 session_id → 404 | PASS | 实际 404 |
| 20 | D2 SQL 注入 payload → 非 500 | PASS | 实际 404（参数化 SQL 应安全） |
| 21 | D3 错误统一走 {code,message,detail} 壳 | PASS |  |
| 22 | D4 全链路无 500 | PASS | 共采集 9 个响应，均 <500 |

# be-task01 打靶报告：chat DELETE 软删（R-2）

- 时间：2026-08-13 13:53:44
- 环境：DEBUG=true（.env 判定），uvicorn 127.0.0.1:8000
- 结果：22/22 PASS
- 说明：DEBUG=true（交付基线）：无 Authorization 被虚拟 admin 兜底，未登录删除预期 200+软删生效；DEBUG=false 生产回归：未登录删除 401。

| # | 断言 | 结果 | 说明 |
|---|------|------|------|
| 1 | A1 /health 200 | PASS | 实际 200 |
| 2 | B1 DEBUG=true 未登录 DELETE → 200（虚拟 admin 语义） | PASS | 实际 200 |
| 3 | B2 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 4 | B3 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 5 | B4 行仍在（UPDATE yn=0，无物理 DELETE） | PASS | row={'session_id': 's_fedfe8e27130', 'user_id': 943, 'yn': 0} |
| 6 | B5 幂等：未登录重复 DELETE → 404 | PASS | 实际 404 |
| 7 | C1 学生 B 删 A 的会话 → 403 | PASS | 实际 403 |
| 8 | C2 错误壳 code=CHAT_SESSION_FORBIDDEN | PASS | body={"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话", "detail": {"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话"}} |
| 9 | C3 403 错误壳含 {code,message,detail} | PASS | keys=['code', 'detail', 'message'] |
| 10 | C4 越权删除未生效（DB yn=1） | PASS | yn=1 |
| 11 | C5 学生 A 删自己 → 200 | PASS | 实际 200 |
| 12 | C6 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 13 | C7 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 14 | C8 GET /sessions → 200 | PASS | 实际 200 |
| 15 | C9 已删会话从列表消失 | PASS | sess_a=s_c5d29c7e2afb in list=False |
| 16 | C10 已删会话历史 → 404 | PASS | 实际 404 |
| 17 | C11 历史 404 错误壳 code=CHAT_SESSION_NOT_FOUND | PASS | body={"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_c5d29c7e2afb", "detail": {"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_c5d29c7e2afb"}} |
| 18 | C12 幂等：重复删除 → 404 | PASS | 实际 404 |
| 19 | D1 非 s_ 前缀 session_id → 404 | PASS | 实际 404 |
| 20 | D2 SQL 注入 payload → 非 500 | PASS | 实际 404（参数化 SQL 应安全） |
| 21 | D3 错误统一走 {code,message,detail} 壳 | PASS |  |
| 22 | D4 全链路无 500 | PASS | 共采集 9 个响应，均 <500 |

# be-task01 打靶报告：chat DELETE 软删（R-2）

- 时间：2026-08-13 13:54:11
- 环境：DEBUG=true（.env 判定），uvicorn 127.0.0.1:8000
- 结果：22/22 PASS
- 说明：DEBUG=true（交付基线）：无 Authorization 被虚拟 admin 兜底，未登录删除预期 200+软删生效；DEBUG=false 生产回归：未登录删除 401。

| # | 断言 | 结果 | 说明 |
|---|------|------|------|
| 1 | A1 /health 200 | PASS | 实际 200 |
| 2 | B1 DEBUG=true 未登录 DELETE → 200（虚拟 admin 语义） | PASS | 实际 200 |
| 3 | B2 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 4 | B3 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 5 | B4 行仍在（UPDATE yn=0，无物理 DELETE） | PASS | row={'session_id': 's_49e6de77a10c', 'user_id': 945, 'yn': 0} |
| 6 | B5 幂等：未登录重复 DELETE → 404 | PASS | 实际 404 |
| 7 | C1 学生 B 删 A 的会话 → 403 | PASS | 实际 403 |
| 8 | C2 错误壳 code=CHAT_SESSION_FORBIDDEN | PASS | body={"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话", "detail": {"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话"}} |
| 9 | C3 403 错误壳含 {code,message,detail} | PASS | keys=['code', 'detail', 'message'] |
| 10 | C4 越权删除未生效（DB yn=1） | PASS | yn=1 |
| 11 | C5 学生 A 删自己 → 200 | PASS | 实际 200 |
| 12 | C6 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 13 | C7 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 14 | C8 GET /sessions → 200 | PASS | 实际 200 |
| 15 | C9 已删会话从列表消失 | PASS | sess_a=s_10322da30dda in list=False |
| 16 | C10 已删会话历史 → 404 | PASS | 实际 404 |
| 17 | C11 历史 404 错误壳 code=CHAT_SESSION_NOT_FOUND | PASS | body={"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_10322da30dda", "detail": {"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_10322da30dda"}} |
| 18 | C12 幂等：重复删除 → 404 | PASS | 实际 404 |
| 19 | D1 非 s_ 前缀 session_id → 404 | PASS | 实际 404 |
| 20 | D2 SQL 注入 payload → 非 500 | PASS | 实际 404（参数化 SQL 应安全） |
| 21 | D3 错误统一走 {code,message,detail} 壳 | PASS |  |
| 22 | D4 全链路无 500 | PASS | 共采集 9 个响应，均 <500 |

# be-task01 打靶报告：chat DELETE 软删（R-2）

- 时间：2026-08-13 23:33:44
- 环境：DEBUG=true（.env 判定），uvicorn 127.0.0.1:8000
- 结果：22/22 PASS
- 说明：DEBUG=true（交付基线）：无 Authorization 被虚拟 admin 兜底，未登录删除预期 200+软删生效；DEBUG=false 生产回归：未登录删除 401。

| # | 断言 | 结果 | 说明 |
|---|------|------|------|
| 1 | A1 /health 200 | PASS | 实际 200 |
| 2 | B1 DEBUG=true 未登录 DELETE → 200（虚拟 admin 语义） | PASS | 实际 200 |
| 3 | B2 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 4 | B3 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 5 | B4 行仍在（UPDATE yn=0，无物理 DELETE） | PASS | row={'session_id': 's_cc3481de2bcb', 'user_id': 972, 'yn': 0} |
| 6 | B5 幂等：未登录重复 DELETE → 404 | PASS | 实际 404 |
| 7 | C1 学生 B 删 A 的会话 → 403 | PASS | 实际 403 |
| 8 | C2 错误壳 code=CHAT_SESSION_FORBIDDEN | PASS | body={"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话", "detail": {"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话"}} |
| 9 | C3 403 错误壳含 {code,message,detail} | PASS | keys=['code', 'detail', 'message'] |
| 10 | C4 越权删除未生效（DB yn=1） | PASS | yn=1 |
| 11 | C5 学生 A 删自己 → 200 | PASS | 实际 200 |
| 12 | C6 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 13 | C7 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 14 | C8 GET /sessions → 200 | PASS | 实际 200 |
| 15 | C9 已删会话从列表消失 | PASS | sess_a=s_5347d360e0a7 in list=False |
| 16 | C10 已删会话历史 → 404 | PASS | 实际 404 |
| 17 | C11 历史 404 错误壳 code=CHAT_SESSION_NOT_FOUND | PASS | body={"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_5347d360e0a7", "detail": {"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_5347d360e0a7"}} |
| 18 | C12 幂等：重复删除 → 404 | PASS | 实际 404 |
| 19 | D1 非 s_ 前缀 session_id → 404 | PASS | 实际 404 |
| 20 | D2 SQL 注入 payload → 非 500 | PASS | 实际 404（参数化 SQL 应安全） |
| 21 | D3 错误统一走 {code,message,detail} 壳 | PASS |  |
| 22 | D4 全链路无 500 | PASS | 共采集 9 个响应，均 <500 |

# be-task01 打靶报告：chat DELETE 软删（R-2）

- 时间：2026-08-14 17:47:20
- 环境：DEBUG=true（.env 判定），uvicorn 127.0.0.1:8000
- 结果：22/22 PASS
- 说明：DEBUG=true（交付基线）：无 Authorization 被虚拟 admin 兜底，未登录删除预期 200+软删生效；DEBUG=false 生产回归：未登录删除 401。

| # | 断言 | 结果 | 说明 |
|---|------|------|------|
| 1 | A1 /health 200 | PASS | 实际 200 |
| 2 | B1 DEBUG=true 未登录 DELETE → 200（虚拟 admin 语义） | PASS | 实际 200 |
| 3 | B2 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 4 | B3 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 5 | B4 行仍在（UPDATE yn=0，无物理 DELETE） | PASS | row={'session_id': 's_0ded4c7d42ba', 'user_id': 1009, 'yn': 0} |
| 6 | B5 幂等：未登录重复 DELETE → 404 | PASS | 实际 404 |
| 7 | C1 学生 B 删 A 的会话 → 403 | PASS | 实际 403 |
| 8 | C2 错误壳 code=CHAT_SESSION_FORBIDDEN | PASS | body={"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话", "detail": {"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话"}} |
| 9 | C3 403 错误壳含 {code,message,detail} | PASS | keys=['code', 'detail', 'message'] |
| 10 | C4 越权删除未生效（DB yn=1） | PASS | yn=1 |
| 11 | C5 学生 A 删自己 → 200 | PASS | 实际 200 |
| 12 | C6 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 13 | C7 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 14 | C8 GET /sessions → 200 | PASS | 实际 200 |
| 15 | C9 已删会话从列表消失 | PASS | sess_a=s_4ec33acb6901 in list=False |
| 16 | C10 已删会话历史 → 404 | PASS | 实际 404 |
| 17 | C11 历史 404 错误壳 code=CHAT_SESSION_NOT_FOUND | PASS | body={"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_4ec33acb6901", "detail": {"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_4ec33acb6901"}} |
| 18 | C12 幂等：重复删除 → 404 | PASS | 实际 404 |
| 19 | D1 非 s_ 前缀 session_id → 404 | PASS | 实际 404 |
| 20 | D2 SQL 注入 payload → 非 500 | PASS | 实际 404（参数化 SQL 应安全） |
| 21 | D3 错误统一走 {code,message,detail} 壳 | PASS |  |
| 22 | D4 全链路无 500 | PASS | 共采集 9 个响应，均 <500 |

# be-task01 打靶报告：chat DELETE 软删（R-2）

- 时间：2026-08-14 18:22:15
- 环境：DEBUG=true（.env 判定），uvicorn 127.0.0.1:8000
- 结果：22/22 PASS
- 说明：DEBUG=true（交付基线）：无 Authorization 被虚拟 admin 兜底，未登录删除预期 200+软删生效；DEBUG=false 生产回归：未登录删除 401。

| # | 断言 | 结果 | 说明 |
|---|------|------|------|
| 1 | A1 /health 200 | PASS | 实际 200 |
| 2 | B1 DEBUG=true 未登录 DELETE → 200（虚拟 admin 语义） | PASS | 实际 200 |
| 3 | B2 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 4 | B3 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 5 | B4 行仍在（UPDATE yn=0，无物理 DELETE） | PASS | row={'session_id': 's_f0ff35516ff3', 'user_id': 1011, 'yn': 0} |
| 6 | B5 幂等：未登录重复 DELETE → 404 | PASS | 实际 404 |
| 7 | C1 学生 B 删 A 的会话 → 403 | PASS | 实际 403 |
| 8 | C2 错误壳 code=CHAT_SESSION_FORBIDDEN | PASS | body={"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话", "detail": {"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话"}} |
| 9 | C3 403 错误壳含 {code,message,detail} | PASS | keys=['code', 'detail', 'message'] |
| 10 | C4 越权删除未生效（DB yn=1） | PASS | yn=1 |
| 11 | C5 学生 A 删自己 → 200 | PASS | 实际 200 |
| 12 | C6 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 13 | C7 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 14 | C8 GET /sessions → 200 | PASS | 实际 200 |
| 15 | C9 已删会话从列表消失 | PASS | sess_a=s_a5106ca1e8d0 in list=False |
| 16 | C10 已删会话历史 → 404 | PASS | 实际 404 |
| 17 | C11 历史 404 错误壳 code=CHAT_SESSION_NOT_FOUND | PASS | body={"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_a5106ca1e8d0", "detail": {"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_a5106ca1e8d0"}} |
| 18 | C12 幂等：重复删除 → 404 | PASS | 实际 404 |
| 19 | D1 非 s_ 前缀 session_id → 404 | PASS | 实际 404 |
| 20 | D2 SQL 注入 payload → 非 500 | PASS | 实际 404（参数化 SQL 应安全） |
| 21 | D3 错误统一走 {code,message,detail} 壳 | PASS |  |
| 22 | D4 全链路无 500 | PASS | 共采集 9 个响应，均 <500 |

# be-task01 打靶报告：chat DELETE 软删（R-2）

- 时间：2026-08-14 18:22:53
- 环境：DEBUG=true（.env 判定），uvicorn 127.0.0.1:8000
- 结果：22/22 PASS
- 说明：DEBUG=true（交付基线）：无 Authorization 被虚拟 admin 兜底，未登录删除预期 200+软删生效；DEBUG=false 生产回归：未登录删除 401。

| # | 断言 | 结果 | 说明 |
|---|------|------|------|
| 1 | A1 /health 200 | PASS | 实际 200 |
| 2 | B1 DEBUG=true 未登录 DELETE → 200（虚拟 admin 语义） | PASS | 实际 200 |
| 3 | B2 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 4 | B3 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 5 | B4 行仍在（UPDATE yn=0，无物理 DELETE） | PASS | row={'session_id': 's_369ca04a9d4f', 'user_id': 1013, 'yn': 0} |
| 6 | B5 幂等：未登录重复 DELETE → 404 | PASS | 实际 404 |
| 7 | C1 学生 B 删 A 的会话 → 403 | PASS | 实际 403 |
| 8 | C2 错误壳 code=CHAT_SESSION_FORBIDDEN | PASS | body={"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话", "detail": {"code": "CHAT_SESSION_FORBIDDEN", "message": "无权限访问该会话"}} |
| 9 | C3 403 错误壳含 {code,message,detail} | PASS | keys=['code', 'detail', 'message'] |
| 10 | C4 越权删除未生效（DB yn=1） | PASS | yn=1 |
| 11 | C5 学生 A 删自己 → 200 | PASS | 实际 200 |
| 12 | C6 返回体 {ok:true} | PASS | 实际 {"ok": true} |
| 13 | C7 DB 直查 yn=0（软删生效） | PASS | yn=0 |
| 14 | C8 GET /sessions → 200 | PASS | 实际 200 |
| 15 | C9 已删会话从列表消失 | PASS | sess_a=s_d3d249f9bd64 in list=False |
| 16 | C10 已删会话历史 → 404 | PASS | 实际 404 |
| 17 | C11 历史 404 错误壳 code=CHAT_SESSION_NOT_FOUND | PASS | body={"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_d3d249f9bd64", "detail": {"code": "CHAT_SESSION_NOT_FOUND", "message": "会话不存在：s_d3d249f9bd64"}} |
| 18 | C12 幂等：重复删除 → 404 | PASS | 实际 404 |
| 19 | D1 非 s_ 前缀 session_id → 404 | PASS | 实际 404 |
| 20 | D2 SQL 注入 payload → 非 500 | PASS | 实际 404（参数化 SQL 应安全） |
| 21 | D3 错误统一走 {code,message,detail} 壳 | PASS |  |
| 22 | D4 全链路无 500 | PASS | 共采集 9 个响应，均 <500 |

