# -*- coding: utf-8 -*-
"""
向量化器（P1 步骤 5）

职责：
  1. 稠密向量（dense_vec 1024 维）—— BGE-M3 本地模型（DashScope API 降级兜底）
  2. 稀疏向量（sparse_vec {index:weight}）—— jieba + 自定义词典 + 停用词 + BM25 风格 TF-IDF
  3. LangGraph 节点 embed_node(state) -> state

关键设计：
- 资源懒加载：第一次调用时才加载 BGE 模型和 jieba 词典，避免启动时间长 / 模型缺失直接崩。
- 模型缺失兜底：BGE 本地模型不存在 → 走 OpenAI 兼容 Embedding API（硅基流动/DashScope，1024 维对齐 dim）。
- jieba 资源路径从 settings.JIEBA_CUSTOM_DICT / STOPWORDS_FILE 取，路径不存在只告警不抛错。
- sparse_vec 输出格式严格对齐 Milvus SPARSE_FLOAT_VECTOR：{"<term_id:int>": <weight:float>}
"""
from __future__ import annotations

import hashlib
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from loguru import logger

from app.config import settings
from app.knowledge.models import ImportState, KnowledgeChunk

# W-NEXT-EXE-SSRF-002：embedder 出站 HTTP（embedding API）必经 SSRF 守门。
# 设计依据：SSRF-001 §6 P2：EMBEDDING_API_URL 走白名单；默认 ark.cn-beijing.volces.com，
# 严禁命中 IMDS（169.254.169.254）/ metadata.google.internal / RFC1918 私网等。
# 拒绝时 log WARN 并回退 embed 失败（绝不静默降级为假向量后再被上层拒）。
try:
    from app.security.ssrf_guard import (
        DEFAULT_ALLOWED_HOSTS as _SSRF_DEFAULT_ALLOWED,
        SSRFBlockedError as _SSRFBlockedError,
        validate_url as _ssrf_validate_url,
    )
    _SSRF_AVAILABLE = True
except Exception as _ssrf_import_exc:  # pragma: no cover - 守护退化不应触发
    # 安全缺省：ssrf_guard 不可用时**拒绝**发外部 embed 请求（fail-closed），
    # 行为是抛 RuntimeError 让上层降级为 sha256 伪向量（默认禁入库），不静默外发。
    _SSRF_AVAILABLE = False
    _SSRF_DEFAULT_ALLOWED = frozenset()
    _SSRFBlockedError = Exception  # type: ignore[assignment]

    def _ssrf_validate_url(url: str, *, allowed_hosts=None) -> None:  # type: ignore[no-redef]
        raise RuntimeError(
            f"app.security.ssrf_guard 不可用，禁止外发 embed HTTP：{_ssrf_import_exc}"
        )


def _embed_ssrf_allowed_hosts() -> frozenset[str]:
    """embedder 出站允许的 host 白名单。

    设计（与 SSRF-001 默认白名单同源 + 扩展）：
      1) 静态白名单：ark.cn-beijing.volces.com（火山 Embed API 默认生产 host）
         + 127.0.0.1/localhost/192.168.85.101/10.0.0.1（本机项目回环/内网）
      2) settings.EMBEDDING_API_URL_ALLOWED_HOSTS（runtime 扩展，多 host 列表/集合）
      3) 备注：**禁止**从 EMBEDDING_API_URL 字面 host 自动放行（防 SSRF 形态 ①
         「.env 被改 host=攻击者域就放行」——必须显式声明 EM...HOSTS 才能扩）。

    取并集再 lower + 去空字符串，**绝不**做后缀通配（必须 host 字面精确匹配）。
    """
    hosts: set[str] = set(_SSRF_DEFAULT_ALLOWED)
    # 火山引擎 Ark 默认生产 Embed 端点（.env 实证 EMBEDDING_API_URL=https://ark.cn-beijing.volces.com/api/plan/v3）
    hosts.add("ark.cn-beijing.volces.com")
    # settings 扩展覆盖（list / tuple / set / str-comma）—— 未声明字段默认空
    custom = getattr(settings, "EMBEDDING_API_URL_ALLOWED_HOSTS", None)
    if isinstance(custom, (list, tuple, set)):
        for x in custom:
            if x and isinstance(x, str):
                hosts.add(x.strip().lower())
    elif isinstance(custom, str) and custom.strip():
        for x in custom.split(","):
            x = x.strip()
            if x:
                hosts.add(x.lower())
    return frozenset(hosts)


