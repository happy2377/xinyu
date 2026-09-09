"""轻量级启动迁移：
- 升级前自动备份 SQLite 数据库（每天一次）
- 为既有表补充新列（ALTER TABLE ADD COLUMN）
- 创建 FTS5 全文检索虚拟表（trigram，支持中文子串）
"""
import logging
import os
import shutil
from datetime import datetime

from sqlalchemy import text

logger = logging.getLogger(__name__)

_NEW_COLUMNS = {
    "messages": [
        ("rag_sources", "JSON"),
    ],
}


def _backup_db(db_path: str) -> str | None:
    """每日一次备份，返回备份路径；失败不阻断启动。"""
    try:
        if not os.path.exists(db_path):
            return None
        today = datetime.now().strftime("%Y%m%d")
        backup_dir = os.path.join(os.path.dirname(db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        target = os.path.join(backup_dir, f"xinyu-{today}.db")
        if os.path.exists(target):
            return target
        shutil.copy2(db_path, target)
        logger.info("数据库已备份到 %s", target)
        return target
    except Exception as e:  # pragma: no cover - 备份失败不应阻断启动
        logger.warning("数据库备份失败（跳过）: %s", e)
        return None


def run_migrations(engine, db_path: str | None = None) -> None:
    """在 create_all 之后执行：备份、补列、FTS5。"""
    if db_path:
        _backup_db(db_path)

    with engine.connect() as conn:
        # 1. 旧表补列
        for table, columns in _NEW_COLUMNS.items():
            existing = {
                row[1]
                for row in conn.execute(
                    text(f"PRAGMA table_info({table})")
                ).fetchall()
            }
            for col_name, col_type in columns:
                if col_name not in existing:
                    conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                    )
                    logger.info("为表 %s 补充列 %s", table, col_name)

        # 2. FTS5 知识分块全文表（trigram 分词，支持中文）
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts "
                "USING fts5(chunk_id UNINDEXED, content, tokenize='trigram')"
            )
        )
        conn.commit()
