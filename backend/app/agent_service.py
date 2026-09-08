"""二期：工具化 Agent（深度探索模式）。

Agent 通过“工具 JSON 协议”自主调用只读工具（知识库检索 / 长期记忆 / 日记 /
量表 / 训练统计 / 训练推荐），最多 4 轮后给出最终回答。
不使用平台私有的 function-calling 协议，纯文本 JSON 更稳、可解释、便于演示。
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from .knowledge_service import hybrid_search
from .llm_service import llm_service
from .memory_service import retrieve_memories
from .models import (
    AssessmentRecord,
    AssessmentTemplate,
    Diary,
    TrainingRecord,
    TrainingTemplate,
    User,
)
from .perception_planning import PerceptionPlanningModule
from .safety import CRISIS_RESPONSE, PROMPT_CORE

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4

AGENT_SYSTEM = (
    PROMPT_CORE
    + """

【深度探索 Agent】
你是心翼的深度探索模式。用户会询问自己的状态、心理知识、数据解读或“我该练什么”。
你可以按需调用下面这些只读工具（一次一个）：

- search_knowledge(query)：检索内置心理知识库（量表、睡眠、CBT 等），参数 query 必填；
- retrieve_memories(query)：检索该用户的长期记忆；
- recent_diaries(days)：读取最近 days 天日记（默认 14）；
- recent_assessments(days, scale_name?)：读取最近量表记录（PHQ-9/GAD-7 等）；
- training_stats(days)：最近训练完成情况；
- recommend_training()：基于最新量表/记忆/日记给训练推荐。

输出协议（每次只输出一个 JSON，不要输出其他文字）：
1) 需要更多数据时：
{"thought":"一句话说明为什么","tool":"工具名","params":{...}}
2) 数据足够时：
{"thought":"一句话总结依据","final":"给用户的最终回答"}

