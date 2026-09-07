"""知识库服务：类型化分块、向量化入库、混合检索（向量 + FTS5 + RRF）。"""
import logging
import os
import asyncio
import re
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .knowledge_seed import SEED_DOCS
from .embedding_service import embed_texts as embed_texts_service
from .models import KnowledgeChunk, KnowledgeDoc
from .vector_utils import cosine_similarity, rrf_merge

logger = logging.getLogger(__name__)

RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.35"))
MAX_CHUNK_CHARS = 800
CHUNK_OVERLAP = 80
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
WHOLE_DOC_TYPES = {"scale", "crisis"}


# ---------- 分块 ----------

def _flush(buffer: List[str], chunks: List[str], overlap: int = CHUNK_OVERLAP) -> str:
    """把当前缓冲区写入 chunks，返回下一缓冲区的开头（重叠部分）。"""
    if not buffer:
        return ""
    text_block = "\n".join(buffer).strip()
    if text_block:
        chunks.append(text_block)
    joined = "\n".join(buffer)
    return joined[-overlap:] if len(joined) > overlap else ""


def chunk_document(content: str, doc_type: str) -> List[str]:
    """按文档类型分块：
    - scale / crisis：整篇单块，禁止切开（量表题目、评分规则、危机资源必须完整）；
    - 其他：按 Markdown 标题分段，块上限 800 字、重叠 80 字，跨段内容不硬切。
    """
    content = (content or "").strip()
    if not content:
        return []
    if doc_type in WHOLE_DOC_TYPES:
        return [content]

    def split_long_line(line: str) -> List[str]:
        """把超过上限的单行切成 ≤800 的片段，片段间保留 80 字重叠。"""
        if len(line) <= MAX_CHUNK_CHARS:
            return [line]
        pieces = []
        start = 0
        while start < len(line):
            end = min(start + MAX_CHUNK_CHARS, len(line))
            pieces.append(line[start:end])
            if end == len(line):
                break
            start = end - CHUNK_OVERLAP
        return pieces

    lines = content.splitlines()
    chunks: List[str] = []
    buffer: List[str] = []
    current_size = 0
    overlap_tail = ""

    for raw_line in lines:
        line = raw_line.rstrip()
        is_heading = bool(re.match(r"^#{1,6}\s", line))
        if is_heading and buffer:
            overlap_tail = _flush(buffer, chunks)
            buffer = []
            current_size = len(overlap_tail)
            if overlap_tail:
                buffer.append(overlap_tail)
        for piece in split_long_line(line):
            piece_len = len(piece) + 1
            if buffer and current_size + piece_len > MAX_CHUNK_CHARS:
                overlap_tail = _flush(buffer, chunks)
                buffer = [overlap_tail] if overlap_tail else []
                current_size = len(overlap_tail)
            buffer.append(piece)
            current_size += piece_len

    _flush(buffer, chunks)
    return [c for c in chunks if c.strip()]


# ---------- 入库 ----------

async def _embed_or_empty(texts: List[str]) -> List[List[float]]:
    try:
        return await embed_texts_service(texts)
    except Exception as e:
        logger.warning("Embedding 调用失败: %s", e)
        return []


async def ingest_doc(
    db: Session,
    title: str,
    content: str,
    doc_type: str,
    source_url: Optional[str] = None,
    license_note: Optional[str] = None,
    is_seed: bool = False,
    user_id: Optional[int] = None,
) -> KnowledgeDoc:
    """分块并写入知识库；embedding 失败时抛出异常（调用方决定是否回滚）。"""
    if is_seed:
        existing = (
            db.query(KnowledgeDoc)
            .filter(KnowledgeDoc.title == title, KnowledgeDoc.is_seed == True)
            .first()
        )
        if existing:
            return existing

    chunks = chunk_document(content, doc_type)
    if not chunks:
        raise ValueError("文档内容为空")

    embeddings = await _embed_or_empty(chunks)
    if not embeddings or len(embeddings) != len(chunks):
        raise RuntimeError("向量化失败，请确认 MODELSCOPE_API_KEY 已配置且网络可用")

    doc = KnowledgeDoc(
        title=title,
        doc_type=doc_type,
        source_url=source_url,
        license_note=license_note,
        is_seed=is_seed,
        user_id=user_id,
    )
    db.add(doc)
    db.flush()

    for index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
        chunk = KnowledgeChunk(
            doc_id=doc.id,
            chunk_index=index,
            content=chunk_text,
            embedding=embedding,
        )
        db.add(chunk)
        db.flush()
        db.execute(
            text(
                "INSERT INTO knowledge_chunks_fts(chunk_id, content) VALUES (:cid, :c)"
            ),
            {"cid": chunk.id, "c": chunk_text},
        )

    db.commit()
    db.refresh(doc)
    logger.info("知识文档入库: %s（%d 块）", title, len(chunks))
    return doc


async def import_seed_knowledge(db: Session) -> int:
    """幂等导入种子知识库；失败时整体跳过并记录日志。"""
    imported = 0
    for doc in SEED_DOCS:
        try:
            await ingest_doc(
                db=db,
                title=doc["title"],
                content=doc["content"],
                doc_type=doc["doc_type"],
                source_url=doc.get("source_url"),
                license_note=doc.get("license_note", "公开资料整理，仅供学习研究"),
                is_seed=True,
            )
            imported += 1
        except Exception as e:
            db.rollback()
            logger.warning("种子文档导入失败（跳过 %s）: %s", doc["title"], e)
        # 避免触发云端向量限流：文档间留间隔
        await asyncio.sleep(1.5)
    return imported


