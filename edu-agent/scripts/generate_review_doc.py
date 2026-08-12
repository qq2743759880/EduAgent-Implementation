"""
生成 P0 知识复习文档(.docx)。
把今天会话里讲过的所有知识点整理成一份可离线复习的文档。

用法:
    python scripts/generate_review_doc.py
"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor


# ============================================================
# 文档内容数据结构
# ============================================================
# 每个章节是一个 dict:title / sections
# sections 是 list,每项是 dict:type + content
# type: heading / paragraph / code / bullet / numbered / table


def add_heading(doc, text, level=1):
    doc.add_heading(text, level=level)


def add_paragraph(doc, text, bold=False):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    return p


def add_code_block(doc, code):
    p = doc.add_paragraph()
    run = p.add_run(code)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    # 给代码块加浅灰背景(通过段落的 shading)
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F5F5F5")
    pPr.append(shd)
    return p


def add_bullets(doc, items):
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def add_numbered(doc, items):
    for item in items:
        doc.add_paragraph(item, style="List Number")


def add_table(doc, headers, rows):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Light Grid Accent 1"
    # 表头
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    # 数据行
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            table.rows[r].cells[c].text = str(val)


# ============================================================
# 生成文档
# ============================================================
def build_document():
    doc = Document()

    # ── 封面 ──────────────────────────────────────────
    title = doc.add_heading("EduAgent P0 知识点复习手册", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = sub.add_run("FastAPI · lifespan · 中间件 · 异步编程 · 信号处理")
    run.italic = True
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    date_p = doc.add_paragraph()
    date_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date_p.add_run("整理日期:2026-08-07").italic = True

    doc.add_paragraph()  # 空行

    # ── 目录概览 ──────────────────────────────────────
    add_heading(doc, "目录", level=1)
    add_bullets(doc, [
        "第 1 章 鉴权中间件与 trace_id 注入",
        "第 2 章 lifespan 生命周期管理",
        "第 3 章 中间件执行机制(洋葱模型)",
        "第 4 章 await 与异步编程原理",
        "第 5 章 字符串与 HTTP 头基础",
        "第 6 章 数据库连接池",
        "第 7 章 ASGI 服务器与端点函数",
        "第 8 章 CORS 与鉴权的区别",
        "第 9 章 signal handler 与关闭流程",
        "第 10 章 完整生命周期时序图",
        "附录 A:关键代码位置速查",
        "附录 B:常见疑问速查表",
    ])

    doc.add_page_break()

    # ============================================================
    # 第 1 章 鉴权中间件与 trace_id 注入
    # ============================================================
    add_heading(doc, "第 1 章 鉴权中间件与 trace_id 注入", level=1)

    add_heading(doc, "1.1 AuthMiddleware 做了什么", level=2)
    add_paragraph(doc, "AuthMiddleware 给每个请求加了三件事:")
    add_table(doc,
        ["#", "加了什么", "作用"],
        [
            ["1", "trace_id 上下文", "生成唯一 ID 存入 ContextVar,业务代码日志可用"],
            ["2", "X-Trace-Id 响应头", "前端可追踪问题,报错时拿这个 ID 查日志"],
            ["3", "鉴权过滤", "非 DEBUG 模式下检查 Authorization 头,不合法返回 401"],
        ])

    add_heading(doc, "1.2 鉴权跳过的两种情况", level=2)
    add_paragraph(doc, "代码位置:app/common/auth.py 第 52-62 行")
    add_code_block(doc, """# 第一段:路径白名单跳过(L52-56)
if request.url.path in self.SKIP_PATHS:
    response = await call_next(request)      # 不验证 token,直接放行
    response.headers["X-Trace-Id"] = tid
    return response

