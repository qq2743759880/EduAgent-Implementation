# -*- coding: utf-8 -*-
"""
task27 prompt caching 三层组织（GWT④；tech-source-audit §二 R5）。

对齐 Claude Code prompt-caching 官方文档（system prompt 三层组织：内置/CLI扩展/项目 MEMORY；
cache_read 命中；缓存失效场景清单：模型切换/effort 变更/环境变量/MCP 工具变更/compaction/升级）。

本模块将可缓存前缀按三层组织并记录失效原因：
  - system       层：模型 / 静态系统规则 / 内置工具规范（模型切换、effort 变更 → 失效）
  - project      层：项目级 MCP 工具清单（MCP 工具增删改 / 描述重写 → 失效）
  - conversation 层：对话级摘要 / 上下文（compaction、消息编辑 → 失效）

每层 key = sha256(content)，set 时若内容变化则记录失效事件（reason + layer + 前后摘要），
供命中率监控 / 审计。纯内存实现，无外部依赖，可直接单测。
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from app.ai.compaction import estimate_tokens

# task-C2：缓存前缀达标配置（对齐 P7）。优先读 settings，导入失败回退默认。
# 2026-08-29 实测修正：火山 ark deepseek-v4-flash 的 prompt cache 按 2048-token 分块
# （usage.prompt_tokens_details.cached_tokens：2812 token 前缀第 2 次命中 2048；6012 命中 4096）。
# 旧门槛 1024 < 2048 → cached_tokens 恒为 0，前缀填充形同虚设。故默认值提至 2048。
try:  # pragma: no cover - 配置模块始终可用
    from app.config import settings as _settings

    _PROMPT_CACHE_MIN_TOKENS: int = int(getattr(_settings, "PROMPT_CACHE_MIN_TOKENS", 2048))
    _CACHE_FILLER_VERSION: str = str(getattr(_settings, "CACHE_FILLER_VERSION", "v3"))
    _CACHE_HIT_RATE_SEV: float = float(getattr(_settings, "CACHE_HIT_RATE_SEV", 0.5))
except Exception:  # pragma: no cover
    _PROMPT_CACHE_MIN_TOKENS = 2048
    _CACHE_FILLER_VERSION = "v3"
    _CACHE_HIT_RATE_SEV = 0.5

__all__ = [
    "PromptCache",
    "CACHE_LAYERS",
    "ensure_min_prefix",
    "anchor_guard",
    "evaluate_cache_sev",
]

CACHE_LAYERS = ("system", "project", "conversation")

# 静态填充注释块（task-C2 ①）：逐字节稳定（无时间/环境相关变量），放 system 层末尾、工具清单后，
# 把短前缀撑到 ≥2048 token 跨过火山 ark 缓存门槛（2026-08-29 实测：2048-token 分块缓存）；
# 改版本号（CACHE_FILLER_VERSION）才变字节，否则两次构建完全一致。
CACHE_FILLER_BLOCK = (
    "\n# cache-filler {ver} —— 静态前缀填充，请勿修改（保 prompt-cache 前缀稳定）"
    "本段为固定注释，用于撑起可缓存前缀长度以满足 provider 最小缓存门槛（>=2048 tokens）。"
    "系统规则与工具清单见上方，本段内容不参与任何决策逻辑，仅作前缀占位以最大化缓存命中率。"
    "EduAgent 教育场景：知识点/学习目标/用户偏好均按 topic 分区存储，检索时按需读取。"
    "安全边界：不泄露用户隐私；不执行未授权写操作；降级时返回友好提示而非异常。"
    "缓存策略：闸门前（System+工具桩）永不变更，动态信息经新消息注入，工具 schema 变更只失效单条。"
).replace("{ver}", _CACHE_FILLER_VERSION)


def ensure_min_prefix(
    prefix: str,
    *,
    min_tokens: int | None = None,
    filler_version: str | None = None,
) -> str:
    """把前缀撑到 ≥ min_tokens（默认 PROMPT_CACHE_MIN_TOKENS=2048），跨过缓存门槛。

    - 仅当 estimate_tokens(prefix) < min_tokens 时追加静态填充注释块（逐字节稳定）。
    - 填充块整块追加直到达标，两次相同输入返回字节完全一致（AC1）。
    - 不改动原有前缀内容/工具桩序（对齐 Glean 静态优先），填充只追加在末尾。
    """
    min_tokens = int(min_tokens if min_tokens is not None else _PROMPT_CACHE_MIN_TOKENS)
    if estimate_tokens(prefix) >= min_tokens:
        return prefix

    block = CACHE_FILLER_BLOCK
    if filler_version is not None:
        block = block.replace(_CACHE_FILLER_VERSION, filler_version)
    out = prefix
    # 逐块追加直到达标（确定性循环，无随机/时间）
    guard = 0
    while estimate_tokens(out) < min_tokens and guard < 500:
        out = out + block
        guard += 1
    return out


def anchor_guard(
    anchor_prefix: str,
    dynamic_messages: list[dict],
    *,
    expected_prefix: str | None = None,
    cache: "PromptCache | None" = None,
) -> list[dict]:
    """锚定闸门（task-C2 ③，对齐 Glean/Claude 锚定策略）。

    - 闸门前 System+工具前缀永远在 messages[0]，动态信息（用户问题/记忆/检索上下文）经
      后续消息注入，不进前缀 → 前缀字节不变，缓存命中。
    - expected_prefix 提供时做漂移检测：若锚定前缀与期望不一致，记录 anchor_drift 失效事件
      （cache 非 None 时），用于监控前缀是否被意外改动。
    """
    if expected_prefix is not None and anchor_prefix != expected_prefix:
        if cache is not None:
            cache.invalidations.append(
                {
                    "ts": time.time(),
                    "layer": "system",
                    "reason": "anchor_drift",
                    "prev_key": _key_of(expected_prefix),
                    "new_key": _key_of(anchor_prefix),
                    "whole_layer": True,
                }
            )
    return [{"role": "system", "content": anchor_prefix}] + list(dynamic_messages)


def evaluate_cache_sev(hit_rate: float, *, threshold: float | None = None) -> dict:
    """命中率 SEV 评估（对齐 Claude 把命中率当 uptime，低即 SEV）。

    返回 {hit_rate, threshold, sev(bool), level}；命中率 < threshold → sev=True（记 SEV）。
    """
    threshold = float(threshold if threshold is not None else _CACHE_HIT_RATE_SEV)
    hr = round(float(hit_rate), 4)
    sev = hr < threshold
    level = "SEV" if sev else ("WARN" if hr < threshold + 0.2 else "OK")
    return {"hit_rate": hr, "threshold": round(threshold, 4), "sev": sev, "level": level}


def evaluate_hit_rate(
    usage_list: list[dict],
    *,
    model: str = "fast",
    layer: str = "project",
) -> dict:
    """纯计量函数（无 LLM，可单测）：从一组 usage 字典计算命中率 + SEV 告警（task-C2 ④）。

    usage_list 每个元素形如 {"prompt_cache_hit_tokens": int, "prompt_cache_miss_tokens": int}
    （与 DeepSeek provider 字段一致）。返回按 {model, layer} 维度的命中率与 SEV 评估。
    """
    hit_acc = miss_acc = 0
    for u in usage_list:
        hit_acc += int(u.get("prompt_cache_hit_tokens") or 0)
        miss_acc += int(u.get("prompt_cache_miss_tokens") or 0)
    total = hit_acc + miss_acc
    hit_rate = round(hit_acc / total, 4) if total else 0.0
    sev = evaluate_cache_sev(hit_rate)
    return {
        "model": model,
        "layer": layer,
        "total_hit_tokens": hit_acc,
        "total_miss_tokens": miss_acc,
        "hit_rate": hit_rate,
        "sev": sev,
    }


def _key_of(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


class PromptCache:
    """三层前缀缓存 + 命中统计 + 失效原因记录。"""

    def __init__(self) -> None:
        # layer -> { key(str sha256) : {"content":..., "set_at":float} }
        self._store: dict[str, dict[str, dict[str, Any]]] = {l: {} for l in CACHE_LAYERS}
        # key(content) 缓存命中判定：layer -> key -> 记录
        self._hits: dict[str, int] = {l: 0 for l in CACHE_LAYERS}
        self._misses: dict[str, int] = {l: 0 for l in CACHE_LAYERS}
        # 失效事件清单 [{ts, layer, key, reason, prev_key, new_key}]
        self.invalidations: list[dict[str, Any]] = []

    # ---------- 写入 + 失效检测 ----------
    def set(self, layer: str, content: str, *, reason: str = "content_change") -> dict:
        """写入某层缓存；内容变化则记录失效原因并替换。返回 cache_control 描述。"""
        if layer not in CACHE_LAYERS:
            raise ValueError(f"未知缓存层: {layer}，可用 {list(CACHE_LAYERS)}")
        new_key = _key_of(content)
        prev = self._store[layer].get(new_key)
        if prev is not None:
            # 同一 key（内容未变）→ 命中态，无失效
            return {"layer": layer, "key": new_key, "changed": False, "cached": True}
        prev_key = None
        # 该层是否有旧内容（原型 key 不同则视为失效）
        existing = self._store[layer]
        if existing:
            prev_key = next(iter(existing.keys()))
            self.invalidations.append(
                {
                    "ts": time.time(),
                    "layer": layer,
                    "reason": reason,
                    "prev_key": prev_key,
                    "new_key": new_key,
                    "whole_layer": True,
                }
            )
        self._store[layer] = {new_key: {"content": content, "set_at": time.time()}}
        self._misses[layer] += 1
        return {"layer": layer, "key": new_key, "changed": True, "cached": False, "prev_key": prev_key}

    # ---------- 读取 + 命中判定 ----------
    def get(self, layer: str, content: str) -> str | None:
        """按内容取缓存 key；命中（key 已存在）返回 key 并计命中，否则计 miss 返回 None。"""
        if layer not in CACHE_LAYERS:
            raise ValueError(f"未知缓存层: {layer}")
        key = _key_of(content)
        if key in self._store[layer]:
            self._hits[layer] += 1
            return key
        self._misses[layer] += 1
        return None

    # ---------- 显式失效 ----------
    def invalidate(self, layer: str, *, reason: str) -> None:
        """显式失效某层（模型切换/effort 变更/MCP 工具变更/compaction/升级等场景调用）。"""
        if layer not in CACHE_LAYERS:
            raise ValueError(f"未知缓存层: {layer}")
        existing = self._store[layer]
        if existing:
            prev_key = next(iter(existing.keys()))
            self.invalidations.append(
                {"ts": time.time(), "layer": layer, "reason": reason, "prev_key": prev_key, "new_key": None, "whole_layer": True}
            )
        self._store[layer] = {}

    # ---------- 按工具粒度写入（task-C2 ②：defer_loading 保前缀稳定）----------
    def set_stubs(self, layer: str, stubs: dict[str, str], *, reason: str = "tool_change") -> dict:
        """按工具名粒度写入项目层桩（deferred 桩：name+summary）。

        与 `set`（整层替换）不同：本方法只记录「变化的工具级失效」，不触发整层失效事件——
        对齐 Claude/Glean：工具增删或某工具 schema 变更只影响该工具单条，前缀其余桩字节不变。

        - 已存在且内容未变 → 命中（hit），不记失效；
        - 新增工具 → 记 add（miss），不记整层失效；
        - 内容变化的工具 → 记 per-tool 失效（whole_layer=False）；
        - 被移除的工具 → 记 per-tool 失效（whole_layer=False）。
        仅 `invalidate()` 显式清空才产生 whole_layer=True 的整层失效事件。
        """
        if layer not in CACHE_LAYERS:
            raise ValueError(f"未知缓存层: {layer}")
        prev = self._store[layer]  # dict name -> content
        changed: list[str] = []
        added: list[str] = []
        for name, content in stubs.items():
            if name in prev:
                if prev[name] != content:
                    changed.append(name)
            else:
                added.append(name)
        removed = [n for n in prev if n not in stubs]
        if changed or removed:
            self.invalidations.append(
                {
                    "ts": time.time(),
                    "layer": layer,
                    "reason": reason,
                    "changed_tools": changed,
                    "removed_tools": removed,
                    "whole_layer": False,
                }
            )
        # 统计：未变→hit；新增/变化→miss
        for name, content in stubs.items():
            if name in prev and prev[name] == content:
                self._hits[layer] += 1
            else:
                self._misses[layer] += 1
        self._store[layer] = dict(stubs)
        return {"layer": layer, "changed_tools": changed, "added": added, "removed": removed, "whole_layer": False}
    def stats(self) -> dict[str, Any]:
        total_reads = {l: self._hits[l] + self._misses[l] for l in CACHE_LAYERS}
        hit_rate = {
            l: round(self._hits[l] / total_reads[l], 4)
            if total_reads[l] > 0
            else 0.0
            for l in CACHE_LAYERS
        }
        return {
            "hits": dict(self._hits),
            "misses": dict(self._misses),
            "hit_rate": hit_rate,
            "invalidations": len(self.invalidations),
            "layers": {l: len(self._store[l]) for l in CACHE_LAYERS},
        }

    def invalidations_list(self, *, layer: str | None = None) -> list[dict[str, Any]]:
        if layer is None:
            return list(self.invalidations)
        return [i for i in self.invalidations if i["layer"] == layer]