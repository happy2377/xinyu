"""统一 LLM 服务（ModelScope OpenAI 兼容接口）。

负责三类调用：
1. chat()            —— 普通文本补全（结构化任务）
2. chat_json()       —— 要求模型返回 JSON 并解析
3. embed_texts()     —— 文本向量化（RAG / 记忆检索共用）
"""
import json
import logging
import os
import asyncio
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

from .database import SessionLocal

# 模块导入即加载 .env（uvicorn 从 backend 目录启动；也兼容被主模块提前 import 的情况）
load_dotenv()

DEFAULT_BASE_URL = "https://api-inference.modelscope.cn/v1"
DEFAULT_CHAT_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"
DEFAULT_EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"


class LlmService:
    """基于 httpx 的轻量 OpenAI 兼容客户端，全部请求走同一 base_url。"""

    def __init__(self) -> None:
        self.api_key = os.getenv("MODELSCOPE_API_KEY", "")
        self.base_url = os.getenv("MODELSCOPE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.chat_model = os.getenv("CHAT_MODEL", DEFAULT_CHAT_MODEL)
        self.embed_model = os.getenv("EMBEDDING_MODEL", DEFAULT_EMBED_MODEL)
        self.vision_model = os.getenv(
            "VISION_MODEL", "Qwen/Qwen3-VL-8B-Instruct"
        )
        self.timeout = float(os.getenv("LLM_TIMEOUT", "90"))

    @property
    def available(self) -> bool:
        return bool(self.api_key) and not self.api_key.startswith("your_")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1500,
        model: str | None = None,
        mode: str = "generic",
    ) -> str:
        """非流式文本补全，返回完整内容。"""
        if not self.available:
            raise RuntimeError("MODELSCOPE_API_KEY 未配置")
        payload = {
            "model": model or self.chat_model,
            "messages": messages,
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
                    if resp.status_code != 200:
                        raise RuntimeError(
                            f"LLM 调用失败 ({resp.status_code}): {resp.text[:300]}"
                        )
                    data = resp.json()
                    record_llm_call(model or self.chat_model, data.get("usage"), mode)
                    return data["choices"][0]["message"]["content"]
            except Exception as e:
                last_error = e
                logger.warning("LLM 调用第 %d 次失败: %s", attempt + 1, e)
                await asyncio.sleep(3 + attempt * 5)
        raise RuntimeError(f"LLM 重试后仍失败: {last_error}")

    async def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 1500,
        model: str | None = None,
        mode: str = "generic",
    ) -> Dict[str, Any]:
        """要求模型输出 JSON 并尽力解析。"""
        text = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            mode=mode,
        )
        return _parse_json(text)

    async def chat_vision(
        self,
        image_data_url: str,
        text: str,
        max_tokens: int = 500,
        mode: str = "vision",
    ) -> str:
        """多模态：把图片 data URL 与文本一起发给视觉模型（OpenAI 兼容格式）。"""
        if not self.available:
            raise RuntimeError("MODELSCOPE_API_KEY 未配置")
        if not image_data_url.startswith("data:image/"):
            raise RuntimeError("图片格式错误：需要 data:image/... 的 data URL")
        payload = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url},
                        },
                        {"type": "text", "text": text[:2000]},
                    ],
                }
            ],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
                    if resp.status_code != 200:
                        raise RuntimeError(
                            f"视觉模型调用失败 ({resp.status_code}): {resp.text[:300]}"
                        )
                    data = resp.json()
                    record_llm_call(self.vision_model, data.get("usage"), mode)
                    content = data["choices"][0]["message"].get("content", "")
                    if not content:
                        raise RuntimeError("视觉模型未返回内容")
                    return content
            except Exception as e:
                last_error = e
                logger.warning("视觉模型第 %d 次失败: %s", attempt + 1, e)
                await asyncio.sleep(2 + attempt * 3)
        raise RuntimeError(f"视觉模型重试后仍失败: {last_error}")

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量文本向量化。"""
        if not self.available:
            raise RuntimeError("MODELSCOPE_API_KEY 未配置")
        if not texts:
            return []
        payload = {
            "model": self.embed_model,
            "input": texts,
            "encoding_format": "float",
        }
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/embeddings",
                        headers=self._headers(),
                        json=payload,
                    )
                    if resp.status_code != 200:
                        raise RuntimeError(
                            f"Embedding 调用失败 ({resp.status_code}): {resp.text[:300]}"
                        )
                    data = resp.json()
                    result = []
                    for item in data["data"]:
                        emb = item.get("embedding") or item.get("vector")
                        if emb is None:
                            raise RuntimeError(
                                "Embedding 响应格式不包含 embedding 字段"
                            )
                        result.append(emb)
                    return result
            except Exception as e:
                last_error = e
                logger.warning("Embedding 调用第 %d 次失败: %s", attempt + 1, e)
                await asyncio.sleep(3 + attempt * 5)
        raise RuntimeError(f"Embedding 重试后仍失败: {last_error}")


def _parse_json(text: str) -> Dict[str, Any]:
    """解析模型输出中的 JSON：容忍 ```json 代码块和前后噪声。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.strip()
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except Exception:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except Exception:
                pass
    logger.warning("模型 JSON 解析失败，返回空对象: %s", text[:200])
    return {}


def record_llm_call(model: str, usage: dict | None, mode: str = "generic") -> None:
    """尽力写入一次 LLM 用量统计；失败只记日志，绝不阻断主流程。"""
    if not usage or not isinstance(usage, dict):
        return
    try:
        from .models import LlmCallStats

        prompt = int(usage.get("prompt_tokens") or 0)
        details = usage.get("prompt_tokens_details") or {}
        cached = 0
        if isinstance(details, dict):
            cached = int(details.get("cached_tokens") or 0)
        total = int(usage.get("total_tokens") or 0)
        db = SessionLocal()
        try:
            db.add(
                LlmCallStats(
                    mode=mode,
                    model=(model or "")[:100],
                    prompt_tokens=prompt,
                    cached_tokens=cached,
                    total_tokens=total,
                )
            )
            db.commit()
        finally:
            db.close()
    except Exception as e:  # pragma: no cover - 统计失败不应影响对话
        logger.warning("LLM 调用统计写入失败（跳过）: %s", e)


# 全局共享实例
llm_service = LlmService()