# 第二段:DEBUG 模式跳过(L59-62)
if settings.DEBUG:
    response = await call_next(request)      # 同样不验证 token,直接放行
    response.headers["X-Trace-Id"] = tid
    return response""")
    add_paragraph(doc, "两段跳过的区别:")
    add_table(doc,
        ["跳过条件", "谁能享受跳过", "什么时候生效"],
        [
            ["path in SKIP_PATHS", "/health、/docs 等白名单路径", "永远生效(不管 DEBUG)"],
            ["settings.DEBUG", "所有路径", "只在开发模式生效"],
        ])

    add_heading(doc, "1.3 SKIP_PATHS 白名单", level=2)
    add_paragraph(doc, "SKIP_PATHS = {/health, /health/detail, /docs, /redoc, /openapi.json, /}")
    add_bullets(doc, [
        "/health、/health/detail:监控系统要在无 token 情况下探测服务是否存活",
        "/docs、/redoc、/openapi.json:Swagger 文档本身就是公开的",
        "/:根路径",
    ])

    add_heading(doc, "1.4 trace_id 的两种用途", level=2)
    add_table(doc,
        ["用途", "载体", "代码"],
        [
            ["程序内部传递", "trace_id_var (ContextVar)", "trace_id_var.set(tid)"],
            ["对外暴露", "X-Trace-Id 响应头", "response.headers['X-Trace-Id'] = tid"],
        ])
    add_paragraph(doc, "为什么用 X-Trace-Id 而不是直接塞 tid:")
    add_bullets(doc, [
        "响应头是键值对,必须有键名;X-Trace-Id 是约定俗成的自定义头名",
        "X- 前缀表示自定义头(RFC 6648 之前的约定)",
        "业界最常用 X-Trace-Id 或 X-Request-Id,前端运维一看就懂",
    ])

    add_heading(doc, "1.5 ContextVar vs 普通全局变量", level=2)
    add_paragraph(doc, "普通变量在多协程环境下,每个请求会互相覆盖。ContextVar 是 Python 异步安全的'协程本地存储',每个请求的 set(tid) 只对当前请求可见,不会串。")

    doc.add_page_break()

    # ============================================================
    # 第 2 章 lifespan 生命周期管理
    # ============================================================
    add_heading(doc, "第 2 章 lifespan 生命周期管理", level=1)

    add_heading(doc, "2.1 lifespan 的本质", level=2)
    add_paragraph(doc, "@asynccontextmanager 装饰器让 lifespan() 变成异步上下文管理器:")
    add_bullets(doc, [
        "yield 之前的代码 = __aenter__(进入上下文时执行一次)",
        "yield 之后的代码 = __aexit__(退出上下文时执行一次)",
        "yield 期间 = 服务正常运行,处理请求",
    ])

    add_heading(doc, "2.2 yield 之前做什么(启动阶段)", level=2)
    add_paragraph(doc, "代码位置:app/main.py 第 37-74 行")
    add_table(doc,
        ["行号", "做了什么", "关键知识"],
        [
            ["L37", "打日志'正在启动'", "可删,纯日志"],
            ["L42", "建 db_status 字典", "收集每个库的初始化结果"],
            ["L44-52", "初始化 MySQL", "await init_mysql() 建 aiomysql 连接池"],
            ["L54-62", "初始化 Milvus", "init_milvus() 建 MilvusClient"],
            ["L64-72", "初始化 MongoDB", "await init_mongo() 建 AsyncIOMotorClient"],
            ["L74", "打印汇总状态", "日志显示三个库的状态"],
        ])

    add_heading(doc, "2.3 yield 做什么(运行阶段)", level=2)
    add_paragraph(doc, "yield 本身不做事,但它是分水岭。yield 期间服务对外提供 API,所有路由在此时可用。")
    add_paragraph(doc, "重要:yield 不是'跳转'或'阻塞',是'交控制权'给 FastAPI,生命周期函数暂停。")

    add_heading(doc, "2.4 yield 之后做什么(关闭阶段)", level=2)
    add_paragraph(doc, "代码位置:app/main.py 第 80-95 行")
    add_table(doc,
        ["行号", "做了什么", "关键知识"],
        [
            ["L80", "打日志'服务正在关闭'", ""],
            ["L82-85", "关 MySQL", "await close_mysql(),try/except: pass 防御"],
            ["L86-89", "关 MongoDB", "await close_mongo()"],
            ["L90-93", "关 Milvus", "close_milvus()(同步函数,不加 await)"],
            ["L95", "打日志'已安全关闭'", ""],
        ])

    add_heading(doc, "2.5 全局单例如何跟 yield 关联", level=2)
    add_paragraph(doc, "关联点只有一个:yield 之前初始化,yield 之后关闭。")
    add_code_block(doc, """# database.py 模块级变量 = 全局单例
_mysql_pool: Pool | None = None
_milvus_client: MilvusClient | None = None
_mongo_client: AsyncIOMotorClient | None = None

# init 函数把变量从 None 变成已连接对象
async def init_mysql():
    global _mysql_pool
    _mysql_pool = await create_pool(...)

# close 函数把变量变回 None
async def close_mysql():
    global _mysql_pool
    if _mysql_pool:
        _mysql_pool.close()
        _mysql_pool = None""")
    add_paragraph(doc, "生命周期:")
    add_code_block(doc, """lifespan:
  ├── 启动阶段: 创建全局单例(_mysql_pool 等)
  ├── 运行阶段: yield 暂停,路由访问这些单例
  └── 关闭阶段: 销毁全局单例""")

    add_heading(doc, "2.6 为什么数据库初始化放 lifespan 里", level=2)
    add_bullets(doc, [
        "保证顺序:FastAPI 在路由可访问前先走完 lifespan 启动,避免'路由可访问但数据库没连上'的竞态",
        "优雅关闭:进程被 SIGTERM 时,FastAPI 自动触发 __aexit__,执行 yield 之后的清理代码",
        "可观测:日志里清清楚楚看到启动了哪些库、状态是什么",
    ])

    add_heading(doc, "2.7 try/except 的两种写法对比", level=2)
    add_table(doc,
        ["", "启动阶段", "关闭阶段"],
        [
            ["目标", "尽可能连接所有库", "尽可能关闭所有库"],
            ["失败后", "记录日志 + 决定 raise 或继续", "静默忽略,继续关下一个"],
            ["为什么不同", "启动时数据库不可用 = 服务没用", "关闭时网络可能已断,报错是预期内的"],
            ["写法", "except Exception as e: 记录 + 条件raise", "except Exception: pass"],
        ])

    doc.add_page_break()

    # ============================================================
    # 第 3 章 中间件执行机制
    # ============================================================
    add_heading(doc, "第 3 章 中间件执行机制(洋葱模型)", level=1)

    add_heading(doc, "3.1 洋葱模型", level=2)
    add_paragraph(doc, "FastAPI 中间件是一层套一层的洋葱,请求从外到内,响应从内到外:")
    add_code_block(doc, """请求 →  AuthMiddleware →  CORSMiddleware  →  路由  →  端点函数
                                                                    │
