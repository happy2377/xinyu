"""多智能体协调器 - 核心调度模块"""
import logging
from typing import AsyncGenerator, Dict, List
from sqlalchemy.orm import Session
from .models import Conversation, Message, User
from .perception_planning import PerceptionPlanningModule
from .conversation_agent import ConversationAgent
from .phase_manager import PhaseManager
from .model_router import ModelRouter
from .knowledge_service import hybrid_search
from .memory_service import extract_from_turn, retrieve_memories

logger = logging.getLogger(__name__)

class MultiAgentCoordinator:
    """多智能体协调器"""
    
    def __init__(self):
        self.perception_module = PerceptionPlanningModule()
        self.agent = ConversationAgent()
        self.phase_manager = PhaseManager()
        self.model_router = ModelRouter()
        
        # 危机应对话术
        self.crisis_response = """我注意到你现在可能很痛苦，这让我很担心。请相信，这些感受是可以改变的。

🆘 紧急求助方式：
- 心理危机热线：400-161-9995（24小时）
- 全国心理援助热线：010-82951332
- 生命热线：400-821-1215

如果情况紧急，请立即拨打 110 或前往最近的医院急诊科。

你的生命很重要，很多人关心你。专业的帮助能让情况变得更好，请不要独自承受。"""
    
    async def process_message(
        self,
        user_input: str,
        user: User,
        db: Session,
        conversation_id: int = None
    ) -> AsyncGenerator[Dict, None]:
        """
        处理用户消息的核心流程
        :param user_input: 用户输入
        :param user: 当前用户
        :param db: 数据库会话
        :param conversation_id: 对话ID
        :yield: 流式响应数据
        """
        # 步骤1：获取或创建对话
        conversation = await self._get_or_create_conversation(
            user, db, conversation_id
        )
        
        # 步骤2：保存用户消息
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=user_input
        )
        db.add(user_message)
        db.commit()
        
        # 更新轮次
        conversation.round_count += 1
        db.commit()
        
        # 步骤3：获取对话历史
        conversation_history = self._get_conversation_history(conversation, db)
        
        # 步骤4：执行感知规划（双层判断 - 使用本地模型）
        perception_result = await self.perception_module.execute(
            user_input, conversation_history
        )
        
        # 步骤5：危机检测
        if perception_result["is_crisis"]:
            # 危机情况：返回紧急应对话术
            conversation.status = "crisis"
            db.commit()
            
            yield {
                "type": "crisis",
                "content": self.crisis_response,
                "conversation_id": conversation.id
            }
            
            # 保存危机响应
            crisis_message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=self.crisis_response,
                agent_type="SafetyAgent",
                model_used="local"
            )
            db.add(crisis_message)
            db.commit()
            return
        
        # 步骤6：阶段管理
        should_transition, new_phase = self.phase_manager.should_transition(
            conversation.phase,
            conversation.round_count,
            user_input
        )
        if should_transition:
            conversation.phase = new_phase
            db.commit()

        # 步骤6.5：长期记忆 + RAG（危机已提前返回，不会走到这里）
        memories = []
        try:
            memory_query = user_input[:200] + " " + " ".join(
                m["content"][:80] for m in conversation_history[-4:]
            )
            memories = await retrieve_memories(db, user, memory_query)
        except Exception as e:
            logger.warning("记忆检索失败（跳过）: %s", e)

        rag_hits = []
        rag_no_hit = False
        if perception_result.get("intent") == "knowledge":
            try:
                rag_hits = await hybrid_search(db, user_input)
            except Exception as e:
                logger.warning("知识库检索失败（跳过）: %s", e)
            if not rag_hits:
                rag_no_hit = True
        
        # 步骤7：选择模型服务并生成AI响应
        model_service = self.model_router.get_model_service(
            perception_result["is_privacy_issue"],
            perception_result["is_complex_issue"]
        )
        model_name = self.model_router.get_model_name(
            perception_result["is_privacy_issue"],
            perception_result["is_complex_issue"]
        )
        
        yield {
            "type": "metadata",
            "conversation_id": conversation.id,
            "phase": conversation.phase,
            "round_count": conversation.round_count,
            "is_privacy": perception_result["is_privacy_issue"],
            "is_complex": perception_result["is_complex_issue"],
            "model_used": model_name
        }
        
        # 根据阶段构造系统提示词
        phase_prompts = {
            "emotional": self.agent.phase_prompts["emotional"],
            "rational": self.agent.phase_prompts["rational"],
            "solution": self.agent.phase_prompts["solution"]
        }
        knowledge_intent = perception_result.get("intent") == "knowledge"
        if knowledge_intent:
            # 知识性问题：切换到“资料助手”模式，避免被共情人格带偏
            system_prompt = (
                "用户正在询问知识性问题。请切换到资料助手模式，并严格按下述结构回答：\n"
                "1. 第一段：用 1-2 句话直接、简洁地回答用户问题，结论先行；\n"
                "2. 若资料中包含多条可操作信息，输出 “### 要点” 无序列表；\n"
                "3. 若资料中包含注意事项、求助或就医建议，输出 “### 提醒” 无序列表；\n"
                "4. 结尾另起一行输出：资料来源：《文档标题》（多篇用顿号分隔）；\n"
                "5. 全文禁止出现 “[来源：…]” 之类的句内引用；\n"
                "6. 只能基于下方【资料库摘录】作答；若摘录与问题不相关或不足以回答，"
                "直接说明“资料库暂无相关内容”，并把资料来源写为：资料来源：无，不要列无关文档；\n"
                "7. 不要长篇共情或堆砌安慰，主体必须是事实性内容。"
            )
        else:
            system_prompt = phase_prompts.get(
                conversation.phase, self.agent.phase_prompts["emotional"]
            )

        if memories and not knowledge_intent:
            memory_lines = "\n".join(
                f"- [{m['created_at'][:10]} · {m['type']}] {m['fact']}"
                for m in memories
            )
            system_prompt += (
                "\n\n【长期记忆（仅供参考，可能已过时）】\n"
                + memory_lines
                + "\n若与当前话题相关可自然引用，不要编造记忆中没有的细节。"
            )

        if rag_hits:
            rag_sections = "\n\n".join(
                f"[{i+1}] 《{h['title']}》\n{h['content'][:900]}"
                for i, h in enumerate(rag_hits)
            )
            system_prompt += (
                "\n\n【资料库摘录】（必须基于此回答并标注来源）\n"
                + rag_sections
            )
        elif rag_no_hit:
            system_prompt += (
                "\n\n当前资料库未命中与问题相关的内容。"
                "请如实告知用户“资料库中暂时没有相关内容”，"
                "并建议换个问法，不要编造答案。"
            )
        
        full_response = ""
        async for chunk in model_service.generate_with_prompt(
            system_prompt,
            user_input,
            conversation_history,
            stream=True
        ):
            full_response += chunk
            yield {
                "type": "chunk",
                "content": chunk
            }
        
        # 步骤8：保存AI响应
        ai_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=full_response,
            agent_type="ConversationAgent",
            model_used=model_name,
            is_privacy_issue=perception_result["is_privacy_issue"],
            is_complex_issue=perception_result["is_complex_issue"],
            rag_sources=[
                {
                    "doc_id": h["doc_id"],
                    "chunk_id": h["chunk_id"],
                    "title": h["title"],
                    "source_url": h["source_url"],
                }
                for h in rag_hits
            ]
            if rag_hits
            else None,
        )
        db.add(ai_message)
        db.commit()

        # 步骤8.5：对话结束后抽取长期记忆（失败不影响主流程）
        try:
            await extract_from_turn(
                db, user, user_input, full_response, conversation.phase
            )
        except Exception as e:
            logger.warning("对话记忆抽取失败（跳过）: %s", e)
        
        yield {"type": "end"}
    
    async def _get_or_create_conversation(
        self, 
        user: User, 
        db: Session, 
        conversation_id: int = None
    ) -> Conversation:
        """获取或创建对话"""
        if conversation_id:
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
                Conversation.status == "ongoing"  # 只获取进行中的对话
            ).first()
            if conversation:
                return conversation
        
        # 创建新对话
        conversation = Conversation(
            user_id=user.id,
            phase="emotional",
            round_count=0,
            status="ongoing"
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation
    
    def _get_conversation_history(
        self, 
        conversation: Conversation, 
        db: Session
    ) -> List[Dict]:
        """获取对话历史"""
        messages = db.query(Message).filter(
            Message.conversation_id == conversation.id
        ).order_by(Message.created_at.asc()).limit(20).all()
        
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]


# 全局协调器实例
coordinator = MultiAgentCoordinator()
