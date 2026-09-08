"""数据分析路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from datetime import datetime, timedelta
from ..database import get_db
from ..models import (
    User,
    Diary,
    AssessmentRecord,
    AssessmentTemplate,
    TrainingRecord,
    GrowthRecord,
    LlmCallStats,
)
from ..auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取仪表盘概览数据"""
    # 计算近30天数据
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    # 日记统计
    diary_count = db.query(Diary).filter(
        Diary.user_id == current_user.id,
        Diary.diary_date >= thirty_days_ago
    ).count()
    
    # 评估统计
    assessment_count = db.query(AssessmentRecord).filter(
        AssessmentRecord.user_id == current_user.id,
        AssessmentRecord.created_at >= thirty_days_ago
    ).count()
    
    # 训练统计
    training_count = db.query(TrainingRecord).filter(
        TrainingRecord.user_id == current_user.id,
        TrainingRecord.completed_at >= thirty_days_ago
    ).count()
    
    training_duration = db.query(func.sum(TrainingRecord.duration)).filter(
        TrainingRecord.user_id == current_user.id,
        TrainingRecord.completed_at >= thirty_days_ago
    ).scalar() or 0
    
    # 成长记录统计（本年度）
    current_year = datetime.now().year
    start_of_year = f"{current_year}-01-01"
    
    growth_stats = db.query(GrowthRecord).filter(
        GrowthRecord.user_id == current_user.id,
        GrowthRecord.record_date >= start_of_year,
        GrowthRecord.has_diary == True
    ).all()
    
    total_diaries = len(growth_stats)
    winged_hearts = sum(1 for r in growth_stats if r.emotion_valence == "positive")
    
    # 计算连续天数
    current_streak = 0
    check_date = datetime.now()
    
    while True:
        date_str = check_date.strftime("%Y-%m-%d")
        record = next((r for r in growth_stats if r.record_date == date_str), None)
        if record and record.has_diary:
            current_streak += 1
            check_date -= timedelta(days=1)
        else:
            break
    
    return {
        "diary_count_30d": diary_count,
        "assessment_count_30d": assessment_count,
        "training_count_30d": training_count,
        "training_duration_30d": training_duration,
        "total_diaries_year": total_diaries,
        "winged_hearts_year": winged_hearts,
        "current_streak": current_streak,
        "positive_ratio": round(winged_hearts / total_diaries * 100) if total_diaries > 0 else 0
    }


