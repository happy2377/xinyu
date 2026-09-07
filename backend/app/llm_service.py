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

logger = logging.getLogger(__name__)

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
    ) -> Dict[str, Any]:
        """要求模型输出 JSON 并尽力解析。"""
        text = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )
        return _parse_json(text)

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


# 全局共享实例
llm_service = LlmService()
