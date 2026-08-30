# -*- coding: utf-8 -*-
"""
task34: Milvus/Neo4j 清除 + 课程/题目知识切片生成与批量入库

子命令:
  snapshot    清除前快照（GWT⑤）：Milvus 集合 schema/分区/索引/计数 + Neo4j 计数
              + raw 双份存储统计（task30 批判①）→ test-reports/task34-pre-rebuild-snapshot.{md,json}
  rebuild     drop edu_knowledge + 重建（loader.ensure_collection_exists）+ Neo4j 全清（GWT①）
  slices      从 seeds CSV 生成 219 系列 + 657 模块 + 1752 题 切片（GWT②）
              → edu-agent/data/kb_slices/courses.json + questions.json
  embed_load  向量化（dense BGE-M3 1024 + sparse jieba-BM25, 批 32）→ loader.load_chunks
              200/批 upsert 断点续跑（已入库 chunk_id 跳过）（GWT③④）
  verify      入库校验：行数/分区/索引/pf_bagu_kb 原样/Neo4j 已清（GWT③ 验收）

用法:
  python scripts/kb_rebuild_task34.py snapshot
  python scripts/kb_rebuild_task34.py rebuild
  python scripts/kb_rebuild_task34.py slices
  python scripts/kb_rebuild_task34.py embed_load [--no-resume]
  python scripts/kb_rebuild_task34.py verify
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------
# 路径与运行环境：cwd 切到 edu-agent（.env / DATA_DIR 相对路径生效）
# ---------------------------------------------------------------
EDU_AGENT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EDU_AGENT))
import os  # noqa: E402
os.chdir(EDU_AGENT)  # noqa: E402

from app.config import settings  # noqa: E402
from app.knowledge.importer import loader  # noqa: E402
from app.knowledge.importer.embedder import build_sparse_vector, encode_dense_batch  # noqa: E402
from app.knowledge.models import ContentType, KnowledgeChunk, Visibility  # noqa: E402

HANDBOOK = EDU_AGENT.parent                      # EduAgent实施手册
SEEDS = HANDBOOK.parent / "edu-data" / "seeds"   # 权威数据源
TEST_REPORTS = HANDBOOK / "test-reports"
SLICE_DIR = EDU_AGENT / "data" / "kb_slices"

EMBED_BATCH = 32    # task34：EMBED_BATCH_SIZE 32（embedder 默认 8）
LOAD_BATCH = 200    # loader.load_chunks 默认批大小
SPARSE_MAX = 4096   # Milvus SPARSE_FLOAT_VECTOR 上限

# ---------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------

def _read_csv(rel: str, enc: str) -> list[dict]:
    """读 CSV → dict 列表（严格按已知编码，不探测）。"""
    with open(SEEDS / rel, encoding=enc, newline="") as f:
        return list(csv.DictReader(f))


def _fmt_opt_json(s: str) -> str:
    """options_json（[{key,text}] JSON 字符串）→ 'A. xxx\nB. xxx' 多行文本。"""
    try:
        opts = json.loads(s)
        return "\n".join(f"{o.get('key', '')}. {o.get('text', '')}" for o in opts if o.get("text"))
    except Exception:
        return s or ""


def _neo4j_driver():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )


def _neo4j_counts() -> dict:
    try:
        d = _neo4j_driver()
        with d.session() as s:
            nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        d.close()
        return {"nodes": nodes, "rels": rels}
    except Exception as e:
        return {"error": str(e)[:120]}


def _indexes(client, col: str) -> dict:
    out = {}
    try:
        for i in client.list_indexes(col):
            d = client.describe_index(col, i)
            out[i] = {"type": d.get("index_type"), "metric": d.get("metric_type"), "params": d.get("params")}
    except Exception as e:
        out = {"error": str(e)[:80]}
    return out


# ---------------------------------------------------------------
# GWT⑤ snapshot：清除前快照落盘
# ---------------------------------------------------------------

def cmd_snapshot() -> None:
    client = loader.get_milvus_client()
    snap: dict = {
        "task": "task34",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "milvus_uri": settings.MILVUS_URI,
        "milvus": {},
        "neo4j": {},
        "notes": "edu_knowledge 将 drop+rebuild；pf_bagu_kb / user_memory 保留；Neo4j 全清",
    }
    for col in client.list_collections():
        entry: dict = {}
        try:
            stats = client.get_collection_stats(col)
            entry["rows"] = stats.get("row_count")
        except Exception as e:
            entry["rows_error"] = str(e)[:80]
        try:
            entry["loaded"] = client.get_load_state(col).get("state")
        except Exception:
            pass
        try:
            entry["partitions"] = {
                p: client.get_partition_stats(col, p).get("row_count", 0)
                for p in client.list_partitions(col)
            }
        except Exception as e:
            entry["partitions_error"] = str(e)[:80]
        entry["indexes"] = _indexes(client, col)
        if col == "edu_knowledge":
            # schema 定义（回滚依据）
            try:
                desc = client.describe_collection(col)
                schema = desc.get("schema", desc)
                fields = schema.get("fields", [])
                entry["schema_fields"] = [
                    {"name": f.get("name"), "type": str(f.get("type")),
                     "params": f.get("params")} for f in fields
                ]
            except Exception as e:
                entry["schema_error"] = str(e)[:80]
            # task30 批判①：raw 双份存储统计（content 前缀版 + raw_content 原文）
            try:
                raw_n = len(client.query(col, filter='raw_content != ""',
                                         output_fields=["chunk_id"], limit=16384))
                ctx_n = len(client.query(col, filter="contextualized == 1",
                                         output_fields=["chunk_id"], limit=16384))
                entry["raw_dup_stats"] = {
                    "raw_content_non_empty": raw_n,
                    "contextualized": ctx_n,
                    "meaning": "raw_content 非空 = 每 chunk 存双份（前缀版 content + 原文 raw_content）",
                }
            except Exception as e:
                entry["raw_dup_error"] = str(e)[:80]
        snap["milvus"][col] = entry

    snap["neo4j"] = _neo4j_counts()

    TEST_REPORTS.mkdir(parents=True, exist_ok=True)
    jp = TEST_REPORTS / "task34-pre-rebuild-snapshot.json"
    jp.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# task34 清除前快照", "", f"- 生成时间：{snap['generated_at']}",
             f"- Milvus：{settings.MILVUS_URI}", ""]
    for col, e in snap["milvus"].items():
        lines.append(f"## {col}")
        lines.append(f"- rows={e.get('rows')} loaded={e.get('loaded')}")
        lines.append(f"- partitions: {json.dumps(e.get('partitions', {}), ensure_ascii=False)}")
        lines.append(f"- indexes: {json.dumps(e.get('indexes', {}), ensure_ascii=False)}")
        if "schema_fields" in e:
            lines.append(f"- schema_fields({len(e['schema_fields'])}): "
                         + ", ".join(f"{f['name']}({f['type']})" for f in e["schema_fields"]))
        if "raw_dup_stats" in e:
            lines.append(f"- raw_dup_stats: {json.dumps(e['raw_dup_stats'], ensure_ascii=False)}")
    lines.append(f"## neo4j")
    lines.append(f"- {json.dumps(snap['neo4j'])}")
    lines.append("")
    lines.append("> 依据：GWT⑤ 清除前快照（schema 定义 + 计数）先落盘，作为回滚依据。")
    mp = TEST_REPORTS / "task34-pre-rebuild-snapshot.md"
    mp.write_text("\n".join(lines), encoding="utf-8")
    print(f"snapshot → {jp}")
    print(f"snapshot → {mp}")


# ---------------------------------------------------------------
# GWT① rebuild：drop+rebuild edu_knowledge + Neo4j 全清
# ---------------------------------------------------------------

def cmd_rebuild() -> None:
    client = loader.get_milvus_client()
    if client.has_collection(settings.MILVUS_COLLECTION):
        client.drop_collection(settings.MILVUS_COLLECTION)
        print(f"[rebuild] dropped {settings.MILVUS_COLLECTION}")
    created = loader.ensure_collection_exists()
    print(f"[rebuild] collection ready (created={created})")

    # Neo4j 全清（FR-KB-01: MATCH (n) DETACH DELETE n）
    d = _neo4j_driver()
    try:
        with d.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
            c = _neo4j_counts()
        print(f"[rebuild] neo4j cleared: {c}")
    finally:
        d.close()

    # 校验：集合存在 + 空 + Neo4j 0
    stats = client.get_collection_stats(settings.MILVUS_COLLECTION)
    parts = client.list_partitions(settings.MILVUS_COLLECTION)
    c = _neo4j_counts()
    assert stats.get("row_count") == 0, f"edu_knowledge 应为空，实际 {stats.get('row_count')}"
    assert parts == ["_default"], f"分区应为 [_default]，实际 {parts}"
    assert c.get("nodes", -1) == 0 and c.get("rels", -1) == 0, f"Neo4j 应为空，实际 {c}"
    print(f"[rebuild] verify OK: rows=0, partitions={parts}, neo4j={c}")


# ---------------------------------------------------------------
# GWT② slices：seeds CSV → KnowledgeChunk 切片（219 系列 + 657 模块 + 1752 题）
# ---------------------------------------------------------------

def _series_desc(series: dict, cats: dict[str, str]) -> tuple[str, str]:
    """描述 = product_name / level3_name / series_name；分类 = level1/2/3 中文链。"""
    l3 = cats.get(series["category_level3_code"], "") if series.get("category_level3_code") else ""
    l2 = cats.get(series["category_level2_code"], "") if series.get("category_level2_code") else ""
    l1 = cats.get(series["category_level1_code"], "") if series.get("category_level1_code") else ""
    desc = f"{series['product_name']} / {l3} / {series['series_name']}"
    category = " / ".join(x for x in (l1, l2, l3) if x)
    return desc, category


def build_course_chunks() -> list[KnowledgeChunk]:
    """系列（course_intro）+ 模块（course_module）。"""
    series_rows = _read_csv("2_course/series.csv", "utf-8-sig")
    module_rows = _read_csv("2_course/series_course.csv", "utf-8-sig")
    cats = {r["category_code"]: r["category_name"] for r in _read_csv("1_foundation/dim_course_category.csv", "utf-8-sig")}
    identity = {r["identity_code"]: r["identity_name"] for r in _read_csv("1_foundation/dim_learner_identity.csv", "utf-8-sig")}
    goals = {r["goal_code"]: r["goal_name"] for r in _read_csv("1_foundation/dim_learning_goal.csv", "utf-8-sig")}
    grades = {r["grade_code"]: r["grade_name"] for r in _read_csv("1_foundation/dim_grade.csv", "utf-8-sig")}

    def names(codes_str: str, m: dict) -> str:
        try:
            codes = json.loads(codes_str or "[]")
        except Exception:
            codes = []
        return ", ".join(m.get(c, c) for c in codes)

    module_by_series: dict[str, list[dict]] = {}
    for m in module_rows:
        module_by_series.setdefault(m["series_code"], []).append(m)

    chunks: list[KnowledgeChunk] = []
    for s in series_rows:
        desc, category = _series_desc(s, cats)
        mods = module_by_series.get(s["series_code"], [])
        content = "\n".join(x for x in [
            f"课程系列：{s['series_name']}",
            f"系列编码：{s['series_code']}",
            f"描述：{desc}",
            f"分类：{category}",
            f"适合人群：{names(s.get('target_learner_identity_codes', ''), identity)}",
            f"学习目标：{names(s.get('target_learning_goal_codes', ''), goals)}",
            f"适合年级：{names(s.get('target_grade_codes', ''), grades)}",
            f"包含 {len(mods)} 个模块",
        ] if x)
        chunks.append(KnowledgeChunk(
            chunk_id=f"course_intro_{s['series_code']}",
            content=content,
            content_type=ContentType.COURSE_INTRO,
            series_code=s["series_code"],
            series_name=s["series_name"],
            module_codes=[m["module_code"] for m in mods],
            category=category,
            audience=names(s.get("target_learner_identity_codes", ""), identity),
            goal=names(s.get("target_learning_goal_codes", ""), goals),
            resource_type="课程介绍",
            tags=[x for x in (s["series_name"], category) if x],
            source_file="seeds/2_course/series.csv",
        ))
        for m in mods:
            kws = [x.strip() for x in json.loads(m.get("module_keywords", "[]") or "[]")] if m.get("module_keywords") else []
            content = "\n".join(x for x in [
                f"课程模块：{m['module_name']}",
                f"模块编码：{m['module_code']}",
                f"所属系列：{s['series_name']}（{s['series_code']}）",
                f"关键词：{'、'.join(kws)}" if kws else "",
                f"课时：{m['lesson_count']}，学时：{m['total_hours']}",
            ] if x)
            chunks.append(KnowledgeChunk(
                chunk_id=f"course_module_{m['module_code']}",
                content=content,
                content_type=ContentType.COURSE_MODULE,
                series_code=s["series_code"],
                series_name=s["series_name"],
                module_codes=[m["module_code"]],
                keywords=kws,
                resource_type="课程模块",
                tags=[m["module_name"], *kws],
                source_file="seeds/2_course/series_course.csv",
            ))
    return chunks


def build_question_chunks() -> list[KnowledgeChunk]:
    """题目（1752 题干+解析）。"""
    q_rows = _read_csv("3_question/question.csv", "utf-8")           # UTF-8（无 BOM）
    bank_rows = _read_csv("3_question/question_bank.csv", "utf-8")
    qtype = {r["type_code"]: r["type_name"] for r in _read_csv("1_foundation/dim_question_type.csv", "utf-8-sig")}
    bank_name = {r["question_bank_code"]: r["question_bank_name"] for r in bank_rows}

    chunks: list[KnowledgeChunk] = []
    for q in q_rows:
        tname = qtype.get(q["question_type_code"], q["question_type_code"])
        options = _fmt_opt_json(q.get("options_json", ""))
        content = "\n".join(x for x in [
            f"【{tname}】题目：{q['stem']}",
            f"选项：\n{options}" if options else "",
            f"答案：{q.get('answer_text', '')}" if q.get("answer_text", "").strip() else "",
            f"解析：{q.get('analysis_text', '')}" if q.get("analysis_text", "").strip() else "",
        ] if x)
        bname = bank_name.get(q["question_bank_code"], q["question_bank_code"])
        chunks.append(KnowledgeChunk(
            chunk_id=f"question_{q['question_code']}",
            content=content,
            content_type=ContentType.QUESTION,
            question_bank_code=q["question_bank_code"],
            question_bank_name=bname,
            question_code=q["question_code"],
            question_type=tname,
            resource_type="题库",
            tags=[bname, tname],
            source_file="seeds/3_question/question.csv",
        ))
    return chunks


def cmd_slices() -> None:
    course_chunks = build_course_chunks()
    question_chunks = build_question_chunks()
    n_series = sum(1 for c in course_chunks if c.content_type == ContentType.COURSE_INTRO)
    n_module = sum(1 for c in course_chunks if c.content_type == ContentType.COURSE_MODULE)
    print(f"[slices] 系列={n_series} 模块={n_module} 题目={len(question_chunks)} "
          f"合计={len(course_chunks) + len(question_chunks)}")

    def dump(chunks: list[KnowledgeChunk]) -> list[dict]:
        out = []
        for c in chunks:
            d = c.model_dump(exclude={"dense_vector", "sparse_indices", "sparse_values", "extra", "created_at"})
            out.append(d)
        return out

    SLICE_DIR.mkdir(parents=True, exist_ok=True)
    (SLICE_DIR / "courses.json").write_text(
        json.dumps(dump(course_chunks), ensure_ascii=False, indent=1), encoding="utf-8")
    (SLICE_DIR / "questions.json").write_text(
        json.dumps(dump(question_chunks), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[slices] → {SLICE_DIR / 'courses.json'}（{len(course_chunks)} 条）")
    print(f"[slices] → {SLICE_DIR / 'questions.json'}（{len(question_chunks)} 条）")


# ---------------------------------------------------------------
# GWT③④ embed_load：双向量分批入库 + 断点续跑
# ---------------------------------------------------------------

def cmd_embed_load(resume: bool) -> None:
    def load(name: str) -> list[KnowledgeChunk]:
        p = SLICE_DIR / name
        data = json.loads(p.read_text(encoding="utf-8"))
        return [KnowledgeChunk(**d) for d in data]

    chunks = load("courses.json") + load("questions.json")   # 先课程后题目
    print(f"[embed_load] 切片总数={len(chunks)}（课程 {len(load('courses.json'))} + 题目 {len(load('questions.json'))}）")

    existing: set[str] = set()
    if resume:
        client = loader.get_milvus_client()
        try:
            rows = client.query(settings.MILVUS_COLLECTION, filter='chunk_id != ""',
                                output_fields=["chunk_id"], limit=16384)
            existing = {r["chunk_id"] for r in rows}
            print(f"[embed_load] 断点续跑：已入库 {len(existing)} 条，跳过")
        except Exception as e:
            print(f"[embed_load] 已入库查询失败（按全量处理）：{e}")

    todo = [c for c in chunks if c.chunk_id not in existing]
    if not todo:
        print("[embed_load] 全部已入库，无需处理")
        return
    print(f"[embed_load] 待处理 {len(todo)} 条（EMBED_BATCH={EMBED_BATCH} LOAD_BATCH={LOAD_BATCH}）")

    # dense（批 32）
    all_texts = [c.content for c in todo]
    all_dense: list[list[float]] = []
    for i in range(0, len(all_texts), EMBED_BATCH):
        batch = all_texts[i:i + EMBED_BATCH]
        all_dense.extend(encode_dense_batch(batch))
        print(f"[embed_load] dense {min(i + EMBED_BATCH, len(all_texts))}/{len(all_texts)}", flush=True)

    # sparse + 回填
    for idx, c in enumerate(todo):
        c.dense_vector = all_dense[idx]
        kw = list(dict.fromkeys([*(c.keywords or []), *(c.tags or [])]))
        svec = build_sparse_vector(c.content, extra_keywords=kw)
        items = sorted(svec.items(), key=lambda kv: -kv[1])[:SPARSE_MAX]
        c.sparse_indices = [int(k) for k, _ in items]
        c.sparse_values = [float(v) for _, v in items]

    # 入库（loader 200/批 upsert，chunk_id 幂等；tenant 公共知识 → _default）
    n = loader.load_chunks(todo, tenant_id="_default")
    print(f"[embed_load] 入库 {n} 条（分区 _default）")


# ---------------------------------------------------------------
# GWT③ 验收：verify
# ---------------------------------------------------------------

def cmd_verify() -> None:
    client = loader.get_milvus_client()
    ok = True

    def chk(cond: bool, msg: str):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + msg)
        ok = ok and cond

    stats = client.get_collection_stats(settings.MILVUS_COLLECTION)
    rows = stats.get("row_count")
    chk(rows == 2628, f"edu_knowledge 行数 == 2628（219 系列 + 657 模块 + 1752 题），实际 {rows}")

    parts = {p: client.get_partition_stats(settings.MILVUS_COLLECTION, p).get("row_count", 0)
             for p in client.list_partitions(settings.MILVUS_COLLECTION)}
    chk(parts.get("_default") == 2628, f"_default 分区 == 2628（公共知识全进 _default），实际 {parts}")
    chk(not [p for p in parts if p.startswith("user_")], f"无机构 user_* 分区残留，实际 {list(parts)}")

    idxs = _indexes(client, settings.MILVUS_COLLECTION)
    chk(idxs.get("dense_vec", {}).get("type") == "IVF_FLAT" and idxs.get("dense_vec", {}).get("metric") == "COSINE",
        f"dense 索引 IVF_FLAT+COSINE，实际 {idxs.get('dense_vec')}")
    chk(idxs.get("sparse_vec", {}).get("type") == "SPARSE_INVERTED_INDEX" and idxs.get("sparse_vec", {}).get("metric") == "IP",
        f"sparse 索引 SPARSE_INVERTED_INDEX+IP，实际 {idxs.get('sparse_vec')}")
    chk(client.get_load_state(settings.MILVUS_COLLECTION).get("state") == "Loaded", "collection Loaded")

    for col, expect in [("pf_bagu_kb", 5724), ("user_memory", 9)]:
        try:
            r = client.get_collection_stats(col).get("row_count")
            chk(r == expect, f"{col} 原样保留（{expect} 行），实际 {r}")
        except Exception as e:
            chk(False, f"{col} 查询失败：{str(e)[:60]}")

    nc = _neo4j_counts()
    chk(nc.get("nodes", -1) == 0 and nc.get("rels", -1) == 0, f"Neo4j 已清空（0 节点 0 关系），实际 {nc}")

    # 内容抽样（防空 content / 乱码）
    for expr, label in [('content_type == "course_intro"', "系列"),
                        ('content_type == "course_module"', "模块"),
                        ('content_type == "question"', "题目")]:
        try:
            hit = client.query(settings.MILVUS_COLLECTION, filter=expr,
                               output_fields=["chunk_id", "content"], limit=1)
            if hit:
                print(f"  [sample {label}] {hit[0]['chunk_id']}: {hit[0]['content'][:60]!r}")
        except Exception as e:
            chk(False, f"抽样 {label} 失败：{str(e)[:60]}")

    print("\n=== verify " + ("ALL PASS" if ok else "HAS FAILURES") + " ===")
    sys.exit(0 if ok else 1)


def main() -> None:
    ap = argparse.ArgumentParser(description="task34 kb rebuild")
    ap.add_argument("cmd", choices=["snapshot", "rebuild", "slices", "embed_load", "verify"])
    ap.add_argument("--no-resume", action="store_true", help="embed_load 不跳过已入库 chunk")
    args = ap.parse_args()

    if args.cmd == "snapshot":
        cmd_snapshot()
    elif args.cmd == "rebuild":
        cmd_rebuild()
    elif args.cmd == "slices":
        cmd_slices()
    elif args.cmd == "embed_load":
        cmd_embed_load(resume=not args.no_resume)
    elif args.cmd == "verify":
        cmd_verify()


if __name__ == "__main__":
    main()
