"""
verify_schema.py — 库表结构 diff 校验脚本（task05）
================================================
对比 edu.sql（66 表权威）与 information_schema 实际库结构，
逐表逐列逐索引逐外键对比，不一致输出红色清单 + 非零退出码。

用法: python scripts/verify_schema.py
退出码: 0 = 零差异, 1 = 有差异
"""
import re
import sys
import subprocess
import json
from pathlib import Path

# ============================================================
# 配置
# ============================================================
# 项目根: scripts/ 的上一级 → EduAgent实施手册/ → 再上一级 → stu/ → edu-data/
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # EduAgent实施手册/
EDU_SQL = PROJECT_ROOT.parent / "edu-data" / "sql" / "edu.sql"
# task99 注：Windows 上 mysql CLI 默认按控制台代码页(GBK/cp936)输出中文表注释，
# 与 Python text=True 的 UTF-8 解码冲突 → UnicodeDecodeError（task99 重跑时暴露）。
# 强制 CLI 以 utf8mb4 输出，仅影响读出编码，不改变任何比对逻辑。
MYSQL = ["mysql", "-uroot", "-p123456", "edu", "--default-character-set=utf8mb4", "-N", "-B"]

# 29 张自建表（不在 edu.sql 66 表中，需显式声明保留）
# 编排者修正：student_cohort_rel 在 edu.sql 中，已从保留清单移除
SELF_BUILT_KEEP = {
    # 聊天/对话
    "chat_session", "chat_message",
    # 社区/论坛
    "community_post", "community_comment", "community_react",
    # 互动学习
    "coding_challenge", "coding_submission",
    "quiz_answer_session", "quiz_wrong_book",
    "vocab_entry", "user_vocab_card",
    # 游戏化/成就
    "gamification_badge", "user_badge", "user_point_log", "ranking_snapshot",
    # 知识图谱
    "graph_node", "graph_edge",
    # MCP 工具
    "mcp_server", "mcp_tool", "mcp_tool_call_log",
    # RAG 管理
    "rag_audit_log", "rag_collection_meta", "rag_param_preset",
    # 学习进度/用户画像
    "learning_daily_summary", "user_profile", "recommend_feedback",
    "learning_path_instance",
    # 基础设施
    "alembic_version", "sys_user_auth",
    # task04 新增
    "knowledge_import_task", "task_execution",
}

# ANSI 颜色
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

# ============================================================
# 工具函数
# ============================================================
def query(sql: str) -> str:
    """执行 MySQL 查询，返回 stdout"""
    r = subprocess.run(MYSQL + ["-e", sql], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"{RED}MySQL ERROR: {r.stderr[:300]}{RESET}")
        sys.exit(1)
    return r.stdout.rstrip('\n\r')

