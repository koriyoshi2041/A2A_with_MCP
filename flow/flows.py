#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - 流程定义
组装故事生成所需的流程
"""

import os
import sys
import asyncio
from typing import Dict, List, Any, Optional

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入PocketFlow核心库
from pocketflow import Flow, AsyncFlow

# 导入项目模块
from utils.logging import get_logger, log_async_function_call
from flow.nodes import (
    StoryPlanningNode, StoryWritingNode, StoryEditingNode, ErrorHandlingNode,
    ToolDiscoveryNode, SearchNode, OutlineNode
)
from flow.shared import create_shared_store

logger = get_logger(__name__)

class StoryFlowFactory:
    """故事生成流程工厂
    
    创建不同类型的故事生成流程
    """
    
    def __init__(self):
        """初始化流程工厂"""
        pass
        
    def create_story_flow(self) -> AsyncFlow:
        """创建完整的故事生成流程
        
        包含规划、写作、编辑等所有节点
        
        Returns:
            AsyncFlow: 故事生成流程
        """
        # 创建各个节点
        planning_node = StoryPlanningNode(max_retries=3, wait=2)
        writing_node = StoryWritingNode(max_retries=3, wait=2)
        editing_node = StoryEditingNode(max_retries=3, wait=2)
        error_node = ErrorHandlingNode(max_retries=1)
        
        # 连接各个节点
        # 正常流程：规划 -> 写作 -> 编辑
        planning_node - "default" >> writing_node
        writing_node - "default" >> editing_node
        
        # 错误处理流程
        planning_node - "error" >> error_node
        writing_node - "error" >> error_node
        editing_node - "error" >> error_node
        
        # 错误处理后的重试流程
        error_node - "retry" >> planning_node  # 从头重试
        
        # 创建流程
        flow = AsyncFlow(start=planning_node)
        
        return flow
    
    def create_planning_flow(self) -> AsyncFlow:
        """创建故事规划流程
        
        仅包含规划节点
        
        Returns:
            AsyncFlow: 故事规划流程
        """
        # 创建节点
        planning_node = StoryPlanningNode(max_retries=3, wait=2)
        error_node = ErrorHandlingNode(max_retries=1)
        
        # 连接节点
        planning_node - "error" >> error_node
        error_node - "retry" >> planning_node  # 重试
        
        # 创建流程
        flow = AsyncFlow(start=planning_node)
        
        return flow
    
    def create_writing_flow(self) -> AsyncFlow:
        """创建故事写作流程
        
        仅包含写作节点，假设已经有规划结果
        
        Returns:
            AsyncFlow: 故事写作流程
        """
        # 创建节点
        writing_node = StoryWritingNode(max_retries=3, wait=2)
        error_node = ErrorHandlingNode(max_retries=1)
        
        # 连接节点
        writing_node - "error" >> error_node
        error_node - "retry" >> writing_node  # 重试
        
        # 创建流程
        flow = AsyncFlow(start=writing_node)
        
        return flow
    
    def create_editing_flow(self) -> AsyncFlow:
        """创建故事编辑流程
        
        仅包含编辑节点，假设已经有写作结果
        
        Returns:
            AsyncFlow: 故事编辑流程
        """
        # 创建节点
        editing_node = StoryEditingNode(max_retries=3, wait=2)
        error_node = ErrorHandlingNode(max_retries=1)
        
        # 连接节点
        editing_node - "error" >> error_node
        error_node - "retry" >> editing_node  # 重试
        
        # 创建流程
        flow = AsyncFlow(start=editing_node)
        
        return flow

    def create_flow(self) -> AsyncFlow:
        """创建基本的故事生成流程
        
        这个方法将被任务管理器调用，用于创建处理单个故事请求的流程。
        
        Returns:
            AsyncFlow: 配置好的故事生成流程
        """
        # 创建各个节点
        tool_discovery = ToolDiscoveryNode(max_retries=2, wait=2)
        search_node = SearchNode(max_retries=2, wait=2)
        outline_node = OutlineNode(max_retries=2, wait=2)
        planning_node = StoryPlanningNode(max_retries=3, wait=2)
        writing_node = StoryWritingNode(max_retries=3, wait=2)
        editing_node = StoryEditingNode(max_retries=3, wait=2)
        error_node = ErrorHandlingNode(max_retries=1)
        
        # 连接节点 - 基本流程
        tool_discovery >> search_node
        search_node >> outline_node
        outline_node >> planning_node
        planning_node >> writing_node
        writing_node >> editing_node
        
        # 错误处理路径
        tool_discovery - "error" >> error_node
        search_node - "error" >> error_node
        outline_node - "error" >> error_node
        planning_node - "error" >> error_node
        writing_node - "error" >> error_node
        editing_node - "error" >> error_node
        
        # 错误恢复路径
        error_node - "retry" >> tool_discovery  # 从头重试
        
        # 创建异步流程
        flow = AsyncFlow(start=tool_discovery)
        logger.info("故事生成流程已创建")
        
        return flow

async def test_story_flow():
    """测试故事生成流程"""
    # 创建流程工厂
    factory = StoryFlowFactory()
    
    # 创建完整的故事生成流程
    flow = factory.create_story_flow()
    
    # 准备测试数据
    shared = {
        "task_id": "test-123",
        "prompt": "写一个关于太空探索的科幻故事，主角是一位在遥远星系发现外星文明的宇航员",
        "options": {
            "style": "sci-fi",
            "length": "medium",
            "tone": "adventurous"
        }
    }
    
    try:
        # 运行流程
        print("开始生成故事...")
        await flow.run_async(shared)
        
        # 检查结果
        result = shared.get("result")
        if result:
            print("\n故事生成成功:")
            print(f"标题: {result['title']}")
            print(f"大纲: {result['outline']}")
            print("\n内容片段:")
            content = result['content']
            print(content[:500] + "..." if len(content) > 500 else content)
        else:
            print(f"故事生成失败: {shared.get('error', '未知错误')}")
            
    except Exception as e:
        print(f"测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_story_flow()) 