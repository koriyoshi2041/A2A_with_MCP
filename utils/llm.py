#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - LLM工具
提供与LLM交互的功能
"""

import os
import sys
import json
import asyncio
from typing import List, Dict, Any, Optional, Union, AsyncGenerator, Callable

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入日志
from utils.logging import get_logger
logger = get_logger(__name__)

try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    logger.warning("OpenAI库未安装，使用模拟LLM")
    OPENAI_AVAILABLE = False

import aiohttp
import requests

# LLM API配置
DEFAULT_LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
LLM_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "2000"))
LLM_API_TIMEOUT = 60

# 模拟响应，用于测试或OpenAI不可用时
MOCK_RESPONSES = {
    "search": "模拟搜索结果: 找到关于此主题的10篇文章",
    "outline": {
        "title": "模拟故事标题",
        "sections": [
            {"id": "section1", "title": "引言", "content": "故事开始..."},
            {"id": "section2", "title": "发展", "content": "故事发展..."},
            {"id": "section3", "title": "高潮", "content": "故事高潮..."},
            {"id": "section4", "title": "结局", "content": "故事结束..."}
        ]
    },
    "write": "模拟写作内容: 这是一段生成的故事内容...",
    "edit": "模拟编辑内容: 这是修改后的更流畅的故事内容..."
}

class LLMClient:
    """LLM客户端类，封装与LLM的交互"""
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 model: str = DEFAULT_LLM_MODEL,
                 temperature: float = LLM_TEMPERATURE,
                 max_tokens: int = LLM_MAX_TOKENS):
        """
        初始化LLM客户端
        
        Args:
            api_key: OpenAI API密钥，如果为None则尝试从环境变量获取
            model: 使用的模型名称
            temperature: 温度参数，控制随机性
            max_tokens: 最大生成令牌数
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # 如果未提供API密钥，尝试从环境变量获取
        self.api_key = api_key or LLM_API_KEY
        
        if OPENAI_AVAILABLE and self.api_key:
            self.client = AsyncOpenAI(api_key=self.api_key)
            logger.info(f"已初始化OpenAI客户端，使用模型: {model}")
        else:
            self.client = None
            logger.warning("使用模拟LLM响应")
    
    async def generate(self, 
                      prompt: str, 
                      system_message: Optional[str] = None) -> str:
        """
        生成文本响应
        
        Args:
            prompt: 用户提示
            system_message: 系统消息
            
        Returns:
            生成的响应文本
        """
        # 准备消息
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        # 使用OpenAI客户端或模拟响应
        if self.client:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.error(f"OpenAI API调用失败: {str(e)}")
                # 发生错误时回退到模拟响应
                return self._get_mock_response(prompt)
        else:
            # 使用模拟响应
            return self._get_mock_response(prompt)
    
    async def generate_with_streaming(self, 
                                     prompt: str, 
                                     system_message: Optional[str] = None):
        """
        生成流式响应
        
        Args:
            prompt: 用户提示
            system_message: 系统消息
            
        Yields:
            生成的部分响应
        """
        # 准备消息
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        
        # 使用OpenAI流式API或模拟流式响应
        if self.client:
            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=True
                )
                
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            except Exception as e:
                logger.error(f"OpenAI流式API调用失败: {str(e)}")
                # 发生错误时回退到模拟流式响应
                mock_response = self._get_mock_response(prompt)
                # 如果是字符串，分段返回
                if isinstance(mock_response, str):
                    for i in range(0, len(mock_response), 5):
                        yield mock_response[i:i+5]
                        await asyncio.sleep(0.1)
                else:
                    # 如果是对象，返回JSON字符串
                    mock_str = json.dumps(mock_response, ensure_ascii=False)
                    for i in range(0, len(mock_str), 5):
                        yield mock_str[i:i+5]
                        await asyncio.sleep(0.1)
        else:
            # 使用模拟流式响应
            mock_response = self._get_mock_response(prompt)
            # 如果是字符串，分段返回
            if isinstance(mock_response, str):
                for i in range(0, len(mock_response), 5):
                    yield mock_response[i:i+5]
                    await asyncio.sleep(0.1)
            else:
                # 如果是对象，返回JSON字符串
                mock_str = json.dumps(mock_response, ensure_ascii=False)
                for i in range(0, len(mock_str), 5):
                    yield mock_str[i:i+5]
                    await asyncio.sleep(0.1)
    
    def _get_mock_response(self, prompt: str) -> Union[str, Dict]:
        """根据提示选择合适的模拟响应"""
        prompt_lower = prompt.lower()
        
        if "搜索" in prompt_lower or "search" in prompt_lower:
            return MOCK_RESPONSES["search"]
        elif "大纲" in prompt_lower or "outline" in prompt_lower:
            return MOCK_RESPONSES["outline"]
        elif "编辑" in prompt_lower or "edit" in prompt_lower:
            return MOCK_RESPONSES["edit"]
        else:
            return MOCK_RESPONSES["write"]

# 创建默认LLM客户端实例
default_llm_client = LLMClient()

async def generate_text(
    prompt: str,
    system_message: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = LLM_MAX_TOKENS
) -> str:
    """生成文本
    
    使用LLM生成文本
    
    Args:
        prompt: 用户提示
        system_message: 系统消息
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大生成token数
        
    Returns:
        生成的文本
    """
    # 创建LLM客户端
    client = LLMClient(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )
    
    # 生成响应
    return await client.generate(prompt, system_message)

async def generate_streaming(
    prompt: str,
    callback: Callable[[str], None],
    system_message: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = LLM_MAX_TOKENS
) -> str:
    """生成流式文本
    
    使用LLM生成流式文本，通过回调函数返回每个部分
    
    Args:
        prompt: 用户提示
        callback: 处理每个生成部分的回调函数
        system_message: 系统消息
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大生成token数
        
    Returns:
        完整的生成文本
    """
    # 创建LLM客户端
    client = LLMClient(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens
    )
    
    # 存储完整响应
    full_response = ""
    
    # 生成流式响应
    async for chunk in client.generate_with_streaming(prompt, system_message):
        callback(chunk)
        full_response += chunk
        
    return full_response

def generate_text_sync(
    prompt: str,
    system_message: Optional[str] = None,
    model: str = DEFAULT_LLM_MODEL,
    temperature: float = LLM_TEMPERATURE,
    max_tokens: int = LLM_MAX_TOKENS
) -> str:
    """同步生成文本
    
    使用LLM同步生成文本
    
    Args:
        prompt: 用户提示
        system_message: 系统消息
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大生成token数
        
    Returns:
        生成的文本
    """
    # 创建事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # 运行异步函数
        return loop.run_until_complete(
            generate_text(
                prompt, 
                system_message, 
                model, 
                temperature, 
                max_tokens
            )
        )
    finally:
        # 关闭事件循环
        loop.close()

async def test_llm():
    """测试LLM功能"""
    print("测试LLM生成功能...")
    
    # 测试文本生成
    prompt = "写一个短故事，主题是太空探险"
    system_message = "你是一个创意故事作家。"
    
    print(f"\n1. 测试简单文本生成:")
    text = await generate_text(prompt, system_message)
    print(f"生成结果:\n{text}\n")
    
    # 测试流式生成
    print(f"\n2. 测试流式文本生成:")
    
    collected_chunks = []
    
    def callback(chunk):
        collected_chunks.append(chunk)
        print(chunk, end="", flush=True)
        
    await generate_streaming(prompt, callback, system_message)
    print("\n\n流式生成完成，共收到", len(collected_chunks), "个文本块")

if __name__ == "__main__":
    asyncio.run(test_llm()) 