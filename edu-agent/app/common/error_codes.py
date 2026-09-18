# -*- coding: utf-8 -*-
"""统一业务错误码值域表（task10 契约冻结① v1.1：字符串错误码，前端硬编码判断）

响应壳：{code, message, data}  — 成功 code=0 (int)，失败 code=<字符串>

码段语义：
  400xx  参数/业务规则错误
  401xx  认证/凭证
  403xx  越权/资源保护
  404xx  资源不存在
  409xx  冲突（重复编码等）
  422xx  校验失败（pydantic）
  429xx  限流
  4xx2x  交易域（trade）
  4xx3x  售后域（after_sales）
  4xx4x  学习域（study）
  5xxxx  服务端错误

口径变更记录（P6 声明）：
  v1.0→v1.1: 2026-08-18 编排者强制批判发现数字码偏离 dev-plan/doc-frontend-spec/tech-source-audit
  三重权威文档的字符串要求，经裁定改为字符串（方案 A）。
  前端 code===0 判断成功不变，失败 code !== 0 按字符串 key 映射错误提示。
  v1.1→v1.2: 2026-09-12 T19-3（contracts/reshape-b.json amendments，用户签字）纯增量新增
  50301 DEPENDENCY_UNAVAILABLE（依赖不可达业务码 + 错误响应脱敏：message 面向用户、
  原始异常仅入日志、data 恒 null；HTTP 状态码语义不变）。回滚=revert 单 commit。
"""

# ═══════════════════════════════════════════
# 成功码（int 保持不变）
# ═══════════════════════════════════════════
OK = 0

# ═══════════════════════════════════════════
# 通用码（字符串）
# ═══════════════════════════════════════════
BAD_REQUEST = "40000"              # 通用参数错误
NOT_FOUND = "40400"                # 通用资源不存在
FORBIDDEN = "40300"                # 通用无权限
CONFLICT = "40900"                 # 通用冲突
VALIDATION = "42200"               # 通用校验失败
RATE_LIMITED = "42900"             # 限流
INTERNAL_ERROR = "50000"           # 服务内部错误
SERVICE_UNAVAILABLE = "50300"      # 服务不可用
# 依赖不可达（T19-3，reshape-b 契约增补，2026-09-12 用户签字）：Milvus/MCP 等外部依赖
# 连接失败/超时时返回。message 一律面向用户（「依赖服务暂不可用，请稍后重试」），
# 原始异常仅入 logger（含堆栈），响应 data 恒为 null；HTTP 语义维持 503/500 不变。
DEPENDENCY_UNAVAILABLE = "50301"   # 依赖不可达（脱敏业务码，替代 500/50300 直泄）

# ═══════════════════════════════════════════
# HTTP 状态码 → 业务错误码 单一事实源（judge R4 裁定）
# main.py handler 与 resp_wrap.py 兜底共同引用，消灭双轨野码（如 "40100"）。
# 401 场景唯一权威默认码 = 40101（AUTH_TOKEN_INVALID，401xx 注册表自 40101 起）。
# 405 未注册 405xx 码段，归并 40000（书面豁免见 task11-contract.md）。
# ═══════════════════════════════════════════
STATUS_TO_CODE: dict[int, str] = {
    400: "40000",
    401: "40101",
    403: "40300",
    404: "40400",
    405: "40000",   # 书面豁免：405xx 码段未注册，方法不允许归通用参数错误
    409: "40900",
    422: "42200",
    429: "42900",
    500: "50000",
    503: "50300",
}

# ═══════════════════════════════════════════
# 认证域（auth）
# ═══════════════════════════════════════════
AUTH_ACCOUNT_MISSING = "40011"     # 缺少登录账号
AUTH_TOKEN_INVALID = "40101"       # 凭证无效
AUTH_TOKEN_EXPIRED = "40102"       # 凭证已过期
AUTH_TOKEN_MALFORMED = "40103"     # 凭证缺失字段
AUTH_TOKEN_TYPE_MISMATCH = "40104" # token 类型不匹配
AUTH_ROLE_INVALID = "40105"        # 角色非法
AUTH_LOGIN_FAILED = "40111"        # 账号或密码错误
AUTH_USER_DISABLED = "40312"       # 账号被禁用
AUTH_USER_NOT_FOUND = "40413"      # 用户不存在
AUTH_ACCOUNT_EXISTS = "40912"      # 账号已存在
AUTH_MOBILE_EXISTS = "40913"       # 手机号已注册
AUTH_EMAIL_EXISTS = "40914"        # 邮箱已注册

