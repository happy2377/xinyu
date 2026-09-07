"""模型路由器 - 根据感知规划结果选择合适的模型服务"""
import os
import logging
import asyncio
from typing import Union, AsyncGenerator
import ollama
import httpx

logger = logging.getLogger(__name__)

class LocalModelService:
    """本地模型服务（Ollama）"""
    
    def __init__(self, model: str = "Ethanwhh/Qwen3-4B-xinyi"):
        self.model = model
        self.client = ollama.AsyncClient()
    
    async def generate_with_prompt(self, system_prompt, user_input, conversation_history, stream=True):
        """生成响应"""
        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_input})
        
        try:
            if stream:
                # 流式响应
                stream_response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    stream=True
                )
                async for chunk in stream_response:
                    if 'message' in chunk and 'content' in chunk['message']:
                        yield chunk['message']['content']
            else:
                # 非流式响应
                response = await self.client.chat(
                    model=self.model,
                    messages=messages,
                    stream=False
                )
                yield response['message']['content']
        except Exception as e:
            yield f"[错误] 本地模型调用失败: {str(e)}"


class RemoteModelService:
    """
    魔搭 ModelScope 云端模型服务
    使用 Qwen/Qwen3-Next-80B-A3B-Instruct 模型
    """
    
    def __init__(self):
        # 从环境变量读取 API Key
        self.api_key = os.getenv("MODELSCOPE_API_KEY", "")
        self.api_key_ready = bool(self.api_key) and not self.api_key.startswith("your_")
        self.model_name = os.getenv(
            "CHAT_MODEL", "Qwen/Qwen3-Next-80B-A3B-Instruct"
        )
        # ModelScope 官方推理 API
        self.base_url = "https://api-inference.modelscope.cn/v1/chat/completions"
    
    async def generate_with_prompt(
        self,
        system_prompt: str,
        user_input: str,
        conversation_history: list,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        使用系统提示词生成响应
        :param system_prompt: 系统提示词
        :param user_input: 用户输入
        :param conversation_history: 对话历史
        :param stream: 是否流式响应
        :yield: 响应文本片段
        """
        if not self.api_key_ready:
            yield "错误：云端模型未配置有效的 API Key。请先在 backend/.env 中填写 MODELSCOPE_API_KEY 后重启服务。"
            return
        
        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_input})
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            "max_tokens": 2000,
            "temperature": 0.7,
            "top_p": 0.8
        }
        
        last_error = None
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    if stream:
                        # 流式响应
                        async with client.stream(
                            "POST",
                            self.base_url,
                            headers=headers,
                            json=payload
                        ) as response:
                            if response.status_code != 200:
                                error_text = await response.aread()
                                error_msg = (
                                    f"云端模型调用失败 ({response.status_code}): "
                                    f"{error_text.decode()}"
                                )
                                if response.status_code == 429 and attempt < 3:
                                    logger.warning("触发限流，第 %d 次重试", attempt + 1)
                                    await asyncio.sleep(5 + attempt * 8)
                                    continue
                                logger.error(error_msg)
                                yield f"错误：{error_msg}"
                                return

                            async for line in response.aiter_lines():
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        import json
                                        data = json.loads(data_str)
                                        if "choices" in data and len(data["choices"]) > 0:
                                            delta = data["choices"][0].get("delta", {})
                                            content = delta.get("content", "")
                                            if content:
                                                yield content
                                    except json.JSONDecodeError:
                                        continue
                    else:
                        # 非流式响应
                        response = await client.post(
                            self.base_url,
                            headers=headers,
                            json=payload
                        )
                        if response.status_code != 200:
                            error_msg = (
                                f"云端模型调用失败 ({response.status_code}): "
                                f"{response.text}"
                            )
                            if response.status_code == 429 and attempt < 3:
                                logger.warning("触发限流，第 %d 次重试", attempt + 1)
                                await asyncio.sleep(5 + attempt * 8)
                                continue
                            logger.error(error_msg)
                            yield f"错误：{error_msg}"
                            return
                        result = response.json()
                        if "choices" in result and len(result["choices"]) > 0:
                            content = result["choices"][0]["message"]["content"]
                            yield content
                break
            except httpx.TimeoutException:
                last_error = "云端模型响应超时，请稍后重试"
                logger.error(last_error)
                if attempt < 3:
                    await asyncio.sleep(3 + attempt * 5)
                    continue
                yield f"错误：{last_error}"
                return
            except Exception as e:
                last_error = f"云端模型调用异常 - {type(e).__name__}: {str(e)}"
                logger.error(last_error)
                if attempt < 3:
                    await asyncio.sleep(3 + attempt * 5)
                    continue
                yield f"错误：{last_error}"
                return


class ModelRouter:
    """
    模型路由器
    根据感知规划模块的判断结果，选择使用本地模型或远程模型
    """
    
    def __init__(self):
        self.local_service = LocalModelService(model="Ethanwhh/Qwen3-4B-xinyi")
        self.remote_service = RemoteModelService()
        # 一期采用魔搭云端单平台；设置 USE_LOCAL_MODEL=true 可恢复“隐私走本地”的原逻辑
        self.use_local = os.getenv("USE_LOCAL_MODEL", "false").lower() in ("1", "true", "yes")
    
    def get_model_service(
        self,
        is_privacy_issue: bool,
        is_complex_issue: bool
    ) -> Union[LocalModelService, RemoteModelService]:
        """
        根据双层判断结果返回合适的模型服务
        
        路由逻辑：
        1. 隐私问题 → 强制使用本地模型（保护隐私）
        2. 复杂问题 → 使用云端大模型（Qwen3-Next-80B）
        3. 简单问答 → 使用本地模型（Qwen3-4B）
        
        :param is_privacy_issue: 是否为隐私问题
        :param is_complex_issue: 是否为复杂问题
        :return: 模型服务实例
        """
        if not self.use_local:
            # 一期默认全部走云端（魔搭）
            return self.remote_service
        if is_privacy_issue:
            # 隐私问题强制本地（可选）
            return self.local_service
        elif is_complex_issue:
            return self.remote_service
        else:
            return self.local_service
    
    def get_model_name(
        self,
        is_privacy_issue: bool,
        is_complex_issue: bool
    ) -> str:
        """返回模型名称（用于日志记录）"""
        if not self.use_local:
            return "remote-Qwen3-Next-80B"
        if is_privacy_issue:
            return "local-Qwen3-4B"
        elif is_complex_issue:
            return "remote-Qwen3-Next-80B"
        else:
            return "local-Qwen3-4B"


# 全局路由器实例
model_router = ModelRouter()
