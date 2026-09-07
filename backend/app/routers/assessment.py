"""心理评估系统路由"""
import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List
from ..database import get_db
from ..models import User, AssessmentTemplate, AssessmentRecord, OutcomeSnapshot
from ..schemas import (
    AssessmentTemplateListItem, 
    AssessmentTemplateDetail,
    AssessmentSubmitRequest,
    AssessmentResultResponse,
    AssessmentHistoryItem
)
from ..auth import get_current_user
from ..memory_service import extract_facts_from_text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assessments", tags=["心理评估"])


# 硬编码评估量表模板数据
ASSESSMENT_TEMPLATES = [
    # PHQ-9 抑郁量表
    {
        "scale_name": "PHQ-9",
        "display_name": "患者健康问卷-9 (PHQ-9)",
        "category": "depression",
        "description": "PHQ-9是世界卫生组织推荐的抑郁症状筛查工具，包含9个问题，评估过去两周的抑郁症状严重程度。",
        "question_count": 9,
        "estimated_time": 3,
        "icon": "😔",
        "questions": [
            {
                "id": 1,
                "text": "做事时提不起劲或没有兴趣",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 2,
                "text": "感到心情低落、沮丧或绝望",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 3,
                "text": "入睡困难、睡不安稳或睡眠过多",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 4,
                "text": "感觉疲倦或没有活力",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 5,
                "text": "食欲不振或吃太多",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 6,
                "text": "觉得自己很糟，或觉得自己很失败，或让自己或家人失望",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 7,
                "text": "对事物专注有困难，例如阅读报纸或看电视时",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 8,
                "text": "动作或说话速度缓慢到别人已经注意到？或正好相反——烦躁或坐立不安、动来动去的情况更胜于平常",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 9,
                "text": "有不如死掉或用某种方式伤害自己的念头",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            }
        ],
        "scoring_rules": {
            "method": "sum",
            "max_score": 27
        },
        "interpretation": [
            {
                "range": [0, 4],
                "level": "正常",
                "interpretation": "您目前的心理状态良好，没有明显的抑郁症状。",
                "suggestion": "建议保持积极的生活方式，继续关注自己的心理健康。如有需要，可以随时与心翼聊天。"
            },
            {
                "range": [5, 9],
                "level": "轻度",
                "interpretation": "您可能存在轻度抑郁症状。这些症状可能会影响您的日常生活，但通过自我调节和支持可以改善。",
                "suggestion": "建议：1) 与信任的朋友或家人交流感受；2) 保持规律作息和适度运动；3) 尝试心翼的呼吸训练和情绪日记功能；4) 如果症状持续，建议咨询专业心理咨询师。"
            },
            {
                "range": [10, 14],
                "level": "中度",
                "interpretation": "您存在中度抑郁症状，这些症状可能已经对您的生活、工作或学习造成一定影响。",
                "suggestion": "强烈建议：1) 尽快预约专业心理咨询或心理治疗；2) 与家人或朋友分享您的感受；3) 使用心翼的训练功能进行辅助调节；4) 保持健康的生活方式。如需帮助，可拨打心理援助热线：400-161-9995"
            },
            {
                "range": [15, 27],
                "level": "重度",
                "interpretation": "您存在重度抑郁症状，这已经严重影响您的日常生活。请务必重视并寻求专业帮助。",
                "suggestion": "⚠️ 紧急建议：1) 立即寻求专业心理/精神科医生的帮助；2) 不要独自承受，告诉信任的人；3) 24小时心理危机干预热线：400-161-9995 或 010-82951332；4) 如有自伤或自杀念头，请立即拨打110或前往最近的医院急诊。"
            }
        ]
    },
    
    # GAD-7 焦虑量表
    {
        "scale_name": "GAD-7",
        "display_name": "广泛性焦虑量表-7 (GAD-7)",
        "category": "anxiety",
        "description": "GAD-7是筛查广泛性焦虑障碍的标准工具，评估过去两周的焦虑症状严重程度。",
        "question_count": 7,
        "estimated_time": 2,
        "icon": "😰",
        "questions": [
            {
                "id": 1,
                "text": "感觉紧张、焦虑或急切",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 2,
                "text": "无法停止或控制担忧",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 3,
                "text": "对各种各样的事情担忧过多",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 4,
                "text": "很难放松下来",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 5,
                "text": "由于不安而无法静坐",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 6,
                "text": "变得容易烦恼或急躁",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            },
            {
                "id": 7,
                "text": "感到似乎将有可怕的事情发生而害怕",
                "options": [
                    {"value": 0, "label": "完全不会"},
                    {"value": 1, "label": "好几天"},
                    {"value": 2, "label": "一半以上的天数"},
                    {"value": 3, "label": "几乎每天"}
                ]
            }
        ],
        "scoring_rules": {
            "method": "sum",
            "max_score": 21
        },
        "interpretation": [
            {
                "range": [0, 4],
                "level": "正常",
                "interpretation": "您目前的焦虑水平在正常范围内，心理状态良好。",
                "suggestion": "建议保持健康的生活方式，适度运动，保证充足睡眠。如遇到压力事件，可以使用心翼的呼吸训练功能。"
            },
            {
                "range": [5, 9],
                "level": "轻度",
                "interpretation": "您存在轻度焦虑症状，这可能影响您的日常生活质量。",
                "suggestion": "建议：1) 学习放松技巧（如深呼吸、正念冥想）；2) 识别并挑战焦虑思维；3) 使用心翼的焦虑训练模块；4) 保持规律作息和适度运动；5) 如症状持续，考虑咨询心理专业人士。"
            },
            {
                "range": [10, 14],
                "level": "中度",
                "interpretation": "您存在中度焦虑症状，这已经对您的生活造成明显影响。",
                "suggestion": "强烈建议：1) 寻求专业心理咨询或治疗；2) 学习并实践放松技术；3) 减少咖啡因摄入；4) 使用心翼的训练功能辅助调节；5) 与信任的人分享感受。心理援助热线：400-161-9995"
            },
            {
                "range": [15, 21],
                "level": "重度",
                "interpretation": "您存在重度焦虑症状，严重影响日常生活。请务必寻求专业帮助。",
                "suggestion": "⚠️ 紧急建议：1) 立即预约心理医生或精神科医生；2) 考虑药物治疗配合心理治疗；3) 避免自我孤立，寻求支持；4) 24小时心理援助热线：400-161-9995 或 010-82951332。"
            }
        ]
    },
    
    # PSS-10 压力量表
    {
        "scale_name": "PSS-10",
        "display_name": "知觉压力量表-10 (PSS-10)",
        "category": "stress",
        "description": "PSS-10评估个体在过去一个月内主观感受到的压力水平，帮助了解您对生活中不可预测性和不可控事件的感知。",
        "question_count": 10,
        "estimated_time": 3,
        "icon": "😫",
        "questions": [
            {
                "id": 1,
                "text": "在过去一个月中，您有多经常因为发生意想不到的事情而感到心烦意乱？",
                "options": [
                    {"value": 0, "label": "从不"},
                    {"value": 1, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 3, "label": "相当常"},
                    {"value": 4, "label": "非常常"}
                ]
            },
            {
                "id": 2,
                "text": "在过去一个月中，您有多经常觉得无法控制生活中重要的事情？",
                "options": [
                    {"value": 0, "label": "从不"},
                    {"value": 1, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 3, "label": "相当常"},
                    {"value": 4, "label": "非常常"}
                ]
            },
            {
                "id": 3,
                "text": "在过去一个月中，您有多经常感到紧张和压力？",
                "options": [
                    {"value": 0, "label": "从不"},
                    {"value": 1, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 3, "label": "相当常"},
                    {"value": 4, "label": "非常常"}
                ]
            },
            {
                "id": 4,
                "text": "在过去一个月中，您有多自信能够处理自己的私事？（反向计分）",
                "options": [
                    {"value": 4, "label": "从不"},
                    {"value": 3, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 1, "label": "相当常"},
                    {"value": 0, "label": "非常常"}
                ]
            },
            {
                "id": 5,
                "text": "在过去一个月中，您有多经常觉得事情按您的意愿发展？（反向计分）",
                "options": [
                    {"value": 4, "label": "从不"},
                    {"value": 3, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 1, "label": "相当常"},
                    {"value": 0, "label": "非常常"}
                ]
            },
            {
                "id": 6,
                "text": "在过去一个月中，您有多经常发现自己无法处理所有必须做的事情？",
                "options": [
                    {"value": 0, "label": "从不"},
                    {"value": 1, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 3, "label": "相当常"},
                    {"value": 4, "label": "非常常"}
                ]
            },
            {
                "id": 7,
                "text": "在过去一个月中，您有多经常能够控制生活中的烦心事？（反向计分）",
                "options": [
                    {"value": 4, "label": "从不"},
                    {"value": 3, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 1, "label": "相当常"},
                    {"value": 0, "label": "非常常"}
                ]
            },
            {
                "id": 8,
                "text": "在过去一个月中，您有多经常觉得一切都在掌控之中？（反向计分）",
                "options": [
                    {"value": 4, "label": "从不"},
                    {"value": 3, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 1, "label": "相当常"},
                    {"value": 0, "label": "非常常"}
                ]
            },
            {
                "id": 9,
                "text": "在过去一个月中，您有多经常因为事情不在您的控制范围内而生气？",
                "options": [
                    {"value": 0, "label": "从不"},
                    {"value": 1, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 3, "label": "相当常"},
                    {"value": 4, "label": "非常常"}
                ]
            },
            {
                "id": 10,
                "text": "在过去一个月中，您有多经常觉得困难堆积如山，无法克服？",
                "options": [
                    {"value": 0, "label": "从不"},
                    {"value": 1, "label": "几乎不"},
                    {"value": 2, "label": "有时"},
                    {"value": 3, "label": "相当常"},
                    {"value": 4, "label": "非常常"}
                ]
            }
        ],
        "scoring_rules": {
            "method": "sum",
            "max_score": 40
        },
        "interpretation": [
            {
                "range": [0, 13],
                "level": "低压力",
                "interpretation": "您目前的压力水平较低，应对生活的能力良好。",
                "suggestion": "建议继续保持健康的生活方式，适时放松和娱乐。如遇到新的压力源，可以使用心翼的压力管理工具。"
            },
            {
                "range": [14, 26],
                "level": "中等压力",
                "interpretation": "您目前承受着中等程度的压力，这是较为常见的状态。",
                "suggestion": "建议：1) 识别主要压力源；2) 学习时间管理技巧；3) 实践放松技术（如深呼吸、正念）；4) 保持社交联系；5) 确保充足睡眠和规律运动；6) 使用心翼的压力缓解训练。"
            },
            {
                "range": [27, 40],
                "level": "高压力",
                "interpretation": "您目前承受着较高水平的压力，这可能影响您的身心健康。",
                "suggestion": "强烈建议：1) 评估并减少可避免的压力源；2) 寻求专业心理咨询；3) 学习有效的应对策略；4) 加强社会支持系统；5) 注意身体健康信号；6) 使用心翼的综合训练计划。如需帮助：心理援助热线 400-161-9995"
            }
        ]
    },
    
    # ISI 失眠严重程度指数
    {
        "scale_name": "ISI",
        "display_name": "失眠严重程度指数 (ISI)",
        "category": "sleep",
        "description": "ISI是评估失眠症状严重程度的简短量表，帮助了解您在过去两周的睡眠质量和失眠困扰。",
        "question_count": 7,
        "estimated_time": 2,
        "icon": "😴",
        "questions": [
            {
                "id": 1,
                "text": "您入睡困难的严重程度如何？",
                "options": [
                    {"value": 0, "label": "没有"},
                    {"value": 1, "label": "轻度"},
                    {"value": 2, "label": "中度"},
                    {"value": 3, "label": "重度"},
                    {"value": 4, "label": "非常重度"}
                ]
            },
            {
                "id": 2,
                "text": "您维持睡眠困难（半夜醒来）的严重程度如何？",
                "options": [
                    {"value": 0, "label": "没有"},
                    {"value": 1, "label": "轻度"},
                    {"value": 2, "label": "中度"},
                    {"value": 3, "label": "重度"},
                    {"value": 4, "label": "非常重度"}
                ]
            },
            {
                "id": 3,
                "text": "您早醒问题的严重程度如何？",
                "options": [
                    {"value": 0, "label": "没有"},
                    {"value": 1, "label": "轻度"},
                    {"value": 2, "label": "中度"},
                    {"value": 3, "label": "重度"},
                    {"value": 4, "label": "非常重度"}
                ]
            },
            {
                "id": 4,
                "text": "您对目前睡眠状况的满意程度如何？",
                "options": [
                    {"value": 0, "label": "非常满意"},
                    {"value": 1, "label": "满意"},
                    {"value": 2, "label": "中等满意"},
                    {"value": 3, "label": "不满意"},
                    {"value": 4, "label": "非常不满意"}
                ]
            },
            {
                "id": 5,
                "text": "您认为别人注意到您的睡眠问题影响了您的生活质量的程度如何？",
                "options": [
                    {"value": 0, "label": "完全没有注意到"},
                    {"value": 1, "label": "有点注意到"},
                    {"value": 2, "label": "很注意到"},
                    {"value": 3, "label": "非常注意到"},
                    {"value": 4, "label": "极其注意到"}
                ]
            },
            {
                "id": 6,
                "text": "您对目前睡眠问题的担心或苦恼程度如何？",
                "options": [
                    {"value": 0, "label": "完全不担心"},
                    {"value": 1, "label": "有点担心"},
                    {"value": 2, "label": "中等担心"},
                    {"value": 3, "label": "很担心"},
                    {"value": 4, "label": "非常担心"}
                ]
            },
            {
                "id": 7,
                "text": "您认为睡眠问题影响日常功能（如白天疲劳、工作/学习能力、注意力、记忆力、情绪等）的程度如何？",
                "options": [
                    {"value": 0, "label": "完全没有影响"},
                    {"value": 1, "label": "有点影响"},
                    {"value": 2, "label": "中等影响"},
                    {"value": 3, "label": "很大影响"},
                    {"value": 4, "label": "非常大影响"}
                ]
            }
        ],
        "scoring_rules": {
            "method": "sum",
            "max_score": 28
        },
        "interpretation": [
            {
                "range": [0, 7],
                "level": "无失眠",
                "interpretation": "您的睡眠状况良好，没有明显的失眠问题。",
                "suggestion": "建议保持良好的睡眠习惯：1) 规律作息；2) 睡前避免使用电子设备；3) 创造舒适的睡眠环境；4) 适度运动但避免睡前剧烈运动。"
            },
            {
                "range": [8, 14],
                "level": "轻度失眠",
                "interpretation": "您存在轻度失眠症状，可能偶尔影响睡眠质量。",
                "suggestion": "建议：1) 建立规律的睡眠作息；2) 睡前1小时放松活动（如阅读、听音乐）；3) 避免咖啡因和酒精；4) 使用心翼的睡眠冥想训练；5) 记录睡眠日记了解睡眠模式。"
            },
            {
                "range": [15, 21],
                "level": "中度失眠",
                "interpretation": "您存在中度失眠症状，已经明显影响您的睡眠质量和日常功能。",
                "suggestion": "强烈建议：1) 咨询睡眠专科医生或心理治疗师；2) 学习认知行为疗法（CBT-I）技巧；3) 排查可能的医学原因；4) 使用心翼的睡眠改善训练计划；5) 避免白天小睡；6) 建立放松的睡前仪式。"
            },
            {
                "range": [22, 28],
                "level": "重度失眠",
                "interpretation": "您存在重度失眠症状，严重影响身心健康和日常生活。",
                "suggestion": "⚠️ 紧急建议：1) 尽快就医，寻求专业睡眠医学或精神科评估；2) 可能需要药物配合心理治疗；3) 全面评估身体健康状况；4) 避免自行服用助眠药物；5) 心理援助热线：400-161-9995。长期失眠会影响免疫力、情绪和认知功能，请务必重视。"
            }
        ]
    },
    
    # CD-RISC-10 心理韧性量表
    {
        "scale_name": "CD-RISC-10",
        "display_name": "简版心理韧性量表 (CD-RISC-10)",
        "category": "resilience",
        "description": "CD-RISC-10评估您在面对压力、逆境和创伤时的心理弹性和恢复能力，帮助了解您的心理韧性水平。",
        "question_count": 10,
        "estimated_time": 3,
        "icon": "💪",
        "questions": [
            {
                "id": 1,
                "text": "我能够适应变化",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            },
            {
                "id": 2,
                "text": "无论发生什么，我都能处理",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            },
            {
                "id": 3,
                "text": "我尽力从挫折中迅速恢复",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            },
            {
                "id": 4,
                "text": "压力反而能让我变得更强",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            },
            {
                "id": 5,
                "text": "我倾向于从困难中恢复得很好",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            },
            {
                "id": 6,
                "text": "我相信我能实现自己的目标，即使有障碍",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            },
            {
                "id": 7,
                "text": "即使事情看起来没有希望，我也不轻易放弃",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            },
            {
                "id": 8,
                "text": "在压力情境下，我知道该去找谁帮忙",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            },
            {
                "id": 9,
                "text": "我不会因为失败或挫折而气馁",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            },
            {
                "id": 10,
                "text": "我认为自己是一个坚强的人",
                "options": [
                    {"value": 0, "label": "完全不符合"},
                    {"value": 1, "label": "很少符合"},
                    {"value": 2, "label": "有时符合"},
                    {"value": 3, "label": "经常符合"},
                    {"value": 4, "label": "几乎总是符合"}
                ]
            }
        ],
        "scoring_rules": {
            "method": "sum",
            "max_score": 40
        },
        "interpretation": [
            {
                "range": [0, 20],
                "level": "心理韧性较低",
                "interpretation": "您在面对压力和逆境时可能感到较为困难，恢复能力相对较弱。",
                "suggestion": "建议：1) 学习积极应对策略；2) 培养成长型思维模式；3) 建立支持性社交网络；4) 设定小而可实现的目标增强信心；5) 使用心翼的心理韧性训练模块；6) 考虑寻求心理咨询帮助提升应对能力。记住，心理韧性是可以培养的！"
            },
            {
                "range": [21, 30],
                "level": "心理韧性中等",
                "interpretation": "您具备一定的心理韧性，能够应对大多数压力情境，但仍有提升空间。",
                "suggestion": "建议：1) 继续发展积极应对策略；2) 从过往克服困难的经历中汲取力量；3) 保持乐观但现实的态度；4) 定期反思和总结应对经验；5) 使用心翼的进阶训练提升韧性；6) 在遇到重大挑战时主动寻求支持。"
            },
            {
                "range": [31, 40],
                "level": "心理韧性较高",
                "interpretation": "您具有很强的心理韧性，能够有效应对压力、从挫折中快速恢复，并在逆境中成长。",
                "suggestion": "优秀！继续保持：1) 将您的应对经验分享给他人；2) 在新的挑战中继续磨练韧性；3) 帮助他人提升心理韧性；4) 保持自我觉察，注意身心平衡；5) 使用心翼记录和反思成长历程。您的韧性是宝贵的心理资源！"
            }
        ]
    },
    
    # LSAS 社交焦虑量表（简版）
    {
        "scale_name": "LSAS-Brief",
        "display_name": "社交焦虑量表-简版 (LSAS-Brief)",
        "category": "social",
        "description": "LSAS简版评估您在社交和表现情境中的焦虑和回避程度，帮助识别社交焦虑障碍的症状。",
        "question_count": 12,
        "estimated_time": 4,
        "icon": "😓",
        "questions": [
            {
                "id": 1,
                "text": "与权威人士交谈时的焦虑程度",
                "options": [
                    {"value": 0, "label": "无"},
                    {"value": 1, "label": "轻度"},
                    {"value": 2, "label": "中度"},
                    {"value": 3, "label": "重度"}
                ]
            },
            {
                "id": 2,
                "text": "与权威人士交谈时的回避程度",
                "options": [
                    {"value": 0, "label": "从不回避"},
                    {"value": 1, "label": "偶尔回避"},
                    {"value": 2, "label": "经常回避"},
                    {"value": 3, "label": "总是回避"}
                ]
            },
            {
                "id": 3,
                "text": "在小组中交谈时的焦虑程度",
                "options": [
                    {"value": 0, "label": "无"},
                    {"value": 1, "label": "轻度"},
                    {"value": 2, "label": "中度"},
                    {"value": 3, "label": "重度"}
                ]
            },
            {
                "id": 4,
                "text": "在小组中交谈时的回避程度",
                "options": [
                    {"value": 0, "label": "从不回避"},
                    {"value": 1, "label": "偶尔回避"},
                    {"value": 2, "label": "经常回避"},
                    {"value": 3, "label": "总是回避"}
                ]
            },
            {
                "id": 5,
                "text": "参加聚会时的焦虑程度",
                "options": [
                    {"value": 0, "label": "无"},
                    {"value": 1, "label": "轻度"},
                    {"value": 2, "label": "中度"},
                    {"value": 3, "label": "重度"}
                ]
            },
            {
                "id": 6,
                "text": "参加聚会时的回避程度",
                "options": [
                    {"value": 0, "label": "从不回避"},
                    {"value": 1, "label": "偶尔回避"},
                    {"value": 2, "label": "经常回避"},
                    {"value": 3, "label": "总是回避"}
                ]
            },
            {
                "id": 7,
                "text": "当众演讲或表演时的焦虑程度",
                "options": [
                    {"value": 0, "label": "无"},
                    {"value": 1, "label": "轻度"},
                    {"value": 2, "label": "中度"},
                    {"value": 3, "label": "重度"}
                ]
            },
            {
                "id": 8,
                "text": "当众演讲或表演时的回避程度",
                "options": [
                    {"value": 0, "label": "从不回避"},
                    {"value": 1, "label": "偶尔回避"},
                    {"value": 2, "label": "经常回避"},
                    {"value": 3, "label": "总是回避"}
                ]
            },
            {
                "id": 9,
                "text": "在公共场所进食时的焦虑程度",
                "options": [
                    {"value": 0, "label": "无"},
                    {"value": 1, "label": "轻度"},
                    {"value": 2, "label": "中度"},
                    {"value": 3, "label": "重度"}
                ]
            },
            {
                "id": 10,
                "text": "在公共场所进食时的回避程度",
                "options": [
                    {"value": 0, "label": "从不回避"},
                    {"value": 1, "label": "偶尔回避"},
                    {"value": 2, "label": "经常回避"},
                    {"value": 3, "label": "总是回避"}
                ]
            },
            {
                "id": 11,
                "text": "被他人注视时的焦虑程度",
                "options": [
                    {"value": 0, "label": "无"},
                    {"value": 1, "label": "轻度"},
                    {"value": 2, "label": "中度"},
                    {"value": 3, "label": "重度"}
                ]
            },
            {
                "id": 12,
                "text": "被他人注视时的回避程度",
                "options": [
                    {"value": 0, "label": "从不回避"},
                    {"value": 1, "label": "偶尔回避"},
                    {"value": 2, "label": "经常回避"},
                    {"value": 3, "label": "总是回避"}
                ]
            }
        ],
        "scoring_rules": {
            "method": "sum",
            "max_score": 36
        },
        "interpretation": [
            {
                "range": [0, 11],
                "level": "无社交焦虑",
                "interpretation": "您在社交情境中表现自然，没有明显的社交焦虑症状。",
                "suggestion": "您的社交能力良好！建议：1) 继续保持积极的社交互动；2) 在舒适的基础上尝试新的社交场景；3) 可以帮助有社交困难的朋友；4) 维护良好的人际关系质量。"
            },
            {
                "range": [12, 18],
                "level": "轻度社交焦虑",
                "interpretation": "您在某些社交情境中可能感到轻微不适，但总体可以应对。",
                "suggestion": "建议：1) 识别让您焦虑的具体社交情境；2) 采用渐进式暴露法逐步适应；3) 练习社交技巧和沟通方法；4) 使用心翼的社交焦虑训练；5) 挑战负面的自我评价；6) 庆祝每一次社交成功。"
            },
            {
                "range": [19, 27],
                "level": "中度社交焦虑",
                "interpretation": "您在社交情境中经常感到焦虑，并可能因此回避某些社交活动，影响生活质量。",
                "suggestion": "强烈建议：1) 寻求专业心理咨询或认知行为疗法（CBT）；2) 学习放松技巧应对焦虑；3) 加入社交技能训练小组；4) 使用心翼的系统化训练计划；5) 挑战消极思维模式；6) 设定渐进式社交目标。心理援助热线：400-161-9995"
            },
            {
                "range": [28, 36],
                "level": "重度社交焦虑",
                "interpretation": "您存在严重的社交焦虑，显著影响日常生活、学习或工作。可能符合社交焦虑障碍诊断标准。",
                "suggestion": "⚠️ 紧急建议：1) 尽快寻求心理医生或精神科医生评估；2) 需要专业的认知行为治疗（CBT）；3) 可能需要药物配合治疗；4) 加入支持小组获得理解和鼓励；5) 避免自我孤立；6) 24小时心理援助热线：400-161-9995。社交焦虑是可以治疗的，请不要放弃！"
            }
        ]
    }
]


