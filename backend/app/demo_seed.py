"""演示数据自动补齐（仅在 SEED_DEMO=true 时启用）。

免费实例没有持久磁盘，容器重启会清空数据；开启后每次启动都会检查并补齐
demo / 123456 账号、近 7 天日记、4 次量表、3 次训练与长期记忆。
"""
import logging
import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .auth import get_password_hash, verify_password
from .models import (
    AssessmentRecord,
    AssessmentTemplate,
    Diary,
    GrowthRecord,
    MemoryFact,
    TrainingRecord,
    TrainingTemplate,
    User,
)

logger = logging.getLogger(__name__)

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "123456"

DIARY_SAMPLES = [
    ("完成了拖了很久的小组汇报，上台前很紧张，深呼吸后顺利讲完。", "平静", 6, 30, "完成了小组汇报", "positive"),
    ("晚上又失眠了，翻来覆去想到明天的面试。", "焦虑", 7, 10, "明天有面试", "negative"),
    ("和朋友去操场跑了三公里，出汗之后心情好多了。", "快乐", 7, 45, "和朋友夜跑", "positive"),
    ("论文进度落后，有点自责，但晚上还是按时睡了。", "压力", 6, 0, "论文进度落后", "negative"),
    ("给家里人打了电话，妈妈说家里一切都好。", "感恩", 6, 20, "和家人通话", "positive"),
    ("下午在图书馆专注了三小时，效率出乎意料地高。", "满足", 7, 40, "图书馆学习", "positive"),
    ("今天什么也没做成，但允许自己休息了一天。", "平静", 5, 25, "允许自己休息", "neutral"),
]

ASSESSMENT_SAMPLES = [
    ("PHQ-9", [1, 1, 1, 1, 1, 1, 2, 2, 2], 12, "中度", 20),
    ("PHQ-9", [0, 0, 1, 1, 0, 1, 1, 1, 1], 6, "轻度", 2),
    ("GAD-7", [1, 2, 1, 2, 1, 1, 2], 10, "中度", 18),
    ("GAD-7", [1, 1, 1, 1, 0, 1, 0], 5, "轻度", 1),
]

TRAINING_SAMPLES = [
    "呼吸练习很放松，做完心率慢下来了。",
    "身体扫描的时候差点睡着，很舒服。",
    "三栏技术帮我把焦虑的想法写清楚了。",
]

MEMORY_SAMPLES = [
    ("用户是大三学生", "identity", 3, 8),
    ("用户正在准备考研复试", "event", 6, 8),
    ("用户喜欢晚上去操场夜跑", "preference", 4, 7),
    ("用户最近常因面试和汇报紧张而失眠", "emotion_pattern", 7, 8),
    ("用户下周三有一场实习面试", "event", 6, 8),
]