规则：
- 最多连续调用 4 次工具，之后必须给 final；
- 用工具返回的真实数据说话，禁止编造用户没有的日记/量表/记忆；
- 没有数据时如实说明“目前还没有足够的记录”，并建议用户先写日记/做量表；
- 涉及危机仍按安全红线处理；涉及医疗建议要说明仅供参考；
- final 里用第一人称“我”之外的称呼保持温柔专业，可用少量 Markdown 结构。"""
)

_TOOL_NAMES = {
    "search_knowledge",
    "retrieve_memories",
    "recent_diaries",
    "recent_assessments",
    "training_stats",
    "recommend_training",
}


def _crisis_check(text: str) -> bool:
    return PerceptionPlanningModule().detect_crisis(text)


async def _run_tool(
    db: Session,
    user: User,
    tool: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    if tool == "search_knowledge":
        query = str(params.get("query") or "")[:120]
        hits = await hybrid_search(db, query)
        return {
            "count": len(hits),
            "results": [
                {"title": h["title"], "content": h["content"][:600]} for h in hits[:3]
            ],
        }

    if tool == "retrieve_memories":
        query = str(params.get("query") or "最近状态")[:200]
        mems = await retrieve_memories(db, user, query, top_k=5)
        return {
            "count": len(mems),
            "memories": [
                {
                    "fact": m["fact"],
                    "type": m["type"],
                    "created_at": m["created_at"][:10],
                    "emotional_weight": m["emotional_weight"],
                }
                for m in mems
            ],
        }

    if tool == "recent_diaries":
        days = min(int(params.get("days") or 14), 90)
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        diaries = (
            db.query(Diary)
            .filter(Diary.user_id == user.id, Diary.diary_date >= start)
            .order_by(Diary.diary_date.desc())
            .limit(30)
            .all()
        )
        return {
            "count": len(diaries),
            "diaries": [
                {
                    "date": d.diary_date,
                    "main_emotion": d.main_emotion,
                    "emotions": d.emotions or [],
                    "ai_score": d.ai_score,
                    "excerpt": (d.content or "")[:100],
                }
                for d in diaries
            ],
        }

    if tool == "recent_assessments":
        days = min(int(params.get("days") or 30), 180)
        start_dt = datetime.now() - timedelta(days=days)
        query = (
            db.query(AssessmentRecord, AssessmentTemplate)
            .join(AssessmentTemplate, AssessmentRecord.template_id == AssessmentTemplate.id)
            .filter(
                AssessmentRecord.user_id == user.id,
                AssessmentRecord.created_at >= start_dt,
            )
        )
        scale = str(params.get("scale_name") or "").strip()
        if scale:
            query = query.filter(AssessmentTemplate.scale_name == scale)
        rows = query.order_by(AssessmentRecord.created_at.desc()).limit(20).all()
        return {
            "count": len(rows),
            "assessments": [
                {
                    "scale": t.scale_name,
                    "date": r.created_at.strftime("%Y-%m-%d"),
                    "score": r.total_score,
                    "risk_level": r.risk_level,
                }
                for r, t in rows
            ],
        }

    if tool == "training_stats":
        days = min(int(params.get("days") or 30), 180)
        start_dt = datetime.now() - timedelta(days=days)
        rows = (
            db.query(TrainingRecord, TrainingTemplate)
            .join(TrainingTemplate, TrainingRecord.training_id == TrainingTemplate.id)
            .filter(
                TrainingRecord.user_id == user.id,
                TrainingRecord.completed_at >= start_dt,
            )
            .all()
        )
        by_type: Dict[str, int] = {}
        for r, t in rows:
            by_type[t.training_type] = by_type.get(t.training_type, 0) + 1
        return {
            "count": len(rows),
            "total_duration_minutes": sum(r.duration or 0 for r, _ in rows),
            "by_type": by_type,
        }

    if tool == "recommend_training":
        return _recommend_training(db, user)

    return {"error": f"未知工具 {tool}"}


def _recommend_training(db: Session, user: User) -> Dict[str, Any]:
    """基于最新量表风险与近期数据做规则推荐（可解释、零额外模型成本）。"""
    latest = (
        db.query(AssessmentRecord, AssessmentTemplate)
        .join(AssessmentTemplate, AssessmentRecord.template_id == AssessmentTemplate.id)
        .filter(AssessmentRecord.user_id == user.id)
        .order_by(AssessmentRecord.created_at.desc())
        .first()
    )

    recent_days = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    diaries = (
        db.query(Diary)
        .filter(Diary.user_id == user.id, Diary.diary_date >= recent_days)
        .all()
    )
    diary_text = " ".join(d.content or "" for d in diaries)[:800].lower()
    recent_emotions = set()
    for d in diaries:
        for item in d.emotions or []:
            recent_emotions.add(str(item.get("emotion") or ""))

    picks = []  # (type, name, reason)
    if latest:
        scale, record = latest[1].scale_name, latest[0]
        if record.total_score >= 15:
            picks.append(("mindfulness", "身体扫描冥想", "最新量表显示压力偏高，先做身体觉察降载"))
        elif record.total_score >= 10:
            if scale == "GAD-7":
                picks.append(("breathing", "4-7-8呼吸法(助眠版)", "焦虑分数偏高，用呼吸调节自主神经"))
            else:
                picks.append(("cognitive", "三栏技术(认知重构)", "情绪分数偏高，先识别自动化思维"))

    if any(k in diary_text for k in ("睡", "失眠", "半夜", "困")) or "失眠" in recent_emotions:
        picks.append(("sleep", "刺激控制疗法", "近 14 天日记提到睡眠困扰，重建床与睡眠的连接"))
    if any(k in diary_text for k in ("焦虑", "紧张", "慌", "担心")):
        picks.append(("breathing", "深呼吸放松法", "近两周记录里多次出现紧张/焦虑"))
    if not picks:
        picks.append(("mindfulness", "正念呼吸冥想", "适合作为日常稳定练习，先建立觉察习惯"))
    if len(picks) == 1:
        picks.append(("emotion", "情绪温度计", "配合觉察训练，量化每次练习前后的变化"))

    return {
        "reason": "综合最近一次量表与近 14 天日记给出建议",
        "items": [{"type": t, "name": n, "reason": r} for t, n, r in picks[:3]],
    }


def _parse_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        obj = json.loads(cleaned)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                obj = json.loads(cleaned[start : end + 1])
                return obj if isinstance(obj, dict) else {}
            except Exception:
                pass
    return {}


def _format_result(result: Dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False)[:2000]


async def run_agent(db: Session, user: User, message: str) -> Dict[str, Any]:
    """执行深度探索 Agent。"""
    if _crisis_check(message):
        return {
            "ok": True,
            "response": CRISIS_RESPONSE,
            "crisis": True,
            "tools": [],
            "rounds": 0,
        }

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": AGENT_SYSTEM},
        {"role": "user", "content": message[:2000]},
    ]
    used_tools: List[str] = []
    last_error = ""

    try:
        for step in range(MAX_TOOL_ROUNDS + 1):
            text = await llm_service.chat(
                messages,
                temperature=0.2,
                max_tokens=1000,
                mode="agent",
            )
            obj = _parse_json(text or "")
            final = str(obj.get("final") or "").strip()
            if final:
                return {
                    "ok": True,
                    "response": final,
                    "crisis": False,
                    "tools": used_tools,
                    "rounds": step,
                }

            tool = str(obj.get("tool") or "").strip()
            if tool not in _TOOL_NAMES:
                messages.append(
                    {
                        "role": "user",
                        "content": f"你的输出不是合法 JSON（或工具名无效）：{text[:300]}。请只按协议返回 JSON。",
                    }
                )
                continue

            used_tools.append(tool)
            params = obj.get("params") or {}
            result = await _run_tool(db, user, tool, params)
            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps({"tool": tool, "params": params}, ensure_ascii=False),
                }
            )
            messages.append(
                {"role": "user", "content": f"工具 {tool} 返回：\n{_format_result(result)}"}
            )
    except Exception as e:  # noqa: BLE001 - Agent 失败要降级而不是崩溃
        last_error = str(e)
        logger.warning("Agent 执行失败（降级）: %s", last_error)

    return {
        "ok": True,
        "response": "抱歉，这次深度分析没有顺利完成。"
        "可以换个问法再试一次，或直接到“智能对话”里和我聊聊。",
        "crisis": False,
        "tools": used_tools,
        "rounds": len(used_tools),
        "error": last_error[:200] or None,
    }
