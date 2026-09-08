"""二期：综合自动周报。

数据全部来自本机数据库（日记/量表/训练/记忆），再由模型生成叙事性总结；
输出仅作自我观察参考，不构成诊断。
"""
import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict

from sqlalchemy.orm import Session

from .llm_service import llm_service
from .memory_service import list_memories
from .models import (
    AssessmentRecord,
    AssessmentTemplate,
    Diary,
    TrainingRecord,
    TrainingTemplate,
    User,
)
from .safety import PROMPT_CORE

logger = logging.getLogger(__name__)

WEEKLY_SYSTEM = (
    PROMPT_CORE
    + """

【综合周报生成】
请根据下方【本周数据】为用户写一份 7-9 句话的周报，结构为：
1. 一句本周整体状态判断（数据不足时如实说明）；
2. 2-3 句日记/情绪层面的观察（引用具体情绪或趋势，不编造）；
3. 1-2 句量表或训练层面的变化（若本周无数据则改为鼓励建立记录习惯）；
4. 一句下周可执行的小建议。
语气温暖克制，不要下诊断，不要使用“病情”“患者”等词。直接输出周报正文，不要标题。"""
)


def _gather_stats(db: Session, user: User, days: int) -> Dict[str, Any]:
    start_dt = datetime.now() - timedelta(days=max(days, 1))
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    diaries = (
        db.query(Diary)
        .filter(Diary.user_id == user.id, Diary.diary_date >= start_date)
        .order_by(Diary.diary_date.asc())
        .all()
    )
    emotions = Counter()
    emotion_days = 0
    for d in diaries:
        if d.main_emotion:
            emotions[d.main_emotion] += 1
        for item in d.emotions or []:
            name = str(item.get("emotion") or "").strip()
            if name:
                emotions[name] += 1
        if d.content and d.content.strip():
            emotion_days += 1

    assessments = (
        db.query(AssessmentRecord, AssessmentTemplate)
        .join(AssessmentTemplate, AssessmentRecord.template_id == AssessmentTemplate.id)
        .filter(
            AssessmentRecord.user_id == user.id,
            AssessmentRecord.created_at >= start_dt,
        )
        .order_by(AssessmentRecord.created_at.asc())
        .all()
    )
    scale_rows: Dict[str, list] = {}
    for r, t in assessments:
        scale_rows.setdefault(t.scale_name, []).append(
            {
                "date": r.created_at.strftime("%Y-%m-%d"),
                "score": r.total_score,
                "risk_level": r.risk_level,
            }
        )

    trainings = (
        db.query(TrainingRecord, TrainingTemplate)
        .join(TrainingTemplate, TrainingRecord.training_id == TrainingTemplate.id)
        .filter(
            TrainingRecord.user_id == user.id,
            TrainingRecord.completed_at >= start_dt,
        )
        .all()
    )
    train_by_name = Counter()
    train_minutes = 0
    for r, t in trainings:
        train_by_name[t.training_name] += 1
        train_minutes += r.duration or 0

    all_memories = list_memories(db, user.id, include_inactive=False)
    new_memories = [
        m for m in all_memories if m["created_at"][:10] >= start_date
    ]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "diary": {
            "count": len(diaries),
            "emotion_days": emotion_days,
            "top_emotions": [{"emotion": e, "count": c} for e, c in emotions.most_common(5)],
        },
        "assessments": {
            "total": len(assessments),
            "scales": {
                name: {
                    "count": len(rows),
                    "first": rows[0],
                    "latest": rows[-1],
                    "delta": rows[-1]["score"] - rows[0]["score"]
                    if len(rows) >= 2
                    else None,
                }
                for name, rows in scale_rows.items()
            },
        },
        "training": {
            "count": len(trainings),
            "minutes": train_minutes,
            "top": [{"name": n, "count": c} for n, c in train_by_name.most_common(4)],
        },
        "new_memories_count": len(new_memories),
    }


async def generate_weekly_report(db: Session, user: User, days: int = 7) -> Dict[str, Any]:
    """生成一周综合数据 + AI 叙事周报。"""
    stats = _gather_stats(db, user, days)
    context = (
        "【本周数据】\n"
        + f"统计区间：{stats['start_date']} 至 {stats['end_date']}\n"
        + f"日记：共 {stats['diary']['count']} 篇，有内容记录 {stats['diary']['emotion_days']} 天；"
        + (
            "高频情绪：" + "、".join(
                f"{i['emotion']}({i['count']}次)" for i in stats["diary"]["top_emotions"][:5]
            )
            if stats["diary"]["top_emotions"]
            else "暂无"
        )
        + "\n"
        + f"量表：本周 {stats['assessments']['total']} 次；"
        + (
            "；".join(
                f"{name} 最新 {s['latest']['score']} 分（{s['latest']['risk_level']}）"
                + (f"，较上次变化 {s['delta']:+d} 分" if s["delta"] is not None else "")
                for name, s in stats["assessments"]["scales"].items()
            )
            if stats["assessments"]["scales"]
            else "暂无"
        )
        + "\n"
        + f"训练：共 {stats['training']['count']} 次、约 {stats['training']['minutes']} 分钟；"
        + (
            "；".join(f"{i['name']}×{i['count']}" for i in stats["training"]["top"])
            if stats["training"]["top"]
            else "暂无"
        )
        + "\n"
        + f"本周新增长期记忆：{stats['new_memories_count']} 条"
    )

    narrative = ""
    try:
        narrative = (
            await llm_service.chat(
                [
                    {"role": "system", "content": WEEKLY_SYSTEM},
                    {"role": "user", "content": context + "\n\n请生成周报正文。"},
                ],
                temperature=0.5,
                max_tokens=900,
                mode="weekly_report",
            )
        ).strip()
    except Exception as e:  # noqa: BLE001 - 模型失败也要返回数据部分
        logger.warning("周报生成失败（仅返回数据）: %s", e)

    return {
        "days": days,
        "stats": stats,
        "narrative": narrative or "本周数据记录较少，暂时生成不了可靠的文字总结。继续写日记、做量表和训练，下周会有更完整的周报。",
        "disclaimer": "仅供自我观察参考，不构成医疗建议。",
    }