def _ensure_user(db: Session) -> User:
    user = db.query(User).filter(User.username == DEMO_USERNAME).first()
    if user is None:
        user = User(
            username=DEMO_USERNAME,
            hashed_password=get_password_hash(DEMO_PASSWORD),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("演示账号已创建：%s", DEMO_USERNAME)
        return user
    # 保证演示账号密码始终为 123456
    if not verify_password(DEMO_PASSWORD, user.hashed_password):
        user.hashed_password = get_password_hash(DEMO_PASSWORD)
        db.commit()
    return user


def _ensure_diaries(db: Session, user: User) -> None:
    today = datetime.now().date()
    existing = {
        row[0]
        for row in db.query(Diary.diary_date)
        .filter(Diary.user_id == user.id)
        .all()
    }
    for offset, (content, emotion, intensity, exercise, trigger, valence) in enumerate(
        DIARY_SAMPLES
    ):
        day = (today - timedelta(days=len(DIARY_SAMPLES) - 1 - offset)).isoformat()
        if day in existing:
            continue
        feedback = {
            "emotion_analysis": {
                "primary_emotion": emotion,
                "emotion_intensity": intensity,
                "emotion_valence": valence,
            },
            "positive_highlights": ["愿意记录本身就是一种自我照顾"],
            "recommendations": [
                {"type": "training", "title": "呼吸放松", "reason": "帮助稳定情绪"}
            ],
        }
        diary = Diary(
            user_id=user.id,
            diary_date=day,
            content=content,
            emotions=[{"emotion": emotion, "intensity": intensity}],
            emotion_trigger=trigger,
            life_dimensions={
                "sleep": 4 if emotion == "平静" else 3,
                "diet": 4,
                "exercise": exercise,
                "social": 3,
                "productivity": 4 if emotion in ("满足", "快乐") else 3,
            },
            template_used="演示数据",
            word_count=len(content),
            writing_duration=8,
            main_emotion=emotion,
            ai_feedback=feedback,
            ai_score=4,
        )
        db.add(diary)
        db.flush()
        growth = (
            db.query(GrowthRecord)
            .filter(GrowthRecord.user_id == user.id, GrowthRecord.record_date == day)
            .first()
        )
        if growth is None:
            db.add(
                GrowthRecord(
                    user_id=user.id,
                    record_date=day,
                    has_diary=True,
                    emotion_valence=valence,
                    main_emotion=emotion,
                    emotion_intensity=intensity,
                    diary_id=diary.id,
                )
            )
    db.commit()


def _ensure_assessments(db: Session, user: User) -> None:
    from .routers.assessment import _ensure_templates_exist

    _ensure_templates_exist(db)
    existing = (
        db.query(AssessmentRecord).filter(AssessmentRecord.user_id == user.id).count()
    )
    if existing >= len(ASSESSMENT_SAMPLES):
        return
    templates = {
        t.scale_name: t
        for t in db.query(AssessmentTemplate).all()
    }
    for scale, answers, score, risk, days_ago in ASSESSMENT_SAMPLES:
        template = templates.get(scale)
        if template is None:
            continue
        created = datetime.now() - timedelta(days=days_ago)
        db.add(
            AssessmentRecord(
                user_id=user.id,
                template_id=template.id,
                answers=answers,
                total_score=score,
                risk_level=risk,
                interpretation=f"{scale} 演示结果：{risk}（总分 {score}），仅作自我观察参考。",
                suggestions="演示数据：建议保持记录习惯，必要时寻求专业支持。",
                created_at=created,
                completed_at=created,
            )
        )
    db.commit()


def _ensure_trainings(db: Session, user: User) -> None:
    from .routers.training import sync_training_templates

    sync_training_templates(db)
    existing = (
        db.query(TrainingRecord).filter(TrainingRecord.user_id == user.id).count()
    )
    if existing >= len(TRAINING_SAMPLES):
        return
    templates = db.query(TrainingTemplate).limit(len(TRAINING_SAMPLES)).all()
    for index, (template, comment) in enumerate(zip(templates, TRAINING_SAMPLES)):
        completed = datetime.now() - timedelta(days=index * 2)
        db.add(
            TrainingRecord(
                user_id=user.id,
                training_id=template.id,
                duration=4 + index,
                feedback={
                    "rating": 5,
                    "comment": comment,
                    "ai_summary": comment,
                    "step_logs": [
                        {"step_index": 0, "kind": "read", "seconds_spent": 20},
                        {"step_index": 1, "kind": "pattern", "seconds_spent": 120},
                    ],
                },
                completed_at=completed,
                created_at=completed,
            )
        )
    db.commit()


def _ensure_memories(db: Session, user: User) -> None:
    existing = db.query(MemoryFact).filter(MemoryFact.user_id == user.id).count()
    if existing:
        return
    now = datetime.now()
    for index, (fact, mem_type, weight, confidence) in enumerate(MEMORY_SAMPLES):
        db.add(
            MemoryFact(
                user_id=user.id,
                fact=fact,
                memory_type=mem_type,
                source="chat",
                confidence=confidence,
                emotional_weight=weight,
                is_high_emotional=mem_type == "crisis_moment" or weight >= 8,
                is_active=True,
                created_at=now - timedelta(days=index),
                last_referenced_at=now - timedelta(days=index),
            )
        )
    db.commit()


def ensure_demo_data(db: Session) -> None:
    if os.getenv("SEED_DEMO", "").lower() not in {"1", "true", "yes"}:
        return
    try:
        user = _ensure_user(db)
        _ensure_diaries(db, user)
        _ensure_assessments(db, user)
        _ensure_trainings(db, user)
        _ensure_memories(db, user)
        logger.info("演示数据检查完成")
    except Exception as exc:  # noqa: BLE001 - 演示数据失败不应阻断启动
        logger.warning("演示数据补齐失败（跳过）: %s", exc)
        db.rollback()
