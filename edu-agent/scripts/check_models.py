"""
验证本地模型能加载、能用 GPU、输出维度正确。
这一步过了，P1/P2 章节的向量化代码就一定能跑。
"""
import time

import torch

EMB_PATH = "C:/ai-models/bge-m3"
RRK_PATH = "C:/ai-models/bge-reranker-v2-m3"


def check_gpu() -> str:
    """确认 GPU 可用，返回该用的 device 名。"""
    print("=" * 60)
    print(f"torch 版本      : {torch.__version__}")
    print(f"CUDA 可用       : {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"显卡            : {torch.cuda.get_device_name(0)}")
        total = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"总显存          : {total:.1f} GB")
        return "cuda"
    # 没有 GPU 也能跑，只是慢 10-20 倍。不要因为这个卡住。
    print("!! 没检测到 CUDA，将用 CPU（慢，但功能完整）")
    return "cpu"


def check_embedding(device: str) -> None:
    """加载 BGE-M3，编码两句话，验证维度和相似度。"""
    from sentence_transformers import SentenceTransformer

    print("\n" + "=" * 60)
    print("加载 BGE-M3（第一次约 10-30 秒，要把 2.2GB 权重读进显存）")
    t0 = time.time()
    model = SentenceTransformer(EMB_PATH, device=device)
    print(f"加载耗时 {time.time() - t0:.1f}s")

    texts = ["Python 全栈课程都学什么？", "全栈开发系列班的课程模块有哪些"]
    t0 = time.time()
    # normalize_embeddings=True 很重要：归一化后，向量点积 == 余弦相似度，
    # 后面算相似度就不用再除模长了。
    vecs = model.encode(texts, normalize_embeddings=True)
    print(f"编码耗时 {time.time() - t0:.2f}s")
    print(f"向量形状 {vecs.shape}   ← 必须是 (2, 1024)")

    assert vecs.shape == (2, 1024), f"维度不对！期望 (2,1024)，实际 {vecs.shape}"

    # 这两句话意思接近，相似度应该比较高（> 0.6）
    sim = float(vecs[0] @ vecs[1])
    print(f"两句话相似度 {sim:.4f}   ← 意思相近，应该 > 0.6")

    if device == "cuda":
        used = torch.cuda.memory_allocated() / 1024**3
        print(f"当前显存占用 {used:.2f} GB")


def check_reranker(device: str) -> None:
    """加载 Reranker，给 3 个候选打分，验证排序合理。"""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    print("\n" + "=" * 60)
    print("加载 BGE-Reranker-v2-m3")
    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(RRK_PATH)
    model = AutoModelForSequenceClassification.from_pretrained(RRK_PATH)
    model.to(device).eval()   # eval() 关掉 dropout，推理必须调
    print(f"加载耗时 {time.time() - t0:.1f}s")

    query = "Python 全栈课程学什么"
    docs = [
        "全栈开发系列班包含前端基础、后端接口、数据库设计三个模块",  # 最相关
        "退款需在开课 7 日内申请，超期不予受理",                    # 完全不相关
        "Python 数据分析班讲 pandas 与可视化",                      # 有点相关
    ]

    # Reranker 的输入格式：[[问题, 文档], [问题, 文档], ...]
    pairs = [[query, d] for d in docs]
    with torch.no_grad():           # 推理不需要梯度，省显存
        inputs = tok(pairs, padding=True, truncation=True,
                     max_length=512, return_tensors="pt").to(device)
        # logits 形状 (3, 1)，view(-1) 拉平成 (3,)
        scores = model(**inputs).logits.view(-1).float().cpu().tolist()

    print("打分结果（分数越高越相关）：")
    for s, d in sorted(zip(scores, docs), reverse=True):
        print(f"  {s:+8.3f}  {d[:40]}")

    # 第 0 个文档最相关，它的分应该最高
    assert scores[0] == max(scores), "排序不合理，模型可能加载错了"
    print("排序正确")


if __name__ == "__main__":
    dev = check_gpu()
    check_embedding(dev)
    check_reranker(dev)
    print("\n" + "=" * 60)
    print("模型全部就绪")
