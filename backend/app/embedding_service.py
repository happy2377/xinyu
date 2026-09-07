"""向量服务：
- 默认使用本地 fastembed（BAAI/bge-small-zh-v1.5，512 维，免费、离线、无限流）；
- 设置 EMBEDDING_PROVIDER=remote 时可退回魔搭云端向量接口。
"""
import logging
import os
from typing import List

from .llm_service import llm_service

logger = logging.getLogger(__name__)

LOCAL_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()

_local_model = None


def _get_local_model():
    global _local_model
    if _local_model is None:
        try:
            from fastembed import TextEmbedding
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "本地向量引擎未安装：请先 pip install fastembed，"
                "或设置 EMBEDDING_PROVIDER=remote 使用云端向量"
            ) from e
        logger.info("加载本地向量模型 %s（首次运行会下载约 100MB）", LOCAL_MODEL)
        _local_model = TextEmbedding(model_name=LOCAL_MODEL)
    return _local_model


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """向量化：默认本地，失败/未安装时尝试云端。"""
    if not texts:
        return []
    if PROVIDER == "remote":
        return await llm_service.embed_texts(texts)

    try:
        model = _get_local_model()
        vectors = []
        for vector in model.embed(list(texts)):
            vectors.append([float(x) for x in vector])
        return vectors
    except Exception as e:
        logger.warning("本地向量化失败，尝试云端: %s", e)
        if llm_service.available:
            return await llm_service.embed_texts(texts)
        raise RuntimeError(f"向量化不可用：{e}") from e