def _gate_embed_url(url: str) -> None:
    """embedder 出站 HTTP 前调：白名单 + 拒 IMDS + 拒私网（ssrf_guard 内置）。

    拒绝语义：抛 SSRFBlockedError → 调用方 _api_embed_batch 捕获 → log WARN +
    返回 None → embed 走本地 BGE-M3 兜底 / sha256 兜底（默认禁入库），绝不静默外发。
    """
    try:
        _ssrf_validate_url(url, allowed_hosts=_embed_ssrf_allowed_hosts())
    except _SSRFBlockedError as exc:
        # 必 log WARN（安全审计可见），绝不静默（避免上层将失败 swallow 成 sha256 假向量）
        logger.warning(
            f"[W-NEXT-EXE-SSRF-002] embed 出站 URL 拒绝：{exc.reason} "
            f"(host={exc.host!r}, scheme={exc.scheme!r}, url={url[:120]!r})"
        )
        raise

# ---------------------------------------------------------------------------
# 全局锁 + 单例，避免多请求重复加载模型 / 重复初始化 jieba
# ---------------------------------------------------------------------------
_BGE_LOCK = threading.Lock()
_BGE_MODEL = None                # FlagEmbedding BGEM3FlagModel 实例
_JIEBA_LOCK = threading.Lock()
_JIEBA_INITIALIZED = False
_STOPWORDS: frozenset[str] = frozenset()  # 停用词缓存（P1-4：避免每次读文件）
_TERM_ID_LOCK = threading.Lock()
_TERM_TO_ID: dict[str, int] = {}  # 词 -> 稀疏索引（纯 hash 确定性分配，不依赖外部字典）


def _jieba_available() -> bool:
    """jieba 可用性探测（幂等）。"""
    try:
        import jieba  # noqa: F401
        return True
    except Exception:
        return False


# ============================================================
# 1. jieba 自定义词典 + 停用词加载
# ============================================================
def load_jieba_resources() -> tuple[set[str], bool]:
    """
    加载自定义词典 + 停用词（幂等，首次调用时初始化）。

    返回：
      (stopwords_set, jieba_available)
    """
    global _JIEBA_INITIALIZED
    global _STOPWORDS

    stopwords: set[str] = set()
    jieba_available = False

    with _JIEBA_LOCK:
        # 已初始化（词典+停用词）→ 幂等直接返回缓存结果
        if _JIEBA_INITIALIZED:
            return _STOPWORDS, _jieba_available()

        # 1) 尝试 import jieba
        try:
            import jieba  # noqa: F401
            jieba_available = True
        except Exception as exc:
            logger.warning(f"jieba 未安装，稀疏向量退化到简单空格分词（{exc.__class__.__name__}: {exc}）")
            jieba_available = False

        # 2) 加载自定义词典（只做一次）
        if jieba_available:
            custom_dict_path = _resolve_path(getattr(settings, "JIEBA_CUSTOM_DICT", None))
            if custom_dict_path and custom_dict_path.exists():
                try:
                    import jieba as _jieba
                    _jieba.load_userdict(str(custom_dict_path))
                    logger.info(f"jieba 自定义词典已加载：{custom_dict_path}")
                except Exception as exc:
                    logger.warning(f"jieba 自定义词典加载失败（忽略）：{exc}")
            elif custom_dict_path:
                logger.debug(f"jieba 自定义词典路径不存在（跳过）：{custom_dict_path}")

        # 3) 加载停用词（一次性，缓存到全局）
        stopwords_path = _resolve_path(getattr(settings, "JIEBA_STOPWORDS_FILE", None))
        if stopwords_path and stopwords_path.exists():
            try:
                raw_text = stopwords_path.read_text(encoding="utf-8")
                for line in raw_text.splitlines():
                    word = line.strip()
                    if word and not word.startswith("#"):
                        stopwords.add(word)
                logger.debug(f"停用词加载完成，共 {len(stopwords)} 条")
            except Exception as exc:
                logger.warning(f"停用词文件读取失败（忽略）：{exc}")

        _JIEBA_INITIALIZED = True
        _STOPWORDS = frozenset(stopwords)
        return set(_STOPWORDS), jieba_available


