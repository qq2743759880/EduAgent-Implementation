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

# ═══════════════════════════════════════════
# 题库域（question_admin）— 40921~40929 唯一约束冲突（task13 新段）
# ═══════════════════════════════════════════
BANK_CODE_CONFLICT = "40921"       # 题库编码重复（institution_id + bank_code）
QUESTION_CODE_CONFLICT = "40922"   # 题目编码重复（bank_id + question_code）
EXAM_CODE_CONFLICT = "40923"       # 考试编码重复（session_id + exam_code）

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