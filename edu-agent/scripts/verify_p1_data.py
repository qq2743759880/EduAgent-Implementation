"""
Verify P1 source data files exist and check their structure.
"""
from pathlib import Path


def check_file(path, label):
    p = Path(path)
    print(f"=== {label} ===")
    print(f"存在: {p.exists()}")
    if not p.exists():
        print()
        return

    text = p.read_text(encoding="utf-8")
    size_kb = len(text.encode("utf-8")) / 1024
    lines = text.count("\n") + 1
    print(f"大小: {size_kb:.1f} KB, {len(text)} chars, {lines} lines")

    if label == "课程介绍.md":
        series_count = text.count("\n## ")
        print(f"系列数: {series_count}")
    else:
        bank_count = text.count("\n## ")
        q_count = text.count("\n### ")
        print(f"题库数: {bank_count}, 题目数: {q_count}")

    print()
    print("--- 前 400 字预览 ---")
    print(text[:400])
    print()


base = Path(r"e:/stu/project/stu")
check_file(base / "课程介绍.md", "课程介绍.md")
check_file(base / "题目资料.md", "题目资料.md")