def ensure_jieba_ready() -> tuple[set[str], bool]:
    """
    对外暴露的幂等入口：确保 jieba + 自定义词典 + 停用词已加载。
    返回：(stopwords_set, jieba_available)  （调用方若只需要 jieba 本身可用，取 [1]）
    """
    return load_jieba_resources()


def _resolve_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    p = Path(raw)
    if p.is_absolute():
        return p
    # 相对路径以 DATA_DIR 为基准
    return Path(settings.DATA_DIR) / p


# ============================================================
# 2. 稠密向量：优先 BGE-M3 本地，降级 DashScope Embedding API
# ============================================================
def _get_bge_model():
    """懒加载 BGEM3FlagModel，失败返回 None。"""
    global _BGE_MODEL
    if _BGE_MODEL is not None:
        return _BGE_MODEL
    with _BGE_LOCK:
        if _BGE_MODEL is not None:
            return _BGE_MODEL
        model_path = Path(settings.BGE_M3_PATH)
        if not model_path.exists():
            logger.warning(f"BGE-M3 本地模型不存在：{model_path} → 稠密向量走 DashScope API 兜底")
            return None
        try:
            from FlagEmbedding import BGEM3FlagModel  # 本地依赖
            model = BGEM3FlagModel(
                str(model_path),
                use_fp16=(settings.EMBED_DEVICE == "cuda"),
                device=settings.EMBED_DEVICE,
            )
            logger.info(f"BGE-M3 本地模型已加载：{model_path}（device={settings.EMBED_DEVICE}）")
            _BGE_MODEL = model
            return _BGE_MODEL
        except Exception as exc:
            logger.warning(f"BGE-M3 本地模型加载失败（降级 DashScope API）：{exc}")
            return None


def _api_embed_batch(texts: list[str]) -> list[list[float]]:
    """OpenAI 兼容 embeddings（硅基流动 / DashScope / a6api 等，输出对齐 Milvus Schema）。

    独立配置优先：
      - url  取 settings.EMBEDDING_API_URL，为空回退 LLM_BASE_URL
      - key  取 settings.EMBEDDING_API_KEY，为空回退 LLM_API_KEY
      - model取 settings.EMBEDDING_MODEL（默认 BAAI/bge-m3，1024 维）

    关键修复（2026-08-10，根因#3 同步）：
      - httpx 与 requests 一样，默认会信任 env / Windows 系统代理（IE 注册表），
        若本机存在 127.0.0.1 本地代理劫持，就会出现 SSLEOF / ReadTimeout 或 503。
        通过 trust_env=False + proxy=None 强制直连出口 embedding 服务。
    """
    import httpx

    api_key = settings.EMBEDDING_API_KEY or settings.LLM_API_KEY
    if not api_key:
        raise RuntimeError("BGE-M3 本地模型不可用且 Embedding/LLM API key 未配置，无法生成稠密向量")
    base_url = settings.EMBEDDING_API_URL or settings.LLM_BASE_URL
    url = str(base_url).rstrip("/") + "/embeddings"
    # W-NEXT-EXE-SSRF-002：白名单守门在 HTTP 之前。失败抛 SSRFBlockedError → RuntimeError。
    _gate_embed_url(url)
    payload = {
        "model": settings.EMBEDDING_MODEL,
        "input": texts,
        "encoding_format": "float",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # trust_env=False 禁止读取 HTTP_PROXY / HTTPS_PROXY / netrc / 系统代理
    # proxy=None 强制禁用默认代理路由 → 直连 LLM_BASE_URL
    with httpx.Client(timeout=120.0, trust_env=False, proxy=None) as client:
        resp = client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"DashScope Embedding API {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
    vecs: list[list[float]] = []
    for item in data.get("data", []):
        v = item.get("embedding", [])
        if len(v) != settings.EMBEDDING_DIM:
            # 维度不一致：截断或补 0（防止 Milvus upsert 失败）
            if len(v) > settings.EMBEDDING_DIM:
                v = v[: settings.EMBEDDING_DIM]
            else:
                v = list(v) + [0.0] * (settings.EMBEDDING_DIM - len(v))
        vecs.append(v)
    if len(vecs) != len(texts):
        raise RuntimeError(f"DashScope Embedding 返回数量不匹配：期望 {len(texts)}，实际 {len(vecs)}")
    return vecs


# ============================================================
# VEC-LOCK（模型一致性锁定）：编码结果溯源 + 空文本判定 + 模型指纹
# ============================================================
@dataclass
class DenseResult:
    """稠密编码结果：向量 + 编码路径/参数溯源（供入库元数据与对账机验）。

    - backend="bge_m3"  ：本地 BGE-M3（CLS pooling + L2 normalize，max_length=8192）
    - backend="cloud"   ：云端 Embedding API（与 BGE-M3 不同向量空间，须显式标记）
    - backend="sha256"  ：sha256 伪向量（默认禁入库，EMBED_ALLOW_FAKE_VECTOR 可放行）
    """
    vectors: list[list[float]]
    backend: str
    normalized: bool
    precision: str          # "fp16" | "fp32"
    embedding_model: str    # 模型名（含 revision 指纹，如 "bge-m3@a1b2c3d4"）
    max_length: int | None  # 编码截断长度（bge=8192；cloud=None=API 默认）


# 空文本/纯标点判定（禁 '.' 占位污染——相同占位向量互相满分互召）
_BLANK_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)