@router.get("/emotion-trends")
async def get_emotion_trends(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取情绪趋势数据"""
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    diaries = db.query(Diary).filter(
        Diary.user_id == current_user.id,
        Diary.diary_date >= start_date
    ).order_by(Diary.diary_date).all()
    
    # 构建趋势数据
    trends = []
    for diary in diaries:
        # 计算情绪得分（基于AI分析）
        emotion_score = 5  # 默认中性
        
        if diary.ai_feedback:
            emotion_analysis = diary.ai_feedback.get("emotion_analysis", {})
            valence = diary.ai_feedback.get("emotion_valence", "neutral")
            intensity = emotion_analysis.get("emotion_intensity", 5)
            
            # 根据效价和强度计算得分 (0-10)
            if valence == "positive":
                emotion_score = 5 + (intensity * 0.5)
            elif valence == "negative":
                emotion_score = 5 - (intensity * 0.5)
            else:
                emotion_score = 5
        
        trends.append({
            "date": diary.diary_date,
            "emotion": diary.main_emotion,
            "score": emotion_score,
            "word_count": diary.word_count
        })
    
    return trends


@router.get("/assessment-trends")
async def get_assessment_trends(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取评估趋势数据"""
    records = db.query(AssessmentRecord).filter(
        AssessmentRecord.user_id == current_user.id
    ).order_by(AssessmentRecord.created_at).all()
    
    # 按量表分组
    trends_by_scale = {}
    
    for record in records:
        scale_name = record.template.scale_name if record.template else "Unknown"
        
        if scale_name not in trends_by_scale:
            trends_by_scale[scale_name] = []
        
        trends_by_scale[scale_name].append({
            "date": record.created_at.strftime("%Y-%m-%d"),
            "score": record.total_score,
            "risk_level": record.risk_level
        })
    
    return trends_by_scale


@router.get("/training-stats")
async def get_training_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取训练统计数据"""
    records = db.query(TrainingRecord).filter(
        TrainingRecord.user_id == current_user.id
    ).all()
    
    # 按训练类型统计
    stats_by_type = {}
    
    for record in records:
        training_type = record.template.training_type if record.template else "Unknown"
        training_name = record.template.training_name if record.template else "Unknown"
        
        if training_type not in stats_by_type:
            stats_by_type[training_type] = {
                "name": training_name,
                "count": 0,
                "total_duration": 0
            }
        
        stats_by_type[training_type]["count"] += 1
        stats_by_type[training_type]["total_duration"] += record.duration
    
    return stats_by_type


@router.get("/emotion-distribution")
async def get_emotion_distribution(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取情绪分布数据"""
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    diaries = db.query(Diary).filter(
        Diary.user_id == current_user.id,
        Diary.diary_date >= start_date,
        Diary.main_emotion.isnot(None)
    ).all()
    
    # 统计各情绪出现次数
    emotion_counts = {}
    
    for diary in diaries:
        emotion = diary.main_emotion
        if emotion:
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
    
    # 转换为列表格式
    distribution = [
        {"emotion": emotion, "count": count}
        for emotion, count in emotion_counts.items()
    ]
    
    # 按次数排序
    distribution.sort(key=lambda x: x["count"], reverse=True)
    
    return distribution


@router.get("/outcome")
async def get_outcome_metrics(
    days: int = 28,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """效果度量：PHQ-9/GAD-7 分数与风险迁移 + 日记情绪趋势。

    仅供用户自我观察的参考趋势，不构成诊断或医疗建议。
    """
    start_dt = datetime.now() - timedelta(days=max(days, 1))
    start_date = start_dt.strftime("%Y-%m-%d")

    risk_order = {
        "正常": 0,
        "normal": 0,
        "轻度": 1,
        "mild": 1,
        "中度": 2,
        "moderate": 2,
        "重度": 3,
        "severe": 3,
    }

    # 1) 量表趋势（每个量表取窗口内第一次与最后一次）
    scale_results = []
    for scale_name in ("PHQ-9", "GAD-7"):
        records = (
            db.query(AssessmentRecord)
            .join(AssessmentTemplate, AssessmentRecord.template_id == AssessmentTemplate.id)
            .filter(
                AssessmentRecord.user_id == current_user.id,
                AssessmentTemplate.scale_name == scale_name,
                AssessmentRecord.created_at >= start_dt,
            )
            .order_by(AssessmentRecord.created_at.asc())
            .all()
        )
        if len(records) < 1:
            scale_results.append(
                {
                    "scale_name": scale_name,
                    "count": 0,
                    "first": None,
                    "latest": None,
                    "delta": None,
                    "risk_transition": None,
                    "improved": None,
                }
            )
            continue

        first, latest = records[0], records[-1]
        delta = first.total_score - latest.total_score  # 正数 = 分数下降
        old_level = risk_order.get(first.risk_level, -1)
        new_level = risk_order.get(latest.risk_level, -1)
        if old_level == -1 or new_level == -1:
            risk_transition = None
        elif new_level < old_level:
            risk_transition = "improved"
        elif new_level > old_level:
            risk_transition = "worsened"
        else:
            risk_transition = "stable"

        improved = None
        if len(records) >= 2:
            improved = delta >= 3 or (
                risk_transition == "improved" and delta > 0
            )

        scale_results.append(
            {
                "scale_name": scale_name,
                "count": len(records),
                "first": {
                    "date": first.created_at.strftime("%Y-%m-%d"),
                    "score": first.total_score,
                    "risk_level": first.risk_level,
                },
                "latest": {
                    "date": latest.created_at.strftime("%Y-%m-%d"),
                    "score": latest.total_score,
                    "risk_level": latest.risk_level,
                },
                "delta": delta,
                "risk_transition": risk_transition,
                "improved": improved,
            }
        )

    # 2) 日记情绪趋势（0-10 得分，逐日平均 + 线性斜率）
    diaries = (
        db.query(Diary)
        .filter(
            Diary.user_id == current_user.id,
            Diary.diary_date >= start_date,
        )
        .order_by(Diary.diary_date.asc())
        .all()
    )

    def _emotion_score(diary: Diary) -> float:
        feedback = diary.ai_feedback or {}
        analysis = feedback.get("emotion_analysis") or {}
        valence = (
            analysis.get("emotion_valence")
            or feedback.get("emotion_valence")
            or "neutral"
        )
        intensity = int(analysis.get("emotion_intensity") or feedback.get("emotion_intensity") or 5)
        if valence == "positive":
            return 5 + intensity * 0.5
        if valence == "negative":
            return 5 - intensity * 0.5
        return 5.0

    daily = {}
    for diary in diaries:
        daily.setdefault(diary.diary_date, []).append(_emotion_score(diary))

    emotion_points = [
        {"date": d, "score": round(sum(scores) / len(scores), 2)}
        for d, scores in sorted(daily.items())
    ]

    emotion = {
        "count": len(emotion_points),
        "first": emotion_points[0] if emotion_points else None,
        "latest": emotion_points[-1] if emotion_points else None,
        "slope": None,
    }
    if len(emotion_points) >= 2:
        xs = list(range(len(emotion_points)))
        ys = [p["score"] for p in emotion_points]
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / max(
            sum((x - mean_x) ** 2 for x in xs), 1e-9
        )
        emotion["slope"] = round(slope, 4)

    # 3) 汇总文案（仅作参考）
    summary_parts = []
    meaningful = [s for s in scale_results if s["count"] >= 1 and s["improved"] is not None]
    improved_scales = [s for s in meaningful if s["improved"]]
    worsened_scales = [s for s in meaningful if not s["improved"]]
    if improved_scales:
        summary_parts.append(
            "量表趋势提示改善：" + "、".join(s["scale_name"] for s in improved_scales)
        )
    if worsened_scales:
        summary_parts.append(
            "量表趋势提示需要关注：" + "、".join(s["scale_name"] for s in worsened_scales)
        )
    if not improved_scales and not worsened_scales:
        summary_parts.append("当前窗口内量表数据不足，暂时无法给出可靠趋势判断")
    if emotion["slope"] is not None and emotion["count"] >= 3:
        if emotion["slope"] > 0.05:
            summary_parts.append("日记情绪整体呈上升趋势")
        elif emotion["slope"] < -0.05:
            summary_parts.append("日记情绪整体呈下降趋势，建议关注并及时寻求支持")
        else:
            summary_parts.append("日记情绪整体平稳")
    summary_text = "；".join(summary_parts) + "。以上仅作自我观察参考，不构成诊断。"

    return {
        "days": days,
        "scales": scale_results,
        "emotion": emotion,
        "summary_text": summary_text,
    }


@router.get("/cache-stats")
async def get_cache_stats(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """LLM Prompt Cache 观测：总调用、缓存命中 token 与命中率（按模式分组）。"""
    start_dt = datetime.now() - timedelta(days=max(days, 1))
    rows = (
        db.query(LlmCallStats)
        .filter(LlmCallStats.created_at >= start_dt)
        .order_by(LlmCallStats.created_at.desc())
        .all()
    )

    by_mode: Dict[str, Dict[str, int]] = {}
    for row in rows:
        bucket = by_mode.setdefault(
            row.mode or "generic",
            {"calls": 0, "prompt_tokens": 0, "cached_tokens": 0, "total_tokens": 0},
        )
        bucket["calls"] += 1
        bucket["prompt_tokens"] += row.prompt_tokens or 0
        bucket["cached_tokens"] += row.cached_tokens or 0
        bucket["total_tokens"] += row.total_tokens or 0

    total_prompt = sum(b["prompt_tokens"] for b in by_mode.values())
    total_cached = sum(b["cached_tokens"] for b in by_mode.values())
    return {
        "days": days,
        "total_calls": len(rows),
        "total_prompt_tokens": total_prompt,
        "total_cached_tokens": total_cached,
        "cache_hit_ratio": round(total_cached / total_prompt * 100, 2) if total_prompt else 0.0,
        "by_mode": by_mode,
    }


@router.get("/weekly-report")
async def get_weekly_report(
    days: int = 7,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """二期：综合自动周报（本周数据 + AI 叙事总结）。"""
    from ..report_service import generate_weekly_report

    return await generate_weekly_report(db, current_user, max(days, 1))
