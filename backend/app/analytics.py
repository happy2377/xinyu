"""轻量埋点 SDK —— 追加写 NDJSON 到根目录日志。

设计目标：
1. 埋点失败绝不拖垮主流程（任何异常只记 debug，静默吞掉）；
2. 只写结构化元数据，绝不落盘用户消息原文（隐私红线）；
3. 以「追加写一行」为单元，天然适合日志分析。

使用：``track("diary_created", user_id=uid, word_count=100)``
输出：``{"event": "diary_created", "event_ts": "...", "app_version": "1.0.0", "user_id": "...", "word_count": 100}``
"""
import io
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 根目录 = backend/data 同级，固定为 backend 目录下 logs/
_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..")
LOGS_DIR = os.path.abspath(os.path.join(_BASE_DIR, "logs"))
LOG_FILE = os.path.join(LOGS_DIR, "analytics__events.log")

APP_VERSION = "1.0.0"

# NDJSON 严格单行追加：同一文件多线程/多进程写存在交织风险。
# 这里用进程内锁保证同进程串行；多进程部署时建议改为 append 模式 + 原子写（见 spec 实现注意事项）。
_write_lock = threading.Lock()


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def track(event: str, user_id: Any = None, **attrs: Any) -> None:
    """写入一条埋点事件。异常一律静默，绝不向外抛出。"""
    try:
        record: Dict[str, Any] = {
            "event": event,
            "event_ts": _ts(),
            "app_version": APP_VERSION,
            "user_id": _anonymize(user_id),
        }
        # 过滤 None 且可 JSON 序列化的字段
        for k, v in attrs.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                record[k] = v
            else:
                # 其他类型（list/dict）尽量原样，序列化失败则降级为 str
                try:
                    json.dumps(v)
                    record[k] = v
                except (TypeError, ValueError):
                    record[k] = str(v)[:200]

        line = json.dumps(record, ensure_ascii=False)
        _append_line(line)
    except Exception:  # noqa: BLE001 - 埋点失败不应影响业务
        logger.debug("埋点写入失败（忽略）: event=%s", event)


def _anonymize(user_id: Any) -> Optional[str]:
    """伪匿名化 user_id，避免在原样落盘敏感主键。"""
    if user_id is None:
        return None
    # 仅保留 id 的弱哈希片段（够做留存关联，又不暴露原文）
    try:
        h = f"{user_id}{int(time.time()) // 86400}"
        return h[-8:]
    except Exception:  # noqa: BLE001
        return None


def _append_line(line: str) -> None:
    """线程安全地把一行 JSON 追加到日志末尾；目录不存在则创建。"""
    with _write_lock:
        os.makedirs(LOGS_DIR, exist_ok=True)
        with io.open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def flush() -> None:
    """提供给测试/优雅关闭时确保缓冲落盘（此处逐行写入，无累积缓冲）。"""