def is_blank_text(text: str) -> bool:
    """空文本判定：strip 后为空，或仅含空白/标点/符号（无任何语义字符）。"""
    t = (text or "").strip()
    if not t:
        return True
    return bool(_BLANK_RE.fullmatch(t))


@lru_cache(maxsize=1)
def _bge_revision_fingerprint() -> str:
    """BGE-M3 模型 revision 指纹：config.json 内容 sha256 前 8 位（模型文件变化即指纹变化）。"""
    try:
        cfg = Path(settings.BGE_M3_PATH) / "config.json"
        if cfg.exists():
            import json
            raw = cfg.read_text(encoding="utf-8")
            name = json.loads(raw).get("_name_or_path") or Path(settings.BGE_M3_PATH).name
            rev = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
            return f"{Path(str(name)).name}@{rev}"
    except Exception:
        pass
    return f"bge-m3@{Path(settings.BGE_M3_PATH).name}"


def _l2_normalize(vecs: list[list[float]]) -> list[list[float]]:
    """显式 L2 归一化（float64 计算，输出干净 float，保证 |‖v‖₂−1|<1e-3 可验）。"""
    out: list[list[float]] = []
    for v in vecs:
        floats = [float(x) for x in v]
        norm = math.sqrt(sum(x * x for x in floats)) or 1.0
        out.append([x / norm for x in floats])
    return out


