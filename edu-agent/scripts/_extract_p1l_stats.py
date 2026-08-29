# -*- coding: utf-8 -*-
"""task-P1L 压测数据提取：从 locust stats.csv 提取 P50/P95/P99/Max/RPS/失败率 + TTFT 行。

用法: PYTHONPATH=. .venv/Scripts/python.exe scripts/_extract_p1l_stats.py ../test-reports/task-P1L-locust_stats.csv
输出: 按请求名分组的 Markdown 表格行（含 L1/L2 分档与 TTFT 独立指标）。
"""
import csv
import sys
from collections import OrderedDict


def main(path: str) -> None:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    # 按 Type 分组: POST(非流式) / TTFT / DEGRADED
    groups = OrderedDict()
    for r in rows:
        groups.setdefault(r["Type"], []).append(r)

    def fmt(row, key):
        try:
            v = float(row.get(key, ""))
        except (TypeError, ValueError):
            return "-"
        if v >= 60000:
            return ">60s"
        if v >= 1000:
            return f"{v / 1000:.1f}s"
        return f"{v:.0f}ms"

    def cnt(row, key):
        try:
            return int(row.get(key, 0))
        except (TypeError, ValueError):
            return 0

    print(f"== 文件: {path} ==")
    for t, rs in groups.items():
        print(f"\n### Type={t}  (共 {len(rs)} 行)")
        print("| Name | 样本 | 失败 | P50 | P95 | P99 | Max | RPS | 失败率 |")
        print("|------|------|------|-----|-----|-----|-----|-----|--------|")
        for r in rs:
            name = r["Name"]
            n = cnt(r, "Request Count")
            fail = cnt(r, "Failure Count")
            rate = f"{fail / n * 100:.1f}%" if n else "-"
            rps = r.get("Requests/s", "-")
            try:
                rps_f = float(rps)
                rps_s = f"{rps_f:.2f}"
            except (TypeError, ValueError):
                rps_s = "-"
            print(f"| {name} | {n} | {fail} | {fmt(r, '50%')} | {fmt(r, '95%')} | "
                  f"{fmt(r, '99%')} | {fmt(r, '100%')} | {rps_s} | {rate} |")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../test-reports/task-P1L-locust_stats.csv")
