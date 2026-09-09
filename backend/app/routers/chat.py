"""对话相关路由"""
import json
import logging
import random
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import AsyncGenerator
from ..database import get_db
from ..models import User, Conversation, Message
from ..schemas import ChatSendRequest, Response
from ..auth import get_current_user
from ..coordinator import coordinator
from ..conversation_agent import ConversationAgent
from ..llm_service import llm_service
from ..memory_service import extract_from_turn
from ..perception_planning import PerceptionPlanningModule
from ..safety import CRISIS_RESPONSE, PROMPT_CORE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["智能对话"])

@router.post("/send")
async def send_message(
    request: ChatSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """发送消息并获取 AI 响应（流式）"""
    
    async def generate() -> AsyncGenerator[str, None]:
        """生成 SSE 流"""
        try:
            events = (
                _process_image_message(request, current_user, db)
                if request.image_data
                else coordinator.process_message(
                    user_input=request.message,
                    user=current_user,
                    db=db,
                    conversation_id=request.conversation_id,
                )
            )
            async for event in events:
                # 将事件序列化为 SSE 格式
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        
        except Exception as e:
            error_event = {
                "type": "error",
                "content": f"处理失败: {str(e)}"
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


async def _process_image_message(
    request: ChatSendRequest,
    user: User,
    db: Session,
) -> AsyncGenerator[dict, None]:
    """多模态图片对话：视觉模型理解图片 → 心屿语气回应 → 写记忆。"""
    user_text = request.message.strip() or "（发来一张图片）"

    # 危机优先
    if PerceptionPlanningModule().detect_crisis(user_text):
        conversation = await _get_or_create_conversation(db, user, request.conversation_id)
        _save_user_message(db, conversation, user_text)
        _save_assistant_message(
            db, conversation, CRISIS_RESPONSE, agent_type="SafetyAgent"
        )
        yield {"type": "crisis", "content": CRISIS_RESPONSE, "conversation_id": conversation.id}
        return

    # 1) 视觉模型分析图片
    analysis = await llm_service.chat_vision(
        request.image_data,
        "请用中文描述这张图片：画面里有什么（人物/场景/物体/文字/表情），"
        "以及它可能传达的情绪氛围。只描述看到的，不要猜测隐私信息。不超过 150 字。",
        max_tokens=400,
        mode="vision_analyze",
    )

    # 2) 取对话历史（不含本轮）并保存用户消息
    conversation = await _get_or_create_conversation(db, user, request.conversation_id)
    history_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(10)
        .all()
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(history_messages)
    ]
    _save_user_message(db, conversation, user_text)

    # 3) 用陪伴语气生成回应
    system = (
        PROMPT_CORE
        + "\n\n"
        + ConversationAgent().phase_prompts["emotional"]
    )
    user_payload = (
        f"用户消息：{user_text}\n\n"
        f"【图片分析】\n{analysis[:600]}\n\n"
        "请自然地把图片内容带入回应：如果它承载了情绪（如风景、旧照片、宠物、涂鸦），"
        "温柔地接住；如果只是普通图片，简单回应后回到用户想聊的事。"
    )
    reply = await llm_service.chat(
        [{"role": "system", "content": system}]
        + history
        + [{"role": "user", "content": user_payload}],
        temperature=0.7,
        max_tokens=700,
        mode="vision_reply",
    )

    _save_assistant_message(db, conversation, reply, agent_type="ConversationAgent")
    try:
        await extract_from_turn(
            db,
            user,
            f"{user_text}\n图片分析：{analysis[:300]}",
            reply,
            conversation.phase,
        )
    except Exception as e:  # noqa: BLE001 - 记忆抽取失败不影响回复
        logger.warning("图片对话记忆抽取失败（跳过）: %s", e)

    yield {
        "type": "metadata",
        "conversation_id": conversation.id,
        "phase": conversation.phase,
        "round_count": conversation.round_count,
        "is_privacy": False,
        "is_complex": False,
    }
    yield {"type": "chunk", "content": reply}
    yield {"type": "end"}


async def _get_or_create_conversation(
    db: Session, user: User, conversation_id: int | None
) -> Conversation:
    if conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
                Conversation.status == "ongoing",
            )
            .first()
        )
        if conversation:
            return conversation
    conversation = Conversation(
        user_id=user.id,
        phase="emotional",
        round_count=0,
        status="ongoing",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _save_user_message(db: Session, conversation: Conversation, content: str) -> None:
    db.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content=content,
        )
    )
    conversation.round_count += 1
    db.commit()


def _save_assistant_message(
    db: Session,
    conversation: Conversation,
    content: str,
    agent_type: str = "ConversationAgent",
) -> None:
    db.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            content=content,
            agent_type=agent_type,
            model_used="vision",
        )
    )
    db.commit()


@router.get("/active")
async def get_active_conversation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户当前活跃的对话"""
    conversation = db.query(Conversation).filter(
        Conversation.user_id == current_user.id,
        Conversation.status == "ongoing"
    ).order_by(Conversation.last_active.desc()).first()
    
    if not conversation:
        return {"conversation_id": None, "phase": None, "round_count": 0}
    
    return {
        "conversation_id": conversation.id,
        "phase": conversation.phase,
        "round_count": conversation.round_count,
        "status": conversation.status
    }


@router.delete("/clear", response_model=Response)
async def clear_conversation(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """手动清空当前对话"""
    # 删除该用户的所有对话（不论状态）
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).all()
    
    for conv in conversations:
        # 删除所有消息（隐私保护）
        db.query(Message).filter(
            Message.conversation_id == conv.id
        ).delete()
        
        # 删除对话记录
        db.delete(conv)
    
    db.commit()
    
    # 返回温暖的结束语
    ending_messages = [
        "很高兴能陪你度过这段时光！每一天都是新的开始，加油！💪",
        "你已经迈出了重要的一步！相信自己，未来会更好！🌟",
        "记住，你并不孤单。随时回来找我聊天，我一直在这里！🤗",
        "你做得很好！继续保持这份勇气和力量！✨",
        "为你的成长感到骄傲！期待你的下一次进步！🌈"
    ]
    
    return Response(
        success=True, 
        message=random.choice(ending_messages)
    )