def encode_dense_batch_detailed(texts: list[str]) -> DenseResult:
    """
    批量生成稠密向量（VEC-LOCK 单一事实源：写入侧 embed_node 与查询侧 retriever
    共用本实现与参数快照，禁两条路径分叉）。

    EMBED_BACKEND="cuda" → 本地 BGE-M3 优先（锁定向量空间）；"cloud" → API 优先（用户显式选择）。
    任何兜底降级都返回 backend 溯源 + 日志 WARNING，绝不静默混写异向量空间：
      - bge_m3  ：BGE-M3（CLS pooling + 显式 L2 normalize，max_length=8192）
      - cloud   ：Embedding API（doubao 等，与 BGE-M3 不同空间，调用方须标记）
      - sha256  ：确定性伪向量（默认禁入库，由调用方按 EMBED_ALLOW_FAKE_VECTOR 裁决）
    不再把空文本替换为 '.' 占位（空文本由入库侧过滤/查询侧原样编码）。
    """
    dim = settings.EMBEDDING_DIM
    texts = list(texts)
    cloud_first = str(getattr(settings, "EMBED_BACKEND", "cloud") or "cloud").lower() != "cuda"
    precision = "fp16" if str(getattr(settings, "EMBED_DEVICE", "cuda")).lower() == "cuda" else "fp32"

    def _try_local_bge() -> DenseResult | None:
        bge = _get_bge_model()
        if bge is None:
            return None
        try:
            out = bge.encode(
                texts,
                batch_size=settings.EMBED_BATCH_SIZE,
                max_length=8192,
            )
            vecs = out.get("dense_vecs", [])
            if len(vecs) == len(texts):
                padded = [list(v) if len(v) == dim else _pad_or_trim(v, dim) for v in vecs]
                return DenseResult(
                    vectors=_l2_normalize(padded),
                    backend="bge_m3",
                    normalized=True,
                    precision=precision,
                    embedding_model=_bge_revision_fingerprint(),
                    max_length=8192,
                )
        except Exception as exc:
            logger.warning(f"BGE-M3 encode 失败：{exc}")
        return None

    def _try_api() -> DenseResult | None:
        try:
            vecs = _api_embed_batch(texts)
            return DenseResult(
                vectors=vecs,
                backend="cloud",
                normalized=False,   # 云端输出归一化不保证，对账以实测为准
                precision="fp32",
                embedding_model=str(getattr(settings, "EMBEDDING_MODEL", "cloud") or "cloud"),
                max_length=None,
            )
        except Exception as exc:
            logger.warning(f"Embedding API 失败（{exc}）")
            return None

    if cloud_first:
        # 1) 云端 API 优先（火山 doubao-embedding-vision 等）
        r = _try_api()
        if r is not None:
            return r
        # 2) 本地 BGE-M3 CUDA 兜底
        r = _try_local_bge()
        if r is not None:
            return r
    else:
        # 旧行为：本地 BGE-M3 优先，API 兜底
        r = _try_local_bge()
        if r is not None:
            return r
        r = _try_api()
        if r is not None:
            return r

    # 3) 最终兜底：确定性伪向量（显式 WARNING + backend 溯源；入库侧默认拒绝）
    logger.warning("稠密编码两级兜底均失败 → 退化为 sha256 伪向量（backend=sha256，默认禁入库）")
    return DenseResult(
        vectors=[_pseudo_dense(t, dim) for t in texts],
        backend="sha256",
        normalized=True,
        precision=precision,
        embedding_model="sha256-pseudo",
        max_length=None,
    )


def encode_dense_batch(texts: list[str]) -> list[list[float]]:
    """兼容入口：只返回向量列表（查询/记忆/脚本通用），实现单一事实源=encode_dense_batch_detailed。"""
    return encode_dense_batch_detailed(texts).vectors


def _pad_or_trim(v: Iterable[float], dim: int) -> list[float]:
    arr = list(v)
    if len(arr) == dim:
        return arr
    if len(arr) > dim:
        return arr[:dim]
    return arr + [0.0] * (dim - len(arr))


