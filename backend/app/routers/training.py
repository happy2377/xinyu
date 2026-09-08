"""训练指导路由"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from datetime import datetime

from ..database import get_db
from ..models import TrainingTemplate, TrainingRecord, TrainingPlan, User
from ..schemas import (
    TrainingTemplateListItem, TrainingTemplateDetail,
    TrainingCompleteRequest, TrainingRecordResponse,
    TrainingPlanCreateRequest, TrainingPlanResponse, TrainingPlanUpdateRequest,
    TrainingAssistRequest, Response
)
from ..auth import get_current_user
from ..training_guide import training_assist as run_training_assist

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/training", tags=["training"])


# 硬编码训练模板数据
TRAINING_TEMPLATES = [
    # 1. 呼吸训练
    {
        "training_type": "breathing",
        "training_name": "深呼吸放松法",
        "description": "通过有节奏的深呼吸缓解焦虑、紧张情绪,适合考试前、演讲前使用",
        "steps": [
            {
                "kind": "read",
                "text": "找一个安静舒适的地方坐下或躺下，闭上眼睛，放松全身肌肉。",
                "voice_script": "请先找一个安静舒服的地方，坐下或躺下。轻轻闭上眼睛，放松肩膀、手臂和脸上的肌肉。",
                "seconds": 20,
            },
            {
                "kind": "pattern",
                "text": "呼吸循环：吸气 4 秒 → 屏息 4 秒 → 呼气 6 秒，共 10 轮。",
                "voice_script": "下面开始呼吸循环，请跟着语音的节奏。",
                "phases": [
                    {"text": "用鼻子缓缓吸气 4 秒", "voice_script": "用鼻子缓缓吸气：", "seconds": 4, "speak_countdown": True},
                    {"text": "屏住呼吸 4 秒", "voice_script": "屏住呼吸：", "seconds": 4, "speak_countdown": True},
                    {"text": "用嘴巴缓缓呼气 6 秒", "voice_script": "慢慢呼气：", "seconds": 6, "speak_countdown": True},
                ],
                "rounds": 10,
            },
            {
                "kind": "read",
                "text": "感受呼吸之后身体的平静，慢慢睁开眼睛。",
                "voice_script": "十轮呼吸完成了。花一点时间，感受身体慢慢平静下来的感觉。准备好后，可以轻轻睁开眼睛。",
                "seconds": 40,
            },
        ],
        "duration": 4,
        "frequency": "每日2-3次",
        "difficulty_level": "beginner",
        "suitable_scenarios": ["焦虑", "紧张", "考试前", "演讲前"],
        "icon": "🫁"
    },
    {
        "training_type": "breathing",
        "training_name": "4-7-8呼吸法(助眠版)",
        "description": "帮助快速入睡的呼吸技巧,适合失眠、入睡困难时使用",
        "steps": [
            {
                "kind": "read",
                "text": "找一个舒适的躺姿，舌尖轻轻顶住上颚，先完全呼出嘴里的气。",
                "voice_script": "请躺好，让身体完全放松。舌尖轻轻顶住上颚，先用嘴巴把所有气呼出去。",
                "seconds": 20,
            },
            {
                "kind": "pattern",
                "text": "4-7-8 呼吸循环：吸气 4 秒 → 屏息 7 秒 → 呼气 8 秒，共 4 轮。",
                "voice_script": "现在开始 4-7-8 呼吸，跟着语音走就可以。",
                "phases": [
                    {"text": "闭嘴，用鼻子轻轻吸气 4 秒", "voice_script": "用鼻子轻轻吸气：", "seconds": 4, "speak_countdown": True},
                    {"text": "屏住呼吸 7 秒", "voice_script": "轻轻屏住呼吸：", "seconds": 7, "speak_countdown": True},
                    {"text": "嘴巴微微张开，呼气 8 秒，发出呼呼声", "voice_script": "缓缓呼气：", "seconds": 8, "speak_countdown": True},
                ],
                "rounds": 4,
            },
            {
                "kind": "read",
                "text": "放松身体，顺其自然地准备入睡。",
                "voice_script": "四轮 4-7-8 呼吸结束了。现在什么都不用做，让身体放松下来，如果困了就顺其自然地睡去。",
                "seconds": 30,
            },
        ],
        "duration": 3,
        "frequency": "睡前使用",
        "difficulty_level": "beginner",
        "suitable_scenarios": ["失眠", "入睡困难", "睡眠质量差"],
        "icon": "😴"
    },
    {
        "training_type": "breathing",
        "training_name": "正念呼吸冥想",
        "description": "通过专注呼吸提升觉察力,缓解思绪混乱、注意力分散",
        "steps": [
            {
                "kind": "read",
                "text": "以舒适的姿势坐下，背部挺直，闭上眼睛或微闭。",
                "voice_script": "请找一个舒服的姿势坐好，让背部自然挺直，然后轻轻闭上眼睛。",
                "seconds": 20,
            },
            {
                "kind": "read",
                "text": "把注意力轻轻放在鼻尖的呼吸感觉上，感受每一次吸气和呼气。",
                "voice_script": "把注意力轻轻放在鼻尖，感受空气进出时的温度变化。不需要控制呼吸，只要观察它。",
                "seconds": 25,
            },
            {
                "kind": "hold",
                "text": "跟随呼吸保持觉察约 5 分钟。思绪漂移时，温和地把注意力拉回呼吸。",
                "voice_script": "接下来是五分钟的静默觉察。如果发现自己走神了，不需要责怪自己，只要温和地把注意力带回呼吸就好。",
                "seconds": 300,
                "speak_countdown": False,
            },
            {
                "kind": "read",
                "text": "轻轻活动手指和脚趾，感受此刻的平静，慢慢睁开眼睛。",
                "voice_script": "静默觉察结束。先轻轻活动一下手指和脚趾，感受身体的存在，然后慢慢睁开眼睛。",
                "seconds": 20,
            },
        ],
        "duration": 7,
        "frequency": "每日1-2次",
        "difficulty_level": "intermediate",
        "suitable_scenarios": ["思绪混乱", "注意力分散", "情绪波动"],
        "icon": "🧘"
    },
    
    # 2. 肌肉放松训练
    {
        "training_type": "muscle_relaxation",
        "training_name": "渐进性肌肉放松(PMR)",
        "description": "通过依次紧绷和放松身体各部位肌肉,缓解全身紧张、焦虑",
        "steps": [
            {
                "kind": "read",
                "text": "找一个安静舒适的地方躺下，先做两次缓慢的深呼吸。",
                "voice_script": "请躺在一个安静舒服的地方，先做两次缓慢的深呼吸，让身体准备好。",
                "seconds": 20,
            },
            {
                "kind": "pattern",
                "text": "脚与小腿：绷紧 5 秒，再彻底放松 10 秒。",
                "voice_script": "现在开始紧绷与放松练习。先绷紧脚和小腿的肌肉，坚持五秒，然后彻底放松。",
                "phases": [
                    {"text": "绷紧脚掌与小腿", "voice_script": "绷紧脚掌和小腿：", "seconds": 5, "speak_countdown": True},
                    {"text": "彻底放松", "voice_script": "现在彻底放松，感受肌肉松下来的感觉：", "seconds": 10, "speak_countdown": False},
                ],
                "rounds": 2,
            },
            {
                "kind": "pattern",
                "text": "手与手臂：绷紧 5 秒，再彻底放松 10 秒。",
                "voice_script": "接下来轮到双手和手臂。",
                "phases": [
                    {"text": "握紧拳头、绷紧手臂", "voice_script": "握紧拳头：", "seconds": 5, "speak_countdown": True},
                    {"text": "彻底放松", "voice_script": "放开，让手臂完全松弛：", "seconds": 10, "speak_countdown": False},
                ],
                "rounds": 2,
            },
            {
                "kind": "pattern",
                "text": "肩膀与面部：绷紧 5 秒，再彻底放松 10 秒。",
                "voice_script": "现在轮到肩膀和面部。",
                "phases": [
                    {"text": "耸起肩膀、皱紧面部", "voice_script": "耸起肩膀，皱紧脸：", "seconds": 5, "speak_countdown": True},
                    {"text": "彻底放松", "voice_script": "放松下来，让肩膀下沉：", "seconds": 10, "speak_countdown": False},
                ],
                "rounds": 2,
            },
            {
                "kind": "hold",
                "text": "保持全身放松约 2 分钟，感受紧张被释放后的轻松。",
                "voice_script": "全身练习完成。接下来静静躺两分钟，感受紧张一点点离开身体的感觉。",
                "seconds": 120,
                "speak_countdown": False,
            },
        ],
        "duration": 8,
        "frequency": "每日1次",
        "difficulty_level": "intermediate",
        "suitable_scenarios": ["全身紧张", "焦虑", "躯体化症状"],
        "icon": "💪"
    },
    
    # 3. 正念冥想训练
    {
        "training_type": "mindfulness",
        "training_name": "身体扫描冥想",
        "description": "从头到脚逐一觉察身体感觉,提升身心连接",
        "steps": [
            {
                "kind": "read",
                "text": "躺下或坐下，闭上眼睛，做两次缓慢的深呼吸。",
                "voice_script": "请躺下或舒服地坐好，闭上眼睛，先做两次缓慢的深呼吸。",
                "seconds": 20,
            },
            {
                "kind": "hold",
                "text": "觉察头部：头顶→额头→眼睛→鼻子→嘴巴→下巴。",
                "voice_script": "把注意力带到头顶，然后是额头、眼睛、鼻子、嘴巴和下巴。不评判，只感受。",
                "seconds": 60,
                "speak_countdown": False,
            },
            {
                "kind": "hold",
                "text": "觉察颈肩与手臂：颈部→肩膀→手臂→手掌。",
                "voice_script": "现在把注意力带到颈部、肩膀，再沿手臂向下到手掌。哪里紧，就让它松一松。",
                "seconds": 90,
                "speak_countdown": False,
            },
            {
                "kind": "hold",
                "text": "觉察躯干：胸部→腹部，感受呼吸带来的起伏。",
                "voice_script": "接下来感受胸部和腹部。留意呼吸时腹部轻轻起伏的感觉。",
                "seconds": 90,
                "speak_countdown": False,
            },
            {
                "kind": "hold",
                "text": "觉察下肢：臀部→大腿→小腿→脚掌→脚趾。",
                "voice_script": "最后把注意力带到臀部、大腿、小腿，一直到脚掌和脚趾，感受双腿稳稳落在地面的感觉。",
                "seconds": 120,
                "speak_countdown": False,
            },
            {
                "kind": "read",
                "text": "感受全身连成一体的感觉，慢慢睁开眼睛。",
                "voice_script": "身体扫描结束。感受全身作为一个整体安静地待在这里，然后慢慢睁开眼睛。",
                "seconds": 30,
            },
        ],
        "duration": 9,
        "frequency": "每日1次",
        "difficulty_level": "intermediate",
        "suitable_scenarios": ["情绪波动", "压力过大", "失眠"],
        "icon": "🌟"
    },
    {
        "training_type": "mindfulness",
        "training_name": "正念行走",
        "description": "专注行走的每一步,培养当下觉知",
        "steps": [
            {
                "kind": "read",
                "text": "找一个安静、可以来回走动的空间，站定，感受双脚踩在地面。",
                "voice_script": "请找一个安静的空间，可以来回走大约十步。先站定，感受双脚踩在地面上的感觉。",
                "seconds": 20,
            },
            {
                "kind": "read",
                "text": "把注意力放在双脚上，不用赶路，只留意走路本身。",
                "voice_script": "开始慢慢走。把注意力放在双脚上，感受脚跟抬起、脚掌离地、向前移动、再落回地面的过程。",
                "seconds": 30,
            },
            {
                "kind": "hold",
                "text": "保持正念行走约 8 分钟。走神时，把注意力温和地带回脚底。",
                "voice_script": "接下来是八分钟的正念行走。走慢一点，感受每一步。走神没有关系，把注意力轻轻带回脚底就好。",
                "seconds": 480,
                "speak_countdown": False,
            },
            {
                "kind": "read",
                "text": "站定，感受身体微微发热与平静，慢慢停下。",
                "voice_script": "时间到了。慢慢站定，感受身体微微发热、心跳平缓下来的感觉，然后结束这次行走。",
                "seconds": 20,
            },
        ],
        "duration": 10,
        "frequency": "每日1-2次",
        "difficulty_level": "beginner",
        "suitable_scenarios": ["焦虑", "烦躁", "注意力不集中"],
        "icon": "🚶"
    },
    
    # 4. 认知重构训练
    {
        "training_type": "cognitive",
        "training_name": "三栏技术(认知重构)",
        "description": "识别并挑战非理性想法,形成理性替代想法",
        "steps": [
            {
                "kind": "read",
                "text": "三栏技术：事件 → 自动化思维 → 替代想法。准备好纸笔或就在下方输入框里写。",
                "voice_script": "欢迎来到三栏技术。我们会按三个部分写下事件、你脑子里的第一反应，以及更理性的替代想法。你可以直接打字，也可以写在纸上。",
                "seconds": 20,
            },
            {
                "kind": "input",
                "text": "第一栏：写下引发负面情绪的具体事件。",
                "voice_script": "请写下今天或最近让你情绪波动的那件事，不用写得很长，一两句话就可以。",
                "input_hint": "例如：下午开会时被当众质疑",
                "input_type": "text",
                "followup_ai": False,
            },
            {
                "kind": "input",
                "text": "第二栏：写下这件事触发你的自动化思维（你的第一反应）。",
                "voice_script": "现在写下当那件事发生时，你脑海里自动冒出来的想法。它通常很直接，比如“我又搞砸了”。",
                "input_hint": "例如：大家都觉得我很差劲",
                "input_type": "text",
                "followup_ai": True,
            },
            {
                "kind": "input",
                "text": "第三栏（上）：挑战这个想法——有哪些证据支持或反对它？",
                "voice_script": "现在站在旁观者的角度，找找看有哪些证据支持这个想法，又有哪些证据并不支持它。",
                "input_hint": "支持与反对的证据都可以写",
                "input_type": "text",
                "followup_ai": False,
            },
            {
                "kind": "input",
                "text": "第三栏（下）：写下更理性、更温和的替代想法。",
                "voice_script": "最后，试着写一个更客观、也更善待自己的替代想法。不用强迫自己完全相信，先写下来。",
                "input_hint": "例如：被质疑一次不代表我很差，我可以改进表达",
                "input_type": "text",
                "followup_ai": True,
            },
            {
                "kind": "read",
                "text": "把替代想法默读一遍，感受它与最初想法的不同。",
                "voice_script": "请把替代想法在心里默读一遍，感受一下它和最初那个想法带来的感觉有什么不同。",
                "seconds": 30,
            },
        ],
        "duration": 10,
        "frequency": "每日记录1-2次",
        "difficulty_level": "intermediate",
        "suitable_scenarios": ["灾难化思维", "黑白思维", "过度概括"],
        "icon": "💭"
    },
    {
        "training_type": "cognitive",
        "training_name": "情绪ABC分析",
        "description": "理解情绪的来源:事件→信念→结果",
        "steps": [
            {
                "kind": "read",
                "text": "情绪 ABC：事件 A → 信念 B → 结果 C。同一个 A，不同的 B 会带来不同的 C。",
                "voice_script": "欢迎来到情绪 ABC 练习。我们会依次写下事件、你对它的看法，以及它带来的情绪和行为结果。",
                "seconds": 20,
            },
            {
                "kind": "input",
                "text": "A（事件）：描述引发情绪的具体事件。",
                "voice_script": "请写下触发情绪的那件事，只描述事实，不加评价。",
                "input_hint": "例如：朋友没有回我的消息",
                "input_type": "text",
                "followup_ai": False,
            },
            {
                "kind": "input",
                "text": "B（信念）：写下你对这件事的看法和解释。",
                "voice_script": "现在写下你对这件事的解释，也就是你心里相信的那句话。",
                "input_hint": "例如：他不理我，说明我一点都不重要",
                "input_type": "text",
                "followup_ai": True,
            },
            {
                "kind": "input",
                "text": "C（结果）：写下这个信念带来的情绪和行为反应。",
                "voice_script": "写下这个想法让你产生的情绪，以及你随后做了什么或想做什么。",
                "input_hint": "例如：委屈、失落，想删除对话框",
                "input_type": "text",
                "followup_ai": False,
            },
            {
                "kind": "input",
                "text": "改写：用更理性、更温和的信念替换 B。",
                "voice_script": "试着换一个更温和的解释，比如对方可能有别的难处，我的价值不需要由一条消息来证明。写下新的信念。",
                "input_hint": "例如：他可能只是忙，我的价值不取决于这条回复",
                "input_type": "text",
                "followup_ai": True,
            },
            {
                "kind": "read",
                "text": "想象带着新信念，同样的事件会带来怎样不同的结果。",
                "voice_script": "最后，闭上眼睛想象一下：如果带着这个新的信念重新经历那件事，你的感受和行为会有什么不同？",
                "seconds": 30,
            },
        ],
        "duration": 10,
        "frequency": "遇到情绪困扰时使用",
        "difficulty_level": "intermediate",
        "suitable_scenarios": ["情绪失控", "认知偏差", "自我责备"],
        "icon": "🔤"
    },
    
    # 5. 情绪调节训练
    {
        "training_type": "emotion",
        "training_name": "情绪命名练习",
        "description": "准确识别和命名情绪,提升情绪觉察能力",
        "steps": [
            {
                "kind": "read",
                "text": "闭上眼睛，感受此刻的情绪，问自己：我现在感觉如何？",
                "voice_script": "先闭上眼睛，感受此刻身体和心里的状态。不用着急，问自己：我现在感觉如何？",
                "seconds": 20,
            },
            {
                "kind": "input",
                "text": "试着用一个具体的词命名这种情绪（不只是“不好”）。",
                "voice_script": "试着用一个具体的词说出这种感觉，比如失望、无助、愤怒、焦虑，或者孤独。",
                "input_hint": "例如：焦虑、委屈、疲惫、孤独",
                "input_type": "text",
                "followup_ai": True,
            },
            {
                "kind": "read",
                "text": "接纳它：在心里对自己说“我感到……，这很正常”。",
                "voice_script": "现在在心里对自己说：我感到刚才写下的那种情绪，这很正常，它不会永远停留。",
                "seconds": 25,
            },
            {
                "kind": "reflect",
                "text": "安静观察这个情绪 30 秒，不推开它，也不被它带走。",
                "voice_script": "接下来安静三十秒，像看云一样观察这个情绪，不推开它，也不被它卷走。",
                "seconds": 30,
            },
        ],
        "duration": 5,
        "frequency": "情绪波动时使用",
        "difficulty_level": "beginner",
        "suitable_scenarios": ["情绪识别困难", "情绪压抑", "情绪失控"],
        "icon": "😊"
    },
    {
        "training_type": "emotion",
        "training_name": "情绪温度计",
        "description": "追踪情绪强度变化,培养情绪觉察",
        "steps": [
            {
                "kind": "read",
                "text": "先识别此刻最主要的情绪是什么。",
                "voice_script": "我们先识别一下：此刻最明显的那种情绪是什么？",
                "seconds": 15,
            },
            {
                "kind": "input",
                "text": "给情绪强度打分：0 分（几乎没有）到 10 分（极度强烈）。",
                "voice_script": "请给你的情绪强度打个分，从 0 到 10，0 表示几乎没有，10 表示强烈到快承受不住。",
                "input_hint": "0-10 之间的整数",
                "input_type": "scale0_10",
                "followup_ai": False,
            },
            {
                "kind": "input",
                "text": "写下触发这种情绪的事件或情境。",
                "voice_script": "如果有明确的触发事件，可以写下来；暂时说不清也没关系。",
                "input_hint": "例如：刚才和妈妈通电话",
                "input_type": "text",
                "followup_ai": False,
            },
            {
                "kind": "hold",
                "text": "使用一个应对策略：做 2 分钟慢呼吸，或离开原地慢慢走一走。",
                "voice_script": "现在请做一个两分钟的应对练习：可以慢慢呼吸，也可以离开原地走一走。",
                "seconds": 120,
                "speak_countdown": False,
            },
            {
                "kind": "input",
                "text": "再次给情绪强度打分（0-10），看看发生了什么变化。",
                "voice_script": "练习结束了。请再打一次分，看看情绪强度发生了什么变化。",
                "input_hint": "0-10 之间的整数",
                "input_type": "scale0_10",
                "followup_ai": False,
            },
            {
                "kind": "read",
                "text": "对比两次分数，把这次“降下来/被看见”的过程记住。",
                "voice_script": "对比一下两次分数。无论数字变化大还是小，你刚刚都为自己做了一件有帮助的事。",
                "seconds": 20,
            },
        ],
        "duration": 6,
        "frequency": "每日多次",
        "difficulty_level": "beginner",
        "suitable_scenarios": ["情绪波动", "情绪调节困难"],
        "icon": "🌡️"
    },
    
    # 6. 睡眠训练
    {
        "training_type": "sleep",
        "training_name": "睡前仪式建立",
        "description": "建立固定的睡前程序,改善睡眠质量",
        "steps": [
            {
                "kind": "read",
                "text": "睡前仪式是把“睡觉信号”重复给身体，让它知道：该放松了。",
                "voice_script": "睡前仪式的作用，是每天用同样的动作告诉身体：现在安全了，可以慢慢放松。",
                "seconds": 20,
            },
            {
                "kind": "input",
                "text": "写下你今晚计划上床的时间，尽量与昨晚保持一致。",
                "voice_script": "写下你今晚计划上床睡觉的时间，尽量固定下来，比如十点半。",
                "input_hint": "例如：22:30",
                "input_type": "text",
                "followup_ai": False,
            },
            {
                "kind": "read",
                "text": "睡前 1 小时关闭电子设备，洗个热水澡或泡脚。",
                "voice_script": "睡前一小时，把手机放到够不着的地方，可以洗个热水澡或泡泡脚，让体温先升后降，帮助入睡。",
                "seconds": 20,
            },
            {
                "kind": "read",
                "text": "阅读纸质书或听轻音乐 15 分钟，内容越平淡越好。",
                "voice_script": "然后读几页纸质书，或听一段舒缓的音乐。挑选内容平淡的，避免刺激性的信息。",
                "seconds": 20,
            },
            {
                "kind": "read",
                "text": "关灯前，做一轮 4-7-8 呼吸，让心率慢下来。",
                "voice_script": "关灯前，可以回到训练列表做一轮 4-7-8 呼吸，让心跳慢下来。",
                "seconds": 20,
            },
            {
                "kind": "read",
                "text": "关灯，保持卧室黑暗、安静、凉爽，把“床”留给睡眠。",
                "voice_script": "最后关灯，让房间保持黑暗安静。躺下后如果睡不着，也不要把床当作战场，明天可以继续调整。",
                "seconds": 20,
            },
        ],
        "duration": 10,
        "frequency": "每晚睡前",
        "difficulty_level": "beginner",
        "suitable_scenarios": ["失眠", "睡眠质量差", "入睡困难"],
        "icon": "🌙"
    },
    {
        "training_type": "sleep",
        "training_name": "刺激控制疗法",
        "description": "建立床与睡眠的条件反射,提高睡眠效率",
        "steps": [
            {
                "kind": "read",
                "text": "刺激控制的核心：让“床”只和睡觉绑定，重新建立条件反射。",
                "voice_script": "刺激控制疗法很简单：让床只和睡觉绑定。坚持几周，身体会重新学会一躺下就想睡。",
                "seconds": 20,
            },
            {
                "kind": "read",
                "text": "只有感到困倦时才上床；床不用于工作、玩手机或焦虑地躺着。",
                "voice_script": "只有真的困了才上床。床只用来睡觉，不在床上工作、刷手机，也不在床上干着急。",
                "seconds": 20,
            },
            {
                "kind": "read",
                "text": "躺下约 20 分钟仍没睡着，就离开床，去客厅做安静的事。",
                "voice_script": "如果躺下大约二十分钟还睡不着，就起来离开卧室，去客厅做点安静的事，比如读几页书。",
                "seconds": 20,
            },
            {
                "kind": "read",
                "text": "重新感到困倦时再回床上；睡不着就重复“离开—回来”。",
                "voice_script": "等到再次感到困倦，再回床上。如果又睡不着，就再离开一次。这样做是在重新训练你的身体。",
                "seconds": 20,
            },
            {
                "kind": "input",
                "text": "写下你打算每天固定起床的时间（无论前一晚睡得多晚）。",
                "voice_script": "固定起床时间同样重要。写下你打算每天起床的时间，即使前一晚睡得不好也尽量坚持。",
                "input_hint": "例如：07:00",
                "input_type": "text",
                "followup_ai": False,
            },
            {
                "kind": "read",
                "text": "白天不小睡超过 30 分钟，下午 3 点后避免午睡。",
                "voice_script": "白天如果午睡，控制在三十分钟以内，下午三点以后尽量不要再睡，以免影响晚上的睡眠动力。",
                "seconds": 15,
            },
        ],
        "duration": 5,
        "frequency": "每晚使用",
        "difficulty_level": "intermediate",
        "suitable_scenarios": ["失眠", "睡眠效率低", "夜间醒来"],
        "icon": "⏰"
    }
]


def _is_legacy_steps(steps) -> bool:
    """旧版模板步骤是纯字符串数组，需要升级。"""
    return isinstance(steps, list) and (not steps or isinstance(steps[0], str))


def sync_training_templates(db: Session) -> int:
    """幂等同步内置训练模板：按 training_name 新增或刷新（旧版纯文本 steps 自动升级）。"""
    changed = 0
    try:
        for data in TRAINING_TEMPLATES:
            template = (
                db.query(TrainingTemplate)
                .filter(TrainingTemplate.training_name == data["training_name"])
                .first()
            )
            if not template:
                db.add(TrainingTemplate(**data))
                changed += 1
                continue
            if (
                _is_legacy_steps(template.steps)
                or template.steps != data["steps"]
                or template.duration != data["duration"]
                or template.description != data["description"]
            ):
                for key, value in data.items():
                    setattr(template, key, value)
                changed += 1
        db.commit()
        if changed:
            logger.info("训练模板同步完成：新增/更新 %s 条", changed)
    except Exception as e:  # pragma: no cover - 同步失败不应阻断启动
        logger.error("训练模板同步失败: %s", e)
        db.rollback()
    return changed


def _ensure_templates_exist(db: Session):
    """确保内置训练模板存在且为最新结构。"""
    sync_training_templates(db)


@router.get("/list", response_model=List[TrainingTemplateListItem])
def get_training_list(
    training_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取训练列表（支持按类型筛选）"""
    # 确保模板已初始化
    _ensure_templates_exist(db)
    
    query = db.query(TrainingTemplate).filter(TrainingTemplate.is_active == True)
    
    if training_type:
        query = query.filter(TrainingTemplate.training_type == training_type)
    
    templates = query.order_by(TrainingTemplate.training_type, TrainingTemplate.id).all()
    
    # 获取用户的完成次数
    result = []
    for template in templates:
        completed_count = db.query(func.count(TrainingRecord.id)).filter(
            and_(
                TrainingRecord.training_id == template.id,
                TrainingRecord.user_id == current_user.id
            )
        ).scalar()
        
        result.append({
            "id": template.id,
            "training_type": template.training_type,
            "training_name": template.training_name,
            "description": template.description,
            "duration": template.duration,
            "frequency": template.frequency,
            "difficulty_level": template.difficulty_level,
            "icon": template.icon,
            "completed_count": completed_count or 0
        })
    
    return result


