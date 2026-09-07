"""感知规划模块：
- 危机关键词检测优先（快、稳，不依赖模型）；
- 其余输入由云端模型一次性输出 隐私 / 复杂度 / 意图 判断；
- 模型不可用时降级为关键词/规则判断。
"""
import logging
import re
from typing import Dict, List

from .llm_service import llm_service

logger = logging.getLogger(__name__)


class PerceptionPlanningModule:
    def __init__(self):
        self.crisis_keywords = [
            "自杀", "想死", "活不下去", "结束生命", "不想活了",
            "自残", "割腕", "跳楼", "了结",
            "暴力", "伤害", "报复", "杀", "打死",
        ]
        self.privacy_keywords = [
            "身份证", "家庭住址", "电话号码", "学号", "真名",
            "恋爱", "分手", "出轨", "暗恋", "前任", "男朋友", "女朋友",
            "父母离婚", "家暴", "家庭矛盾", "性侵", "欺凌", "霸凌",
            "保密", "隐私", "不要记录",
        ]
        self.complexity_keywords = [
            "计划", "步骤", "方案", "分析", "建议", "对策",
            "怎么办", "如何", "怎样", "怎么做", "具体", "详细",
        ]
        self.knowledge_keywords = [
            "什么是", "是什么", "介绍", "解释", "量表", "phq", "gad",
            "评分", "等级", "焦虑", "抑郁", "失眠", "睡眠", "正念",
            "呼吸", "放松", "热线", "危机", "求助", "认知", "cbt",
            "怎么用", "如何用",
        ]

    def detect_crisis(self, user_input: str) -> bool:
        text = (user_input or "").lower()
        return any(kw in text for kw in self.crisis_keywords)

    async def execute(
        self, user_input: str, conversation_history: List[Dict]
    ) -> Dict:
        is_crisis = self.detect_crisis(user_input)
        if is_crisis:
            return {
                "is_crisis": True,
                "is_privacy_issue": True,
                "is_complex_issue": False,
                "intent": "crisis",
                "privacy_reason": "危机情况",
                "complexity_reason": "",
                "recommended_model": "remote",
            }

        result = await self._remote_classify(user_input, conversation_history)
        if (
            result.get("intent") != "knowledge"
            and self._looks_like_knowledge_question(user_input)
        ):
            result["intent"] = "knowledge"
        result["is_crisis"] = False
        result["recommended_model"] = "remote"
        return result

    def _looks_like_knowledge_question(self, text: str) -> bool:
        """规则兜底：防止“PHQ-9 是什么”这类问题被误判成情绪倾诉。"""
        t = (text or "").strip().lower()
        explicit = (
            "什么是" in t
            or "是什么" in t
            or "是什么意思" in t
            or "有什么用" in t
            or "介绍一下" in t
            or "解释" in t
            or "怎么缓解" in t
            or "怎么改善" in t
            or "有哪些" in t
            or "如何用" in t
            or "怎么用" in t
            or "量表" in t
            or "评分标准" in t
        )
        if explicit:
            return True
        domain = any(
            kw in t
            for kw in (
                "phq", "gad", "焦虑", "抑郁", "失眠", "睡眠",
                "正念", "呼吸放松", "热线", "危机", "cbt", "认知行为",
            )
        )
        question = any(kw in t for kw in ("怎么", "如何", "怎样"))
        return domain and question and len(text) <= 80

    async def _remote_classify(
        self, user_input: str, conversation_history: List[Dict]
    ) -> Dict:
        recent = conversation_history[-6:] if conversation_history else []
        history_text = "\n".join(
            f"{m.get('role')}: {m.get('content')}" for m in recent
        )[:1200]
        prompt = f"""你是心翼的感知判断模块。请分析用户输入，返回 JSON。

对话历史：
{history_text}

当前用户输入：{user_input}

判断维度：
1. is_privacy：是否涉及敏感隐私（身份信息、恋爱/家庭隐私、创伤事件、明确要求保密）；
2. is_complex：是否需要系统性方案、详细计划或跨多轮深入分析；
3. intent：用户此刻最需要什么，只能是以下之一：
   - knowledge：询问知识/概念/量表/方法（如“PHQ-9 是什么”“怎么缓解失眠”）
   - emotional：需要倾听、共情与情绪支持
   - planning：需要具体计划、步骤、行动建议
   - chit_chat：日常寒暄/一般闲聊

只返回 JSON：
{{"is_privacy": false, "privacy_reason": "理由", "is_complex": false, "complexity_reason": "理由", "intent": "emotional"}}"""
        try:
            data = await llm_service.chat_json(
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=600,
            )
            intent = str(data.get("intent", "emotional")).strip().lower()
            if intent not in {"knowledge", "emotional", "planning", "chit_chat"}:
                intent = "emotional"
            return {
                "is_privacy_issue": bool(data.get("is_privacy", False)),
                "privacy_reason": str(data.get("privacy_reason", ""))[:50],
                "is_complex_issue": bool(data.get("is_complex", False)),
                "complexity_reason": str(data.get("complexity_reason", ""))[:50],
                "intent": intent,
            }
        except Exception as e:
            logger.warning("云端感知判断失败，降级为规则: %s", e)
            return self._fallback_classify(user_input, conversation_history)

    def _fallback_classify(
        self, user_input: str, conversation_history: List[Dict]
    ) -> Dict:
        text = (user_input or "").lower()
        is_privacy = any(kw in text for kw in self.privacy_keywords)
        if re.search(r"\d{11}", user_input):
            is_privacy = True
        if re.search(r"\d{17}[\dxX]", user_input):
            is_privacy = True

        is_complex = any(kw in text for kw in self.complexity_keywords)
        if len(user_input) > 100:
            is_complex = True
        if len(conversation_history) > 16:
            is_complex = True

        intent = "emotional"
        if any(kw in text for kw in self.knowledge_keywords):
            intent = "knowledge"
        elif is_complex:
            intent = "planning"
        return {
            "is_privacy_issue": is_privacy,
            "privacy_reason": "命中隐私关键词" if is_privacy else "",
            "is_complex_issue": is_complex,
            "complexity_reason": "命中复杂度关键词" if is_complex else "",
            "intent": intent,
        }
