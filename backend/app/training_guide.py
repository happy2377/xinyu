"""训练引导服务：关键节点 AI 介入（开训 / 步骤反馈 / 结束总结）。

设计约束：
- 系统提示为固定常量（COMMON_CORE + 本阶段固定段），动态内容（记忆、步骤日志、用户输入）
  一律放在最后一条 user 消息里，便于 prompt cache 命中；
- 危机关键词命中时直接返回固定危机话术，不调用模型；
- 任何模型失败都静默降级，不阻断纯计时+语音训练。
"""
import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from .llm_service import llm_service
from .memory_service import extract_facts_from_text, retrieve_memories
from .models import TrainingTemplate, User
from .perception_planning import PerceptionPlanningModule
from .safety import CRISIS_RESPONSE, PROMPT_CORE

logger = logging.getLogger(__name__)


_STAGE_SYSTEM = {
    "intro": (
        PROMPT_CORE
        + "\n\n"
        + """【开训引导】
用户即将开始一次自助心理训练。请结合下方【训练信息】与【用户记忆】，用 3-5 句话：
1. 说明这个训练此刻适合哪种状态，并结合记忆点题（例如“你最近提到入睡困难”），不要展开无关隐私；
2. 说明节奏：接下来会由语音逐步播报，跟着做、不用记步骤；
3. 给一句温和的鼓励。
不要提“记忆系统”或“AI 记忆”；不要编造记忆中没有的信息；直接输出给用户的话，不要任何标题。"""
    ),
    "step_feedback": (
        PROMPT_CORE
        + "\n\n"
        + """【训练步骤即时反馈】
用户在认知/情绪训练的某个输入步骤写下了内容。请给出 2-4 句反馈：
1. 先肯定“愿意写下来”这个行为本身；
2. 对内容做温和、不评判的回应：认知类可给一个苏格拉底式追问（如“如果朋友这样想，你会怎么劝他？”），
   情绪类帮助命名/确认感受；
3. 用一句话引导用户进入下一步，不替用户下结论。
禁止诊断、禁止建议用药/停药、禁止长篇大论。直接输出给用户的话。"""
    ),
    "summary": (
        PROMPT_CORE
        + "\n\n"
        + """【训练结束总结】
用户刚完成一次自助训练。请用 3-5 句话：
1. 肯定完成；
2. 结合下方【本场记录】中的前后情绪评分或输入内容，克制地描述变化（用“看起来”“有一点”等措辞，不夸大）；
3. 给一个接下来 24 小时内可执行的小建议；
4. 若有需要，提示可再做量表或与专业心理师沟通，不替代专业意见。
若记录中出现自伤/危机信息，优先表达关心并建议立即求助。直接输出给用户的话。"""
    ),
}

_PERCEPTION = PerceptionPlanningModule()


def _normalize_steps(template: TrainingTemplate) -> List[dict]:
    """兼容旧版纯字符串步骤；新版为对象数组。"""
    raw = template.steps or []
    result = []
    for s in raw:
        if isinstance(s, dict):
            result.append(dict(s))
        else:
            result.append({"kind": "read", "text": str(s), "seconds": 20})
    return result


def _log_line(index: int, log: dict, step_text: str = "") -> str:
    parts = [f"[{index + 1}]"]
    if step_text:
        parts.append(step_text[:80])
    user_input = (log.get("input") or "").strip()
    if user_input:
        parts.append(f"用户记录：{user_input[:120]}")
    seconds = log.get("seconds_spent") or log.get("seconds")
    if seconds:
        parts.append(f"耗时 {seconds}s")
    if log.get("value") is not None and str(log.get("value")) != "":
        parts.append(f"评分 {log['value']}")
    return "；".join(parts)


def _resolve_step_text(log: dict, steps: List[dict]) -> str:
    idx = log.get("step_index")
    if isinstance(idx, int) and 0 <= idx < len(steps):
        return steps[idx].get("text", "")[:80]
    return ""


def _memory_lines(memories: List[dict]) -> str:
    if not memories:
        return "（暂无）"
    return "\n".join(
        f"- [{m['created_at'][:10]} · {m['type']}] {m['fact']}" for m in memories
    )


