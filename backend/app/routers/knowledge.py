"""知识库路由：种子导入、列表、用户文档上传与删除。"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..knowledge_service import (
    MAX_UPLOAD_BYTES,
    delete_doc,
    import_seed_knowledge,
    ingest_doc,
)
from ..models import KnowledgeChunk, KnowledgeDoc, User

router = APIRouter(prefix="/api/knowledge", tags=["知识库"])


@router.get("")
async def list_knowledge(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出种子文档与当前用户上传的文档。"""
    docs = db.query(KnowledgeDoc).all()
    counts = dict(
        db.query(KnowledgeChunk.doc_id, func.count(KnowledgeChunk.id))
        .group_by(KnowledgeChunk.doc_id)
        .all()
    )
    result = []
    for doc in docs:
        if doc.is_seed or doc.user_id == current_user.id:
            result.append(
                {
                    "id": doc.id,
                    "title": doc.title,
                    "doc_type": doc.doc_type,
                    "source_url": doc.source_url,
                    "is_seed": doc.is_seed,
                    "chunk_count": counts.get(doc.id, 0),
                    "created_at": doc.created_at.isoformat(),
                }
            )
    return result


@router.post("/seed")
async def seed_knowledge(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """幂等导入精选种子知识库（任意登录用户可触发）。"""
    imported = await import_seed_knowledge(db)
    return {"success": True, "imported": imported, "message": f"种子知识库导入完成（新增 {imported} 篇）"}


@router.post("/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传 txt/markdown 文档（一期），仅当前用户可管理。"""
    filename = (file.filename or "").lower()
    if not filename.endswith((".txt", ".md", ".markdown")):
        raise HTTPException(status_code=400, detail="一期仅支持 .txt / .md / .markdown 文件")

    content_bytes = await file.read()
    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 2MB 限制")
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件必须为 UTF-8 编码")

    title = file.filename or "未命名文档"
    try:
        doc = await ingest_doc(
            db=db,
            title=title,
            content=content,
            doc_type="psychoeducation",
            license_note="用户上传，仅供个人学习研究",
            is_seed=False,
            user_id=current_user.id,
        )
    except RuntimeError as e:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "success": True,
        "doc_id": doc.id,
        "title": doc.title,
        "message": "文档已入库",
    }


@router.delete("/{doc_id}")
async def remove_knowledge(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除本人上传的文档（种子文档不可删除）。"""
    ok = delete_doc(db, doc_id, user_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在或不可删除")
    return {"success": True, "message": "文档已删除"}
