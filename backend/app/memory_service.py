"""长期记忆服务：
- 云端模型结构化抽取事实（chat/diary/assessment）；
- 同类高相似新事实取代旧事实（保留历史，只检索 active）；
- 检索时按相似度 + 时效衰减 + 情绪峰值加权排序；
- 惰性失效：超过 N 天未引用且非高情绪的事实自动失效。
"""
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from .llm_service import llm_service
from .embedding_service import embed_texts as embed_texts_service
from .models import MemoryFact, User
from .vector_utils import cosine_similarity

logger = logging.getLogger(__name__)

MEMORY_TOP_K = int(os.getenv("MEMORY_TOP_K", "5"))
RECENCY_WEIGHT = float(os.getenv("MEMORY_RECENCY_WEIGHT", "0.3"))
EMOTION_WEIGHT = float(os.getenv("MEMORY_EMOTION_WEIGHT", "0.2"))
INACTIVE_DAYS = int(os.getenv("MEMORY_INACTIVE_DAYS", "90"))
CONFLICT_THRESHOLD = 0.85

ALLOWED_TYPES = {
    "identity",
    "preference",
    "event",
    "emotion_pattern",
    "crisis_moment",
}


def _extraction_prompt(text: str, source: str) -> str:
    return f"""从下面的内容中提取值得长期记住的、关于“用户本人”的事实（不包括助手说的话本身）。

内容来源：{source}
内容：
{text}

只提取稳定、对以后陪伴有意义的信息，例如：
- identity：身份/角色/背景（如“我是大三学生”）
- preference：偏好/喜好/厌恶（如“我不喜欢运动”“我喜欢下雨天”）
- event：发生过的具体事件（如“下周要参加考研复试”）
- emotion_pattern：反复出现的情绪模式（如“每次考试前都很焦虑”）
- crisis_moment：强烈的情绪崩溃/危机时刻（需要长期关注）

规则：
1. 一句话一条事实，语言简洁、以用户为主语；
2. 没有可提取内容时返回空列表；
3. emotional_weight 为该事实相关的情绪强度，取值 0-10（普通日常记 1-3，明显情绪化 6-8，崩溃/危机时刻 9-10）；
4. confidence 取值 0-10。

只返回 JSON，格式：
{{"facts": [{{"fact": "事实", "type": "类型", "emotional_weight": 3, "confidence": 7}}]}}"""


async def extract_facts_from_text(
    db: Session, user: User, text: str, source: str
) -> List[MemoryFact]:
    """抽取并写入记忆；模型/网络失败时静默跳过（不阻断主流程）。"""
    if not text or not text.strip() or len(text.strip()) < 12:
        return []
    try:
        result = await llm_service.chat_json(
            [
                {
                    "role": "user",
                    "content": _extraction_prompt(text[:3000], source),
                }
            ],
            temperature=0.1,
            max_tokens=1500,
        )
    except Exception as e:
        logger.warning("记忆抽取失败（跳过）: %s", e)
        return []

    facts = result.get("facts") or []
    if not isinstance(facts, list):
        return []

    texts = []
    parsed = []
    for item in facts:
        if not isinstance(item, dict):
            continue
        fact_text = str(item.get("fact", "")).strip()
        mem_type = str(item.get("type", "event")).strip()
        if not fact_text or mem_type not in ALLOWED_TYPES:
            continue
        weight = _clamp_int(item.get("emotional_weight"), 0, 10, 3)
        confidence = _clamp_int(item.get("confidence"), 0, 10, 7)
        texts.append(fact_text)
        parsed.append((fact_text, mem_type, weight, confidence))
    if not texts:
        return []

    embeddings: List[List[float]] = []
    try:
        embeddings = await embed_texts_service(texts)
    except Exception as e:
        logger.warning("记忆向量化失败，仅写入无向量记忆: %s", e)
        embeddings = [[] for _ in texts]

    created = []
    for index, (fact_text, mem_type, weight, confidence) in enumerate(parsed):
        embedding = embeddings[index] if index < len(embeddings) else []
        try:
            created.append(
                _insert_fact(
                    db=db,
                    user=user,
                    fact=fact_text,
                    mem_type=mem_type,
                    source=source,
                    emotional_weight=weight,
                    confidence=confidence,
                    embedding=embedding,
                )
            )
        except Exception as e:  # 单条失败不影响其余
            logger.warning("记忆写入失败: %s", e)
            db.rollback()
    return created


async def extract_from_turn(
    db: Session,
    user: User,
    user_input: str,
    assistant_response: str,
    phase: str,
) -> List[MemoryFact]:
    text = f"用户说：{user_input}\n\n助手陪伴阶段：{phase}\n助手回应：{assistant_response[:800]}"
    return await extract_facts_from_text(db, user, text, "chat")


