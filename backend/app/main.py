"""FastAPI 主应用"""
import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base
from .migrations import run_migrations
from .routers import (
    auth,
    chat,
    assessment,
    training,
    diary,
    growth,
    analytics,
    knowledge,
    memory,
    agent,
)

# 加载环境变量
load_dotenv()

# 创建数据库表
Base.metadata.create_all(bind=engine)

# 轻量迁移：备份 + 补列 + FTS5
run_migrations(engine, db_path=engine.url.database)

# 创建 FastAPI 应用
app = FastAPI(
    title="心屿 Xinyu API",
    description="心理健康陪伴助手后端 API",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_seed_knowledge():
    """启动时同步训练模板、幂等导入种子知识库；异常时静默跳过。"""
    from .database import SessionLocal
    from .knowledge_service import import_seed_knowledge
    from .routers.training import sync_training_templates

    db = SessionLocal()
    try:
        sync_training_templates(db)
        imported = await import_seed_knowledge(db)
        if imported:
            print(f"[启动] 种子知识库导入完成：新增 {imported} 篇")
    except Exception as e:
        print(f"[启动] 种子知识库导入跳过: {e}")
    finally:
        db.close()

# 配置 CORS（允许前端跨域请求）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js 开发服务器
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(assessment.router)
app.include_router(training.router)
app.include_router(diary.router)
app.include_router(growth.router)
app.include_router(analytics.router)
app.include_router(knowledge.router)
app.include_router(memory.router)
app.include_router(agent.router)

# 根路径
@app.get("/")
async def root():
    """API 根路径"""
    return {
        "message": "心屿 Xinyu API",
        "version": "1.0.0",
        "status": "running"
    }

# 健康检查
@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}
