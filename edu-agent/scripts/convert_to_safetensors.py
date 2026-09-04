"""
把 bge-m3 的 pytorch_model.bin 转成 model.safetensors。

背景:
- transformers 4.57 因 CVE-2025-32434,要求 torch>=2.6 才能用 torch.load 加载 .bin
- 我们 kb311 是 torch 2.5.1+cu121(4060 + CUDA 12.1),升级 torch 风险大
- safetensors 格式不受这个限制,且加载更快、更安全
- 转换后 transformers/sentence_transformers 会自动优先用 safetensors

用法:
    python scripts/convert_to_safetensors.py
"""
from pathlib import Path

import torch
from safetensors.torch import save_file

MODEL_DIR = Path("C:/ai-models/bge-m3")
SRC = MODEL_DIR / "pytorch_model.bin"
DST = MODEL_DIR / "model.safetensors"


def main() -> None:
    if DST.exists():
        print(f"目标文件已存在,跳过转换: {DST}")
        return
    if not SRC.exists():
        raise FileNotFoundError(f"源文件不存在: {SRC}")

    print(f"加载 {SRC}  (约 2.2GB,可能需要 10-30 秒)")
    # weights_only=False 因为这是我们自己下的可信模型
    # 注意:torch.load 仍然能工作 —— CVE 拦截的是 transformers 内部调用,
    # 这里我们直接用 torch.load,绕开 transformers 的检查
    state_dict = torch.load(str(SRC), map_location="cpu", weights_only=False)
    print(f"加载完成,共 {len(state_dict)} 个张量")

    # safetensors 要求 key 是 str,且 tensor 是 contiguous
    cleaned = {}
    for k, v in state_dict.items():
        if not isinstance(k, str):
            k = str(k)
        if not v.is_contiguous():
            v = v.contiguous()
        cleaned[k] = v

    print(f"写入 {DST}")
    save_file(cleaned, str(DST), metadata={"format": "pt"})
    print("转换完成")

    # 验证
    src_size = SRC.stat().st_size / 1024**3
    dst_size = DST.stat().st_size / 1024**3
    print(f"源文件 {src_size:.2f} GB  →  目标文件 {dst_size:.2f} GB")
    print(f"\n现在可以删除旧的 pytorch_model.bin 节省空间(可选):")
    print(f"  del \"{SRC}\"")


if __name__ == "__main__":
    main()