响应 ←  AuthMiddleware ←  CORSMiddleware  ←  路由  ←────────────────┘""")

    add_heading(doc, "3.2 call_next 是什么", level=2)
    add_paragraph(doc, "call_next(request) 的作用:把请求传给下一层处理,等它处理完拿到响应。")
    add_paragraph(doc, "重要:call_next 不是 lifespan 里的方法,也不是 Python 自带的。它是 Starlette 的 BaseHTTPMiddleware 父类提供的回调函数,通过方法参数注入进来。")

    add_heading(doc, "3.3 中间件注册顺序 vs 执行顺序", level=2)
    add_paragraph(doc, "代码位置:app/main.py 第 109-121 行")
    add_code_block(doc, """# 后注册的先执行(对请求而言)
app.add_middleware(CORSMiddleware, ...)   # 后注册 → 请求时后执行
app.add_middleware(AuthMiddleware)        # 先注册 → 请求时先执行""")
    add_paragraph(doc, "请求处理顺序:AuthMiddleware → CORSMiddleware → 路由")
    add_paragraph(doc, "响应处理顺序:路由 → CORSMiddleware → AuthMiddleware")

    add_heading(doc, "3.4 dispatch 方法签名", level=2)
    add_code_block(doc, """class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # request:当前请求对象
        # call_next:框架注入的回调,调它就交给下一层
        response = await call_next(request)
        return response""")
    add_paragraph(doc, "识别框架注入参数的方法:看方法签名里的参数,如果代码里没给它赋值,就是框架自动注入的。")

    doc.add_page_break()

    # ============================================================
    # 第 4 章 await 与异步编程原理
    # ============================================================
    add_heading(doc, "第 4 章 await 与异步编程原理", level=1)

    add_heading(doc, "4.1 await 的精确定义", level=2)
    add_paragraph(doc, "await 只能用在 async def 函数里,后面必须跟一个 awaitable 对象(通常是 coroutine)。它做两件事:")
    add_numbered(doc, [
        "暂停当前函数的执行,把控制权还给事件循环(event loop)",
        "等 awaitable 完成后,恢复当前函数继续往下执行",
    ])

    add_heading(doc, "4.2 关键误区:await 不是'启动新任务'", level=2)
    add_paragraph(doc, "await func() 不是'启动 func() 在后台跑,我等它'。A 和 B 是串行的,A 暂停期间 B 在跑,B 跑完 A 才恢复。")
    add_code_block(doc, """async def A():
    print("A 开始")
    result = await B()         # A 暂停,B 开始
    print(f"A 拿到结果: {result}")

async def B():
    print("B 开始")
    await asyncio.sleep(1)     # B 暂停,等 1 秒
    print("B 结束")
    return 42""")

    add_heading(doc, "4.3 '让出资源'的真正含义", level=2)
    add_paragraph(doc, "'让出资源'指的是:当 B 自己也在等 I/O 时(等网络响应、等数据库返回),B 会把控制权交还给事件循环,事件循环可以去做别的事。")
    add_paragraph(doc, "异步并发的本质:单线程下,通过 I/O 等待时让出控制权,实现并发。")

    add_heading(doc, "4.4 三种情况对照", level=2)
    add_table(doc,
        ["写法", "是否让出控制权", "说明"],
        [
            ["await coroutine()", "✅ 让出", "当前函数暂停,coroutine 执行,期间事件循环可做别的"],
            ["await asyncio.gather(a(), b())", "✅ 让出", "a 和 b 并发执行,当前函数等它们都完成"],
            ["time.sleep(1)", "❌ 不让出", "阻塞整个事件循环,其他协程都卡住,千万别用"],
            ["asyncio.sleep(1)", "✅ 让出", "异步 sleep,让出控制权给事件循环"],
        ])

    add_heading(doc, "4.5 不加 await 会怎样", level=2)
    add_paragraph(doc, "async def 函数不加 await 调用,返回 coroutine 对象但函数体不执行。")
    add_code_block(doc, """# 不加 await:
init_mysql()
# 返回:<coroutine object init_mysql at 0x...>
# 函数体根本没执行!_mysql_pool 还是 None!

# 加 await:
await init_mysql()
# 1. 返回 coroutine 对象
# 2. await 立即开始执行它
# 3. 等它执行完
# 4. _mysql_pool 被赋值成连接池对象""")
    add_paragraph(doc, "一句话规则:async def 定义的函数,必须用 await 调用才会执行。")

    add_heading(doc, "4.6 怎么判断要不要 await", level=2)
    add_bullets(doc, [
        "看函数定义:async def → 要 await",
        "def → 直接调,不能 await",
        "例:init_mysql() 是 async def → 要 await;init_milvus() 是 def → 直接调",
    ])

    doc.add_page_break()

    # ============================================================
    # 第 5 章 字符串与 HTTP 头基础
    # ============================================================
    add_heading(doc, "第 5 章 字符串与 HTTP 头基础", level=1)

    add_heading(doc, "5.1 HTTP Authorization 头的标准格式", level=2)
    add_code_block(doc, """Authorization: <认证方案> <凭证>
              ↑      ↑
           方案名   空格   token""")
    add_table(doc,
        ["方案", "例子", "用途"],
        [
            ["Bearer", "Authorization: Bearer eyJhbGc...", "JWT token(OAuth 2.0)"],
            ["Basic", "Authorization: Basic dXNlcjpwYXNz", "用户名密码(Base64 编码)"],
            ["Digest", "Authorization: Digest username=\"...\"", "摘要认证"],
        ])

    add_heading(doc, "5.2 为什么是 'Bearer ' 不是 'Bearer'", level=2)
    add_paragraph(doc, "HTTP 协议规定空格是方案名和凭证的分隔符。如果没有空格,解析器无法知道哪里是方案名结束、哪里是 token 开始。")
    add_code_block(doc, """auth_header = "Bearer eyJhbGc..."
auth_header.startswith("Bearer ")  # True

auth_header = "BearereyJhbGc..."   # 没空格
auth_header.startswith("Bearer ")  # False

auth_header = "Basic dXNlcg=="     # 别的方案
auth_header.startswith("Bearer ")  # False""")

    add_heading(doc, "5.3 字符串里的空字符串 ''", level=2)
    add_paragraph(doc, "空字符串是长度为 0 的字符串。常见用法:")
    add_table(doc,
        ["用法", "含义", "例子"],
        [
            ["默认值", "防止 None 导致后续操作报错", "dict.get(key, '')"],
            ["字符串拼接", "起始值,后面 .join 或 +=", "result = ''; result += 'a'"],
            ["布尔判断", "空字符串是 falsy", "if not auth_header: ..."],
            ["占位", "暂时占位,后面赋值", "token = ''; if not token: return 401"],
        ])

    add_heading(doc, "5.4 request.headers.get(key, default) 的作用", level=2)
    add_code_block(doc, """auth_header = request.headers.get("Authorization", "")
# 尝试从请求头取 Authorization
# 如果没有,返回默认值 ''(空字符串)
# 为什么默认值是 '' 而不是 None:
#   None.startswith(...) 会报 AttributeError
#   ''.startswith(...) 返回 False,流程继续""")

    add_heading(doc, "5.5 removeprefix 删除前缀", level=2)
    add_paragraph(doc, "Python 3.9+ 的字符串方法,删除前缀:")
    add_code_block(doc, """"Bearer eyJhbGc...".removeprefix("Bearer ")   # → "eyJhbGc..."
"Bearer eyJhbGc...".removeprefix("Bearer")    # → " eyJhbGc..."(还多个空格)
"Basic dXNlcg==".removeprefix("Bearer ")      # → "Basic dXNlcg=="(没匹配,原样返回)""")

    doc.add_page_break()

    # ============================================================
    # 第 6 章 数据库连接池
    # ============================================================
    add_heading(doc, "第 6 章 数据库连接池", level=1)

    add_heading(doc, "6.1 连接池是什么", level=2)
    add_paragraph(doc, "建连接池 = 后端和数据库的连接建立了,但不是'建一条连接',是'建一堆连接备用'。")
    add_table(doc,
        ["", "没连接池", "有连接池"],
        [
            ["每次查询", "建 TCP(50ms)→ 认证(10ms)→ SQL → 关 TCP", "从池借连接(0ms)→ SQL → 还回池子"],
            ["问题", "每次建/关连接,开销大", "连接复用,开销小"],
        ])

    add_heading(doc, "6.2 你项目里的连接池配置", level=2)
    add_paragraph(doc, "代码位置:app/database.py 第 28-45 行")
    add_code_block(doc, """async def init_mysql():
    global _mysql_pool
    _mysql_pool = await create_pool(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DATABASE,
        charset=settings.MYSQL_CHARSET,
        autocommit=False,
        pool_recycle=settings.MYSQL_POOL_RECYCLE,
        minsize=1,                        # 池子最少保持 1 条连接
        maxsize=settings.MYSQL_POOL_SIZE, # 最多 5 条(默认)
    )""")

    add_heading(doc, "6.3 三个数据库的池子对比", level=2)
    add_table(doc,
        ["数据库", "客户端", "连接池机制"],
        [
            ["MySQL", "aiomysql", "create_pool 显式建池子"],
            ["Milvus", "MilvusClient", "客户端内部维护连接(不显式建池)"],
            ["MongoDB", "AsyncIOMotorClient", "客户端内部维护连接池"],
        ])

    add_heading(doc, "6.4 什么时候真正用连接", level=2)
    add_paragraph(doc, "连接池是'水管',SQL 查询是'水流'。建池子是铺水管,水管铺好了,以后用水(查 SQL)随时开龙头。")
    add_code_block(doc, """pool = get_mysql_pool()              # 拿到池子
async with pool.acquire() as conn:   # 从池子借一条连接
    async with conn.cursor() as cur:
        await cur.execute("SELECT 1") # 真正用这条连接执行 SQL
# 离开 async with,连接自动还回池子""")

    doc.add_page_break()

    # ============================================================
    # 第 7 章 ASGI 服务器与端点函数
    # ============================================================
    add_heading(doc, "第 7 章 ASGI 服务器与端点函数", level=1)

    add_heading(doc, "7.1 端点函数是什么", level=2)
    add_paragraph(doc, "端点函数 = 处理某个 URL 请求的 Python 函数。就是 async def xxx() 加上 @app.get(...) 装饰器。")
    add_table(doc,
        ["URL", "端点函数", "代码位置"],
        [
            ["GET /", "root()", "app/main.py 第 160-162 行"],
            ["GET /health", "health_check()", "app/routers/health.py"],
            ["GET /health/detail", "health_detail()", "同上"],
        ])

    add_heading(doc, "7.2 ASGI 是什么", level=2)
    add_paragraph(doc, "ASGI = Asynchronous Server Gateway Interface(异步服务器网关接口)。")
    add_paragraph(doc, "它是一套协议约定,规定了'HTTP 服务器怎么把请求传给 Python 应用'。")
    add_code_block(doc, """浏览器请求 GET /health
       ↓
┌──────────────────────────┐
│  ASGI 服务器(uvicorn)    │  监听 8000 端口,接 TCP 连接
│                          │  解析 HTTP 字节流
│  把请求包装成 ASGI 格式:   │
│  {                       │
│    "type": "http",       │
│    "method": "GET",      │
│    "path": "/health",    │
│    "headers": [...],     │
│  }                       │
└────────────┬─────────────┘
             ↓ 按 ASGI 协议调用
┌──────────────────────────┐
│  FastAPI 应用(app)       │  接收 ASGI 格式的请求
│                          │
│  1. 走中间件链            │
│  2. 路由匹配              │
│  3. 调端点函数            │
│  4. 把返回值转 ASGI 格式   │
└────────────┬─────────────┘
             ↓ 返回 ASGI 格式响应
┌──────────────────────────┐
│  uvicorn                 │  把 ASGI 响应转回 HTTP 字节流
│                          │  发回浏览器
└──────────────────────────┘""")

    add_heading(doc, "7.3 uvicorn 的职责", level=2)
    add_bullets(doc, [
        "监听 8000 端口,接 TCP 连接",
        "解析 HTTP 请求字节流,转成 Python 对象",
        "调用 FastAPI 的 ASGI 接口处理请求",
        "把 FastAPI 返回的响应转成 HTTP 字节流发回去",
        "管理进程生命周期(启动、接收信号、优雅关闭)",
    ])

    add_heading(doc, "7.4 为什么 FastAPI 不能直接监听端口", level=2)
    add_paragraph(doc, "FastAPI 只是个符合 ASGI 协议的 Python 对象,它知道:")
    add_bullets(doc, [
        "怎么走路由",
        "怎么调端点函数",
        "怎么处理中间件",
    ])
    add_paragraph(doc, "但它不知道:")
    add_bullets(doc, [
        "怎么监听 TCP 端口",
        "怎么解析 HTTP 字节流",
        "怎么管理并发连接",
    ])
    add_paragraph(doc, "这些'脏活累活'由 uvicorn 做。这是关注点分离的设计。")

    add_heading(doc, "7.5 类比", level=2)
    add_bullets(doc, [
        "uvicorn = 餐厅的建筑 + 服务员(接客、传菜)",
        "FastAPI = 餐厅的厨房 + 菜单(做菜逻辑)",
        "你的代码 = 菜谱(具体每道菜怎么做)",
    ])

    doc.add_page_break()

    # ============================================================
    # 第 8 章 CORS 与鉴权的区别
    # ============================================================
    add_heading(doc, "第 8 章 CORS 与鉴权的区别", level=1)

    add_heading(doc, "8.1 CORS 是什么", level=2)
    add_paragraph(doc, "CORS = Cross-Origin Resource Sharing(跨源资源共享)。")
    add_paragraph(doc, "问题场景:浏览器同源策略规定,https://a.com 的网页默认不能请求 https://b.com 的 API。这是浏览器为了防止恶意网站偷数据。")
    add_paragraph(doc, "你的场景:前端 http://localhost:3000,后端 http://localhost:8000。端口不同 = 不同源 = 浏览器默认拦截。")

    add_heading(doc, "8.2 CORS 中间件干的事", level=2)
    add_paragraph(doc, "代码位置:app/main.py 第 112-118 行")
    add_code_block(doc, """app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)""")
    add_paragraph(doc, "CORS 中间件做的事:后端在响应头里加 Access-Control-Allow-Origin,告诉浏览器'我允许 a.com 访问我'。")

    add_heading(doc, "8.3 CORS vs 鉴权的区别", level=2)
    add_table(doc,
        ["", "CORS", "鉴权(AuthMiddleware)"],
        [
            ["谁检查", "浏览器(前端)", "服务器(后端)"],
            ["防什么", "防恶意网页偷数据", "防未登录用户访问 API"],
            ["怎么放行", "后端响应加 CORS 头", "后端检查 Token"],
            ["失败表现", "浏览器控制台报 CORS 错,但请求其实到了后端", "后端返回 401"],
        ])

    add_heading(doc, "8.4 curl 测试为什么不受 CORS 限制", level=2)
    add_paragraph(doc, "因为 CORS 是浏览器强制执行的,curl 不理这一套。所以用 curl 测 API,永远不会有 CORS 错误。CORS 错误只在浏览器里才会出现。")

    doc.add_page_break()

    # ============================================================
    # 第 9 章 signal handler 与关闭流程
    # ============================================================
    add_heading(doc, "第 9 章 signal handler 与关闭流程", level=1)

    add_heading(doc, "9.1 常见信号", level=2)
    add_table(doc,
        ["信号", "编号", "含义", "触发方式"],
        [
            ["SIGINT", "2", "中断", "Ctrl+C"],
            ["SIGTERM", "15", "请求终止", "kill <pid> / systemctl stop"],
            ["SIGKILL", "9", "强制终止", "kill -9 <pid>(不可拦截)"],
            ["SIGHUP", "1", "挂起", "终端关闭"],
        ])

    add_heading(doc, "9.2 signal handler 是什么", level=2)
    add_paragraph(doc, "signal handler 是程序里专门处理某种信号的函数。Python 里用 signal 模块注册:")
    add_code_block(doc, """import signal

def my_handler(signum, frame):
    print(f"收到信号 {signum},开始清理...")

signal.signal(signal.SIGTERM, my_handler)  # 注册:收到 SIGTERM 时调 my_handler""")
    add_paragraph(doc, "进程运行时,操作系统如果给它发 SIGTERM,会立即中断当前执行,跳去运行 my_handler。")

    add_heading(doc, "9.3 你的代码里有 signal handler 吗", level=2)
    add_paragraph(doc, "没有!signal handler 是 uvicorn 内部的代码,不在这个项目里。", bold=True)
    add_table(doc,
        ["代码", "谁写的", "在哪"],
        [
            ["app/main.py", "你", "你的项目"],
            ["app/common/auth.py", "你", "你的项目"],
            ["uvicorn 的 signal handler", "uvicorn 开发团队", "uvicorn 包里"],
        ])

    add_heading(doc, "9.4 uvicorn 在哪里注册 signal handler", level=2)
    add_paragraph(doc, "uvicorn 的 Server.install_signal_handlers() 方法,位于:")
    add_code_block(doc, "Z:/anaconda3/envs/kb311/Lib/site-packages/uvicorn/server.py")
    add_paragraph(doc, "大致逻辑:")
    add_code_block(doc, """# uvicorn/server.py 大致逻辑(伪代码)
import signal

class Server:
    def install_signal_handlers(self):
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.handle_exit, sig, None)

    def handle_exit(self, sig, frame):
        self.should_exit = True   # 设置退出标志
        # 主循环检测到这个标志,开始优雅关闭""")

    add_heading(doc, "9.5 完整信号传递链", level=2)
    add_code_block(doc, """1. 你按 Ctrl+C
       ↓
2. 操作系统给 uvicorn 进程发 SIGINT
       ↓
3. uvicorn 注册的 signal handler 被调用
   (这个 handler 在 uvicorn 包里,不在你项目里)
       ↓
4. handler 设置 should_exit = True
       ↓
5. uvicorn 主循环检测到 should_exit
       ↓
6. uvicorn 触发 ASGI lifespan 的 shutdown 事件
       ↓
7. FastAPI 收到 shutdown 事件,调用你的 lifespan 函数的 __aexit__
       ↓
8. 你的 lifespan 函数从 yield 恢复执行
       ↓
9. 执行 main.py 第 82-93 行的关闭代码:
   ├── close_mysql()
   ├── close_mongo()
   └── close_milvus()""")

    add_heading(doc, "9.6 SIGTERM vs SIGKILL", level=2)
    add_bullets(doc, [
        "kill <pid>(默认 SIGTERM)→ 优雅关闭,你的 close 代码会跑",
        "kill -9 <pid>(SIGKILL)→ 瞬间死亡,close 代码不会跑,数据库连接被硬断",
        "生产环境永远优先用 SIGTERM,只有 SIGTERM 几十秒没反应才用 SIGKILL 兜底",
    ])

    add_heading(doc, "9.7 async with 语句的保证", level=2)
    add_paragraph(doc, "FastAPI 内部用 async with 调用 lifespan:")
    add_code_block(doc, """# FastAPI 内部伪代码
async with lifespan(app) as state:  # 进入时调用 __aenter__
    # 服务正常运行,处理请求
    # 收到 SIGTERM 时,async with 块退出
    # 退出时自动调用 __aexit__ ← 这就是关键!""")
    add_paragraph(doc, "async with 语句的最核心特性:只要 async with 块退出(无论正常结束还是异常),__aexit__ 都一定会被调用。这是 Python 语言保证的。")

    doc.add_page_break()

    # ============================================================
    # 第 10 章 完整生命周期时序图
    # ============================================================
    add_heading(doc, "第 10 章 完整生命周期时序图", level=1)

    add_heading(doc, "10.1 启动阶段(只发生一次)", level=2)
    add_numbered(doc, [
        "你执行 uvicorn app.main:app",
        "uvicorn 进程启动,import app.main,加载 app 对象",
        "uvicorn 在事件循环里注册 signal handler(SIGINT/SIGTERM → handle_exit)",
        "uvicorn 触发 ASGI startup 事件,通知 FastAPI'要启动了'",
        "FastAPI 调用 lifespan 函数的 __aenter__(即 yield 之前的代码)",
        "执行 main.py 第 37-74 行:打日志、init_mysql、init_milvus、init_mongo、打印汇总状态",
        "代码走到 yield,lifespan 函数暂停,把控制权交还 FastAPI",
        "FastAPI 通知 uvicorn'启动完成'",
        "uvicorn 开始监听 8000 端口,打印 Application startup complete.,服务就绪",
    ])

    add_heading(doc, "10.2 运行阶段(每个请求重复)", level=2)
    add_numbered(doc, [
        "浏览器/curl 发 HTTP 请求到 localhost:8000/health",
        "uvicorn 接收 TCP 连接,读取 HTTP 字节流,解析成 ASGI 消息",
        "uvicorn 把 ASGI 消息传给 FastAPI 的 app 对象",
        "FastAPI 开始走中间件链(洋葱模型,请求从外到内):AuthMiddleware → CORSMiddleware → 路由 → 端点函数",
        "AuthMiddleware.dispatch() 执行:生成 tid、设 trace_id、检查 SKIP_PATHS/DEBUG、调 call_next",
        "CORSMiddleware 执行:检查 Origin、调 call_next",
        "FastAPI 路由匹配,GET /health 命中 health_check()",
        "执行端点函数 health_check(),返回 dict",
        "响应从内到外回流:路由 → CORSMiddleware → AuthMiddleware → 返回",
        "CORSMiddleware 在响应头加 Access-Control-Allow-Origin",
        "AuthMiddleware 在响应头加 X-Trace-Id",
        "FastAPI 把最终响应转成 ASGI 消息,返回给 uvicorn",
        "uvicorn 把 ASGI 响应转回 HTTP 字节流,通过 TCP 发回客户端",
        "浏览器/curl 收到响应,包含 X-Trace-Id 头和 JSON body",
    ])

    add_heading(doc, "10.3 关闭阶段(只发生一次)", level=2)
    add_numbered(doc, [
        "你按 Ctrl+C(或 systemctl stop 发 SIGTERM)",
        "操作系统给 uvicorn 进程发送 SIGINT(或 SIGTERM)信号",
        "uvicorn 进程被中断,跳去执行它注册的 signal handler(handle_exit 函数)",
        "handle_exit 设置 should_exit = True",
        "uvicorn 主循环检测到 should_exit,停止接受新连接",
        "uvicorn 等待正在处理的请求完成(有超时,默认 5 秒)",
        "uvicorn 触发 ASGI shutdown 事件,通知 FastAPI'要关闭了'",
        "FastAPI 调用 lifespan 函数的 __aexit__(即 yield 之后的代码)",
        "lifespan 函数从 yield 处恢复,执行 main.py 第 80-95 行:打日志、close_mysql、close_mongo、close_milvus、打日志",
        "lifespan 函数 return,__aexit__ 完成",
        "FastAPI 通知 uvicorn'关闭完成'",
        "uvicorn 打印 Application shutdown complete.,进程退出",
        "终端回到提示符",
    ])

    add_heading(doc, "10.4 你能控制的 4 件事", level=2)
    add_table(doc,
        ["阶段", "触发方", "执行方", "你能控制吗"],
        [
            ["加载 app", "uvicorn", "Python import 机制", "✅ 写 app = FastAPI(...)"],
            ["注册 signal handler", "uvicorn", "uvicorn 内部", "❌ uvicorn 写死了"],
            ["lifespan 启动代码", "FastAPI", "你的 lifespan 函数", "✅ 写 yield 之前的代码"],
            ["监听端口", "uvicorn", "uvicorn 内部", "❌ 但能传 --port 参数"],
            ["中间件链", "FastAPI", "你的中间件类", "✅ 写 dispatch 方法"],
            ["端点函数", "FastAPI 路由", "你的端点函数", "✅ 写 @app.get(...)"],
            ["signal handler 触发", "OS 信号", "uvicorn 内部", "❌ 自动触发"],
            ["lifespan 关闭代码", "FastAPI", "你的 lifespan 函数", "✅ 写 yield 之后的代码"],
            ["进程退出", "uvicorn", "uvicorn 内部", "❌ 自动"],
        ])

    doc.add_page_break()

    # ============================================================
    # 附录 A:关键代码位置速查
    # ============================================================
    add_heading(doc, "附录 A:关键代码位置速查", level=1)

    add_heading(doc, "A.1 P0 项目文件清单", level=2)
    add_table(doc,
        ["文件", "作用", "关键行号"],
        [
            ["app/config.py", "配置管理(读 .env)", "Settings 类"],
            ["app/database.py", "三库连接池管理", "init_mysql 第 28-45 行"],
            ["app/main.py", "FastAPI 应用入口", "lifespan 第 29-95 行"],
            ["app/common/auth.py", "鉴权中间件 + trace_id", "AuthMiddleware 第 33 行"],
            ["app/common/exceptions.py", "自定义异常", "AppException 类"],
            ["app/common/logging.py", "loguru 日志配置", "setup_logging()"],
            ["app/routers/health.py", "健康检查接口", "health_check / health_detail"],
        ])

    add_heading(doc, "A.2 关键代码位置", level=2)
    add_table(doc,
        ["功能", "代码位置"],
        [
            ["lifespan 函数", "app/main.py 第 29-95 行"],
            ["yield 之前(启动)", "app/main.py 第 37-74 行"],
            ["yield(运行)", "app/main.py 第 77 行"],
            ["yield 之后(关闭)", "app/main.py 第 80-95 行"],
            ["AuthMiddleware 类", "app/common/auth.py 第 33 行"],
            ["trace_id 生成", "app/common/auth.py 第 49-50 行"],
            ["call_next 调用", "app/common/auth.py 第 54 行"],
            ["Bearer 检查", "app/common/auth.py 第 66 行"],
            ["X-Trace-Id 注入", "app/common/auth.py 第 55 行"],
            ["MySQL 连接池创建", "app/database.py 第 28-45 行"],
            ["CORS 中间件", "app/main.py 第 112-118 行"],
            ["全局异常处理", "app/main.py 第 125、138 行"],
        ])

    doc.add_page_break()

    # ============================================================
    # 附录 B:常见疑问速查表
    # ============================================================
    add_heading(doc, "附录 B:常见疑问速查表", level=1)

    add_table(doc,
        ["问题", "答案"],
        [
            ["call_next 哪来的?", "Starlette 的 BaseHTTPMiddleware 约定的参数,框架自动注入"],
            ["await 什么时候让出资源?", "等 I/O 时让出(网络响应、sleep 到期等);不是无脑让出"],
            ["不加 await 会怎样?", "返回 coroutine 对象但不执行函数体,后续操作全崩"],
            ["'Bearer ' 为啥带空格?", "HTTP 协议规定空格是方案名和凭证的分隔符"],
            ["'' 是啥?", "空字符串,长度为 0,常用作默认值防止 None"],
            ["连接池=建连接吗?", "是,但建的是'多条连接的池子'待命用,不是单条"],
            ["X-Trace-Id 是啥?", "响应头的键名,值是 trace_id,用于端到端追踪"],
            ["lifespan 是啥?", "FastAPI 的生命周期管理,yield 前启动、yield 后关闭"],
            ["signal handler 在哪?", "不在你项目里,在 uvicorn 包内部"],
            ["CORS = 权限吗?", "不是!CORS 是浏览器跨域检查,鉴权是后端身份检查"],
            ["ASGI 服务器是啥?", "把 HTTP 字节流翻译成 Python 调用的中间层(uvicorn)"],
            ["端点函数是啥?", "@app.get(...) 装饰的 async def 函数,处理具体 URL 请求"],
            ["DEBUG 模式是啥?", "开发友好模式:.env 里 DEBUG=true,影响日志、文档、鉴权、容错"],
            ["try/except pass 是啥?", "完全忽略错误,确保一个库关失败不阻塞其他库"],
            ["db_status 是方法吗?", "不是,是 lifespan 里的普通局部字典变量"],
        ])

    # ── 文档结尾 ──────────────────────────────────────
    doc.add_paragraph()
    end_p = doc.add_paragraph()
    end_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = end_p.add_run("— 本手册基于 EduAgent P0 阶段实施整理 —")
    run.italic = True
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

    return doc


def main():
    output_path = Path("e:/stu/project/stu/edu-agent/docs/P0_知识复习手册.docx")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = build_document()
    doc.save(str(output_path))
    print(f"文档已生成: {output_path}")
    print(f"文件大小: {output_path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
