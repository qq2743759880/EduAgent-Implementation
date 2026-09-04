"""
下载本地模型（BGE-M3 嵌入模型 + BGE-Reranker 重排模型）。

用法：
    python scripts/download_models.py

说明：
- 从 ModelScope 下载（国内快，不用梯子）
- 跳过 onnx / tf / flax 等我们用不到的格式，省一半流量
- 支持断点续传：中断后重跑会接着下，不会从头开始
"""
import os
from pathlib import Path

# 模型统一放这里。放 C 盘是因为实测 C: 剩 34GB，Z: 只剩 16GB。
# 如果你的 C 盘紧张，改成别的路径，记得 .env 里也要同步改。
MODEL_ROOT = Path("C:/ai-models")

# (ModelScope 模型 ID, 本地文件夹名)
MODELS = [
    ("BAAI/bge-m3", "bge-m3"),
    ("BAAI/bge-reranker-v2-m3", "bge-reranker-v2-m3"),
]

# 不下载这些文件：onnx 是给 ONNX Runtime 用的，tf/flax 是给 TensorFlow/JAX 用的，
# 我们用 PyTorch，全都不需要。跳过能省 2GB+ 流量。
IGNORE = ["*.onnx", "*.onnx_data", "onnx/*", "*.msgpack", "*.h5", "*.tflite"]


def main() -> None:
    # 延迟导入：万一 modelscope 没装，报错信息更清楚
    from modelscope import snapshot_download

    MODEL_ROOT.mkdir(parents=True, exist_ok=True)

    for model_id, local_name in MODELS:
        target = MODEL_ROOT / local_name
        print(f"\n{'=' * 60}")
        print(f"下载 {model_id}")
        print(f"目标目录 {target}")
        print(f"{'=' * 60}")

        # local_dir 指定下载到哪；ignore_file_pattern 控制下哪些文件
        path = snapshot_download(
            model_id,
            local_dir=str(target),
            ignore_file_pattern=IGNORE,
        )
        print(f"完成 -> {path}")

        # 列出下到了什么，确认关键文件在
        files = sorted(p.name for p in Path(path).iterdir() if p.is_file())
        print(f"文件清单：{files}")


if __name__ == "__main__":
    main()
