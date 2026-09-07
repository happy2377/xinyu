"""FastAPI 应用启动入口"""
import os

from dotenv import load_dotenv

# 必须在导入 app 模块之前加载环境变量，否则各服务初始化时读不到 .env
load_dotenv()

import uvicorn
from app.main import app

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,  # 开发模式自动重载
        log_level="info"
    )
