"""
检查 P1 知识库导入所需的全部前置依赖。
运行结果会打印每个包是否安装、模型文件是否齐全。
"""
import importlib
from pathlib import Path


def check_module(name, pkg_name):
    try:
        m = importlib.import_module(name)
        ver = getattr(m, "__version__", "ok")
        print(f"  [OK] {pkg_name} ({name}): {ver}")
        return True
    except ImportError:
        print(f"  [MISS] {pkg_name} ({name}): not installed")
        return False


print("=== P1 Dependency Check ===\n")

deps = [
    ("jieba", "jieba"),
    ("rank_bm25", "rank-bm25"),
    ("docx", "python-docx"),
    ("pypdf", "pypdf"),
    ("PyPDF2", "PyPDF2"),
    ("sentence_transformers", "sentence-transformers"),
    ("transformers", "transformers"),
    ("torch", "torch"),
    ("pymilvus", "pymilvus"),
    ("motor", "motor"),
    ("aiomysql", "aiomysql"),
    ("loguru", "loguru"),
    ("pydantic", "pydantic"),
    ("pydantic_settings", "pydantic-settings"),
    ("aiofiles", "aiofiles"),
]

for mod, pkg in deps:
    check_module(mod, pkg)

print("\n=== Model Files Check ===\n")

# BGE-M3
m3_path = Path("C:/ai-models/bge-m3")
if m3_path.exists():
    print(f"  [OK] bge-m3 dir exists")
    for f in ["model.safetensors", "config.json", "tokenizer.json"]:
        fp = m3_path / f
        status = "OK" if fp.exists() else "MISS"
        print(f"    [{status}] {f}")
    for f in ["1_Pooling/config.json"]:
        fp = m3_path / f
        status = "OK" if fp.exists() else "MISS"
        print(f"    [{status}] {f}")
else:
    print(f"  [MISS] C:/ai-models/bge-m3 dir not found")

# Reranker
rr_path = Path("C:/ai-models/bge-reranker-v2-m3")
if rr_path.exists():
    print(f"  [OK] bge-reranker dir exists")
    for f in ["model.safetensors", "config.json", "tokenizer.json"]:
        fp = rr_path / f
        status = "OK" if fp.exists() else "MISS"
        print(f"    [{status}] {f}")
else:
    print(f"  [MISS] C:/ai-models/bge-reranker-v2-m3 dir not found")

# Upload dir
upload_path = Path("e:/stu/project/stu/edu-agent/data/uploads")
if upload_path.exists():
    print(f"\n  [OK] data/uploads dir exists")
else:
    print(f"\n  [CREATE] data/uploads dir missing, P1 needs it")

# Data/cache
cache_path = Path("e:/stu/project/stu/edu-agent/data/cache")
if cache_path.exists():
    print(f"  [OK] data/cache dir exists")
else:
    print(f"  [CREATE] data/cache dir missing")

print("\n=== Check Complete ===")
