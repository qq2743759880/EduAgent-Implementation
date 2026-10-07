"""
Embedding 服务封装

支持两种backend：local_api和remote_api

通过.env里的EMBEDDING_BACKEND 配置选择
"""

from abc import ABC, abstractmethod
from typing import List

import httpx

class EmbeddingService(ABC):
    """
    Embedding 服务抽象基类
    所有的embedding实现都继承这个类
    实现embed_text方法
    """

    @abstractmethod
    async def embed_text(self,texts:List[str])->List[List[float]]:
        """
        把一组文本转成向量

        
        Args:
            texts: 文本列表（一批文本一起转，效率更高）

        Returns:
            向量列表，每个文本对应一个向量（1024 维浮点数列表）
        """
        

class LocalAPIEmbeddingService(EmbeddingService):
    """本地 API 实现的 Embedding 服务。

    调用本地部署的 embedding HTTP 服务（如 BGE-M3）。
    API 格式遵循 OpenAI 兼容接口：POST /v1/embeddings
    """

    def __init__(self, api_base: str, model_name: str, batch_size: int = 32):
        """初始化本地 embedding 客户端。

        Args:
            api_base: 服务地址（如 http://127.0.0.1:8001）
            model_name: 模型名（如 BAAI/bge-m3）
            batch_size: 每批处理的文本数量（默认 32）
        """
        self.api_base = api_base.rstrip("/")  # 去掉末尾的 /
        self.model_name = model_name
        self.batch_size = batch_size
        # 创建异步 HTTP 客户端（连接池，超时 30 秒）
        self.client = httpx.AsyncClient(timeout=30.0)
        
    

