#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - 节点定义
实现故事生成所需的各种节点
"""

import os
import sys
import asyncio
import json
from typing import Dict, List, Any, Optional, Union
import traceback
import uuid

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入PocketFlow核心库
from pocketflow import Node, AsyncNode, AsyncParallelBatchNode, Flow, AsyncFlow

# 导入项目模块
from utils.logging import get_logger, log_async_function_call
from utils.progress import update_progress
from utils.llm import generate_text, generate_streaming
from mcp.client import get_tools, call_tool, check_service_health, MCPClient, MCPClientException
from config import MAX_RETRIES
from a2a.schema import AgentRole, MessageType, StoryOutline, StorySection

logger = get_logger(__name__)

class BaseStoryNode(AsyncNode):
    """
    故事生成基础节点
    提供通用功能
    """
    
    async def update_progress(self, shared, progress, message, artifacts=None):
        """
        更新任务进度
        
        Args:
            shared: 共享存储
            progress: 进度(0.0-1.0)
            message: 进度消息
            artifacts: 附加数据
        """
        task_id = shared.get("task_id")
        if not task_id:
            logger.warning("无法更新进度：缺少task_id")
            return
            
        tracker = shared.get("progress_tracker")
        if tracker:
            tracker.update_progress(task_id, progress, message, artifacts)
        else:
            logger.warning("无法更新进度：缺少progress_tracker")
    
    async def get_mcp_tools(self, shared, service_type):
        """
        获取MCP工具列表
        
        Args:
            shared: 共享存储
            service_type: 服务类型
            
        Returns:
            工具列表
        """
        # 检查缓存
        mcp_tools = shared.get("mcp_tools", {})
        if service_type in mcp_tools:
            return mcp_tools[service_type]
            
        # 获取工具
        try:
            tools = await get_tools(service_type)
            
            # 更新缓存
            if "mcp_tools" not in shared:
                shared["mcp_tools"] = {}
            shared["mcp_tools"][service_type] = tools
            
            return tools
        except Exception as e:
            logger.error(f"获取MCP工具失败: {str(e)}")
            return []

class ToolDiscoveryNode(BaseStoryNode):
    """
    工具发现节点
    用于获取所有可用的MCP工具
    """
    
    async def prep_async(self, shared):
        """准备阶段：获取服务类型列表"""
        # 存储shared以便在其他方法中使用
        self._shared = shared
        
        # 创建MCP客户端
        self.mcp_client = MCPClient()
        
        # 不再硬编码服务类型，而是从配置或动态发现
        return None
    
    async def exec_async(self, prep_res):
        """执行阶段：获取每种服务的工具"""
        try:
            # 使用MCPClient的discover_tools方法来发现所有可用的MCP工具
            all_services_tools = {}
            
            # 定义我们需要的服务类型
            required_services = ["search", "outline", "writing", "editing"]
            
            # 直接获取每种服务的工具
            for service_type in required_services:
                try:
                    tools = await get_tools(service_type)
                    if tools:
                        all_services_tools[service_type] = {
                            "healthy": True,
                            "tools": tools
                        }
                    else:
                        logger.warning(f"服务 {service_type} 没有可用工具")
                        all_services_tools[service_type] = {
                            "healthy": False,
                            "tools": []
                        }
                except Exception as e:
                    logger.error(f"获取服务 {service_type} 的工具失败: {str(e)}")
                    all_services_tools[service_type] = {
                        "healthy": False,
                        "tools": [],
                        "error": str(e)
                    }
                    
            # 检查结果
            if not all_services_tools:
                logger.warning("没有找到任何MCP服务")
                
            return all_services_tools
        except Exception as e:
            logger.error(f"发现工具失败: {str(e)}")
            traceback.print_exc()
            return {}
    
    async def post_async(self, shared, prep_res, exec_res):
        """后处理阶段：存储工具信息到共享存储"""
        # 存储工具信息
        shared["mcp_tools"] = {}
        
        available_services = []
        for service_type, result in exec_res.items():
            if result["healthy"]:
                shared["mcp_tools"][service_type] = result["tools"]
                available_services.append(service_type)
                
        # 记录可用服务
        shared["available_services"] = available_services
        
        # 更新进度
        message = f"发现了{len(available_services)}种可用服务"
        await self.update_progress(shared, 0.1, message)
        
        # 决定下一步
        if not available_services:
            logger.error("没有可用的MCP服务")
            return "error"
            
        return "default"
    
    async def exec_fallback_async(self, prep_res, exc):
        """异常处理：工具发现失败"""
        logger.error(f"工具发现失败: {str(exc)}")
        return {
            "search": {"healthy": False, "tools": []},
            "outline": {"healthy": False, "tools": []},
            "writing": {"healthy": False, "tools": []},
            "editing": {"healthy": False, "tools": []}
        }

class SearchNode(BaseStoryNode):
    """
    搜索节点
    执行主题搜索以获取相关信息
    """
    
    async def prep_async(self, shared):
        """准备阶段：获取搜索查询"""
        # 获取用户输入
        inputs = shared.get("inputs", {})
        prompt = inputs.get("prompt", "")
        
        # 检查是否已有搜索查询
        if "search_queries" not in shared:
            shared["search_queries"] = []
            
        # 从提示生成搜索查询
        system_message = """
        你是一个提取搜索关键词的助手。从用户的故事创作请求中提取2-3个最重要的搜索关键词。
        只返回关键词列表，每行一个，不要有标点符号或序号。
        """
        
        # 存储shared以便在exec_async中使用
        self._shared = shared
        
        # 检查服务可用性
        available_services = shared.get("available_services", [])
        if "search" not in available_services:
            logger.warning("搜索服务不可用")
            return None
            
        return prompt, system_message
    
    async def exec_async(self, inputs):
        """执行阶段：生成搜索查询并执行搜索"""
        if inputs is None:
            return {"queries": [], "results": {}}
            
        prompt, system_message = inputs
        
        # 生成搜索查询
        try:
            queries_text = await generate_text(prompt, system_message)
            queries = [q.strip() for q in queries_text.split("\n") if q.strip()]
            
            # 限制查询数量
            queries = queries[:3]
            
            # 执行搜索
            results = {}
            
            # 使用MCP客户端执行搜索
            for query in queries:
                try:
                    # 调用MCP服务执行搜索
                    result = await call_tool(
                        "search",
                        {"query": query, "max_results": 3},
                        self._shared.get("mcp_service_url")
                    )
                    
                    # 处理结果
                    if isinstance(result, dict):
                        results[query] = result
                    else:
                        logger.warning(f"搜索查询 '{query}' 返回了无效结果")
                        results[query] = {"text": "没有找到相关结果", "error": "无效的响应格式"}
                        
                except Exception as e:
                    logger.error(f"搜索查询 '{query}' 失败: {str(e)}")
                    results[query] = {"text": "搜索过程中出错", "error": str(e)}
                    
                # 添加短暂延迟避免频率限制
                await asyncio.sleep(0.5)
                    
            return {"queries": queries, "results": results}
        except Exception as e:
            logger.error(f"搜索失败: {str(e)}")
            traceback.print_exc()
            return {"queries": [], "results": {}, "error": str(e)}
    
    async def post_async(self, shared, prep_res, exec_res):
        """后处理阶段：存储搜索结果"""
        queries = exec_res.get("queries", [])
        results = exec_res.get("results", {})
        
        # 存储搜索查询和结果
        if "search_queries" not in shared:
            shared["search_queries"] = []
        if "search_results" not in shared:
            shared["search_results"] = {}
            
        shared["search_queries"].extend(queries)
        shared["search_results"].update(results)
        
        # 更新进度
        message = f"完成了{len(queries)}个搜索查询"
        await self.update_progress(shared, 0.2, message)
        
        return "default"
    
    async def exec_fallback_async(self, prep_res, exc):
        """异常处理：搜索失败"""
        logger.error(f"搜索失败: {str(exc)}")
        return {"queries": [], "results": {}, "error": str(exc)}

class OutlineNode(BaseStoryNode):
    """
    大纲生成节点
    基于搜索结果和用户输入生成故事大纲
    """
    
    async def prep_async(self, shared):
        """准备阶段：获取搜索结果和用户输入"""
        # 获取用户输入
        inputs = shared.get("inputs", {})
        prompt = inputs.get("prompt", "")
        
        # 获取搜索结果
        search_results = shared.get("search_results", {})
        search_context = ""
        
        for query, result in search_results.items():
            if isinstance(result, dict) and "text" in result:
                search_context += f"关于\"{query}\"的信息:\n{result['text']}\n\n"
            elif isinstance(result, str):
                search_context += f"关于\"{query}\"的信息:\n{result}\n\n"
                
        # 存储shared以便在exec_async中使用
        self._shared = shared
                
        # 检查服务可用性
        available_services = shared.get("available_services", [])
        if "outline" not in available_services:
            logger.warning("大纲服务不可用")
            # 尝试使用LLM生成简单大纲
            return prompt, search_context, "llm"
            
        return prompt, search_context, "mcp"
    
    async def exec_async(self, inputs):
        """执行阶段：生成故事大纲"""
        if not inputs:
            return {"title": "未能生成大纲", "sections": []}
            
        prompt, search_context, mode = inputs
        
        try:
            if mode == "mcp":
                # 调用MCP服务生成大纲
                try:
                    outline_result = await call_tool(
                        "outline", 
                        {
                            "prompt": prompt,
                            "context": search_context,
                            "style": self._shared.get("options", {}).get("style", "general"),
                            "sections_count": 5  # 默认5个章节
                        },
                        self._shared.get("mcp_service_url")
                    )
                    
                    # 检查结果格式
                    if isinstance(outline_result, dict) and "title" in outline_result and "sections" in outline_result:
                        return outline_result
                    else:
                        logger.warning("大纲服务返回了无效的格式，切换到LLM模式")
                        mode = "llm"
                except Exception as e:
                    logger.error(f"调用大纲服务失败: {str(e)}")
                    mode = "llm"  # 失败时切换到LLM模式
            
            if mode == "llm":
                # 使用本地LLM生成大纲
                system_message = """
                你是一个专业的故事大纲规划师。根据用户的请求和提供的相关信息，创建一个引人入胜的故事大纲。
                大纲应包含标题和4-5个章节。每个章节包含标题和简短描述。
                
                请以下面的JSON格式返回：
                ```json
                {
                  "title": "故事标题",
                  "sections": [
                    {"id": "section1", "title": "章节标题", "content": "章节简述"},
                    ...
                  ]
                }
                ```
                只返回JSON，不要有其他文字。
                """
                
                combined_prompt = f"用户请求: {prompt}\n\n相关信息:\n{search_context}"
                outline_json = await generate_text(combined_prompt, system_message)
                
                # 解析JSON
                try:
                    start_idx = outline_json.find("{")
                    end_idx = outline_json.rfind("}")
                    if start_idx >= 0 and end_idx >= 0:
                        outline_json = outline_json[start_idx:end_idx+1]
                    outline = json.loads(outline_json)
                    return outline
                except Exception as e:
                    logger.error(f"解析大纲JSON失败: {str(e)}")
                    # 返回基本结构
                    return {
                        "title": "故事标题",
                        "sections": [
                            {"id": "section1", "title": "引言", "content": "故事开始..."},
                            {"id": "section2", "title": "发展", "content": "故事发展..."},
                            {"id": "section3", "title": "高潮", "content": "故事高潮..."},
                            {"id": "section4", "title": "结局", "content": "故事结束..."}
                        ]
                    }
        except Exception as e:
            logger.error(f"生成大纲失败: {str(e)}")
            traceback.print_exc()
            return {"title": "生成失败", "sections": [], "error": str(e)}
    
    async def post_async(self, shared, prep_res, exec_res):
        """后处理阶段：存储大纲"""
        # 存储大纲
        shared["outline"] = exec_res
        
        # 确保每个章节都有id
        for i, section in enumerate(shared["outline"]["sections"]):
            if "id" not in section:
                section["id"] = f"section{i+1}"
                
        # 更新进度
        sections_count = len(shared["outline"]["sections"])
        message = f"生成了包含{sections_count}个章节的大纲: {shared['outline']['title']}"
        await self.update_progress(shared, 0.3, message, {"outline": shared["outline"]})
        
        return "default"
    
    async def exec_fallback_async(self, prep_res, exc):
        """异常处理：大纲生成失败"""
        logger.error(f"大纲生成失败: {str(exc)}")
        return {
            "title": "基础故事大纲",
            "sections": [
                {"id": "intro", "title": "引言", "content": "故事开始..."},
                {"id": "middle", "title": "发展", "content": "故事发展..."},
                {"id": "climax", "title": "高潮", "content": "故事高潮..."},
                {"id": "end", "title": "结局", "content": "故事结束..."}
            ],
            "error": str(exc)
        }

class StoryPlanningNode(AsyncNode):
    """故事规划节点
    
    根据用户提示生成故事大纲
    """
    
    def __init__(self, max_retries=3, wait=2):
        """初始化故事规划节点
        
        Args:
            max_retries: 最大重试次数
            wait: 重试等待时间(秒)
        """
        super().__init__(max_retries=max_retries, wait=wait)
        self.mcp_client = MCPClient()
    
    async def prep_async(self, shared):
        """准备故事规划数据
        
        Args:
            shared: 共享数据
            
        Returns:
            故事规划所需数据
        """
        # 获取任务ID
        task_id = shared.get("task_id")
        if not task_id:
            raise ValueError("未找到任务ID")
            
        # 获取用户提示
        prompt = shared.get("prompt")
        if not prompt:
            raise ValueError("未找到用户提示")
            
        # 获取选项
        options = shared.get("options", {})
        
        # 更新进度
        update_progress(task_id, 5, "准备生成故事大纲")
        
        return {
            "task_id": task_id,
            "prompt": prompt,
            "options": options
        }
    
    @log_async_function_call
    async def exec_async(self, prep_res):
        """执行故事规划
        
        Args:
            prep_res: 准备阶段的结果
            
        Returns:
            故事大纲
        """
        task_id = prep_res["task_id"]
        prompt = prep_res["prompt"]
        options = prep_res["options"]
        
        # 更新进度
        update_progress(task_id, 10, "正在生成故事大纲")
        
        try:
            # 获取可用的规划工具
            available_tools = []
            
            # 发现所有服务中可用的工具
            tools_by_service = await self.mcp_client.discover_tools()
            
            # 从多个可能的服务中查找适合故事规划的工具
            for service_name, tools in tools_by_service.items():
                for tool in tools:
                    # 判断工具是否适合故事规划/大纲生成
                    tool_name = tool.get("name", "").lower()
                    tool_desc = tool.get("description", "").lower()
                    
                    if any(keyword in tool_name or keyword in tool_desc 
                           for keyword in ["story", "plan", "outline", "structure"]):
                        available_tools.append((service_name, tool))
            
            # 如果找到了合适的工具，使用第一个
            if available_tools:
                service_name, tool = available_tools[0]
                logger.info(f"使用 {service_name} 服务的 {tool['name']} 工具生成故事大纲")
                
                # 构造工具参数
                tool_params = {
                    "prompt": prompt,
                    "style": options.get("style", "general"),
                    "length": options.get("length", "medium"),
                    "format": "json"
                }
                
                # 调用工具
                outline_result = await self.mcp_client.call_tool_with_retry(
                    tool["name"],
                    tool_params,
                    service_name
                )
                
                # 检查结果
                if not outline_result or not isinstance(outline_result, dict):
                    raise ValueError("故事大纲生成失败，返回结果无效")
                    
                # 提取大纲内容 - 适应不同工具可能有不同的输出格式
                outline = outline_result.get("outline") or outline_result.get("content") or outline_result
                title = outline_result.get("title", "未命名故事")
                
                if not outline:
                    raise ValueError("故事大纲生成失败，未返回大纲内容")
                    
                # 更新进度
                update_progress(task_id, 30, "故事大纲生成完成")
                
                return {
                    "title": title,
                    "outline": outline
                }
            else:
                # 没有找到合适的工具，使用LLM生成
                logger.warning("没有找到适合故事规划的工具，使用LLM生成")
                
                # 使用LLM生成大纲
                system_message = """
                你是一个专业的故事大纲规划师。请根据用户的请求创建一个引人入胜的故事大纲。
                """
                
                outline_text = await generate_text(
                    f"为以下故事创建大纲:\n{prompt}\n\n风格：{options.get('style', '一般')}\n长度：{options.get('length', '中等')}",
                    system_message
                )
                
                # 更新进度
                update_progress(task_id, 30, "故事大纲生成完成")
                
                return {
                    "title": "故事大纲",
                    "outline": outline_text
                }
                
        except MCPClientException as e:
            logger.error(f"调用故事规划工具失败: {str(e)}")
            raise Exception(f"故事大纲生成失败: {str(e)}")
        except Exception as e:
            logger.error(f"故事规划失败: {str(e)}")
            raise
    
    async def exec_fallback_async(self, prep_res, exc):
        """故事规划失败时的回退策略
        
        Args:
            prep_res: 准备阶段的结果
            exc: 异常
            
        Returns:
            简单的故事大纲
        """
        task_id = prep_res["task_id"]
        prompt = prep_res["prompt"]
        
        logger.warning(f"故事规划失败，使用简单大纲: {str(exc)}")
        update_progress(task_id, 20, "生成基础大纲")
        
        # 创建简单大纲
        return {
            "title": "故事",
            "outline": f"基于提示: {prompt}\n\n1. 开始\n2. 发展\n3. 结束"
        }
    
    async def post_async(self, shared, prep_res, exec_res):
        """处理故事规划结果
        
        Args:
            shared: 共享数据
            prep_res: 准备阶段的结果
            exec_res: 执行阶段的结果
            
        Returns:
            下一个动作
        """
        task_id = prep_res["task_id"]
        
        # 保存故事标题和大纲
        shared["title"] = exec_res["title"]
        shared["outline"] = exec_res["outline"]
        
        # 记录日志
        logger.info(f"故事规划完成: 标题 '{exec_res['title']}'")
        
        # 更新进度
        update_progress(task_id, 35, f"故事大纲已生成: {exec_res['title']}")
        
        return "default"

class StoryWritingNode(AsyncNode):
    """故事写作节点
    
    根据故事大纲生成故事内容
    """
    
    def __init__(self, max_retries=3, wait=2):
        """初始化故事写作节点
        
        Args:
            max_retries: 最大重试次数
            wait: 重试等待时间(秒)
        """
        super().__init__(max_retries=max_retries, wait=wait)
        self.mcp_client = MCPClient()
    
    async def prep_async(self, shared):
        """准备故事写作数据
        
        Args:
            shared: 共享数据
            
        Returns:
            故事写作所需数据
        """
        # 获取任务ID
        task_id = shared.get("task_id")
        if not task_id:
            raise ValueError("未找到任务ID")
            
        # 获取用户提示
        prompt = shared.get("prompt")
        if not prompt:
            raise ValueError("未找到用户提示")
            
        # 获取故事标题和大纲
        title = shared.get("title")
        outline = shared.get("outline")
        
        if not title or not outline:
            raise ValueError("未找到故事标题或大纲")
            
        # 获取选项
        options = shared.get("options", {})
        
        # 更新进度
        update_progress(task_id, 40, "准备生成故事内容")
        
        return {
            "task_id": task_id,
            "prompt": prompt,
            "title": title,
            "outline": outline,
            "options": options
        }
    
    @log_async_function_call
    async def exec_async(self, prep_res):
        """执行故事写作
        
        Args:
            prep_res: 准备阶段的结果
            
        Returns:
            故事内容
        """
        task_id = prep_res["task_id"]
        title = prep_res.get("title")
        outline = prep_res.get("outline")
        prompt = prep_res.get("prompt")
        options = prep_res.get("options", {})
        
        # 更新进度
        await self.update_progress(
            {"task_id": task_id, "progress_tracker": prep_res.get("progress_tracker")}, 
            0.45, 
            "正在生成故事内容"
        )
        
        try:
            # 准备MCP调用参数
            tool_params = {
                "title": title,
                "outline": json.dumps(outline) if isinstance(outline, dict) else outline,
                "prompt": prompt,
                "style": options.get("style", "general"),
                "tone": options.get("tone", "neutral"),
                "length": options.get("length", "medium")
            }
            
            # 调用MCP工具生成故事内容
            content_result = await call_tool("writing", tool_params)
            
            # 检查结果
            if not content_result or not isinstance(content_result, dict):
                raise ValueError("故事内容生成失败，返回结果无效")
                
            # 提取内容
            content = content_result.get("content")
            
            if not content:
                logger.warning("MCP服务没有返回内容，尝试使用备用方法")
                
                # 使用本地LLM生成内容
                system_message = f"""
                你是一个创意故事写作者。根据以下大纲写一个完整的故事。
                标题: {title}
                大纲: {json.dumps(outline, ensure_ascii=False) if isinstance(outline, dict) else outline}
                写作风格: {options.get("style", "general")}
                语调: {options.get("tone", "neutral")}
                长度: {options.get("length", "medium")}
                """
                
                content = await generate_text(prompt, system_message, max_tokens=2000)
                
            # 更新进度
            await self.update_progress(
                {"task_id": task_id, "progress_tracker": prep_res.get("progress_tracker")}, 
                0.7, 
                "故事内容生成完成"
            )
            
            return {
                "content": content
            }
            
        except Exception as e:
            logger.error(f"故事写作失败: {str(e)}")
            traceback.print_exc()
            raise Exception(f"故事内容生成失败: {str(e)}")
    
    async def exec_fallback_async(self, prep_res, exc):
        """故事写作失败时的回退策略
        
        Args:
            prep_res: 准备阶段的结果
            exc: 异常
            
        Returns:
            简单的故事内容
        """
        task_id = prep_res["task_id"]
        title = prep_res["title"]
        outline = prep_res["outline"]
        
        logger.warning(f"故事写作失败，生成简单内容: {str(exc)}")
        update_progress(task_id, 50, "生成基础内容")
        
        # 创建简单内容
        return {
            "content": f"# {title}\n\n故事大纲:\n{outline}\n\n由于技术原因，无法生成完整故事内容。请稍后重试。"
        }
    
    async def post_async(self, shared, prep_res, exec_res):
        """处理故事写作结果
        
        Args:
            shared: 共享数据
            prep_res: 准备阶段的结果
            exec_res: 执行阶段的结果
            
        Returns:
            下一个动作
        """
        task_id = prep_res["task_id"]
        
        # 保存故事内容
        shared["content"] = exec_res["content"]
        
        # 记录日志
        content_length = len(exec_res["content"])
        logger.info(f"故事写作完成: 长度 {content_length} 字符")
        
        # 更新进度
        update_progress(task_id, 75, "故事内容已生成")
        
        return "default"

class StoryEditingNode(AsyncNode):
    """故事编辑节点
    
    对生成的故事内容进行润色和改进
    """
    
    def __init__(self, max_retries=3, wait=2):
        """初始化故事编辑节点
        
        Args:
            max_retries: 最大重试次数
            wait: 重试等待时间(秒)
        """
        super().__init__(max_retries=max_retries, wait=wait)
        self.mcp_client = MCPClient()
    
    async def prep_async(self, shared):
        """准备故事编辑数据
        
        Args:
            shared: 共享数据
            
        Returns:
            故事编辑所需数据
        """
        # 获取任务ID
        task_id = shared.get("task_id")
        if not task_id:
            raise ValueError("未找到任务ID")
            
        # 获取故事标题、大纲和内容
        title = shared.get("title")
        outline = shared.get("outline")
        content = shared.get("content")
        
        if not title or not outline or not content:
            raise ValueError("未找到故事标题、大纲或内容")
            
        # 获取选项
        options = shared.get("options", {})
        
        # 更新进度
        update_progress(task_id, 80, "准备润色故事")
        
        return {
            "task_id": task_id,
            "title": title,
            "outline": outline,
            "content": content,
            "options": options
        }
    
    @log_async_function_call
    async def exec_async(self, prep_res):
        """执行故事编辑
        
        Args:
            prep_res: 准备阶段的结果
            
        Returns:
            编辑后的故事
        """
        task_id = prep_res["task_id"]
        title = prep_res["title"]
        outline = prep_res["outline"]
        content = prep_res["content"]
        options = prep_res["options"]
        
        # 更新进度
        await self.update_progress(
            {"task_id": task_id, "progress_tracker": prep_res.get("progress_tracker")}, 
            0.85, 
            "正在润色故事"
        )
        
        try:
            # 准备MCP调用参数
            tool_params = {
                "title": title,
                "content": content,
                "outline": json.dumps(outline) if isinstance(outline, dict) else outline,
                "edit_level": options.get("edit_level", "moderate"),
                "focus": options.get("focus", "grammar,coherence,flow")
            }
            
            # 调用MCP工具进行故事编辑
            edited_result = await call_tool("editing", tool_params)
            
            # 检查结果
            if not edited_result or not isinstance(edited_result, dict):
                raise ValueError("故事编辑失败，返回结果无效")
                
            # 提取编辑后的内容
            edited_content = edited_result.get("edited_content")
            if not edited_content and "content" in edited_result:
                edited_content = edited_result.get("content")
                
            if not edited_content:
                logger.warning("MCP服务没有返回编辑内容，使用原始内容")
                edited_content = content
                
            # 提取优化建议
            suggestions = edited_result.get("suggestions", [])
            if not suggestions:
                suggestions = ["故事已完成基本编辑"]
            
            # 更新进度
            await self.update_progress(
                {"task_id": task_id, "progress_tracker": prep_res.get("progress_tracker")}, 
                0.95, 
                "故事润色完成"
            )
            
            return {
                "edited_content": edited_content,
                "suggestions": suggestions
            }
            
        except Exception as e:
            logger.error(f"调用故事编辑服务失败: {str(e)}")
            traceback.print_exc()
            raise Exception(f"故事编辑失败: {str(e)}")
    
    async def exec_fallback_async(self, prep_res, exc):
        """故事编辑失败时的回退策略
        
        Args:
            prep_res: 准备阶段的结果
            exc: 异常
            
        Returns:
            原始故事内容
        """
        task_id = prep_res["task_id"]
        content = prep_res["content"]
        
        logger.warning(f"故事编辑失败，使用原始内容: {str(exc)}")
        update_progress(task_id, 90, "保留原始内容")
        
        # 返回原始内容
        return {
            "edited_content": content,
            "suggestions": ["由于技术原因，无法进行故事润色。"]
        }
    
    async def post_async(self, shared, prep_res, exec_res):
        """处理故事编辑结果
        
        Args:
            shared: 共享数据
            prep_res: 准备阶段的结果
            exec_res: 执行阶段的结果
            
        Returns:
            下一个动作
        """
        task_id = prep_res["task_id"]
        title = prep_res["title"]
        outline = prep_res["outline"]
        edited_content = exec_res["edited_content"]
        suggestions = exec_res["suggestions"]
        
        # 组装最终结果
        result = {
            "title": title,
            "outline": outline,
            "content": edited_content,
            "suggestions": suggestions
        }
        
        # 保存最终结果
        shared["result"] = result
        
        # 记录日志
        logger.info(f"故事编辑完成: '{title}'")
        
        # 更新进度
        update_progress(task_id, 100, "故事生成完成", "completed")
        
        return "default"

class ErrorHandlingNode(AsyncNode):
    """错误处理节点
    
    处理流程中出现的错误，尝试恢复或提供反馈
    """
    
    def __init__(self, max_retries=1):
        """初始化错误处理节点
        
        Args:
            max_retries: 最大重试次数
        """
        super().__init__(max_retries=max_retries)
    
    async def prep_async(self, shared):
        """准备错误处理数据
        
        Args:
            shared: 共享数据
            
        Returns:
            错误处理所需数据
        """
        # 获取任务ID
        task_id = shared.get("task_id")
        if not task_id:
            return {"error": "未找到任务ID"}
            
        # 获取当前状态
        return {
            "task_id": task_id,
            "error": shared.get("error"),
            "title": shared.get("title"),
            "outline": shared.get("outline"),
            "content": shared.get("content"),
            "options": shared.get("options", {})
        }
    
    async def exec_async(self, prep_res):
        """执行错误处理
        
        Args:
            prep_res: 准备阶段的结果
            
        Returns:
            处理结果
        """
        task_id = prep_res["task_id"]
        error = prep_res["error"]
        
        # 记录错误
        logger.error(f"处理任务 {task_id} 错误: {error}")
        
        # 更新进度
        update_progress(task_id, 0, f"发生错误: {error}", "failed")
        
        # 检查是否已有部分结果可以返回
        title = prep_res.get("title")
        outline = prep_res.get("outline")
        content = prep_res.get("content")
        
        has_partial_results = title or outline or content
        
        if has_partial_results:
            return {
                "retry": False,
                "error": error,
                "partial_results": {
                    "title": title or "故事生成失败",
                    "outline": outline or "无法生成故事大纲",
                    "content": content or "无法生成故事内容"
                }
            }
        else:
            # 没有部分结果，尝试重试
            return {
                "retry": True,
                "error": error
            }
    
    async def post_async(self, shared, prep_res, exec_res):
        """处理错误处理结果
        
        Args:
            shared: 共享数据
            prep_res: 准备阶段的结果
            exec_res: 执行阶段的结果
            
        Returns:
            下一个动作
        """
        task_id = prep_res["task_id"]
        retry = exec_res["retry"]
        error = exec_res["error"]
        
        # 保存错误信息
        shared["error"] = error
        
        if retry:
            # 要求重试
            logger.info(f"任务 {task_id} 将重试")
            return "retry"
        else:
            # 返回部分结果
            partial_results = exec_res.get("partial_results", {})
            if partial_results:
                shared["result"] = partial_results
                logger.info(f"任务 {task_id} 返回部分结果")
            
            # 标记任务已失败，不再继续
            return "failed" 