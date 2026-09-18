"""WNEXTRAG1 契约单测：上传 API 命名修复 + classify_internal 不误判。

背景：旧实现用 ``uuid4().hex[:12] + ext`` 作上传临时 basename（如 ``a1b2c3d4e5f6.md``），
100% 命中 ``classify_internal`` 来源正则 ``^[0-9a-f]{8,32}\\.(md|txt|pdf)$``
→ 学生上传的 doc_chunk 全被标 ``internal=True`` → 学生检索侧剔除 → 自己都查不到。

修复（Scheme A）：上传临时名改为非 hex 前缀 ``up_{user_id}_{hex8}_{safe_name}``，
不再命中来源正则；旧 hash 命名（存量 ``_default`` 内部文档）仍按原逻辑判 internal。
"""
import re

import pytest

from app.knowledge.importer.loader import classify_internal
from app.knowledge.routers.upload import _make_upload_basename

# 与 loader.py DEFAULT_INTERNAL_SOURCE_PATTERNS[0] 保持一致，作为契约断言
INTERNAL_SOURCE_RE = re.compile(r"^[0-9a-f]{8,32}\.(md|txt|pdf)$", re.I)


def test_new_upload_basename_is_not_internal_source_pattern():
    """新命名格式不以 hex 开头，不会被来源正则误判为内部文档。"""
    name = _make_upload_basename(1001, "my_course_notes.md")
    assert name.startswith("up_1001_"), name
    assert not INTERNAL_SOURCE_RE.match(name), f"新命名仍命中内部来源正则: {name}"


def test_new_upload_basename_preserves_original_name():
    """新命名保留原文件名，便于追溯。"""
    name = _make_upload_basename(1001, "线性代数_第一章.md")
    assert "线性代数_第一章.md" in name


def test_old_hash_naming_still_classified_internal_backward_compat():
    """迁移期向后兼容：旧 hash 命名文件（如 _default 内部文档库导出）仍判 internal=True。

    这条保证存量 732 条 _default 内部文档在重新导入时依然被正确隐藏，
    不因修复而丢失 internal 标记。
    """
    assert classify_internal("a1b2c3d4e5f6.md", "benign course content") is True
    assert classify_internal("deadbeefcafe1234.pdf", None) is True


def test_new_naming_not_internal_with_benign_content():
    """新命名 + 普通课程内容 → classify_internal 返回 False（学生可见）。"""
    name = _make_upload_basename(1001, "微积分笔记.md")
    assert classify_internal(name, "这是给学生看的微积分求导笔记") is False


def test_classify_internal_still_catches_genuine_internal_content():
    """内容强特征仍生效：即便用新命名，含内部工程术语的内容仍判 internal=True。"""
    name = _make_upload_basename(1001, "项目笔记.md")
    body = "task09 sys_user_auth restore_admin.py 认证表结构需要修正"
    assert classify_internal(name, body) is True


@pytest.mark.parametrize("ext", [".md", ".txt", ".pdf", ".markdown", ".docx"])
def test_new_basename_never_matches_internal_regex_for_allowed_ext(ext):
    """对所有允许的上传后缀，新命名都不命中内部来源正则。"""
    name = _make_upload_basename(7, f"file{ext}")
    assert not INTERNAL_SOURCE_RE.match(name), name