async def training_assist(
    db: Session,
    user: User,
    template: TrainingTemplate,
    stage: str,
    step_index: Optional[int] = None,
    user_input: str = "",
    step_logs: Optional[List[dict]] = None,
) -> Dict:
    """执行一次训练 AI 引导；返回 {ok, content, crisis}。"""
    stage = stage or "intro"
    logs = step_logs or []
    steps = _normalize_steps(template)

    # 1) 危机优先：任何入口出现危机信号都返回固定话术
    check_texts = [user_input] + [
        str(log.get("input") or "") for log in logs if log.get("input")
    ]
    if any(_PERCEPTION.detect_crisis(t) for t in check_texts):
        return {"ok": True, "content": CRISIS_RESPONSE, "crisis": True}

    try:
        # 2) 检索相关长期记忆（top_k 固定，排序稳定，利于缓存与个性化）
        memory_query_parts = [
            template.training_name,
            template.description[:80],
        ]
        if stage == "step_feedback" and isinstance(step_index, int) and 0 <= step_index < len(steps):
            memory_query_parts.append(steps[step_index].get("text", ""))
        if user_input:
            memory_query_parts.append(user_input[:120])
        memories = await retrieve_memories(
            db, user, " ".join(memory_query_parts), top_k=3
        )

        # 3) 组装动态上下文（放最后一条 user 消息）
        info_lines = [
            f"训练：{template.training_name}",
            f"类型：{template.training_type}",
            f"说明：{template.description}",
        ]
        if stage == "step_feedback" and isinstance(step_index, int) and 0 <= step_index < len(steps):
            info_lines.append(f"当前步骤：{steps[step_index].get('text', '')}")

        parts = [
            "【训练信息】\n" + "\n".join(info_lines),
            "【用户记忆（仅用于个性化，不向用户提及来源）】\n" + _memory_lines(memories),
        ]
        if stage == "summary":
            recent_logs = logs[-12:]
            if recent_logs:
                parts.append(
                    "【本场记录】\n"
                    + "\n".join(
                        _log_line(i, log, _resolve_step_text(log, steps))
                        for i, log in enumerate(recent_logs)
                        if isinstance(log, dict)
                    )
                )
        elif logs:
            parts.append(
                "【本场已完成步骤（最近的几条）】\n"
                + "\n".join(
                    _log_line(i, log, _resolve_step_text(log, steps))
                    for i, log in enumerate(logs[-4:])
                    if isinstance(log, dict)
                )
            )

        if user_input:
            parts.append(f"【用户本步输入】\n{user_input[:800]}")
        parts.append("请直接输出给用户的话，不要输出任何标题或说明文字。")

        content = await llm_service.chat(
            [
                {"role": "system", "content": _STAGE_SYSTEM.get(stage, _STAGE_SYSTEM["intro"])},
                {"role": "user", "content": "\n\n".join(parts)},
            ],
            temperature=0.6,
            max_tokens=600,
            mode=f"training_{stage}",
        )
        content = (content or "").strip()
    except Exception as e:
        logger.warning("训练 AI 引导失败（stage=%s，已降级）: %s", stage, e)
        return {"ok": False, "content": "", "crisis": False, "error": str(e)[:200]}

    # 4) 总结后顺手把本场信息写入长期记忆（失败不影响主流程）
    if stage == "summary" and content:
        try:
            await _extract_training_memory(db, user, template, logs, content)
        except Exception as e:  # pragma: no cover
            logger.warning("训练记忆抽取失败（跳过）: %s", e)

    return {"ok": True, "content": content, "crisis": False}


async def _extract_training_memory(
    db: Session,
    user: User,
    template: TrainingTemplate,
    logs: List[dict],
    summary: str,
) -> None:
    """把训练中的有效输入与总结提炼为长期记忆（source=training）。"""
    record_lines = []
    for i, log in enumerate(logs):
        if not isinstance(log, dict):
            continue
        value = (log.get("input") or "").strip()
        if value:
            record_lines.append(f"第{i + 1}步：{value[:300]}")
    if not record_lines and not summary:
        return
    text = (
        f"用户完成了训练《{template.training_name}》。\n"
        + ("\n".join(record_lines[:6]) if record_lines else "（本次无文字记录）")
        + f"\nAI 总结：{summary[:600]}"
    )
    await extract_facts_from_text(db, user, text, "training")
