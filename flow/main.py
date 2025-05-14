#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - 主流程
定义系统的主要流程
"""

import os
import sys
import asyncio
from typing import Dict, Any, Optional, Union

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入PocketFlow核心库
from pocketflow import AsyncFlow

# 导入项目模块
from utils.logging import get_logger
from flow.nodes import (
    ToolDiscoveryNode, SearchNode, OutlineNode, 
    StoryWritingNode, StoryEditingNode, ErrorHandlingNode
)

# 创建日志记录器
logger = get_logger(__name__)

def create_story_flow() -> AsyncFlow:
    """
    创建故事生成流程
    
    Returns:
        流程对象
    """
    # 创建节点
    tool_discovery = ToolDiscoveryNode()
    search = SearchNode()
    outline = OutlineNode()
    writing = StoryWritingNode()
    editing = StoryEditingNode()
    error = ErrorHandlingNode()
    
    # 连接流程
    # 正常流程: 工具发现 -> 搜索 -> 大纲 -> 写作 -> 编辑
    tool_discovery - "default" >> search
    search - "default" >> outline
    outline - "default" >> writing
    writing - "default" >> editing
    
    # 错误处理路径
    tool_discovery - "error" >> error
    search - "error" >> error
    outline - "error" >> error
    writing - "error" >> error
    editing - "error" >> error
    
    # 创建流程
    flow = AsyncFlow(start=tool_discovery)
    
    logger.info("故事生成流程已创建")
    return flow

# 创建批处理流程 (多故事并行生成)
def create_batch_story_flow() -> AsyncFlow:
    """
    创建批量故事生成流程，可以处理多个任务
    
    Returns:
        批处理流程对象
    """
    # 创建单个故事流程
    story_flow = create_story_flow()
    
    # TODO: 如果需要，可以使用AsyncParallelBatchFlow包装单个故事流程
    
    return story_flow

# 测试
if __name__ == "__main__":
    from flow.shared import create_shared_store
    
    async def test_flow():
        # 创建流程
        flow = create_story_flow()
        
        # 创建测试共享存储
        shared = create_shared_store(
            "test-task-001",
            {"content": "创作一个关于太空探险的科幻故事", "style": "sci-fi"}
        )
        
        # 运行流程
        await flow.run_async(shared)
        
        # 检查结果
        result = shared.get("result")
        if result:
            print(f"标题: {result.get('title')}")
            print(f"内容摘要: {result.get('content')[:100]}...")
        else:
            error = shared.get("error")
            print(f"执行失败: {error}")
    
    # 运行测试
    asyncio.run(test_flow()) 