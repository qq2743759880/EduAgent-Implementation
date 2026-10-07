"""
下载公共本地模型（BGE-M3、重排模型、Faster Whisper）。

用法：
    python scripts/download_models.py

说明：
- 从模型发布者的 Hugging Face 仓库下载
- 跳过 onnx / tf / flax 等我们用不到的格式，省一半流量
- 支持断点续传：中断后重跑会接着下，不会从头开始
"""
import argparse
from pathlib import Path

# Portable project-relative default, overridable without editing source.
MODEL_ROOT = Path(__file__).resolve().parents[2] / "models"

# (ModelScope 模型 ID, 本地文件夹名)
MODELS = [
    ("BAAI/bge-m3", "bge-m3"),
    ("BAAI/bge-reranker-v2-m3", "bge-reranker-v2-m3"),
    ("Systran/faster-whisper-base", "faster-whisper-base"),
]

# 不下载这些文件：onnx 是给 ONNX Runtime 用的，tf/flax 是给 TensorFlow/JAX 用的，
# 我们用 PyTorch，全都不需要。跳过能省 2GB+ 流量。
IGNORE = ["*.onnx", "*.onnx_data", "onnx/*", "*.msgpack", "*.h5", "*.tflite"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download public BGE-M3 / reranker / ASR weights; never package private media")
    parser.add_argument('--models-dir', type=Path, default=MODEL_ROOT)
    parser.add_argument('--model', choices=['all', *[name for _, name in MODELS]], default='all')
    args = parser.parse_args()
    from huggingface_hub import snapshot_download

    args.models_dir.mkdir(parents=True, exist_ok=True)

    for model_id, local_name in MODELS:
        if args.model not in ('all', local_name):
            continue
        target = args.models_dir / local_name
        print(f"\n{'=' * 60}")
        print(f"下载 {model_id}")
        print(f"目标目录 {target}")
        print(f"{'=' * 60}")

        # local_dir 指定下载到哪；ignore_file_pattern 控制下哪些文件
        path = snapshot_download(
            model_id,
            local_dir=str(target),
            ignore_patterns=IGNORE,
        )
        print(f"完成 -> {path}")

        # 列出下到了什么，确认关键文件在
        files = sorted(p.name for p in Path(path).iterdir() if p.is_file())
        print(f"文件清单：{files}")


if __name__ == "__main__":
    main()
