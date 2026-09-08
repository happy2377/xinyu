"""深度探索 Agent 路由。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..agent_service import run_agent
from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..schemas import AgentRunRequest

router = APIRouter(prefix="/api/agent", tags=["深度探索Agent"])


@router.post("/run")
async def agent_run(
    request: AgentRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """运行一次深度探索：Agent 自主调用只读工具后给出回答。"""
    return await run_agent(db, current_user, request.message)