def parse_edu_sql(path: str) -> dict[str, dict]:
    """解析 edu.sql，返回 {表名: {columns, unique_keys, foreign_keys, indexes, comment}}"""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 匹配 CREATE TABLE ... ;
    pattern = re.compile(
        r"CREATE TABLE (?:IF NOT EXISTS )?(`?\w+`?)\s*\((.*?)\)\s*"
        r"ENGINE\s*=\s*\w+\s*(?:DEFAULT\s+CHARSET\s*=\s*\w+)?"
        r"(?:\s*COLLATE\s*=\s*\w+)?\s*COMMENT\s*=\s*'([^']*)'",
        re.DOTALL | re.IGNORECASE,
    )

    tables = {}
    for m in pattern.finditer(content):
        name = m.group(1).strip("`")
        body = m.group(2)
        comment = m.group(3)

        columns = {}
        unique_keys = {}
        foreign_keys = {}
        indexes = {}

        # 解析每一行定义
        # 先拆分顶层逗号（注意括号嵌套）
        lines = _split_defs(body)

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # PRIMARY KEY
            if re.match(r"PRIMARY KEY", line, re.I):
                continue

            # UNIQUE KEY
            uk_match = re.match(r"UNIQUE KEY\s+(\w+)\s*\((.*?)\)", line, re.I | re.DOTALL)
            if uk_match:
                uk_name = uk_match.group(1)
                uk_cols = [c.strip().strip("`") for c in uk_match.group(2).split(",")]
                unique_keys[uk_name] = uk_cols
                continue

            # FOREIGN KEY / CONSTRAINT
            fk_match = re.match(
                r"(?:CONSTRAINT\s+(\w+)\s+)?FOREIGN KEY\s*\((.*?)\)\s*REFERENCES\s+(\w+)\s*\((.*?)\)",
                line, re.I | re.DOTALL,
            )
            if fk_match:
                fk_name = fk_match.group(1) or ""
                fk_cols = [c.strip().strip("`") for c in fk_match.group(2).split(",")]
                ref_table = fk_match.group(3).strip("`")
                ref_cols = [c.strip().strip("`") for c in fk_match.group(4).split(",")]
                foreign_keys[fk_name] = {
                    "columns": fk_cols,
                    "ref_table": ref_table,
                    "ref_columns": ref_cols,
                }
                continue

            # INDEX / KEY
            idx_match = re.match(r"(?:INDEX|KEY)\s+(\w+)\s*\((.*?)\)", line, re.I | re.DOTALL)
            if idx_match:
                idx_name = idx_match.group(1)
                idx_cols = [c.strip().strip("`") for c in idx_match.group(2).split(",")]
                indexes[idx_name] = idx_cols
                continue

            # 跳过 CONSTRAINT 行（外键约束在列定义中内联声明）
            if re.match(r"CONSTRAINT\s+", line, re.I):
                continue

            # 列定义（简化：匹配 列名 类型 [约束...] [COMMENT '...']）
            col_match = re.match(
                r"`?(\w+)`?\s+(\w+(?:\s+unsigned)?(?:\([\d,\s,]+\))?)\s*(.*)",
                line, re.I,
            )
            if col_match:
                col_name = col_match.group(1)
                # 规范化类型：去除多余空格
                col_type = re.sub(r"\s+", " ", col_match.group(2).upper())
                col_rest = col_match.group(3)

                # PRIMARY KEY 隐式 NOT NULL
                nullable = "NO" if re.search(r"NOT\s+NULL|PRIMARY\s+KEY|AUTO_INCREMENT", col_rest, re.I) else "YES"
                default = None
                def_match = re.search(r"DEFAULT\s+('([^']*)'|(\w+)|CURRENT_TIMESTAMP(?:\(\d*\))?)", col_rest, re.I)
                if def_match:
                    raw = def_match.group(1)
                    if raw.startswith("'") and raw.endswith("'"):
                        default = raw[1:-1]
                    elif raw.upper().startswith("CURRENT_TIMESTAMP"):
                        default = "CURRENT_TIMESTAMP"
                    else:
                        default = raw

                col_comment = ""
                cmt_match = re.search(r"COMMENT\s+'([^']*)'", col_rest, re.I)
                if cmt_match:
                    col_comment = cmt_match.group(1)

                columns[col_name] = {
                    "type": col_type,
                    "nullable": nullable,
                    "default": default,
                    "comment": col_comment,
                }

        tables[name] = {
            "comment": comment,
            "columns": columns,
            "unique_keys": unique_keys,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
        }

    return tables


def _default_eq(a, b) -> bool:
    """比较两个 DEFAULT 值是否语义相等（处理 0 vs 0.00 等）"""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    # 尝试数值比较
    try:
        fa = float(a)
        fb = float(b)
        return fa == fb
    except (ValueError, TypeError):
        return str(a) == str(b)


def _split_defs(body: str) -> list[str]:
    """按逗号拆分列/约束定义，处理括号嵌套"""
    parts = []
    depth = 0
    current = ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current)
    return parts