def _pseudo_dense(text: str, dim: int) -> list[float]:
    """纯兜底伪向量（sha256 -> 均匀分布 -> 单位化）。"""
    h = hashlib.sha256(text.encode("utf-8")).digest()
    # 每 4 字节转 float
    floats: list[float] = []
    for i in range(0, min(len(h) // 4 * 4, dim * 4), 4):
        u = int.from_bytes(h[i : i + 4], "big", signed=False)
        # [-1, 1] 线性映射
        floats.append((u / 0xFFFFFFFF) * 2.0 - 1.0)
    # 不够循环再用 digest 一次
    seed = 1
    while len(floats) < dim:
        extra = hashlib.sha256(h + seed.to_bytes(4, "big")).digest()
        seed += 1
        for i in range(0, len(extra) // 4 * 4, 4):
            if len(floats) >= dim:
                break
            u = int.from_bytes(extra[i : i + 4], "big", signed=False)
            floats.append((u / 0xFFFFFFFF) * 2.0 - 1.0)
    # 单位化
    norm = math.sqrt(sum(x * x for x in floats)) or 1.0
    return [x / norm for x in floats]


# ============================================================
# 3. 稀疏向量：jieba 分词 + 停用词过滤 + BM25(TF)-风格权重
# ============================================================
_RE_CHINESE_WORD = re.compile(r"^[\u4e00-\u9fa5A-Za-z0-9_+\-#.]{1,32}$")


def _tokenize(text: str, stopwords: set[str], jieba_available: bool) -> list[str]:
    text = text or ""
    if not text.strip():
        return []
    tokens: list[str] = []
    if jieba_available:
        try:
            import jieba as _jieba
            for tok in _jieba.cut(text):
                tok = tok.strip()
                if not tok:
                    continue
                if tok in stopwords:
                    continue
                if not _RE_CHINESE_WORD.match(tok):
                    continue
                tokens.append(tok.lower())
        except Exception:
            jieba_available = False

    if not jieba_available:
        # 退化：按非中文切开 + 英文按空格
        raw_chunks = re.split(r"[^\u4e00-\u9fa5A-Za-z0-9_]+", text)
        for tok in raw_chunks:
            tok = tok.strip().lower()
            if not tok or tok in stopwords:
                continue
            if len(tok) == 1 and not tok.isascii():  # 去掉单字中文噪音
                continue
            tokens.append(tok)
    return tokens


def _term_to_id(word: str) -> int:
    """
    词 → 稀疏索引：确定性 hash 映射，避免依赖外部词表。
    取值范围 [1, 2^30 - 1]（避开 0，0 作为兜底空位）。
    """
    with _TERM_ID_LOCK:
        cached = _TERM_TO_ID.get(word)
        if cached is not None:
            return cached
    h = 0x7FFFFFFF & int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
    tid = (h % (1 << 29)) + 1  # 1 ~ 2^29
    with _TERM_ID_LOCK:
        _TERM_TO_ID[word] = tid
    return tid


def build_sparse_vector(text: str, extra_keywords: list[str] | None = None) -> dict[str, float]:
    """
    生成 Milvus SPARSE_FLOAT_VECTOR 格式：{"<term_id>": weight}

    权重：BM25 风格 TF（sqrt(tf) * IDF 常数近似），关键词额外 boost。
    """
    stopwords, jieba_available = load_jieba_resources()

    # 1) 分词 + 词频
    tokens = _tokenize(text, stopwords, jieba_available)
    counter = Counter(tokens)

    # 2) 注入外部 keywords（提升权重 × 2）
    if extra_keywords:
        for kw in extra_keywords:
            for sub in _tokenize(kw, stopwords, jieba_available) or [kw.strip().lower()]:
                if not sub:
                    continue
                counter[sub] += 2

    if not counter:
        # 空文本也要给一个非空占位，避免 Milvus hybrid_search 时全 0 导致检索失败
        return {"1": 0.0001}

    # 3) 权重 = (1 + log tf) × 关键词加成；最后做 L2 归一化
    weighted: dict[int, float] = {}
    for term, tf in counter.items():
        boost = 2.0 if extra_keywords and term in {k.lower() for k in extra_keywords} else 1.0
        w = (1.0 + math.log(max(tf, 1))) * boost
        weighted[_term_to_id(term)] = w
    norm = math.sqrt(sum(v * v for v in weighted.values())) or 1.0
    sparse: dict[str, float] = {}
    for tid, w in weighted.items():
        val = w / norm
        if val > 1e-6:
            sparse[str(tid)] = round(val, 6)
    return sparse or {"1": 0.0001}


# ============================================================
# 4. LangGraph 节点：embed_node
# ============================================================
def embed_node(state: ImportState) -> dict:
    """
    LangGraph 节点：批量生成 dense + sparse 向量写入每个 chunk。

    VEC-LOCK（模型一致性锁定）：
      - 空文本/纯标点 chunk 过滤不入库（禁 '.' 占位——相同占位向量互相满分互召）；
      - 稠密编码走单一事实源 encode_dense_batch_detailed（与查询侧同模型同参数）；
      - sha256 伪向量默认禁入库（EMBED_ALLOW_FAKE_VECTOR=False → 任务失败标记重试）；
      - 入库元数据四字段写入 chunk.extra：embedding_model/embed_precision/embed_normalized/embed_fallback。
    出错不中断流程，state.error 记录后返回（由下游节点判定跳过）。
    """
    if state.error:
        logger.warning("跳过 embed_node（前序节点已出错）")
        return {}
    if not state.chunks:
        logger.info("embed_node：chunks 为空，跳过")
        return {}

    # VEC-LOCK：空文本/纯标点过滤（禁 '.' 占位污染入库）
    kept: list[KnowledgeChunk] = [c for c in state.chunks if not is_blank_text(c.content)]
    dropped = len(state.chunks) - len(kept)
    if dropped:
        logger.warning(f"embed_node：过滤 {dropped} 个空文本/纯标点 chunk（禁 '.' 占位污染入库）")
    if not kept:
        logger.warning("embed_node：全部 chunk 为空/纯标点，无可入库内容")
        return {"chunks": []}

    try:
        # 4.1 稠密向量（VEC-LOCK 单一事实源：与查询侧 retriever 同一编码器同参数）
        batch_size = max(1, int(settings.EMBED_BATCH_SIZE))
        all_texts = [c.content for c in kept]
        all_dense: list[list[float]] = []
        backends: set[str] = set()
        last_result: DenseResult | None = None
        for i in range(0, len(all_texts), batch_size):
            batch = all_texts[i : i + batch_size]
            res = encode_dense_batch_detailed(batch)
            backends.add(res.backend)
            last_result = res
            all_dense.extend(res.vectors)

        # VEC-LOCK：sha256 伪向量默认禁入库（宁可任务失败标记重试，不静默混写假向量）
        if "sha256" in backends and not getattr(settings, "EMBED_ALLOW_FAKE_VECTOR", False):
            msg = (
                "向量化失败：dense 编码兜底为 sha256 伪向量，EMBED_ALLOW_FAKE_VECTOR=False"
                "（默认）→ 拒绝入库，任务标记失败待重试"
            )
            logger.error(msg)
            return {"error": msg}

        # VEC-LOCK：入库元数据四字段（写入 Milvus dynamic field，供对账/机验）
        meta: dict = {
            "embedding_model": last_result.embedding_model if last_result else "unknown",
            "embed_precision": last_result.precision if last_result else "unknown",
            "embed_normalized": 1 if (last_result and last_result.normalized) else 0,
        }
        if last_result is not None and last_result.backend in ("cloud", "sha256"):
            meta["embed_fallback"] = last_result.backend
        if last_result is not None and last_result.backend == "cloud":
            logger.warning(
                f"embed_node：dense 编码降级到云端（{meta['embedding_model']}），"
                f"已标记 embed_fallback=cloud（异向量空间，检索质量可能退化）"
            )

        # 4.2 稀疏向量 + 回填 chunk
        for idx, chunk in enumerate(kept):
            chunk.dense_vector = all_dense[idx]
            # 稀疏向量：content + keywords 合并输入
            keywords_boost = list(dict.fromkeys([*(chunk.keywords or []), *(chunk.tags or [])]))
            svec = build_sparse_vector(chunk.content, extra_keywords=keywords_boost)
            # 同步回 KnowledgeChunk 的 sparse_indices/values（方便调试/持久化）
            items = sorted(svec.items(), key=lambda kv: -kv[1])[:4096]  # Milvus 限制上限
            chunk.sparse_indices = [int(k) for k, _ in items]
            chunk.sparse_values = [float(v) for _, v in items]
            # 额外保留 Milvus 格式在 extra（loader 再转，兼容两种写法）
            chunk.extra["_sparse_vec_milvus"] = {k: v for k, v in items}
            chunk.extra.update(meta)  # VEC-LOCK 元数据

        logger.info(
            f"embed_node 完成：{len(kept)} chunks × dense(1024) + sparse"
            f"（backend={last_result.backend if last_result else '?'}，过滤 {dropped} 空文本）"
        )
        return {"chunks": kept}
    except Exception as exc:
        msg = f"向量化失败：{exc.__class__.__name__}: {exc}"
        logger.exception(msg)
        return {"error": msg}