def _ensure_templates_exist(db: Session):
    """确保评估量表模板存在（首次访问时自动初始化）"""
    existing = db.query(AssessmentTemplate).first()
    if existing:
        return
    
    # 自动初始化
    try:
        for template_data in ASSESSMENT_TEMPLATES:
            template = AssessmentTemplate(**template_data)
            db.add(template)
        db.commit()
        logger.info(f"✅ 自动初始化 {len(ASSESSMENT_TEMPLATES)} 个评估量表")
    except Exception as e:
        logger.error(f"❌ 自动初始化评估量表失败: {e}")
        db.rollback()


@router.get("/list", response_model=List[AssessmentTemplateListItem])
async def get_assessment_list(
    category: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    获取评估量表列表
    可选按分类筛选：depression/anxiety/stress/sleep/personality
    """
    # 确保模板已初始化
    _ensure_templates_exist(db)
    
    query = db.query(AssessmentTemplate).filter(AssessmentTemplate.is_active == True)
    
    if category:
        query = query.filter(AssessmentTemplate.category == category)
    
    templates = query.order_by(AssessmentTemplate.id).all()
    
    # 获取用户最后完成时间
    result = []
    for template in templates:
        last_record = db.query(AssessmentRecord).filter(
            AssessmentRecord.user_id == current_user.id,
            AssessmentRecord.template_id == template.id
        ).order_by(desc(AssessmentRecord.created_at)).first()
        
        item = AssessmentTemplateListItem(
            id=template.id,
            scale_name=template.scale_name,
            display_name=template.display_name,
            category=template.category,
            description=template.description,
            question_count=template.question_count,
            estimated_time=template.estimated_time,
            icon=template.icon,
            last_completed=last_record.created_at if last_record else None
        )
        result.append(item)
    
    return result


@router.get("/{template_id}/template", response_model=AssessmentTemplateDetail)
async def get_assessment_template(
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取评估量表题目"""
    template = db.query(AssessmentTemplate).filter(
        AssessmentTemplate.id == template_id,
        AssessmentTemplate.is_active == True
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="量表不存在")
    
    return AssessmentTemplateDetail(
        id=template.id,
        scale_name=template.scale_name,
        display_name=template.display_name,
        category=template.category,
        description=template.description,
        question_count=template.question_count,
        estimated_time=template.estimated_time,
        questions=template.questions,
        icon=template.icon
    )


@router.post("/submit", response_model=AssessmentResultResponse)
async def submit_assessment(
    request: AssessmentSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """提交评估答案，返回评分结果"""
    # 获取量表模板
    template = db.query(AssessmentTemplate).filter(
        AssessmentTemplate.id == request.template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="量表不存在")
    
    # 验证答案数量
    if len(request.answers) != template.question_count:
        raise HTTPException(
            status_code=400, 
            detail=f"答案数量不匹配，期望{template.question_count}题，实际{len(request.answers)}题"
        )
    
    # 计算总分
    total_score = sum(request.answers)
    
    # 根据评分规则判断风险等级和解释
    interpretation_rules = template.interpretation
    risk_level = "unknown"
    interpretation = ""
    suggestions = ""
    
    for rule in interpretation_rules:
        score_range = rule.get("range", [0, 0])
        if score_range[0] <= total_score <= score_range[1]:
            risk_level = rule.get("level", "unknown")
            interpretation = rule.get("interpretation", "")
            suggestions = rule.get("suggestion", "")
            break
    
    # 保存评估记录
    record = AssessmentRecord(
        user_id=current_user.id,
        template_id=template.id,
        answers=request.answers,
        total_score=total_score,
        risk_level=risk_level,
        interpretation=interpretation,
        suggestions=suggestions
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # 效果度量：PHQ-9 / GAD-7 提交时写周快照
    if template.scale_name in ("PHQ-9", "GAD-7"):
        week_start = (record.created_at - timedelta(days=record.created_at.weekday())).strftime("%Y-%m-%d")
        snapshot = (
            db.query(OutcomeSnapshot)
            .filter(
                OutcomeSnapshot.user_id == current_user.id,
                OutcomeSnapshot.scale_name == template.scale_name,
                OutcomeSnapshot.week_start == week_start,
            )
            .first()
        )
        if snapshot:
            snapshot.total_score = total_score
            snapshot.risk_level = risk_level
        else:
            db.add(
                OutcomeSnapshot(
                    user_id=current_user.id,
                    scale_name=template.scale_name,
                    week_start=week_start,
                    total_score=total_score,
                    risk_level=risk_level,
                )
            )
        db.commit()

    # 长期记忆：评估结果作为情绪模式记忆
    try:
        await extract_facts_from_text(
            db,
            current_user,
            f"用户完成了 {template.display_name} 评估：得分 {total_score}，风险等级 {risk_level}。",
            "assessment",
        )
    except Exception as e:
        logger.warning("评估记忆抽取失败（跳过）: %s", e)
    
    logger.info(f"用户 {current_user.username} 完成评估 {template.scale_name}，得分: {total_score}，等级: {risk_level}")
    
    # 如果是高风险，记录日志
    if risk_level in ["severe", "重度"]:
        logger.warning(f"⚠️ 高风险评估 - 用户 {current_user.username}，量表 {template.scale_name}，得分 {total_score}")
    
    return AssessmentResultResponse(
        id=record.id,
        template_id=template.id,
        scale_name=template.scale_name,
        display_name=template.display_name,
        total_score=total_score,
        risk_level=risk_level,
        interpretation=interpretation,
        suggestions=suggestions,
        created_at=record.created_at
    )


@router.get("/history", response_model=List[AssessmentHistoryItem])
async def get_assessment_history(
    scale_name: str = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户评估历史记录"""
    query = db.query(AssessmentRecord, AssessmentTemplate).join(
        AssessmentTemplate,
        AssessmentRecord.template_id == AssessmentTemplate.id
    ).filter(
        AssessmentRecord.user_id == current_user.id
    )
    
    # 如果指定了量表类型，则筛选
    if scale_name:
        query = query.filter(AssessmentTemplate.scale_name == scale_name)
    
    records = query.order_by(desc(AssessmentRecord.created_at)).limit(limit).all()
    
    result = []
    for record, template in records:
        result.append(AssessmentHistoryItem(
            id=record.id,
            scale_name=template.scale_name,
            display_name=template.display_name,
            total_score=record.total_score,
            risk_level=record.risk_level,
            created_at=record.created_at
        ))
    
    return result


@router.get("/{record_id}/result", response_model=AssessmentResultResponse)
async def get_assessment_result(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取评估结果详情"""
    record = db.query(AssessmentRecord).filter(
        AssessmentRecord.id == record_id,
        AssessmentRecord.user_id == current_user.id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="评估记录不存在")
    
    template = db.query(AssessmentTemplate).filter(
        AssessmentTemplate.id == record.template_id
    ).first()
    
    return AssessmentResultResponse(
        id=record.id,
        template_id=template.id,
        scale_name=template.scale_name,
        display_name=template.display_name,
        total_score=record.total_score,
        risk_level=record.risk_level,
        interpretation=record.interpretation,
        suggestions=record.suggestions,
        created_at=record.created_at
    )


@router.get("/trends/{scale_name}")
async def get_assessment_trends(
    scale_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取评估趋势数据（用于绘制历史曲线）"""
    # 获取该量表的模板
    template = db.query(AssessmentTemplate).filter(
        AssessmentTemplate.scale_name == scale_name
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="量表不存在")
    
    # 获取用户该量表的所有记录
    records = db.query(AssessmentRecord).filter(
        AssessmentRecord.user_id == current_user.id,
        AssessmentRecord.template_id == template.id
    ).order_by(AssessmentRecord.created_at).all()
    
    if not records:
        return {"dates": [], "scores": [], "levels": []}
    
    dates = [record.created_at.strftime("%Y-%m-%d %H:%M") for record in records]
    scores = [record.total_score for record in records]
    levels = [record.risk_level for record in records]
    
    return {
        "scale_name": scale_name,
        "display_name": template.display_name,
        "dates": dates,
        "scores": scores,
        "levels": levels,
        "count": len(records)
    }
