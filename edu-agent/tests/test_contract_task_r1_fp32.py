# -*- coding: utf-8 -*-
"""
R1-① 契约测试：fp32 批处理评估（task-R1 技术批判 批判1 落地）。

验收指标（来自 task-R1 技术批判）：
- fp32 模式下「排序稳定」：跨请求把多对的 (query, content) 合并成一条大 batch
  一次前向，不改变单对分数（每对序列独立，与分批/逐对调用分数逐位一致）。
- 分数噪声 < 1e-4：fp32 路径全程 float32（仅末尾 .float() 无损），相对参考实现噪声≈0；
  fp16 路径因 .half() 引入 ~1e-2 级噪声——这正是 R1-① 启用 fp32 要消除的。

全程无真实模型（不加载 2.2GB），用 fake torch/transformers 驱动真实
reranker._load / rerank_pairs 代码路径，确定性验证精度分支与排序稳定性。
真实 CUDA 一致性见 gated 测试（R1_RUN_CUDA_TESTS=1）。
"""
from __future__ import annotations

import os
import sys
import types

import numpy as np
import pytest

import app.config as app_config
import app.knowledge.reranker as reranker_mod


# ======================================================================
# fake torch / transformers：让真实 Reranker._load 与 rerank_pairs 跑起来
# ======================================================================
class _FakeTensor:
    """极简张量替身：携带 (queries, passages) 文本，支持 .to()/.view()/.float()/.cpu()/.tolist()。"""

    def __init__(self, data=None, queries=None, passages=None):
        self._data = data
        self.queries = queries
        self.passages = passages

    def to(self, device):
        return _FakeTensor(self._data, self.queries, self.passages)

    def view(self, *shape):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return []


class _FakeLogits:
    """模型输出 .logits：支持 .view(-1,).float().cpu().tolist()。"""

    def __init__(self, scores: list[float]):
        self._scores = list(scores)

    def view(self, *shape):
        return self

    def float(self):
        return self

    def cpu(self):
        return self

    def tolist(self):
        return list(self._scores)


class _FakeResult:
    def __init__(self, logits):
        self.logits = logits


def _fp16_round(x: float) -> float:
    """模拟 fp16 舍入（与真实 .half() 噪声同源），用于证明 fp16 路径噪声。"""
    return float(np.float32(x).astype(np.float16).astype(np.float32))


def _ref_score(query: str, passage: str) -> float:
    """确定性参考分数（非整数幅值，便于暴露 fp16 舍入噪声）。"""
    return (len(query) * 1.23456789 + len(passage) * 9.87654321) % 10.0


class _FakeModel:
    @classmethod
    def from_pretrained(cls, *a, **k):
        return cls()

    def __init__(self):
        self.is_half = False
        self.device = None

    def half(self):
        self.is_half = True
        return self

    def to(self, device):
        self.device = device
        return self

    def eval(self):
        return self

    def __call__(self, **inputs):
        return self.forward(**inputs)

    def parameters(self):
        outer = self

        class _Param:
            device = outer.device if outer.device is not None else "cuda"

        return iter([_Param()])

    def forward(self, **inputs):
        qt = inputs.get("input_ids")
        queries = getattr(qt, "queries", []) or []
        passages = getattr(qt, "passages", []) or []
        ref = [_ref_score(q, p) for q, p in zip(queries, passages)]
        if self.is_half:
            scores = [_fp16_round(s) for s in ref]
        else:
            scores = [float(s) for s in ref]  # fp32：无损
        return _FakeResult(logits=_FakeLogits(scores))


class _FakeTokenizer:
    @classmethod
    def from_pretrained(cls, *a, **k):
        return cls()

    def __init__(self, *a, **k):
        pass

    def __call__(self, text=None, text_pair=None, **kw):
        queries = text if isinstance(text, list) else [text]
        passages = text_pair if isinstance(text_pair, list) else [text_pair]
        return {
            "input_ids": _FakeTensor(None, queries=queries, passages=passages),
            "attention_mask": _FakeTensor(None),
        }


def _make_fake_torch(cuda_available: bool):
    fake = types.ModuleType("torch")

    class _Cuda:
        @staticmethod
        def is_available():
            return cuda_available

    fake.cuda = _Cuda()

    class _NoGrad:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake.no_grad = _NoGrad
    return fake


def _make_fake_transformers():
    fake = types.ModuleType("transformers")
    fake.AutoTokenizer = _FakeTokenizer
    fake.AutoModelForSequenceClassification = _FakeModel
    return fake


class _SettingsProxy:
    """只读代理：以真实 settings 为基础，按 overrides 覆盖个别字段（避免 pydantic setattr 限制）。"""

    def __init__(self, base, **overrides):
        object.__setattr__(self, "_base", base)
        object.__setattr__(self, "_overrides", overrides)

    def __getattr__(self, name):
        ov = object.__getattribute__(self, "_overrides")
        if name in ov:
            return ov[name]
        return getattr(object.__getattribute__(self, "_base"), name)


@pytest.fixture
def fake_model_env(monkeypatch, tmp_path):
    """注入 fake torch/transformers，让真实 Reranker._load 跑通（不加载模型文件）。"""
    fake_torch = _make_fake_torch(True)
    fake_tf = _make_fake_transformers()
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_tf)
    # 让 RERANKER_PATH 存在以通过 _load 前置检查
    model_dir = tmp_path / "fake_model"
    model_dir.mkdir()
    proxy = _SettingsProxy(
        app_config.settings,
        RERANKER_PATH=str(model_dir),
        RERANKER_DEVICE="cuda",
        RERANKER_BATCH_SIZE=4,
        RERANKER_MAX_LENGTH=512,
        RERANKER_PRECISION="fp16",
    )
    monkeypatch.setattr(reranker_mod, "settings", proxy)
    return proxy