# ═══════════════════════════════════════════
# 交易域（trade）— 4xx2x
# ═══════════════════════════════════════════
TRADE_ORDER_NOT_FOUND = "40420"    # 订单不存在
TRADE_ORDER_STATUS_INVALID = "40021"  # 订单状态不允许操作
TRADE_ORDER_AMOUNT_MISMATCH = "40022"  # 金额不一致
TRADE_COUPON_EXPIRED = "40023"     # 优惠券已过期
TRADE_COUPON_EXHAUSTED = "40920"   # 优惠券已领完（task16 GWT①：第 501 起返回 40920）
TRADE_COUPON_ALREADY_USED = "40025"  # 优惠券已使用
TRADE_IDEMPOTENCY_IN_PROGRESS = "40930"  # 幂等键同一请求正在执行（并发去重，对齐 Stripe/AWS Powertools 在途锁；task39 批判 Round3）
TRADE_IDEMPOTENCY_PAYLOAD_MISMATCH = "42230"  # 幂等键复用但请求 payload 不一致（禁止借键改content重放；task39 批判 Round3）
TRADE_PAYMENT_FAILED = "40220"     # 支付失败
TRADE_PAYMENT_DUPLICATE = "40221"  # 重复支付
TRADE_REFUND_EXCEED = "40230"      # 退款金额超限
TRADE_REFUND_STATUS_INVALID = "40031"  # 退款状态不允许操作

# ═══════════════════════════════════════════
# 售后域（after_sales）— 4xx3x
# ═══════════════════════════════════════════
AFTERSALES_TICKET_NOT_FOUND = "40430"  # 工单不存在
AFTERSALES_TICKET_CLOSED = "40032"     # 工单已关闭，不可操作
AFTERSALES_SATISFACTION_DUPLICATE = "40033"  # 已评价

# ═══════════════════════════════════════════
# 学习域（study）— 4xx4x
# ═══════════════════════════════════════════
STUDY_SESSION_NOT_FOUND = "40440"   # 课次不存在
STUDY_HOMEWORK_NOT_FOUND = "40441"  # 作业不存在
STUDY_EXAM_NOT_FOUND = "40442"      # 考试不存在
STUDY_ACCESS_DENIED = "40340"       # 无学习权限（未报名）
STUDY_PROGRESS_INVALID = "40041"    # 学习进度数据异常
STUDY_REVIEW_DUPLICATE = "40044"    # 已评价过该系列（course_review 防刷，Season-2 需求 B 登记）

# ═══════════════════════════════════════════
# 课程管理域（course_admin）— 40901~40907 唯一约束冲突
# ═══════════════════════════════════════════
SERIES_CODE_CONFLICT = "40901"      # 系列编码重复（institution_id + series_code）
COHORT_CODE_CONFLICT = "40902"     # 班次编码重复（institution_id + cohort_code）
MODULE_STAGE_CONFLICT = "40903"    # 模块阶段号重复（cohort_id + stage_no）
SESSION_NO_CONFLICT = "40904"      # 课次编号重复（module_id + session_no）
ASSET_CODE_CONFLICT = "40905"      # 资源编码重复（session_id + asset_code）
VIDEO_CODE_CONFLICT = "40906"      # 视频编码重复（asset_id + video_code）
CHAPTER_NO_CONFLICT = "40907"      # 章节号重复（video_id + chapter_no）
SERIES_IN_USE = "40908"          # 系列被班次/订单引用，禁止真删（hard delete 前置校验）

# ═══════════════════════════════════════════
# 题库域（question_admin）— 40921~40929（task13 唯一约束 + F-8 引用保护）
# ═══════════════════════════════════════════
BANK_CODE_CONFLICT = "40921"       # 题库编码重复（institution_id + bank_code）
QUESTION_CODE_CONFLICT = "40922"   # 题目编码重复（bank_id + question_code）
EXAM_CODE_CONFLICT = "40923"       # 考试编码重复（session_id + exam_code）
BANK_IN_USE = "40924"              # 题库内仍有有效题目，禁止直接删除（F-8：force=true 级联软删）

# ═══════════════════════════════════════════
# HITL 人机协作域（chat hitl）— 4045x（R11，contracts/reshape-r-hitl.json 冻结 2026-09-15）
# 语义：POST /api/chat/resume 未找到挂起中的 thread_id（未知 / TTL 过期自动失效）→「确认已超时」。
# HTTP 404（404xx 码段 → _http_status_for_code 自动映射）。
# ═══════════════════════════════════════════
CHAT_HITL_THREAD_NOT_FOUND = "40450"   # HITL 确认超时/线程不存在（resume 未知或过期 thread_id）