@router.get("/records")
def get_training_records(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户训练历史"""
    records = db.query(TrainingRecord, TrainingTemplate).join(
        TrainingTemplate, TrainingRecord.training_id == TrainingTemplate.id
    ).filter(
        TrainingRecord.user_id == current_user.id
    ).order_by(
        TrainingRecord.completed_at.desc()
    ).all()
    
    return [{
        "id": record.id,
        "training_id": template.id,
        "training_name": template.training_name,
        "training_type": template.training_type,
        "duration": record.duration,
        "feedback": record.feedback or {},
        "completed_at": record.completed_at.isoformat()
    } for record, template in records]


@router.get("/statistics")
def get_training_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取训练统计数据"""
    total_count = db.query(func.count(TrainingRecord.id)).filter(
        TrainingRecord.user_id == current_user.id
    ).scalar() or 0
    
    total_duration = db.query(func.sum(TrainingRecord.duration)).filter(
        TrainingRecord.user_id == current_user.id
    ).scalar() or 0
    
    type_stats = db.query(
        TrainingTemplate.training_type,
        func.count(TrainingRecord.id)
    ).join(
        TrainingRecord, TrainingTemplate.id == TrainingRecord.training_id
    ).filter(
        TrainingRecord.user_id == current_user.id
    ).group_by(
        TrainingTemplate.training_type
    ).all()
    
    return {
        "total_count": int(total_count),
        "total_duration": int(total_duration),
        "type_distribution": {row[0]: row[1] for row in type_stats}
    }


@router.get("/{training_id}", response_model=TrainingTemplateDetail)
def get_training_detail(
    training_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取训练详情"""
    _ensure_templates_exist(db)

    template = db.query(TrainingTemplate).filter(TrainingTemplate.id == training_id).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="训练模板不存在"
        )
    
    return template


@router.post("/complete", response_model=TrainingRecordResponse)
def complete_training(
    request: TrainingCompleteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """完成训练（记录完成时间和反馈）"""
    template = db.query(TrainingTemplate).filter(TrainingTemplate.id == request.training_id).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="训练模板不存在"
        )
    
    # 合并本场步骤日志与 AI 总结到反馈中
    feedback = dict(request.feedback or {})
    if request.step_logs:
        feedback["step_logs"] = request.step_logs
    if request.ai_summary:
        feedback["ai_summary"] = request.ai_summary

    # 创建训练记录
    record = TrainingRecord(
        user_id=current_user.id,
        training_id=request.training_id,
        duration=request.duration,
        feedback=feedback,
        completed_at=datetime.now()
    )
    
    db.add(record)
    db.commit()
    db.refresh(record)
    
    # 返回记录详情
    return {
        "id": record.id,
        "training_id": template.id,
        "training_name": template.training_name,
        "training_type": template.training_type,
        "duration": record.duration,
        "feedback": record.feedback,
        "completed_at": record.completed_at
    }


@router.post("/assist")
async def training_assist_endpoint(
    request: TrainingAssistRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """训练关键节点 AI 引导：开训 intro / 步骤反馈 step_feedback / 结束总结 summary。"""
    template = (
        db.query(TrainingTemplate)
        .filter(TrainingTemplate.id == request.training_id)
        .first()
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="训练模板不存在",
        )

    return await run_training_assist(
        db=db,
        user=current_user,
        template=template,
        stage=request.stage,
        step_index=request.step_index,
        user_input=request.user_input or "",
        step_logs=request.step_logs or [],
    )


@router.post("/plan/create", response_model=TrainingPlanResponse)
def create_training_plan(
    request: TrainingPlanCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建训练计划"""
    template = db.query(TrainingTemplate).filter(TrainingTemplate.id == request.training_id).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="训练模板不存在"
        )
    
    # 创建训练计划
    plan = TrainingPlan(
        user_id=current_user.id,
        training_id=request.training_id,
        plan_name=request.plan_name,
        start_date=request.start_date,
        end_date=request.end_date,
        frequency=request.frequency,
        reminder_time=request.reminder_time,
        status="active"
    )
    
    db.add(plan)
    db.commit()
    db.refresh(plan)
    
    return {
        "id": plan.id,
        "training_id": template.id,
        "training_name": template.training_name,
        "plan_name": plan.plan_name,
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "frequency": plan.frequency,
        "reminder_time": plan.reminder_time,
        "status": plan.status,
        "created_at": plan.created_at
    }


@router.get("/plan/list", response_model=List[TrainingPlanResponse])
def get_training_plans(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户训练计划列表"""
    plans = db.query(TrainingPlan, TrainingTemplate).join(
        TrainingTemplate, TrainingPlan.training_id == TrainingTemplate.id
    ).filter(
        TrainingPlan.user_id == current_user.id
    ).order_by(
        TrainingPlan.created_at.desc()
    ).all()
    
    result = []
    for plan, template in plans:
        result.append({
            "id": plan.id,
            "training_id": template.id,
            "training_name": template.training_name,
            "plan_name": plan.plan_name,
            "start_date": plan.start_date,
            "end_date": plan.end_date,
            "frequency": plan.frequency,
            "reminder_time": plan.reminder_time,
            "status": plan.status,
            "created_at": plan.created_at
        })
    
    return result


@router.put("/plan/{plan_id}/status")
def update_training_plan_status(
    plan_id: int,
    request: TrainingPlanUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新训练计划状态"""
    plan = db.query(TrainingPlan).filter(
        and_(
            TrainingPlan.id == plan_id,
            TrainingPlan.user_id == current_user.id
        )
    ).first()
    
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="训练计划不存在"
        )
    
    # 更新状态
    plan.status = request.status
    plan.updated_at = datetime.now()
    
    db.commit()
    
    return Response(
        success=True,
        message="训练计划状态已更新",
        data={"plan_id": plan.id, "status": plan.status}
    )