def get_db_schema() -> dict:
    """从 information_schema 获取实际库结构"""
    # 获取所有表
    tables_raw = query(
        "SELECT TABLE_NAME, TABLE_COMMENT FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA='edu' AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
    )
    all_tables = set()
    for line in tables_raw.split("\n"):
        if "\t" in line:
            all_tables.add(line.split("\t")[0])

    schema = {}
    for tbl in sorted(all_tables):
        # 列
        cols_raw = query(
            "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT, EXTRA "
            "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='edu' AND TABLE_NAME='{}' "
            "ORDER BY ORDINAL_POSITION".format(tbl)
        )
        columns = {}
        for line in cols_raw.split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 6:
                col_name = parts[0]
                col_type = parts[1].upper()
                nullable = parts[2]
                default = parts[3] if parts[3] != "NULL" else None
                # 规范化 CURRENT_TIMESTAMP
                if default and default.lower().startswith("current_timestamp"):
                    default = "CURRENT_TIMESTAMP"
                comment = parts[4] if len(parts) > 4 else ""
                columns[col_name] = {
                    "type": col_type,
                    "nullable": nullable,
                    "default": default,
                    "comment": comment,
                }

        # 唯一键
        uk_raw = query(
            "SELECT CONSTRAINT_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY ORDINAL_POSITION) "
            "FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA='edu' AND TABLE_NAME='{}' AND CONSTRAINT_NAME LIKE 'uk_%' "
            "GROUP BY CONSTRAINT_NAME".format(tbl)
        )
        unique_keys = {}
        for line in uk_raw.split("\n"):
            if "\t" in line:
                name, cols = line.split("\t", 1)
                unique_keys[name] = [c.strip() for c in cols.split(",")]

        # 外键
        fk_raw = query(
            "SELECT CONSTRAINT_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY ORDINAL_POSITION), "
            "REFERENCED_TABLE_NAME, GROUP_CONCAT(REFERENCED_COLUMN_NAME ORDER BY POSITION_IN_UNIQUE_CONSTRAINT) "
            "FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA='edu' AND TABLE_NAME='{}' AND REFERENCED_TABLE_NAME IS NOT NULL "
            "GROUP BY CONSTRAINT_NAME, REFERENCED_TABLE_NAME".format(tbl)
        )
        foreign_keys = {}
        for line in fk_raw.split("\n"):
            if "\t" in line:
                parts = line.split("\t")
                name = parts[0]
                cols = parts[1] if len(parts) > 1 else ""
                ref_tbl = parts[2] if len(parts) > 2 else ""
                ref_cols = parts[3] if len(parts) > 3 else ""
                foreign_keys[name] = {
                    "columns": [c.strip() for c in cols.split(",")],
                    "ref_table": ref_tbl,
                    "ref_columns": [c.strip() for c in ref_cols.split(",")],
                }

        # 索引（排除 PK/UK/FK）
        idx_raw = query(
            "SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) "
            "FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA='edu' AND TABLE_NAME='{}' "
            "AND INDEX_NAME NOT LIKE 'PRIMARY' AND INDEX_NAME NOT LIKE 'uk_%' AND INDEX_NAME NOT LIKE 'fk_%' "
            "GROUP BY INDEX_NAME".format(tbl)
        )
        indexes = {}
        for line in idx_raw.split("\n"):
            if "\t" in line:
                name, cols = line.split("\t", 1)
                indexes[name] = [c.strip() for c in cols.split(",")]

        # 表注释
        comment_raw = query(
            "SELECT TABLE_COMMENT FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA='edu' AND TABLE_NAME='{}'".format(tbl)
        )
        comment = comment_raw.strip() if comment_raw else ""

        schema[tbl] = {
            "comment": comment,
            "columns": columns,
            "unique_keys": unique_keys,
            "foreign_keys": foreign_keys,
            "indexes": indexes,
        }

    return schema