# ═══════════════════════════════════════════
# 问答/LLM 下游域（chat/llm）— 5001x（流式"建连后"错误通道专用，W2 批判 C3 登记 2026-09-04）
# 语义：SSE 连接建立后，token 迭代 / 落库阶段的失败不再固定 50000 单调或静默 degraded_reason，
# 统一走 `event: error` 并携带可区分 subcode。映射规则见 router._map_stream_exception。
# ═══════════════════════════════════════════
LLM_AUTH = "50011"            # LLM 下游认证/密钥失效（401/403/authentication/invalid api key）
LLM_TIMEOUT = "50012"         # LLM 下游超时（无增量 60s / 请求 timeout / timed out）
LLM_RATE_LIMIT = "50013"      # LLM 下游限流（429/rate limit/too many requests）
LLM_UNAVAILABLE = "50014"     # LLM 下游不可达（连接失败/ConnectionError/下游 5xx）
SERVICE_DOWNSTREAM = "50015"  # 下游依赖通用兜底（生成期其它未归类异常）
CHAT_PERSIST_FAIL = "50016"   # 流式答案已生成但落库失败（build_finalize 抛错）

# ═══════════════════════════════════════════
# 社区域（community）
# ═══════════════════════════════════════════
COMMUNITY_POST_NOT_FOUND = "40410"     # 帖子不存在
COMMUNITY_COMMENT_NOT_FOUND = "40411"  # 评论不存在
COMMUNITY_POST_LOCKED = "40310"        # 帖子已锁定
COMMUNITY_FORBIDDEN_UPDATE = "40311"   # 不能修改他人帖子
COMMUNITY_BOARD_INVALID = "40020"      # 非法版块
COMMUNITY_REACT_INVALID = "40024"      # 非法反应类型（原 40021 与 TRADE_ORDER_STATUS_INVALID 一码两用，已拆分）

# ═══════════════════════════════════════════
# 学习事件分析域（analytics）— R-M1（contracts/reshape-r-analytics.json，draft:true 2026-09-18）
# 数据面 = MongoDB learning_event（旁路异步写，M-1）；对账基线 = MySQL 进度表。
# ═══════════════════════════════════════════
ANALYTICS_RANGE_INVALID = "40030"      # 非法 range 时间窗（支持 1d/7d/30d/90d）
ANALYTICS_FORBIDDEN = "40320"          # student 查询他人学习事件聚合（越权）

# ═══════════════════════════════════════════
# 知识图谱域（kg）— R-N1（contracts/reshape-r-kg.json，draft:true 2026-09-18）
# 语义：Neo4j 先修图 KG-2 端点的资源缺失与脏数据防御码；依赖不可达复用 50301。
# 纯增量注册（40460~40462 / 40910 均为未占用码位），回滚=revert 单 commit。
# ═══════════════════════════════════════════
KG_COURSE_NOT_FOUND = "40460"        # 图谱课程不存在（course_id 未同步进 Neo4j）
KG_CHAPTER_NOT_FOUND = "40461"       # 图谱章节不存在（chapter_code 未同步进 Neo4j）
KG_NODE_NOT_FOUND = "40462"          # 知识点不存在（path 的 from/to code 非法）
KG_PREREQUISITE_CYCLE = "40910"      # 先修图存在环（脏数据防御，拓扑语义失效，fail-closed）

# ═══════════════════════════════════════════
# 字符串子码 → 数字码 映射（内部用，保留兼容）
# ═══════════════════════════════════════════
SUBCODE_MAP = {
    "AUTH_TOKEN_INVALID": (AUTH_TOKEN_INVALID, 401),
    "AUTH_TOKEN_EXPIRED": (AUTH_TOKEN_EXPIRED, 401),
    "AUTH_TOKEN_MALFORMED": (AUTH_TOKEN_MALFORMED, 401),
    "AUTH_TOKEN_TYPE_MISMATCH": (AUTH_TOKEN_TYPE_MISMATCH, 401),
    "AUTH_ROLE_INVALID": (AUTH_ROLE_INVALID, 401),
    "AUTH_ACCOUNT_MISSING": (AUTH_ACCOUNT_MISSING, 400),
    "AUTH_ACCOUNT_EXISTS": (AUTH_ACCOUNT_EXISTS, 409),
    "AUTH_MOBILE_EXISTS": (AUTH_MOBILE_EXISTS, 409),
    "AUTH_EMAIL_EXISTS": (AUTH_EMAIL_EXISTS, 409),
    "AUTH_LOGIN_FAILED": (AUTH_LOGIN_FAILED, 401),
    "AUTH_USER_DISABLED": (AUTH_USER_DISABLED, 403),
    "AUTH_USER_NOT_FOUND": (AUTH_USER_NOT_FOUND, 404),
}