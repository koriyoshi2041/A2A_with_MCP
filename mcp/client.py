#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - MCP客户端
实现与外部MCP服务的交互，支持多服务调用
"""

import os
import sys
import json
import time
import asyncio
import logging
import traceback
from typing import Dict, List, Any, Optional, Callable, Union, Tuple

import aiohttp
import requests

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp.config import (
    get_mcp_service_url, get_service_url, get_auth_headers,
    get_request_timeout, get_max_retries, get_all_services
)
from utils.logging import get_logger, log_function_call, log_async_function_call

logger = get_logger(__name__)

class MCPClientException(Exception):
    """MCP客户端异常"""
    pass

class ToolNotFoundException(MCPClientException):
    """工具未找到异常"""
    pass

class ServiceUnavailableException(MCPClientException):
    """服务不可用异常"""
    pass

class MCPClient:
    """MCP协议客户端
    
    负责与MCP服务进行通信，获取工具列表和调用工具执行操作
    支持多服务调用
    """
    
    def __init__(self, 
                 service_name: Optional[str] = None,
                 api_key: Optional[str] = None):
        """初始化MCP客户端
        
        Args:
            service_name: 服务名称，如果为None则使用默认服务
            api_key: MCP服务API密钥，如果为None则使用配置中的API密钥
        """
        self.service_name = service_name
        self.api_key = api_key
        
        # 创建会话字典，为每个服务保留一个会话
        self.sessions = {}
        
        logger.info(f"初始化MCP客户端: {service_name if service_name else '默认'}")
    
    def _get_service_url(self, service_name: Optional[str] = None) -> str:
        """获取服务URL
        
        Args:
            service_name: 服务名称，如果为None则使用初始化时的服务名称
            
        Returns:
            str: 服务URL
        
        Raises:
            MCPClientException: 服务URL未配置时抛出
        """
        name = service_name or self.service_name
        if name:
            url = get_service_url(name)
        else:
            url = get_mcp_service_url()
            
        if not url:
            raise MCPClientException(f"MCP服务 {name if name else '默认'} 的URL未配置")
            
        return url
    
    def _get_timeout(self, service_name: Optional[str] = None) -> int:
        """获取服务超时时间
        
        Args:
            service_name: 服务名称，如果为None则使用初始化时的服务名称
            
        Returns:
            int: 超时时间(秒)
        """
        name = service_name or self.service_name
        return get_request_timeout(name)
    
    async def _get_session(self, service_url: str) -> aiohttp.ClientSession:
        """获取或创建HTTP会话
        
        Args:
            service_url: 服务URL
            
        Returns:
            aiohttp.ClientSession: HTTP会话
        """
        if service_url not in self.sessions or self.sessions[service_url].closed:
            headers = get_auth_headers()
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
                
            timeout = self._get_timeout(self.service_name)
            self.sessions[service_url] = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            )
            
        return self.sessions[service_url]
    
    async def _close_sessions(self) -> None:
        """关闭所有HTTP会话"""
        for url, session in self.sessions.items():
            if not session.closed:
                await session.close()
        self.sessions = {}
    
    @log_async_function_call
    async def get_tools(self, service_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取可用工具列表
        
        Args:
            service_name: 服务名称，如果为None则使用初始化时的服务名称
        
        Returns:
            List[Dict[str, Any]]: 可用工具列表
        
        Raises:
            MCPClientException: 获取工具列表失败时抛出
        """
        service_url = self._get_service_url(service_name)
        endpoint = f"{service_url}/tools"
        
        try:
            session = await self._get_session(service_url)
            async with session.get(endpoint) as response:
                if response.status == 404:
                    logger.warning(f"服务 {service_name if service_name else '默认'} 的工具端点不存在")
                    return []
                    
                if response.status != 200:
                    error_text = await response.text()
                    raise MCPClientException(
                        f"获取工具列表失败: HTTP状态码 {response.status}, 响应: {error_text}"
                    )
                
                result = await response.json()
                logger.info(f"从服务 {service_name if service_name else '默认'} 获取到 {len(result)} 个工具")
                return result
                
        except aiohttp.ClientError as e:
            logger.error(f"获取工具列表时网络错误: {str(e)}")
            raise ServiceUnavailableException(f"服务 {service_name if service_name else '默认'} 不可用: {str(e)}")
        except json.JSONDecodeError as e:
            raise MCPClientException(f"解析工具列表响应失败: {str(e)}")
        except Exception as e:
            raise MCPClientException(f"获取工具列表时发生未知错误: {str(e)}")
    
    @log_async_function_call
    async def call_tool(self, 
                      tool_name: str, 
                      params: Dict[str, Any],
                      service_name: Optional[str] = None,
                      stream: bool = False) -> Dict[str, Any]:
        """调用工具
        
        Args:
            tool_name: 工具名称
            params: 工具参数
            service_name: 服务名称，如果为None则使用初始化时的服务名称
            stream: 是否使用流式响应
        
        Returns:
            Dict[str, Any]: 工具执行结果
        
        Raises:
            MCPClientException: 调用工具失败时抛出
        """
        service_url = self._get_service_url(service_name)
        endpoint = f"{service_url}/run/{tool_name}"
        
        if stream:
            endpoint += "?stream=true"
        
        try:
            session = await self._get_session(service_url)
            
            if not stream:
                # 常规调用
                async with session.post(endpoint, json=params) as response:
                    if response.status == 404:
                        raise ToolNotFoundException(f"工具 '{tool_name}' 在服务 {service_name if service_name else '默认'} 中不存在")
                        
                    if response.status != 200:
                        error_text = await response.text()
                        raise MCPClientException(
                            f"调用工具 '{tool_name}' 失败: HTTP状态码 {response.status}, 响应: {error_text}"
                        )
                    
                    result = await response.json()
                    return result
            else:
                # 流式调用
                result = {"chunks": []}
                async with session.post(endpoint, json=params) as response:
                    if response.status == 404:
                        raise ToolNotFoundException(f"工具 '{tool_name}' 在服务 {service_name if service_name else '默认'} 中不存在")
                        
                    if response.status != 200:
                        error_text = await response.text()
                        raise MCPClientException(
                            f"调用工具 '{tool_name}' 流式模式失败: HTTP状态码 {response.status}, 响应: {error_text}"
                        )
                    
                    # 处理SSE（Server-Sent Events）格式
                    async for line in response.content:
                        line = line.decode('utf-8').strip()
                        if line.startswith('data:'):
                            data_str = line[5:].strip()
                            if data_str:
                                try:
                                    data = json.loads(data_str)
                                    if 'chunk' in data:
                                        result["chunks"].append(data["chunk"])
                                        yield data  # 生成器模式，将每个块传递给调用者
                                except json.JSONDecodeError:
                                    logger.warning(f"无法解析流式响应: {data_str}")
                
                # 合并所有块
                result["content"] = "".join(result["chunks"])
                return result
                
        except aiohttp.ClientError as e:
            logger.error(f"调用工具 '{tool_name}' 时网络错误: {str(e)}")
            raise ServiceUnavailableException(f"服务 {service_name if service_name else '默认'} 不可用: {str(e)}")
        except json.JSONDecodeError as e:
            raise MCPClientException(f"解析工具 '{tool_name}' 响应失败: {str(e)}")
        except (ToolNotFoundException, ServiceUnavailableException):
            raise
        except Exception as e:
            raise MCPClientException(f"调用工具 '{tool_name}' 时发生未知错误: {str(e)}")
    
    async def call_tool_with_retry(self,
                                tool_name: str,
                                params: Dict[str, Any],
                                service_name: Optional[str] = None,
                                max_retries: Optional[int] = None,
                                stream: bool = False) -> Dict[str, Any]:
        """带重试的工具调用
        
        Args:
            tool_name: 工具名称
            params: 工具参数
            service_name: 服务名称，如果为None则使用初始化时的服务名称
            max_retries: 最大重试次数，如果为None则使用配置中的重试次数
            stream: 是否使用流式响应
            
        Returns:
            Dict[str, Any]: 工具执行结果
        
        Raises:
            MCPClientException: 重试后仍然失败时抛出
        """
        retries = max_retries if max_retries is not None else get_max_retries()
        retry_count = 0
        
        while True:
            try:
                return await self.call_tool(tool_name, params, service_name, stream)
            except (MCPClientException, aiohttp.ClientError) as e:
                retry_count += 1
                if retry_count > retries or isinstance(e, ToolNotFoundException):
                    raise
                
                wait_time = 2 ** retry_count  # 指数退避
                logger.warning(f"调用工具 '{tool_name}' 失败，将在 {wait_time} 秒后进行第 {retry_count} 次重试: {str(e)}")
                await asyncio.sleep(wait_time)
    
    @log_async_function_call
    async def discover_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """发现所有服务中可用的工具
        
        Returns:
            Dict[str, List[Dict[str, Any]]]: 按服务名称分组的工具列表
        """
        services = get_all_services()
        results = {}
        
        for service_name, _ in services.items():
            try:
                tools = await self.get_tools(service_name)
                results[service_name] = tools
            except Exception as e:
                logger.error(f"获取服务 {service_name} 的工具列表失败: {str(e)}")
                results[service_name] = []
                
        return results
    
    async def close(self) -> None:
        """关闭客户端，释放资源"""
        await self._close_sessions()
    
    async def __aenter__(self):
        """支持异步上下文管理器"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出异步上下文管理器"""
        await self.close()

