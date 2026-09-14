# -*- coding: utf-8 -*-
"""
task-E1 对抗采样评估集（AC2）：
  - 线上脏数据采样（错别字 / 口语 / 超短句）≥ 20 条
  - 对抗样本（易混淆对 / 缺主语 / 长尾专业词）≥ 20 条
  每条含 ground_truth（关键要点），供 4 维 Judge 判断。

运行 `python -m scripts.eval.build_adversarial_set` 生成 adversarial_dataset.json。
数据全部为手写真实形态样本（不伪造），覆盖线上常见噪声分布。
"""
from __future__ import annotations

import json
import os
try:
    from _safeio import safe_w  # 直接运行（脚本目录在 sys.path）
except ImportError:  # 以包形式导入（pytest: from scripts.eval import ...）
    from scripts.eval._safeio import safe_w  # Mimosa 路径穿越防护:写出统一收容校验


_DIR = os.path.dirname(os.path.abspath(__file__))
_OUT = os.path.join(_DIR, "adversarial_dataset.json")


# 字段：id, query, category("dirty"|"adversarial"), ground_truth
# ── 线上脏数据：错别字 / 口语 / 超短句 ──────────────────────
DIRTY: list[tuple[str, str, str]] = [
    ("AD-D01", "python怎么装", "给出官方下载或 pip 安装步骤"),
    ("AD-D02", "djang和flask哪个好", "对比两者定位与选型建议"),
    ("AD-D03", "咋用git上传代码", "git add/commit/push 流程"),
    ("AD-D04", "sql注入和xss啥区别", "注入点与安全目标不同"),
    ("AD-D05", "c语言里指针是啥", "指针即内存地址变量"),
    ("AD-D06", "英语时态有哪几种", "一般现在/过去/将来/进行/完成等"),
    ("AD-D07", "高数是啥", "高等数学范围：微积分/线代/概率"),
    ("AD-D08", "怎么读写文件python", "open/read/write/with 用法"),
    ("AD-D09", "js里var let const区别", "作用域与可变性差异"),
    ("AD-D10", "递归和迭代哪个好", "对比优劣与适用场景"),
    ("AD-D11", "mysql怎么建表", "CREATE TABLE 语法"),
    ("AD-D12", "什么是api", "应用程序编程接口概念"),
    ("AD-D13", "http和https差在哪", "HTTPS 加密更安全"),
    ("AD-D14", "数组和链表区别", "内存连续 vs 离散"),
    ("AD-D15", "虚函数和纯虚函数", "是否含实现/能否实例化"),
    ("AD-D16", "线程和进程区别", "资源拥有与调度单位"),
    ("AD-D17", "深拷贝浅拷贝", "引用共享 vs 完全独立"),
    ("AD-D18", "怎么排序一个列表", "sort/sorted 用法"),
    ("AD-D19", "闭包是啥意思", "函数捕获外部变量"),
    ("AD-D20", "同步和异步区别", "阻塞等待 vs 非阻塞回调"),
    ("AD-D21", "tcp和udp区别", "可靠连接 vs 无连接"),
    ("AD-D22", "栈和队列区别", "LIFO vs FIFO"),
]

# ── 对抗样本：易混淆 / 缺主语 / 长尾专业词 ─────────────────
ADVERSARIAL: list[tuple[str, str, str]] = [
    ("AD-A01", "Java 和 JavaScript 是一个东西吗", "否，两者无关仅名字相似"),
    ("AD-A02", "SQL 注入和 XSS 有什么区别", "注入位置与攻击目标不同"),
    ("AD-A03", "零基础学 Python 还是 Java 好", "给其一并说明理由"),
    ("AD-A04", "机器学习和深度学习什么关系", "深度学习是机器学习的子集"),
    ("AD-A05", "编译型和解释型语言区别", "执行方式差异"),
    ("AD-A06", "乐观锁和悲观锁区别", "冲突处理时机不同"),
    ("AD-A07", "Cookie 和 Session 区别", "客户端 vs 服务端存储"),
    ("AD-A08", "GET 和 POST 区别", "语义与安全/长度差异"),
    ("AD-A09", "进程和程序区别", "动态执行 vs 静态文件"),
    ("AD-A10", "堆和栈区别（内存）", "分配与管理方式不同"),
    ("AD-A11", "列表推导式和 for 循环哪个快", "推导式通常更快且更简洁"),
    ("AD-A12", "什么是闭包又什么是装饰器", "两者关系：装饰器基于闭包"),
    ("AD-A13", "怎么学最快", "缺主语，需澄清学科再给路径"),
    ("AD-A14", "Rust 的 lifetime 标注怎么理解", "生命周期保证引用有效"),
    ("AD-A15", "transformer 和 rnn 区别", "并行注意力 vs 序列递归"),
    ("AD-A16", "softmax 和 sigmoid 区别", "多类 vs 二分类归一化"),
    ("AD-A17", "梯度消失和梯度爆炸", "反向传播数值不稳定两端"),
    ("AD-A18", "C++ 的 STL 是啥", "标准模板库容器/算法"),
    ("AD-A19", "面向对象和面向过程", "封装抽象 vs 步骤化"),
    ("AD-A20", "索引为什么快", "B+树有序定位减少 IO"),
    ("AD-A21", "正则的贪婪和非贪婪", "量词匹配长度策略"),
    ("AD-A22", "并发和并行区别", "交替执行 vs 同时执行"),
]


def build() -> dict:
    samples = [
        {"id": i, "query": q, "category": c, "ground_truth": g}
        for (i, q, c, g) in [(r[0], r[1], "dirty", r[2]) for r in DIRTY]
        + [(r[0], r[1], "adversarial", r[2]) for r in ADVERSARIAL]
    ]
    out = {
        "dirty_count": len(DIRTY),
        "adversarial_count": len(ADVERSARIAL),
        "total": len(samples),
        "samples": samples,
    }
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def load() -> list[dict]:
    with open(_OUT, "r", encoding="utf-8") as f:
        return json.load(f)["samples"]


if __name__ == "__main__":
    data = build()
    assert data["dirty_count"] >= 20, "脏数据不足 20 条"
    assert data["adversarial_count"] >= 20, "对抗样本不足 20 条"
    for s in data["samples"]:
        assert s["ground_truth"], f"{s['id']} 缺 ground_truth"
    print(f"OK: dirty={data['dirty_count']} adversarial={data['adversarial_count']} -> {_OUT}")
