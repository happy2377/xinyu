"""长期记忆路由：查看与删除。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..memory_service import delete_memory, list_memories
from ..models import User

router = APIRouter(prefix="/api/memory", tags=["长期记忆"])


@router.get("")
async def get_memories(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出当前用户的长期记忆（默认只看有效记忆）。"""
    return {
        "memories": list_memories(db, current_user.id, include_inactive=include_inactive)
    }


@router.delete("/{memory_id}")
async def remove_memory(
    memory_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除一条记忆（用户主动删除，含高情绪记忆）。"""
    ok = delete_memory(db, current_user.id, memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"success": True, "message": "记忆已删除"}
