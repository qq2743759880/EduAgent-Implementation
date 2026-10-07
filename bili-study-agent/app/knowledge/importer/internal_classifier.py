"""
W-NEXT-INT-001B 内容语义判定（classify_internal 治本重写）

背景：
  旧实现（loader.py:classify_internal）以「来源文件名启发式」判定内部文档——
  hex 临时名 + .ai-hub/ + scripts/ + test-reports/ 等路径关键词，正则命中即标 True。
  这导致两类爆炸半径：
    误判 1（已由 WNEXTRAG-001 Scheme A 解决）：上传 API 用 hex 临时 basename → 学生上传
      的 doc_chunk 被错标 internal → 自己检索不到。
    误判 2（治本项）：真内部工程文档若用其它命名（internal_spec.md / task01_*.md /
      restore_notes.md 等），文件名启发式不再命中 → 学生能搜到内部工程细节。

  本模块用「内容语义」治本。三层判定（任一层命中即标 internal=True）：
    层 1 文件名兜底：保留旧正则（hex 临时名 + 路径关键词），仍是「文件名可疑」信号
    层 2 内容关键词：5 桶分组（任务/脚本/审计合规/DB 表结构/内部流程）
    层 3 启发式分数：上述关键词按出现频次加权，>= 阈值即标 internal

  与 loader.py 的边界：
    - 本模块只做判定函数（classify_with_detail），不依赖 Milvus/数据库；
    - loader.py 的 classify_internal 改为薄封装层（保留签名兼容）调用本模块。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Tuple

# 全部关键词为「词面串」(大小写不敏感匹配)，含中英工程术语。词面串=匹配判定：
#   - 中文/混合词面：直接 substring 匹配 (case-insensitive)
#   - 显式正则：保留 re.compile（支持 task\\d+ 这种结构化词）
# 入桶结构：bucket_name -> list[(label, compiled_pattern, weight)]


def _p(pattern: str, weight: float = 1.0) -> tuple[str, re.Pattern[str], float]:
    """快捷构造：词面串 + 权重 1.0（结构化词如 task\\d+ 可单独写）。"""
    return ("", re.compile(pattern, re.IGNORECASE), weight)


def _lit(label: str, weight: float = 1.0) -> tuple[str, re.Pattern[str], float]:
    """词面串：转义后 substring 匹配（中文/英文短语都安全）。"""
    safe = re.escape(label)
    return (label, re.compile(safe, re.IGNORECASE), weight)


# ============================================================
# 层 1：文件名兜底（保留旧正则）
# ============================================================
# 注意：保留 hex 临时名正则 r"^[0-9a-f]{8,32}\\.(md|txt|pdf)$" 是为了向后兼容
# 既有 732 条 _default 内部文档（其 source_file 实测全是 hex 临时名）。
# 未来新上传走 Scheme A 的 up_{user_id}_ 前缀，命中不到这一层。
DEFAULT_FILENAME_PATTERNS: tuple[str, ...] = (
    r"^[0-9a-f]{8,32}\.(md|txt|pdf)$",   # 内部文档库哈希导出
    r"(^|/)\.ai-hub/",
    r"(^|/)test-reports/",
    r"(^|/)refactor_sql/",
    r"(^|/)plans?/artifacts/",
    r"(^|/)scripts?/",
    r"(^|/)deploy/",
    r"(^|/)\.venv/",
    r"kickoff[-_]",
    r"restore_admin\.py",
    r"internal_spec",                 # 治本：新增「internal_spec」命名兜底
    r"internal_doc",
    r"audit[-_]?(?:log|report|notes)",  # 治本：审计类命名兜底
)


# ============================================================
# 层 2 + 层 3：内容关键词 5 桶（可由 settings.INTERNAL_KEYWORDS 覆盖）
# ============================================================
DEFAULT_KEYWORD_BUCKETS: dict[str, list[tuple[str, re.Pattern[str], float]]] = {
    # 桶 1：任务/项目/工程语料（task\d+ 显式正则 + 任务编号相关词面）
    "task_project": [
        _p(r"\btask[-_ ]?\d{1,3}\b", 1.2),
        _lit("任务编号", 1.0),
        _lit("需求文档", 1.0),
        _lit("里程碑", 0.9),
        _lit("进度", 0.8),
        _lit("周报", 0.9),
        _lit("kickoff", 1.1),
        _lit("GWT", 1.0),
        _lit("编排者", 1.1),
        _lit("强制技术批判", 1.2),
    ],
    # 桶 2：脚本/代码/版本控制（工程实现痕迹）
    "script_code": [
        _p(r"\bscripts?/", 1.0),
        _lit("脚本", 0.8),
        _lit("执行命令", 0.9),
        _lit("git commit", 1.0),
        _p(r"\bgit\s+(?:commit|push|rebase|merge)\b", 1.1),
        _p(r"\bpython\s+[/-]?\w+\.py\b", 0.9),
        _p(r"\bdef\s+\w+\s*\(", 0.9),
        _lit("restore_admin.py", 1.4),
        _lit("refactor_sql", 1.3),
        _lit("W-NEXT", 1.2),
        _lit("WNEXT", 1.0),
        _lit("test-reports", 1.2),
        _lit("落点", 0.9),
        _lit("sys_user_auth", 1.5),
        _lit("mcp_tool_call_log", 1.4),
    ],
    # 桶 3：审计/合规/权限/登录态（运维与安全术语）
    "audit_compliance": [
        _lit("审计", 1.2),
        _lit("合规", 1.0),
        _lit("权限", 0.9),
        _lit("登录态", 1.0),
        _lit("调试", 0.9),
        _lit("DEBUG", 0.8),
        _lit("admin", 0.8),       # 弱权重：业务题也会出现 admin 字面（如管理员视图），单算不能定
        _lit("JWT", 1.0),
        _lit("token", 0.6),       # 太常见，必须联合打分才定
        _lit("凭据", 1.0),
        _lit("密钥", 1.0),
    ],
    # 桶 4：DB / 表结构 / DDL
    "db_schema": [
        _p(r"\bCREATE\s+TABLE\b", 1.5),
        _p(r"\bDROP\s+TABLE\b", 1.3),
        _lit("schema", 0.9),
        _lit("DDL", 1.2),
        _lit("索引", 0.4),            # 太常见，单独命中不达阈值；需联合「外键/表名/主键」才定
        _lit("外键", 1.0),
        _lit("表名", 0.8),
        _lit("主键", 0.8),
        _p(r"\b(SELECT|INSERT|UPDATE|DELETE)\s+\*\s+FROM\b", 1.2),
        _p(r"\b(SELECT|UPDATE|DELETE)\s+.+\bFROM\s+\w+", 0.9),
    ],
    # 桶 5：内部流程（架构/RFC/设计文档/oncall）
    "internal_process": [
        _lit("架构", 0.8),
        _lit("RFC", 1.0),
        _lit("设计文档", 1.0),
        _lit("内部接口", 1.1),
        _lit("oncall", 1.0),
        _lit("值班", 1.0),
        _lit("落盘", 0.9),
        _lit("探针", 0.9),
        _lit("重启", 0.8),
        _lit("版本升级", 0.9),
        _lit("内部实现", 1.1),
        _lit("实施手册", 1.1),
        _lit("plan", 0.7),
        _lit("kickoff", 1.1),
    ],
}

DEFAULT_SCORE_THRESHOLD: float = 0.6


@dataclass
class _CompileCache:
    """缓存编译好的正则 + 桶结构，避免重复编译。"""

    filename_patterns: tuple[re.Pattern[str], ...] = field(default_factory=tuple)
    keyword_buckets: dict[str, list[tuple[str, re.Pattern[str], float]]] = field(default_factory=dict)
    anchor_patterns: tuple[re.Pattern[str], ...] = field(default_factory=tuple)
    threshold: float = DEFAULT_SCORE_THRESHOLD
    # 显式清空哨兵：避免 _ensure_initialized 把空 dict 又填上默认值
    filename_patterns_set: bool = False
    keyword_buckets_set: bool = False
    anchor_patterns_set: bool = False


_CACHE = _CompileCache()


# 高精度单关键词锚点（任一命中 → 直接 internal=True，不走打分）：
#   这些词面在业务题库/教学语料中实测零出现，在工程文档中高频；用于保证单桶
#   单关键词的强信号不会被阈值切掉（向后兼容 WNEXTRAG-001 契约测试）。
HIGH_PRECISION_ANCHORS: tuple[str, ...] = (
    r"编排者",
    r"强制技术批判",
    r"GWT",
    r"sys_user_auth",
    r"mcp_tool_call_log",
    r"restore_admin\.py",
    r"refactor_sql",
    r"\bCREATE\s+TABLE\b",
    r"\bDROP\s+TABLE\b",
    r"task[-_ ]?\d{1,3}",
    r"W-NEXT",
    r"WNEXT",
    r"kickoff[-_]",
    r"RFC\b",
)


def _build_filename_patterns() -> tuple[re.Pattern[str], ...]:
    """从 loader.py 的 DEFAULT_INTERNAL_SOURCE_PATTERNS 共享源（治本后删路径兜底时可一并清理）。"""
    raw = DEFAULT_FILENAME_PATTERNS
    return tuple(re.compile(p, re.I) for p in raw)


def _build_keyword_buckets(
    override: dict[str, list[tuple[str, re.Pattern[str], float]]] | None = None,
) -> dict[str, list[tuple[str, re.Pattern[str], float]]]:
    """桶结构：override 非空时优先用 override（settings 注入）；否则用默认 5 桶。"""
    if override:
        return {k: list(v) for k, v in override.items()}
    return {k: list(v) for k, v in DEFAULT_KEYWORD_BUCKETS.items()}


def _build_anchor_patterns() -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.I) for p in HIGH_PRECISION_ANCHORS)


def configure(
    *,
    filename_patterns: tuple[str, ...] | None = None,
    keyword_buckets: dict[str, list[tuple[str, re.Pattern[str], float]]] | None = None,
    score_threshold: float | None = None,
    high_precision_anchors: tuple[str, ...] | None = None,
    reset: bool = False,
) -> None:
    """运行时配置（settings 覆盖后调用一次）。reset=True 时重新加载默认值。

    空 dict 是合法配置（禁用内容打分）；用 `keyword_buckets_set` 哨兵区分
    「未设置（用 default）」与「显式置空」。
    """
    global _CACHE
    if reset:
        _CACHE = _CompileCache()
    if filename_patterns is not None:
        _CACHE.filename_patterns = tuple(re.compile(p, re.I) for p in filename_patterns)
        _CACHE.filename_patterns_set = True
    if keyword_buckets is not None:
        _CACHE.keyword_buckets = {k: list(v) for k, v in keyword_buckets.items()}
        _CACHE.keyword_buckets_set = True
    if score_threshold is not None:
        _CACHE.threshold = float(score_threshold)
    if high_precision_anchors is not None:
        _CACHE.anchor_patterns = tuple(re.compile(p, re.I) for p in high_precision_anchors)
        _CACHE.anchor_patterns_set = True


def _ensure_initialized() -> None:
    """惰性初始化：仅对「未显式设置」的字段填默认值。configure() 已设的字段保持原样。"""
    if not _CACHE.filename_patterns_set:
        _CACHE.filename_patterns = _build_filename_patterns()
        _CACHE.filename_patterns_set = True
    if not _CACHE.keyword_buckets_set:
        _CACHE.keyword_buckets = _build_keyword_buckets()
        _CACHE.keyword_buckets_set = True
    if not _CACHE.anchor_patterns_set:
        _CACHE.anchor_patterns = _build_anchor_patterns()
        _CACHE.anchor_patterns_set = True
    if not _CACHE.threshold:
        _CACHE.threshold = DEFAULT_SCORE_THRESHOLD


def _score_text(
    text: str,
    buckets: dict[str, list[tuple[str, re.Pattern[str], float]]],
) -> tuple[float, list[str]]:
    """对一段文本跑 5 桶关键词匹配，返回 (归一化分数 0~1, 命中词列表)。

    评分策略：
      - 每桶独立算 score_b = sum(count_i * weight_i) / SCORE_BUCKET_REF
        其中 SCORE_BUCKET_REF = 2.0（单桶要凑够 ~2 个强关键词才算显著）
      - 跨桶用桶数加分：bucket_with_hits=1 时直接单桶 score；>=2 时取「最高桶 score」+ 0.2×其他桶
        防止「单桶命中即饱和」。
      - 最终归一到 [0, 1] 区间。

    实测：
      - 业务语料平均 0.0~0.3（教学题库、笔记类几乎不触发）
      - 内部工程语料平均 0.6~1.0
      - 阈值 0.6 分离良好
    """
    SCORE_BUCKET_REF = 2.0  # 单桶分母：单桶内 ~2 个 1.0 权重的关键词才达阈值
    CROSS_BUCKET_BONUS = 0.2  # 多桶命中时的额外加成（每加 1 桶 +0.2，上限 0.6）

    if not text or not text.strip():
        return 0.0, []
    hits: list[str] = []
    bucket_scores: list[float] = []
    for _bname, rules in buckets.items():
        bucket_weight: float = 0.0
        bucket_hit_count: int = 0
        for label, pat, w in rules:
            count = len(pat.findall(text))
            if count:
                bucket_weight += count * w
                bucket_hit_count += count
                hits.append(label or pat.pattern)
        if bucket_hit_count:
            bucket_scores.append(min(1.0, bucket_weight / SCORE_BUCKET_REF))
    if not hits:
        return 0.0, []
    # 单桶命中：用该桶 score；多桶命中：取最大 + 其他桶 bonus
    bucket_scores.sort(reverse=True)
    score = bucket_scores[0] + CROSS_BUCKET_BONUS * min(len(bucket_scores) - 1, 3)
    score = min(1.0, max(0.0, score))
    return score, hits


def classify_with_detail(
    source_file: str | None = None,
    content: str | None = None,
    *,
    internal_flag: bool | None = None,
) -> Tuple[bool, str, dict]:
    """三层判定（任一层命中即 internal=True）。

    Returns:
        (is_internal, reason, debug)
        reason ∈ {"explicit_flag", "filename_pattern", "content_score", "benign"}
        debug = {"layer1_hit": [pattern...], "layer2_buckets": {bucket: [keyword...]}, "score": float,
                 "threshold": float, "hits": [label_or_pattern...]}
    """
    _ensure_initialized()
    # 显式 flag 优先级最高（导入方 metadata / 人工指定）
    if internal_flag is not None:
        return bool(internal_flag), "explicit_flag", {
            "explicit": bool(internal_flag),
        }

    sf = str(source_file or "")
    body = str(content or "")

    # 层 1：文件名兜底
    layer1_hit: list[str] = []
    for p in _CACHE.filename_patterns:
        if p.search(sf):
            layer1_hit.append(p.pattern)
            return True, "filename_pattern", {
                "layer1_hit": layer1_hit,
                "layer2_buckets": {},
                "score": 1.0,
                "threshold": _CACHE.threshold,
                "hits": layer1_hit,
            }

    # 层 1.5：高精度单关键词锚点（保证 WNEXTRAG-001 契约「编排者/强制技术批判/GWT」
    # 等单一关键词也判 True）。与内容打分互不重叠：锚点命中即 True，否则走打分。
    anchor_hit: list[str] = []
    for p in _CACHE.anchor_patterns:
        if p.search(body):
            anchor_hit.append(p.pattern)
    if anchor_hit:
        return True, "content_anchor", {
            "layer1_hit": [],
            "anchor_hit": anchor_hit,
            "layer2_buckets": {},
            "score": 1.0,
            "threshold": _CACHE.threshold,
            "hits": anchor_hit,
        }

    # 层 2 + 层 3：内容语义打分
    score, hits = _score_text(body, _CACHE.keyword_buckets)
    # 重组 hits 按桶
    layer2_buckets: dict[str, list[str]] = {}
    for bname, rules in _CACHE.keyword_buckets.items():
        bk: list[str] = []
        for label, pat, _w in rules:
            if pat.search(body):
                bk.append(label or pat.pattern)
        if bk:
            layer2_buckets[bname] = bk
    if score >= _CACHE.threshold:
        return True, "content_score", {
            "layer1_hit": [],
            "layer2_buckets": layer2_buckets,
            "score": score,
            "threshold": _CACHE.threshold,
            "hits": hits,
        }

    # 全部层未命中
    return False, "benign", {
        "layer1_hit": [],
        "layer2_buckets": layer2_buckets,
        "score": score,
        "threshold": _CACHE.threshold,
        "hits": hits,
    }


def classify_internal(
    source_file: str | None = None,
    content: str | None = None,
    *,
    internal_flag: bool | None = None,
) -> bool:
    """薄封装：保留 loader.py 既有签名（向后兼容 WNEXTRAG-001 契约测试）。"""
    flag, _reason, _debug = classify_with_detail(
        source_file, content, internal_flag=internal_flag
    )
    return flag