# ======================================================================
# 默认配置 & 精度分支（真实 _load 代码路径）
# ======================================================================
def test_default_precision_is_fp16():
    """默认 fp16：历史行为零回归。"""
    assert app_config.settings.RERANKER_PRECISION == "fp16"


def test_load_fp32_skips_half(fake_model_env):
    """R1-①：RERANKER_PRECISION=fp32 时 _load 不调用 .half()（高精度路径）。"""
    fake_model_env.RERANKER_PRECISION = "fp32"
    rk = reranker_mod.Reranker()
    rk._load()
    assert rk._model is not None
    assert rk._model.is_half is False, "fp32 模式不应 .half()，否则引入 fp16 噪声"
    assert rk._model.device == "cuda"


def test_load_fp16_calls_half_on_cuda(fake_model_env):
    """默认 fp16 + cuda 可用 → _load 调用 .half()（历史行为零回归）。"""
    fake_model_env.RERANKER_PRECISION = "fp16"
    rk = reranker_mod.Reranker()
    rk._load()
    assert rk._model.is_half is True, "fp16 模式应 .half() 省显存"


# ======================================================================
# fp32 排序稳定 + 噪声 < 1e-4
# ======================================================================
def test_fp32_scores_lossless_and_ordering_stable(fake_model_env):
    """fp32 路径：分数相对参考无损（噪声≈0 < 1e-4），跨请求批合并不改变单对分数（排序稳定）。"""
    fake_model_env.RERANKER_PRECISION = "fp32"
    rk = reranker_mod.Reranker()
    rk._load()
    pairs = [(f"q{i}", f"passage content number {i} with extra text") for i in range(20)]
    ref = [_ref_score(q, c) for q, c in pairs]

    # 一次调用（跨请求合并为一条大 batch，内部按 BATCH_SIZE=4 分多批）
    merged = rk.rerank_pairs(pairs)
    assert merged is not None
    # 噪声 < 1e-4（fp32 无损）
    for got, exp in zip(merged, ref):
        assert got == pytest.approx(exp, abs=1e-4)

    # 分批逐对调用 vs 一次合并：分数逐位一致（排序稳定）
    chunked = []
    for i in range(0, len(pairs), 5):
        chunked.extend(rk.rerank_pairs(pairs[i:i + 5]))
    assert chunked == pytest.approx(merged, abs=1e-9)

    # 排序稳定：两种调用方式得到的排序索引一致
    order_merged = sorted(range(len(merged)), key=lambda i: merged[i], reverse=True)
    order_chunked = sorted(range(len(chunked)), key=lambda i: chunked[i], reverse=True)
    assert order_merged == order_chunked


def test_fp16_introduces_noise_fp32_eliminates(fake_model_env):
    """对照：fp16 路径引入 ~1e-2 级噪声（批判1 原问题），fp32 消除（R1-① 目标）。"""
    pairs = [(f"q{i}", f"passage content number {i} with extra text") for i in range(20)]
    ref = [_ref_score(q, c) for q, c in pairs]

    # fp16
    fake_model_env.RERANKER_PRECISION = "fp16"
    rk16 = reranker_mod.Reranker()
    rk16._load()
    fp16_scores = rk16.rerank_pairs(pairs)
    fp16_max_noise = max(abs(g - e) for g, e in zip(fp16_scores, ref))

    # fp32
    fake_model_env.RERANKER_PRECISION = "fp32"
    rk32 = reranker_mod.Reranker()
    rk32._load()
    fp32_scores = rk32.rerank_pairs(pairs)
    fp32_max_noise = max(abs(g - e) for g, e in zip(fp32_scores, ref))

    assert fp16_max_noise > 1e-3, f"fp16 噪声应 ~1e-2 级，实测 {fp16_max_noise}"
    assert fp32_max_noise < 1e-4, f"fp32 噪声应 < 1e-4，实测 {fp32_max_noise}"


# ======================================================================
# 真实 CUDA 一致性（gated，默认跳过）
# ======================================================================
@pytest.mark.skipif(
    os.environ.get("R1_RUN_CUDA_TESTS") != "1",
    reason="真实 CUDA fp32 排序稳定性校验需加载模型，默认跳过（设 R1_RUN_CUDA_TESTS=1 开启）",
)
def test_r1_fp32_real_cuda_ordering_stable(monkeypatch):
    """真实模型 fp32：rerank_pairs 一次合并 vs 分批逐对调用，排序索引一致（噪声 < 1e-4）。"""
    proxy = _SettingsProxy(app_config.settings, RERANKER_PRECISION="fp32")
    monkeypatch.setattr(app_config, "settings", proxy)
    monkeypatch.setattr(reranker_mod, "settings", proxy)
    reranker_mod.Reranker._instance = None  # 强制按新精度重载
    rk = reranker_mod.Reranker.get()
    rk._load_error = None
    q = "什么是检索增强生成"
    contents = [f"passage-{i} " + "内容 " * (i % 7) for i in range(15)]
    pairs = [(q, c) for c in contents]
    merged = rk.rerank_pairs(pairs)
    if merged is None:
        pytest.skip("真实模型未加载（确认 RERANKER_PATH 与 CUDA）")
    chunked = []
    for i in range(0, len(pairs), 5):
        chunked.extend(rk.rerank_pairs(pairs[i:i + 5]))
    assert merged == pytest.approx(chunked, abs=1e-4)
    order_merged = sorted(range(len(merged)), key=lambda i: merged[i], reverse=True)
    order_chunked = sorted(range(len(chunked)), key=lambda i: chunked[i], reverse=True)
    assert order_merged == order_chunked