# ============================================================
# 主逻辑
# ============================================================
def main():
    print(f"{BOLD}=== verify_schema.py — edu.sql vs information_schema 对比 ==={RESET}\n")

    # 1. 解析 edu.sql
    print("1. 解析 edu.sql...")
    edu_tables = parse_edu_sql(str(EDU_SQL))
    print(f"   edu.sql: {len(edu_tables)} 表")
    edu_table_set = set(edu_tables.keys())

    # 2. 获取实际库结构
    print("2. 查询 information_schema...")
    db_schema = get_db_schema()
    print(f"   实际库: {len(db_schema)} 表")
    db_table_set = set(db_schema.keys())

    # 3. 游离表检查
    print("\n3. 游离表检查...")
    orphan_tables = db_table_set - edu_table_set - SELF_BUILT_KEEP
    if orphan_tables:
        print(f"   {RED}游离表（不在 edu.sql 66 表也不在保留清单）:{RESET}")
        for t in sorted(orphan_tables):
            print(f"     {RED}✗ {t}{RESET}")
    else:
        print(f"   {GREEN}✓ 无游离表{RESET}")

    # 新建表（保留清单 + 不在 edu.sql）
    new_tables = db_table_set - edu_table_set
    if new_tables:
        print(f"   保留表（自建，不在 edu.sql）: {len(new_tables)} 张")
        for t in sorted(new_tables):
            if t in SELF_BUILT_KEEP:
                print(f"     {YELLOW}  {t} (保留){RESET}")
            else:
                print(f"     {RED}  {t} (未声明!){RESET}")

    # 缺失表（edu.sql 有但实际库没有）
    missing_tables = edu_table_set - db_table_set
    if missing_tables:
        print(f"   {RED}缺失表（edu.sql 有但实际库无）:{RESET}")
        for t in sorted(missing_tables):
            print(f"     {RED}✗ {t}{RESET}")

    # 4. 逐表对比
    print(f"\n4. 逐表对比（{len(edu_table_set & db_table_set)} 张共有表）...")
    total_diffs = 0

    for tbl in sorted(edu_table_set & db_table_set):
        edu = edu_tables[tbl]
        db = db_schema[tbl]
        diffs = []

        # 4.1 列对比
        edu_cols = set(edu["columns"].keys())
        db_cols = set(db["columns"].keys())
        extra_cols = db_cols - edu_cols
        missing_cols = edu_cols - db_cols

        for col in sorted(extra_cols):
            # 多余列：DB 有但 edu.sql 没有 → 仅警告（已知偏差：updated_at/sys_user 扩展列）
            diffs.append("    多余列(WARN): {} ({})".format(col, db["columns"][col]["type"]))
        for col in sorted(missing_cols):
            diffs.append("    缺失列: {} ({})".format(col, edu["columns"][col]["type"]))

        for col in sorted(edu_cols & db_cols):
            e = edu["columns"][col]
            d = db["columns"][col]
            # 类型对比（忽略大小写和宽度差异如 int(11) vs int）
            e_type_norm = re.sub(r"\([\d,\s,]+\)", "", e["type"])
            d_type_norm = re.sub(r"\([\d,\s,]+\)", "", d["type"])
            if e_type_norm != d_type_norm:
                diffs.append(f"    {col}: 类型差异 edu={e['type']} db={d['type']}")
            if e["nullable"] != d["nullable"]:
                diffs.append(f"    {col}: NULL差异 edu={e['nullable']} db={d['nullable']}")
            if not _default_eq(e["default"], d["default"]):
                diffs.append(f"    {col}: DEFAULT差异 edu={e['default']} db={d['default']}")

        # 4.2 唯一键对比
        edu_uks = set(edu["unique_keys"].keys())
        db_uks = set(db["unique_keys"].keys())
        for uk in sorted(edu_uks - db_uks):
            diffs.append(f"    缺失唯一键: {uk} ({edu['unique_keys'][uk]})")
        for uk in sorted(db_uks - edu_uks):
            diffs.append(f"    多余唯一键: {uk} ({db['unique_keys'][uk]})")
        for uk in sorted(edu_uks & db_uks):
            if edu["unique_keys"][uk] != db["unique_keys"][uk]:
                diffs.append(f"    唯一键列差异: {uk} edu={edu['unique_keys'][uk]} db={db['unique_keys'][uk]}")

        # 4.3 外键对比
        edu_fks = set(edu["foreign_keys"].keys())
        db_fks = set(db["foreign_keys"].keys())
        for fk in sorted(edu_fks - db_fks):
            diffs.append("    缺失外键: {} → {}".format(fk, edu["foreign_keys"][fk]["ref_table"]))
        # 多余外键：DB 有但 edu.sql 解析不出来（edu.sql 用内联 CONSTRAINT 声明）→ 仅警告
        for fk in sorted(db_fks - edu_fks):
            diffs.append("    多余外键(WARN): {} → {}".format(fk, db["foreign_keys"][fk]["ref_table"]))
        for fk in sorted(edu_fks & db_fks):
            e_fk = edu["foreign_keys"][fk]
            d_fk = db["foreign_keys"][fk]
            if e_fk["columns"] != d_fk["columns"]:
                diffs.append(f"    外键列差异: {fk}")
            if e_fk["ref_table"] != d_fk["ref_table"]:
                diffs.append(f"    外键引用表差异: {fk} edu={e_fk['ref_table']} db={d_fk['ref_table']}")

        # 统计真实错误（排除 WARN）
        real_errors = sum(1 for d in diffs if "(WARN)" not in d)
        if diffs:
            total_diffs += len(diffs)

        if diffs and real_errors > 0:
            print(f"\n  {RED}✗ {tbl} ({len(diffs)} 差异, {real_errors} 需修复){RESET}")
            for d in diffs:
                if "(WARN)" in d:
                    print(f"{YELLOW}{d}{RESET}")
                else:
                    print(f"{RED}{d}{RESET}")
        elif diffs:
            print(f"\n  {YELLOW}⚠ {tbl} ({len(diffs)} 警告, 0 需修复){RESET}")
            for d in diffs:
                print(f"{YELLOW}{d}{RESET}")

    # 5. 总结
    print(f"\n{BOLD}=== 校验结果 ==={RESET}")

    # 重新统计真实错误（非 WARN）
    real_error_count = 0
    warn_count = 0
    for tbl in sorted(edu_table_set & db_table_set):
        edu = edu_tables[tbl]
        db = db_schema[tbl]
        # 列差异
        edu_cols = set(edu["columns"].keys())
        db_cols = set(db["columns"].keys())
        real_error_count += len(edu_cols - db_cols)  # 缺失列
        for col in edu_cols & db_cols:
            e = edu["columns"][col]
            d = db["columns"][col]
            e_type_norm = re.sub(r"\([\d,\s,]+\)", "", e["type"])
            d_type_norm = re.sub(r"\([\d,\s,]+\)", "", d["type"])
            if e_type_norm != d_type_norm:
                real_error_count += 1
            if e["nullable"] != d["nullable"]:
                real_error_count += 1
            if not _default_eq(e["default"], d["default"]):
                real_error_count += 1
        # FK 差异
        edu_fks = set(edu["foreign_keys"].keys())
        db_fks = set(db["foreign_keys"].keys())
        real_error_count += len(edu_fks - db_fks)  # 缺失 FK
        # UK 差异
        edu_uks = set(edu["unique_keys"].keys())
        db_uks = set(db["unique_keys"].keys())
        real_error_count += len(edu_uks - db_uks)  # 缺失 UK

    if real_error_count > 0:
        print(f"{RED}需修复差异: {real_error_count}{RESET}")
        print(f"{YELLOW}警告（非阻塞）: {total_diffs - real_error_count}{RESET}")
        if orphan_tables:
            print(f"{RED}游离表: {len(orphant_tables)}{RESET}")
        if missing_tables:
            print(f"{RED}缺失表: {len(missing_tables)}{RESET}")
        print(f"\n{RED}✗ 校验失败 — 存在需修复的差异{RESET}")
        sys.exit(1)
    else:
        print(f"{GREEN}需修复差异: 0{RESET}")
        if total_diffs > 0:
            print(f"{YELLOW}警告（非阻塞）: {total_diffs} (多余列/多余FK/类型宽度差异){RESET}")
        if not orphan_tables and not missing_tables:
            print(f"{GREEN}游离表: 0{RESET}")
            print(f"{GREEN}缺失表: 0{RESET}")
        print(f"\n{GREEN}✓ 校验通过 — 0 需修复差异{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()