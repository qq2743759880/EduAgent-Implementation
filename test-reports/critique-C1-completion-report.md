# W2 批判 C1 —— OpenAPI 响应壳契约上移 · 完工报告（后端）

> 任务：把"响应壳 {code,message,data}"从上到运行时黑盒兜底，**上移到 OpenAPI 契约声明层**，
> 使 `/docs`（`/openapi.json`）对每个 2xx 的 `application/json` 响应 schema 展开为壳，与运行实体一致。
> 只改后端，不 commit。所有改动均独立实证（curl / openapi.json / TestClient / pytest）。

## 一、实现文件与逻辑

### 1. 新增 `edu-agent/app/core/openapi_shell.py`（核心机制，OpenAPI 后处理器）
- 常量：`_HTTP_METHODS`、`_SKIP_PATHS = ("/docs","/redoc","/openapi.json","/favicon.ico","/health","/metrics")`。
- `_shell_schema(data)`：把原 schema 包成 `{type:object, required:[code,message,data], properties:{code:{type:integer,const:0}, message:{type:string,const:"ok"}, data:<原schema>}}`。
- `_is_shell_schema(schema, components)`：幂等判定。已含 `code`+`data` 属性即视为壳，跳过二次包装。**兼容两类表达**：
  - 内联对象：直接看 properties 是否同时含 code/data；
  - `$ref`：解析 `#/components/schemas/<名>` 到目标组件再判 —— 否则 `response_model=Shell[...]` 生成的 `{$ref: Shell_X_}` 会被误判为未壳而**二次包裹**（实测发现并修复的双包 bug）。
  - 用「同时含 code/data」而非仅查 code，避免顶层自带 code 字段的业务 DTO 被误判为已壳而漏包（对齐 RespWrapMiddleware._is_shell 思路）。
- `install_openapi_shell(app, skip_paths=())`：覆写 `app.openapi`，遍历每个 path×method 的 responses，对**每个 2xx 的 `application/json` 内容 schema** 统一包壳（幂等）。额外 `skip_paths` 用于 SSE 端点。

### 2. `edu-agent/app/core/resp.py`（新增泛型壳类型）
- 新增 `Shell[T](BaseModel, Generic[T])`：`{code:int=0, message:str="ok", data:T│None}`，供显式 `response_model=Shell[X]` 使用，与运行时 `ok()` 一致。`resp.py` 本就不在 git 跟踪（原文件即未纳入版本控制），本次在其上新增该类。

### 3. `edu-agent/app/users/router.py`（修复裸 DTO 端点，2 处）
- `GET/PUT /api/users/me/profile`：`response_model=UserProfile` → `response_model=Shell[UserProfile]`，handler 返回改为 `ok(data=...)`，即 /docs 不再标裸 `UserProfile`。
- 其余端点（`/me`、`/me/student-profile`、`/me/learning-summary`）本就是 `dict` 或裸 dict，无需改。

### 4. `edu-agent/app/main.py`（挂载）
- 末尾 `install_openapi_shell(app, skip_paths=("/api/chat/stream",))`：SSE 端点按路径豁免。FastAPI 对无 response_model 的流式端点在 /docs 会自动生成 `application/json` 200，无法仅凭 schema 区分真 JSON 与 SSE，故显式豁免（运行时由 RespWrapMiddleware 按 content-type 豁免，二者一致）。

## 二、豁免清单
| 项 | 处理 | 原因 |
|---|---|---|
| SSE `/api/chat/stream` | 不包壳 | text/event-stream，非 JSON；openapi 里 FastAPI 默认给 application/json，按路径 `skip_paths` 豁免 |
| `/health`、`/metrics`、`/docs`、`/redoc`、`/openapi.json`、`/favicon.ico` | 不包壳 | `_SKIP_PATHS` 豁免 |
| 活动代码 `response_model=dict`（chat/mcp/users /me） | 不单独改 | dict 是通用 object，无"裸业务 DTO"问题，transform 已自动包壳 |
| `app/_archived/question_admin/` | 整体豁免 | 归档目录（任务规定不处理） |
| `app/rerank_service/main.py` | 整体豁免 | 独立 sidecar 服务（端口 8003），不属于主 8000 app 的运行壳体系 |

## 三、/docs 壳形态 curl 证据

**进程内（真实 app，`app.openapi()`）验证：**
```
=== users/me/profile GET/PUT（原裸 UserProfile）===
  GET  /api/users/me/profile  200 -> schema = {"$ref": "#/components/schemas/Shell_UserProfile_"}   （壳组件，data=UserProfile，不再是裸 UserProfile）
  PUT  /api/users/me/profile  200 -> schema = {"$ref": "#/components/schemas/Shell_UserProfile_"}
  Shell_UserProfile_ = {properties:{code,message,data:{anyOf:[UserProfile,null]}}}   （单层壳，无二次包裹）
=== ok() 列表/普通端点 ===
  GET  /api/users/me              200 -> SHELL  required:[code,message,data], code.const=0, msg.const="ok"
  GET  /api/users/me/learning-summary  200 -> SHELL  同上
  GET  /api/chat/sessions         200 -> SHELL  同上
  POST /api/chat                  200 -> SHELL  同上
=== SSE /api/chat/stream           200 -> 不包壳（props 无 code/data）===
=== /health、/metrics              200 -> 不包壳 ===
```

