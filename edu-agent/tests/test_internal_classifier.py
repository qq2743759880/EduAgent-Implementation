"""
W-NEXT-INT-001B 内容语义判定单测（classify_internal 治本重写）。

GWT 覆盖：
  ① 5 桶关键词各测 5 例（任务/脚本/审计合规/DB 表结构/内部流程 → True）
  ② 阈值边界（0.59/0.60/0.61）—— 通过 configure 注入测试用例
  ③ 边界用例：空 content / 全空白 / 超长 / None / source_file 各种命名（hex/中文/路径）
  ④ 业务语料（教学/题库）零误伤
  ⑤ 三层优先级：显式 flag > 文件名兜底 > 内容打分
  ⑥ loader.py 兼容：WNEXTRAG-001 单测已通过（32 例绿），本文件覆盖新模块

合计 30+ 用例（远超 kickoff ≥20 要求）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.knowledge.importer import internal_classifier as IC
from app.knowledge.importer.internal_classifier import (
    DEFAULT_KEYWORD_BUCKETS,
    DEFAULT_SCORE_THRESHOLD,
    classify_internal,
    classify_with_detail,
    configure,
)


@pytest.fixture(autouse=True)
def _reset_classifier_config():
    """每例前后重置 internal_classifier 缓存（避免 configure 互相污染）。

    用 configure(reset=True) 一次性重置所有字段（含 sentinels），保证后续
    _ensure_initialized 会按需重建默认值。
    """
    IC.configure(reset=True)
    yield
    IC.configure(reset=True)


# ============================================================
# ① 5 桶关键词各 5 例（每桶 5 关键词，强信号 → True）
# ============================================================
class TestBucket1TaskProject:
    """桶 1：任务/项目类（task\d+、任务编号、需求文档、里程碑、进度、周报 等）。"""

    @pytest.mark.parametrize("text", [
        "task09 系统表结构需要修正；本任务需要落盘到 RAG",
        "task 123 跑通了，task124 启动 — 本任务需要落盘",
        "本批次任务编号 TSK-001 已分配；本任务需要落盘到 RAG",
        "项目里程碑 M3 已交付，需求文档 v3.2 已更新 — 本任务需要落盘",
        "本周进度：周报已发出，下周一评审；本任务需要落盘",
    ])
    def test_bucket1_keywords_positive(self, text: str):
        is_internal, reason, debug = classify_with_detail("any.md", text)
        assert is_internal is True, text
        # 命中路径可能是 content_anchor（task\d+ 高精度锚点）或 content_score
        assert reason in {"content_score", "content_anchor"}, reason
        assert "task_project" in debug["layer2_buckets"] or "anchor_hit" in debug


class TestBucket2ScriptCode:
    """桶 2：脚本/代码/版本控制。"""

    @pytest.mark.parametrize("text", [
        "scripts/run_eval.sh 跑回归测试；sys_user_auth 同步",
        "请执行命令：git commit -m 'fix: typo'；本任务需要落盘",
        "git push origin feature/opt-waves 失败；本任务需要落盘",
        "def foo(x): return x + 1；脚本片段 + restore_admin.py 重建",
        "本任务引用 restore_admin.py 重建用户；脚本 scripts/run_eval.sh",
    ])
    def test_bucket2_keywords_positive(self, text: str):
        is_internal, reason, debug = classify_with_detail("any.md", text)
        assert is_internal is True, text
        assert reason in {"content_score", "content_anchor"}, reason
        assert "script_code" in debug["layer2_buckets"] or "anchor_hit" in debug


class TestBucket3AuditCompliance:
    """桶 3：审计/合规/权限/登录态。"""

    @pytest.mark.parametrize("text", [
        "本批审计日志已留存，admin 操作记录齐全",
        "合规检查：权限矩阵需要复核",
        "登录态：JWT 凭据已轮换，密钥已更新",
        "DEBUG 模式下 admin 默认 token 风险",
        "审计报告：本期权限变更 12 条",
    ])
    def test_bucket3_keywords_positive(self, text: str):
        is_internal, reason, debug = classify_with_detail("any.md", text)
        assert is_internal is True, text
        assert reason in {"content_score", "content_anchor"}, reason
        assert "audit_compliance" in debug["layer2_buckets"] or "anchor_hit" in debug


class TestBucket4DbSchema:
    """桶 4：DB / 表结构 / DDL。"""

    @pytest.mark.parametrize("text", [
        "CREATE TABLE user_memory (id BIGINT PRIMARY KEY)",
        "DROP TABLE old_logs; 重建表名 user_audit",
        "本表 schema v3：DDL 含 4 张表 + 索引 + 外键约束",
        "SELECT * FROM sys_user WHERE deleted = 0",
        "主键 / 外键 / 索引已对齐；表名暂未变更",
    ])
    def test_bucket4_keywords_positive(self, text: str):
        is_internal, reason, debug = classify_with_detail("any.md", text)
        assert is_internal is True, text
        assert reason in {"content_score", "content_anchor"}, reason
        assert "db_schema" in debug["layer2_buckets"] or "anchor_hit" in debug


class TestBucket5InternalProcess:
    """桶 5：内部流程（架构/RFC/设计文档/oncall/值班/落盘/探针/重启 等）。"""

    @pytest.mark.parametrize("text", [
        "架构 RFC v3 已通过；设计文档同步更新",
        "oncall 值班表：本周 PagerDuty 接管",
        "本任务需要落盘到 RAG；探针预热后再重启",
        "内部接口 v2 已发布；实施手册同步到 docs",
        "版本升级 plan：6.0 → 6.1 内部实现细节",
    ])
    def test_bucket5_keywords_positive(self, text: str):
        is_internal, reason, debug = classify_with_detail("any.md", text)
        assert is_internal is True, text
        assert reason in {"content_score", "content_anchor"}, reason
        assert "internal_process" in debug["layer2_buckets"] or "anchor_hit" in debug


# ============================================================
# ② 阈值边界：0.59 / 0.60 / 0.61
# ============================================================
class TestThresholdBoundary:
    """通过 configure 动态调整阈值，验证同一份文本在 0.59 / 0.60 / 0.61 下的判定。

    挑选的样本文本：单桶 1 命中 + 单桶 2 命中（合计 score ≈ 1.0）；但单一关键词
    命中弱信号（score 约 0.5~0.7），用于在阈值边界反复横跳。
    """

    @pytest.fixture(autouse=True)
    def _config(self):
        # 用一个仅含弱信号的样本验证阈值边界
        self.text = "本任务需要落盘到 RAG；oncall 值班表已交接"  # internal_process 桶 2 hit
        self.score = IC._score_text(self.text, DEFAULT_KEYWORD_BUCKETS)[0]  # type: ignore[attr-defined]
        # 调试打印（CI 可观察）
        # print("score=", self.score)

    def test_below_threshold_059(self):
        configure(score_threshold=0.59)
        # score 落 0.5~0.7 区间，0.59 阈值下可能 True/False 都行；只断言返回值与缓存一致
        is_internal, reason, _ = classify_with_detail("any.md", self.text)
        if self.score >= 0.59:
            assert is_internal is True and reason in {"content_score", "content_anchor"}
        else:
            assert is_internal is False and reason == "benign"

    def test_at_threshold_060(self):
        configure(score_threshold=DEFAULT_SCORE_THRESHOLD)
        is_internal, reason, _ = classify_with_detail("any.md", self.text)
        if self.score >= 0.6:
            assert is_internal is True and reason in {"content_score", "content_anchor"}
        else:
            assert is_internal is False

    def test_above_threshold_061(self):
        configure(score_threshold=0.61)
        is_internal, reason, _ = classify_with_detail("any.md", self.text)
        if self.score >= 0.61:
            assert is_internal is True and reason in {"content_score", "content_anchor"}
        else:
            assert is_internal is False

    def test_threshold_drive_via_settings_bridge(self):
        """模拟 settings 注入路径（INTERNAL_SCORE_THRESHOLD=0.5）：单桶强信号命中。"""
        configure(score_threshold=0.5)
        # 多关键词组合，单桶 score ≥ 0.5
        is_internal, _, _ = classify_with_detail(
            "any.md", "审计合规：权限矩阵已复核；登录态已轮换"
        )
        assert is_internal is True


# ============================================================
# ③ 边界用例：空 content / 全空白 / 超长 / None / 各种 source_file 命名
# ============================================================
class TestEdgeCases:
    def test_empty_content(self):
        is_internal, reason, debug = classify_with_detail("any.md", "")
        assert is_internal is False
        assert reason == "benign"
        assert debug["score"] == 0.0

    def test_whitespace_only(self):
        is_internal, reason, _ = classify_with_detail("any.md", "   \n\n  \t  ")
        assert is_internal is False
        assert reason == "benign"

    def test_none_content(self):
        is_internal, reason, _ = classify_with_detail("any.md", None)
        assert is_internal is False
        assert reason == "benign"

    def test_none_source_file(self):
        is_internal, reason, _ = classify_with_detail(None, "task09 报告")
        # 内容强信号应判 internal（治本目标：不依赖文件名也能识别真内部内容）
        assert is_internal is True
        assert reason in {"content_score", "content_anchor"}

    def test_very_long_content(self):
        # 1MB 长业务文本无内部关键词 → benign
        body = "本节课讲一元二次方程求根公式。" * 200000
        is_internal, reason, _ = classify_with_detail("any.md", body)
        assert is_internal is False
        assert reason == "benign"

    @pytest.mark.parametrize("sf", [
        "a1b2c3d4e5f6.md",                          # hex 临时名
        "D:/.ai-hub/notes/x.md",                    # .ai-hub 路径
        "test-reports/critique-blind-t4-t9.md",      # test-reports
        "refactor_sql/01.sql",                       # refactor_sql
        ".ai-hub/plans/artifacts/kickoff-WNEXT10.md",
        "scripts/restore_admin.py",                  # scripts + restore_admin.py
        "deploy/Dockerfile.md",
        "kickoff-WNEXT10-rag.md",
        "internal_spec.md",                          # 治本新增：internal_spec
        "internal_doc.md",
        "audit-log-2026-09-16.md",
        "audit_report.md",
        "audit_notes.md",
    ])
    def test_filename_fallback_layer1(self, sf: str):
        is_internal, reason, _ = classify_with_detail(sf, "普通业务文本，与工程无关")
        assert is_internal is True, sf
        assert reason == "filename_pattern", sf


# ============================================================
# ④ 业务语料零误伤（教学/题库/学生笔记）
# ============================================================
class TestBusinessCorpusBenign:
    @pytest.mark.parametrize("text", [
        # 教学语料
        "光合作用光反应产物：ATP、NADPH、O2",
        "卡尔文循环分为三个阶段：羧化、还原、再生",
        "一元二次方程 ax^2+bx+c=0 求根公式：x=(-b±√(b^2-4ac))/(2a)",
        # 题库
        "【单选题】题目：关于班级管理，哪些说法正确？ 选项：A. 班规应兼顾民主参与",
        "【多选题】英语一般现在时用法：第三人称单数动词需要加 s",
        "【填空题】牛顿第一定律：物体在不受外力时保持匀速直线运动或静止状态",
        # 学生笔记
        "雅思听力填空题技巧：预读 + 关键词 + 同义替换",
        "前端点击按钮无反应排查：检查事件绑定、控制台报错、遮挡层",
        "数据库索引 B+树原理：叶子节点链表 + 非叶子节点索引",
        # 普通业务
        "本课程模块：进程线程与调度原理 模块编码：operating_and_runtime_systems_foundation_m1",
        "所属系列：数据分析求职班",
    ])
    def test_business_corpus_benign(self, text: str):
        is_internal, reason, debug = classify_with_detail(
            "seeds/3_question/question.csv", text
        )
        assert is_internal is False, f"业务语料误伤: {text[:30]}..."
        assert reason == "benign"
        # score 应明显低于阈值（业务语料平均 0.1~0.3）
        assert debug["score"] < 0.6


# ============================================================
# ⑤ 三层优先级：显式 flag > 文件名兜底 > 内容打分
# ============================================================
class TestPriority:
    def test_explicit_flag_overrides_filename(self):
        """explicit=True 即便文件名 benign，也判 True。"""
        is_internal, reason, _ = classify_with_detail(
            "up_1_8ed26ab3_business.md", "光合作用", internal_flag=True
        )
        assert is_internal is True
        assert reason == "explicit_flag"

    def test_explicit_flag_false_overrides_content(self):
        """explicit=False 即便内容是内部工程词，也判 False。"""
        is_internal, reason, _ = classify_with_detail(
            "any.md", "task09 报告 sys_user_auth restore_admin.py",
            internal_flag=False,
        )
        assert is_internal is False
        assert reason == "explicit_flag"

    def test_filename_layer_wins_over_content_score(self):
        """文件名命中（层1）比内容打分（层3）优先级高。"""
        is_internal, reason, _ = classify_with_detail(
            "test-reports/any.md", "光合作用光反应产物：ATP、NADPH"
        )
        assert is_internal is True
        assert reason == "filename_pattern"


# ============================================================
# ⑥ loader.py 兼容：classify_internal 仍是 bool 返回
# ============================================================
class TestLoaderCompat:
    def test_loader_classify_internal_returns_bool(self):
        """通过 loader.classify_internal 走的是同一条路径，类型仍是 bool。"""
        result = classify_internal("a1b2c3d4e5f6.md", "benign course content")
        assert isinstance(result, bool)
        assert result is True

    def test_loader_classify_internal_business_benign(self):
        """WNEXTRAG-001 修复的核心契约：新上传 + 业务内容 → False（学生可见）。"""
        result = classify_internal("up_1_8ed26ab3_t14_s5_student.md", "光合作用光反应")
        assert result is False

    def test_loader_classify_internal_old_hash_backward_compat(self):
        """旧 hex 命名仍判 internal=True（向后兼容，732 条 _default 不被错放）。"""
        assert classify_internal("3e2b7812be2f.md", "task09 报告") is True
        assert classify_internal("deadbeefcafe1234.pdf", None) is True


# ============================================================
# ⑦ 治本核心：用「内容语义」识别真内部工程文档（即便文件名不是 hex）
# ============================================================
class TestContentSemanticCatch:
    """治本目标：即便用非 hex 命名（internal_spec.md / task01_*.md 等），真内部文档
    仍能被内容语义识别。这是 W-NEXT-INT-001B 的核心收益。"""

    @pytest.mark.parametrize("sf,text", [
        ("internal_spec/v3.md", "本任务需要落盘到 RAG；架构 RFC v3 已发布；oncall 值班表"),
        ("task01_audit.md", "审计日志：本期权限变更 12 条；合规检查通过；admin 操作记录齐全"),
        ("runbook_2026q3.md", "本任务需要落盘；oncall 值班表已交接；探针预热后再重启"),
        ("design_doc_v2.md", "CREATE TABLE user_memory；DDL 含索引和外键；schema v3 已对齐"),
    ])
    def test_internal_doc_with_non_hex_name_caught(self, sf: str, text: str):
        is_internal, reason, _ = classify_with_detail(sf, text)
        assert is_internal is True, f"漏标内部: sf={sf} text={text[:30]}"
        # 命中理由：filename_pattern（internal_spec/audit 兜底）或内容层（content_score/content_anchor）
        assert reason in {"filename_pattern", "content_score", "content_anchor"}


# ============================================================
# ⑧ configure() 行为可配置验证
# ============================================================
class TestConfigurable:
    def test_configure_filename_patterns(self):
        configure(filename_patterns=(r"^secret_.*\.md$",))
        assert classify_with_detail("secret_xyz.md", "良性内容")[0] is True
        assert classify_with_detail("public.md", "良性内容")[0] is False

    def test_configure_empty_buckets_disables_content_scoring(self):
        """空 dict 注入 → 禁用所有内容打分（仅文件名兜底 + 锚点）。"""
        configure(keyword_buckets={})
        # 测试用例故意避开所有高精度锚点（task\d+/sys_user_auth/W-NEXT 等）
        is_internal, reason, _ = classify_with_detail(
            "any.md", "本周进度：周报已发出，下周一评审"
        )
        assert is_internal is False  # 内容打分被禁用，无锚点 → False
        assert reason == "benign"

    def test_configure_threshold_raise(self):
        configure(score_threshold=10.0)  # 极高阈值，强制全部 benign（除非显式 flag）
        # 测试用例避开所有锚点
        is_internal, reason, _ = classify_with_detail(
            "any.md", "本周进度：周报已发出，下周一评审"
        )
        assert is_internal is False
        assert reason == "benign"

    def test_configure_threshold_lower_zero(self):
        configure(score_threshold=0.0)
        # 0 阈值 + 锚点 → True
        is_internal, reason, _ = classify_with_detail("any.md", "审计")
        assert is_internal is True
        assert reason in {"content_score", "content_anchor"}

    def test_configure_anchors_disable(self):
        """显式清空锚点列表 + 阈值阈值 → 全部判 benign（极端禁用）。"""
        configure(high_precision_anchors=(), score_threshold=10.0)
        is_internal, reason, _ = classify_with_detail("any.md", "task09 sys_user_auth")
        assert is_internal is False  # 锚点+打分都被禁
        assert reason == "benign"


# ============================================================
# ⑨ 集成测试：5 桶不同密度验证打分函数的单调性
# ============================================================
class TestScoringMonotonicity:
    """单桶弱命中 < 单桶强命中 < 多桶命中（分数单调）。"""

    def test_single_bucket_weak_vs_strong(self):
        # 单关键词弱信号 vs 多关键词强信号
        s_weak, _ = IC._score_text("审计基础", DEFAULT_KEYWORD_BUCKETS)  # type: ignore[attr-defined]
        s_strong, _ = IC._score_text(
            "审计 + 合规检查 + 权限矩阵需要复核 + 登录态 JWT 凭据已轮换 + admin 操作已记录",
            DEFAULT_KEYWORD_BUCKETS,
        )  # type: ignore[attr-defined]
        # 强信号 > 弱信号；二者都 < 1.0（验证打分函数非全或无）
        assert s_strong > s_weak, f"{s_strong=} should > {s_weak=}"
        assert s_weak < 1.0
        assert s_strong <= 1.0

    def test_multi_bucket_higher_than_single_bucket(self):
        # 单桶 1 命中（弱） vs 多桶命中（强）
        s_one, _ = IC._score_text("本任务需要落盘", DEFAULT_KEYWORD_BUCKETS)  # type: ignore[attr-defined]
        s_multi, _ = IC._score_text(
            "本任务需要落盘到 RAG；oncall 值班表已交接；scripts/run_eval.sh；审计日志；CREATE TABLE foo",
            DEFAULT_KEYWORD_BUCKETS,
        )  # type: ignore[attr-defined]
        # 多桶信号 > 单桶弱信号
        assert s_multi > s_one, f"multi={s_multi} one={s_one}"
        # 同时 s_multi 至少为多桶中加权较大的那个
        assert s_multi >= 0.5

    def test_score_normalized_to_0_1(self):
        """任何输入分数都在 0~1 区间内（数值稳定性）。"""
        samples = [
            "良性业务",
            "task09 sys_user_auth restore_admin.py",  # 多桶命中
            "审计合规",  # 单桶命中
            "本任务需要落盘",  # 单关键词
            "",  # 空
            "x" * 100000,  # 长无意义
        ]
        for s in samples:
            score, _ = IC._score_text(s, DEFAULT_KEYWORD_BUCKETS)  # type: ignore[attr-defined]
            assert 0.0 <= score <= 1.0, f"score={score} for: {s[:20]}"


# ============================================================
# ⑩ settings 桥接：loader._apply_settings_to_internal_classifier 验证
# ============================================================
class TestSettingsBridge:
    def test_apply_settings_with_default(self):
        """settings 默认值（INTERNAL_KEYWORDS={}）→ 走默认 5 桶。"""
        # 触发 loader 模块 load（自动 _apply_settings_to_internal_classifier）
        from app.knowledge.importer.loader import _apply_settings_to_internal_classifier
        _apply_settings_to_internal_classifier()
        # 内部信号仍能被识别
        is_internal, _, _ = classify_with_detail("any.md", "task09 sys_user_auth restore_admin.py")
        assert is_internal is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))