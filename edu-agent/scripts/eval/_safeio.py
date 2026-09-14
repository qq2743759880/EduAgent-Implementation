# -*- coding: utf-8 -*-
"""eval 脚本统一安全写出助手(Mimosa 路径穿越修复)。

所有写文件必须经 safe_w():路径规范化+收容校验(仅允许本目录树内),
越界直接抛错。用法:open(safe_w(OUT_PATH), "w", encoding="utf-8")。
"""
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def safe_w(path: str) -> str:
    p = os.path.abspath(os.path.join(_HERE, path))
    if os.path.commonpath([p, _HERE]) != _HERE:
        raise ValueError(f"path escapes eval dir: {path}")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p
