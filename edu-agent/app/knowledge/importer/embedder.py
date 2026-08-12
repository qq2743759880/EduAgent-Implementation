# -*- coding: utf-8 -*-
"""
向量化器（P1 步骤 5）

职责：
  1. 稠密向量（dense_vec 1024 维）—— BGE-M3 本地模型（DashScope API 降级兜底）
  2. 稀疏向量（sparse_vec {index:weight}）—— jieba + 自定义词典 + 停用词 + BM25 风格 TF-IDF
  3. LangGraph 节点 embed_node(state) -> state

关键设计：
- 资源懒加载：第一次调用时才加载 BGE 模型和 jieba 词典，避免启动时间长 / 模型缺失直接崩。
- 模型缺失兜底：BGE 本地模型不存在 → 走 DashScope text-embedding-v3（1024 维，对齐 dim）。
- jieba 资源路径从 settings.JIEBA_CUSTOM_DICT / STOPWORDS_FILE 取，路径不存在只告警不抛错。
- sparse_vec 输出格式严格对齐 Milvus SPARSE_FLOAT_VECTOR：{"<term_id:int>": <weight:float>}
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Iterable

from loguru import logger

from app.config import settings
from app.knowledge.models import ImportState, KnowledgeChunk

# ---------------------------------------------------------------------------
# 全局锁 + 单例，避免多请求重复加载模型 / 重复初始化 jieba
# ---------------------------------------------------------------------------
_BGE_LOCK = threading.Lock()
_BGE_MODEL = None                # FlagEmbedding BGEM3FlagModel 实例
_JIEBA_LOCK = threading.Lock()
_JIEBA_INITIALIZED = False
_TERM_ID_LOCK = threading.Lock()
_TERM_TO_ID: dict[str, int] = {}  # 词 -> 稀疏索引（纯 hash 确定性分配，不依赖外部字典）


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

    stopwords: set[str] = set()
    jieba_available = False

    with _JIEBA_LOCK:
        # 1) 尝试 import jieba
        try:
            import jieba  # noqa: F401
            jieba_available = True
        except Exception as exc:
            logger.warning(f"jieba 未安装，稀疏向量退化到简单空格分词（{exc.__class__.__name__}: {exc}）")
            jieba_available = False

        # 2) 加载自定义词典（只做一次）
        if jieba_available and not _JIEBA_INITIALIZED:
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

        # 3) 加载停用词（每次读取，保证内容可热更）
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
        return stopwords, jieba_available


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


def _dashscope_embed_batch(texts: list[str]) -> list[list[float]]:
    """DashScope 兼容模式 text-embedding-v3（输出 1024 维对齐 Milvus Schema）。

    关键修复（2026-08-10，根因#3 同步）：
      - httpx 与 requests 一样，默认会信任 env / Windows 系统代理（IE 注册表），
        若本机存在 127.0.0.1 本地代理劫持，就会出现 SSLEOF / ReadTimeout 或 503。
        通过 trust_env=False + proxy=None 强制直连出口 LLM_BASE_URL。
    """
    import httpx

    api_key = settings.LLM_API_KEY
    if not api_key:
        raise RuntimeError("BGE-M3 本地模型不可用且 LLM_API_KEY 未配置，无法生成稠密向量")
    url = str(settings.LLM_BASE_URL).rstrip("/") + "/embeddings"
    payload = {
        "model": "text-embedding-v3",
        "input": texts,
        "dimensions": 1024,
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


def encode_dense_batch(texts: list[str]) -> list[list[float]]:
    """
    批量生成稠密向量。

    策略：
      · texts 全为空 → 直接返回全零向量（避免 API 报错）
      · 本地 BGE-M3 可用 → 优先本地（快、不花钱）
      · 本地不可用 → DashScope Embedding API（兜底）
      · 任何失败 → 退化为 sha256 伪向量（让导入流程不中断，后续可重建）
    """
    dim = settings.EMBEDDING_DIM
    safe_texts = [t if t and t.strip() else "." for t in texts]

    # 1) 本地 BGE-M3
    bge = _get_bge_model()
    if bge is not None:
        try:
            out = bge.encode(
                safe_texts,
                batch_size=settings.EMBED_BATCH_SIZE,
                max_length=8192,
            )
            vecs = out.get("dense_vecs", [])
            if len(vecs) == len(safe_texts):
                return [
                    (list(v) if len(v) == dim else _pad_or_trim(v, dim))
                    for v in vecs
                ]
        except Exception as exc:
            logger.warning(f"BGE-M3 encode 失败，降级 DashScope Embedding：{exc}")

    # 2) DashScope 兜底
    try:
        return _dashscope_embed_batch(safe_texts)
    except Exception as exc:
        logger.warning(f"DashScope Embedding 也失败（{exc}）→ 退化为伪向量，仅保证导入不中断")

    # 3) 最终兜底：确定性伪向量（可导入但检索质量极差，便于排查）
    return [_pseudo_dense(t, dim) for t in safe_texts]


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

    出错不中断流程，state.error 记录后返回（由下游节点判定跳过）。
    """
    if state.error:
        logger.warning("跳过 embed_node（前序节点已出错）")
        return {}
    if not state.chunks:
        logger.info("embed_node：chunks 为空，跳过")
        return {}

    try:
        # 4.1 稠密向量（按 EMBED_BATCH_SIZE 批处理）
        batch_size = max(1, int(settings.EMBED_BATCH_SIZE))
        all_texts = [c.content for c in state.chunks]
        all_dense: list[list[float]] = []
        for i in range(0, len(all_texts), batch_size):
            batch = all_texts[i : i + batch_size]
            all_dense.extend(encode_dense_batch(batch))

        # 4.2 稀疏向量 + 回填 chunk
        for idx, chunk in enumerate(state.chunks):
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

        logger.info(f"embed_node 完成：{len(state.chunks)} chunks × dense(1024) + sparse")
        return {}
    except Exception as exc:
        msg = f"向量化失败：{exc.__class__.__name__}: {exc}"
        logger.exception(msg)
        return {"error": msg}