# 简单的服务健康检查
async def check_service_health(service_name: str) -> bool:
    """检查MCP服务的健康状态
    
    Args:
        service_name: 服务名称
        
    Returns:
        bool: 服务是否可用
    """
    try:
        client = MCPClient(service_name)
        await client.get_tools()
        await client.close()
        return True
    except Exception:
        return False

# 测试函数
async def test_mcp_client():
    """测试MCP客户端"""
    try:
        async with MCPClient() as client:
            print("\n--- 发现可用工具 ---")
            all_tools = await client.discover_tools()
            for service_name, tools in all_tools.items():
                print(f"\n服务 '{service_name}' 有 {len(tools)} 个工具:")
                for tool in tools:
                    print(f"  - {tool['name']}: {tool['description']}")
                
            if all_tools:
                # 尝试调用第一个发现的工具
                first_service = next(iter(all_tools.keys()))
                if all_tools[first_service]:
                    first_tool = all_tools[first_service][0]
                    print(f"\n--- 测试调用工具 '{first_tool['name']}' ---")
                    # 构造一个简单的参数字典，实际使用时应该根据工具的inputSchema来构造
                    result = await client.call_tool_with_retry(
                        first_tool['name'],
                        {"test": "value"},
                        first_service
                    )
                    print(f"调用结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"测试失败: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mcp_client()) 