**curl 实测（真实 HTTP 8000）：**
- `GET /api/users/me/profile`（Bearer token）→ `{code:0, message:"ok", data:{nickname:..., weekly_available_hours:15,...}}`，顶层仅 code/message/data 三键，`data` 无二级 code → 单层壳、未双包。
- `GET /api/chat/sessions`（Bearer token）→ `{code:0, message:"ok", data:[...]}`，`data` 为列表。
- 幂等测试实测 409 错误体仍为壳 `{"code":"40920","message":"...","data":null}`。

## 四、pytest / 冒烟输出
- `tests/test_chat_delete.py tests/test_chat_stream_error.py tests/test_auth_service.py` → **36 passed**。
- test-reports 独立实证脚本 `_c1_verify_transform.py`（覆盖 5 类形态：裸DTO包壳 / Shell泛型不双包 / ok(dict)列表包壳 / SSE与health豁免）→ **ALL PASS**。
- TestClient 冒烟（真实中间件栈）：`GET /api/users/me/profile` 单层壳、`GET /api/users/me` 壳且未双包、`GET /api/health` 保持未包壳原体。
- 说明：`test_contract_middleware.py` / `test_contract_all_routers.py` 为**直连 live 后端**的集成测试，运行中多例因端口/种子数据环境差异（10061 connection refused、已满员 409）失败，**与本次改动无关**（其中幂等用例仍实测返回合法壳 40920，反证运行壳行为完好）。

## 五、git grep response_model= 裸 DTO 清零证据
```
活动代码非 dict/非 None 的 response_model：
  edu-agent/app/users/router.py:24  @router.get ("/me/profile", response_model=Shell[UserProfile])   ✓ 已壳化
  edu-agent/app/users/router.py:31  @router.put("/me/profile", response_model=Shell[UserProfile])   ✓ 已壳化
其余（chat/mcp/router、users/me、_archived/question_admin、rerank_service）均为 dict / 归档 / 独立服务，见豁免清单。
```
**结论：活动代码中已无"裸业务 DTO 作 response_model 却运行时被包壳"的声明。**

## 六、对运行期与既有契约影响（应=无影响）
- **运行期：无影响。** 未改动 RespWrapMiddleware / 任何 HTTP 响应实体。profile 端点的最终响应体在改造前（中间件包壳）与改造后（FastAPI 经 `Shell` 序列化 + 中间件对壳幂等透传）均为同一单层 `{code:0,message:"ok",data:profile}`；curl 实测确认。
- **既有契约：无破坏。** 对各 2xx JSON 端点 /docs 从"裸 DTO/裸 dict"变为"壳"，与运行实体一致（正向对齐）；code=0/message="ok" 常量与运行 `ok()` 一致。
- **新增能力点**：`$ref` 感知的幂等判定（避免 `response_model=Shell[...]` 二次包裹）与任意 2xx JSON schema 的通用包壳，使后续新增业务 DTO 端点即使漏声明壳，/docs 也会自动对齐运行时。

## 七、资产消费证据（tt 纪律要求）
- **Skill 加载**：动手前已通过 Skill 工具加载 **`harden`**（C:\Users\Administrator\.agents\skills\harden），其方法论指导了本次改动：
  - 「防御/健壮性优先」→ transform 对"FastAPI 实际会生成的 `$ref` 表达"做幂等判定，实测捕获并修复了 `response_model=Shell[X]` 会二次包裹的双包 bug；
  - 「处理真实世界形态而非理想数据」→ 发现 FastAPI 会给 SSE 端点自动生成 `application/json` 200，无法仅凭 schema 区分真 JSON 与流式，故引入显式 `skip_paths` 豁免；
  - 「边界/豁免清单」→ `_SKIP_PATHS` + 内容类型/路径豁免对齐 RespWrapMiddleware，双端一致。
- **改动前状态**：直接读取 `app/main.py`、`app/users/router.py`、`app/core/resp.py`、`app/middleware/resp_wrap.py`、`app/chat/router.py`，据此设计上移机制，未臆测。
- **可重跑证据**：`test-reports/_c1_verify_transform.py`（机制级 5 用例）＋上文 curl/openapi 实证命令。

## 待办（不属本任务）
- 未 commit（任务要求）。已完成/未完成工程由编排者复核后统一收敛。