def delete_doc(db: Session, doc_id: int, user_id: Optional[int]) -> bool:
    """删除文档；仅允许删除本人上传的非种子文档。"""
    doc = db.query(KnowledgeDoc).filter(KnowledgeDoc.id == doc_id).first()
    if not doc:
        return False
    if doc.is_seed:
        return False
    if user_id is not None and doc.user_id != user_id:
        return False

    chunk_ids = [
        row[0]
        for row in db.query(KnowledgeChunk.id)
        .filter(KnowledgeChunk.doc_id == doc_id)
        .all()
    ]
    for chunk_id in chunk_ids:
        db.execute(
            text("DELETE FROM knowledge_chunks_fts WHERE chunk_id = :cid"),
            {"cid": chunk_id},
        )
    db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc_id).delete()
    db.delete(doc)
    db.commit()
    return True


# ---------- 检索 ----------

def _query_terms(query: str) -> List[str]:
    """抽取检索词：中文连续段与字母数字词，用于 trigram FTS / LIKE。"""
    terms = set()
    for piece in re.split(r"[\s，。！？、；：,.!?;:'\"()（）\[\]【】]+", query):
        piece = piece.strip()
        if not piece:
            continue
        if re.search(r"[\u4e00-\u9fff]", piece):
            terms.add(piece)
        else:
            terms.update(re.findall(r"[A-Za-z0-9][A-Za-z0-9\-.]*", piece))
    return [t for t in terms if t]


def _fts_search(db: Session, query: str, limit: int = 20) -> List[int]:
    """FTS5 trigram 检索；MATCH 需要每词 >= 3 字符，否则退回 LIKE。"""
    terms = _query_terms(query)
    matchers = [t for t in terms if len(t) >= 3]
    if matchers:
        match_sql = " OR ".join(
            '"' + t.replace('"', '""') + '"' for t in matchers
        )
        try:
            rows = db.execute(
                text(
                    "SELECT chunk_id FROM knowledge_chunks_fts "
                    "WHERE knowledge_chunks_fts MATCH :m ORDER BY rank LIMIT :lim"
                ),
                {"m": match_sql, "lim": limit},
            ).fetchall()
            if rows:
                return [r[0] for r in rows]
        except Exception as e:
            logger.warning("FTS 检索失败，改用 LIKE: %s", e)

    # LIKE 兜底（覆盖 1-2 字词）
    found: List[int] = []
    for term in terms[:5]:
        rows = db.execute(
            text(
                "SELECT chunk_id FROM knowledge_chunks_fts "
                "WHERE content LIKE :kw LIMIT :lim"
            ),
            {"kw": f"%{term}%", "lim": limit},
        ).fetchall()
        found.extend(r[0] for r in rows)
    return found[:limit]


def _chunk_map(db: Session, chunk_ids: List[int]) -> Dict[int, KnowledgeChunk]:
    if not chunk_ids:
        return {}
    rows = db.query(KnowledgeChunk).filter(KnowledgeChunk.id.in_(chunk_ids)).all()
    return {row.id: row for row in rows}


async def hybrid_search(db: Session, query: str) -> List[Dict]:
    """向量 + FTS5 → RRF 合并 → top-k；相关性不足返回空列表（触发拒答）。"""
    chunks_all = db.query(KnowledgeChunk).all()
    if not chunks_all:
        return []

    # 1) 向量检索
    vector_ids: List[int] = []
    query_embedding: List[float] = []
    try:
        query_embedding = (await embed_texts_service([query]))[0]
    except Exception as e:
        logger.warning("查询向量化失败: %s", e)

    cosine_map: Dict[int, float] = {}
    if query_embedding:
        scored = []
        for chunk in chunks_all:
            if not chunk.embedding:
                continue
            score = cosine_similarity(query_embedding, chunk.embedding)
            cosine_map[chunk.id] = score
            scored.append((chunk.id, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        vector_ids = [cid for cid, _ in scored[:20]]

    # 2) 关键词检索
    keyword_ids = _fts_search(db, query, limit=20)
    keyword_set = set(keyword_ids)

    # 3) RRF 合并
    merged = rrf_merge([vector_ids, keyword_ids])
    top_ids = [cid for cid, _ in merged[:RAG_TOP_K]]
    if not top_ids:
        return []

    chunk_map = _chunk_map(db, top_ids)
    doc_ids = list({chunk_map[cid].doc_id for cid in top_ids if cid in chunk_map})
    docs = (
        db.query(KnowledgeDoc)
        .filter(KnowledgeDoc.id.in_(doc_ids))
        .all()
        if doc_ids
        else []
    )
    doc_map = {d.id: d for d in docs}

    results = []
    for cid in top_ids:
        chunk = chunk_map.get(cid)
        if not chunk:
            continue
        doc = doc_map.get(chunk.doc_id)
        cosine = cosine_map.get(cid, 0.0)
        keyword_boost = 0.45 if cid in keyword_set else 0.0
        results.append(
            {
                "chunk_id": chunk.id,
                "doc_id": chunk.doc_id,
                "title": doc.title if doc else "",
                "doc_type": doc.doc_type if doc else "",
                "source_url": doc.source_url if doc else "",
                "content": chunk.content,
                "score": max(cosine, keyword_boost),
                "matched_fts": cid in keyword_set,
            }
        )

    # 4) 相关性闸门：向量与关键词都没有足够信号 → 拒答
    best = max((r["score"] for r in results), default=0.0)
    if best < RAG_MIN_SCORE:
        return []
    results.sort(key=lambda r: r["score"], reverse=True)
    return results
