"""向量工具：余弦相似度、RRF 合并（纯 Python，不引入向量库）。"""
import math
from typing import Dict, Iterable, List, Tuple


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度；维度不一致返回 0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def rrf_merge(
    ranked_lists: Iterable[List[int]], k: int = 60
) -> List[Tuple[int, float]]:
    """Reciprocal Rank Fusion：合并多路候选 id 列表，返回 (id, score)。"""
    scores: Dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