def _insert_fact(
    db: Session,
    user: User,
    fact: str,
    mem_type: str,
    source: str,
    emotional_weight: int,
    confidence: int,
    embedding: List[float],
) -> MemoryFact:
    """同类高相似新事实取代旧事实。"""
    is_high = mem_type == "crisis_moment" or emotional_weight >= 8

    # 冲突处理：同类型、active、语义相似 ≥0.85 → 旧事实失效
    old_facts = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == user.id,
            MemoryFact.memory_type == mem_type,
            MemoryFact.is_active == True,
        )
        .all()
    )
    for old in old_facts:
        if embedding and old.embedding:
            sim = cosine_similarity(embedding, old.embedding)
        else:
            sim = 1.0 if old.fact.strip() == fact.strip() else 0.0
        if sim >= CONFLICT_THRESHOLD:
            old.is_active = False
            old.deactivated_at = datetime.now()

    new_fact = MemoryFact(
        user_id=user.id,
        fact=fact,
        memory_type=mem_type,
        source=source,
        confidence=confidence,
        emotional_weight=emotional_weight,
        is_high_emotional=is_high,
        is_active=True,
        embedding=embedding if embedding else None,
    )
    db.add(new_fact)
    db.flush()

    # 把被取代的旧事实指向新事实
    for old in old_facts:
        if not old.is_active and old.superseded_by is None:
            old.superseded_by = new_fact.id
    db.commit()
    db.refresh(new_fact)
    return new_fact


def _lazy_deactivate(db: Session, user_id: int) -> None:
    """惰性失效：超过 INACTIVE_DAYS 未引用且非高情绪的事实自动失效。"""
    cutoff = datetime.now() - timedelta(days=INACTIVE_DAYS)
    stale = (
        db.query(MemoryFact)
        .filter(
            MemoryFact.user_id == user_id,
            MemoryFact.is_active == True,
            MemoryFact.is_high_emotional == False,
            MemoryFact.last_referenced_at < cutoff,
        )
        .all()
    )
    for fact in stale:
        fact.is_active = False
        fact.deactivated_at = datetime.now()
    if stale:
        db.commit()


async def retrieve_memories(
    db: Session, user: User, query: str, top_k: Optional[int] = None
) -> List[Dict]:
    """检索该用户 active 记忆，按 相似度*(1-R) + 时效*R + 情绪加成 排序。"""
    _lazy_deactivate(db, user.id)
    top_k = top_k or MEMORY_TOP_K

    active = (
        db.query(MemoryFact)
        .filter(MemoryFact.user_id == user.id, MemoryFact.is_active == True)
        .all()
    )
    if not active:
        return []

    query_embedding: List[float] = []
    try:
        query_embedding = (await embed_texts_service([query]))[0]
    except Exception as e:
        logger.warning("记忆查询向量化失败，降级为纯时效排序: %s", e)

    now = datetime.now()
    scored = []
    for fact in active:
        sim = 0.0
        if query_embedding and fact.embedding:
            sim = cosine_similarity(query_embedding, fact.embedding)
        elif query_embedding:
            # 无向量的事实：按关键词粗匹配给一个基础相似度
            sim = 0.4 if any(k in fact.fact for k in query[:6]) else 0.0

        days = max((now - (fact.last_referenced_at or fact.created_at)).days, 0)
        recency = _exp_decay(days)
        score = sim * (1 - RECENCY_WEIGHT) + recency * RECENCY_WEIGHT
        if fact.is_high_emotional:
            score += EMOTION_WEIGHT * (fact.emotional_weight / 10.0)
        scored.append((score, fact))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = scored[:top_k]

    result = []
    for score, fact in picked:
        fact.last_referenced_at = datetime.now()
        result.append(
            {
                "id": fact.id,
                "fact": fact.fact,
                "type": fact.memory_type,
                "source": fact.source,
                "emotional_weight": fact.emotional_weight,
                "is_high_emotional": fact.is_high_emotional,
                "score": round(score, 4),
                "created_at": fact.created_at.isoformat(),
                "last_referenced_at": (
                    fact.last_referenced_at.isoformat()
                    if fact.last_referenced_at
                    else None
                ),
            }
        )
    if picked:
        db.commit()
    return result


def list_memories(db: Session, user_id: int, include_inactive: bool = True) -> List[Dict]:
    facts = (
        db.query(MemoryFact)
        .filter(MemoryFact.user_id == user_id)
        .order_by(MemoryFact.is_active.desc(), MemoryFact.created_at.desc())
        .all()
    )
    result = []
    for fact in facts:
        if not fact.is_active and not include_inactive:
            continue
        result.append(
            {
                "id": fact.id,
                "fact": fact.fact,
                "type": fact.memory_type,
                "source": fact.source,
                "emotional_weight": fact.emotional_weight,
                "is_high_emotional": fact.is_high_emotional,
                "is_active": fact.is_active,
                "superseded_by": fact.superseded_by,
                "created_at": fact.created_at.isoformat(),
                "last_referenced_at": (
                    fact.last_referenced_at.isoformat()
                    if fact.last_referenced_at
                    else None
                ),
            }
        )
    return result


def delete_memory(db: Session, user_id: int, memory_id: int) -> bool:
    fact = (
        db.query(MemoryFact)
        .filter(MemoryFact.id == memory_id, MemoryFact.user_id == user_id)
        .first()
    )
    if not fact:
        return False
    db.delete(fact)
    db.commit()
    return True


def _exp_decay(days: int, half_life_days: float = 30.0) -> float:
    """指数衰减：30 天后衰减一半。"""
    return 2 ** (-days / half_life_days)


def _clamp_int(value, low: int, high: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, v))
