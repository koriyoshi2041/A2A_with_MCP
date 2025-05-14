#!/usr/bin/env python3
"""
MCP服务集成测试脚本
用于测试多代理协作故事生成器与MCP服务的连接和交互
"""

import os
import sys
import json
import asyncio
import argparse
from typing import Dict, List, Any, Optional

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mcp.client import MCPClient, check_service_health
from mcp.config import get_all_services, initialize as init_config
from utils.logging import get_logger

logger = get_logger(__name__)

class ColorPrinter:
    """带颜色的终端打印工具"""
    
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
    @staticmethod
    def print_header(msg: str) -> None:
        """打印带颜色的标题"""
        print(f"\n{ColorPrinter.HEADER}{ColorPrinter.BOLD}{msg}{ColorPrinter.ENDC}")
    
    @staticmethod
    def print_success(msg: str) -> None:
        """打印成功信息"""
        print(f"{ColorPrinter.GREEN}✓ {msg}{ColorPrinter.ENDC}")
    
    @staticmethod
    def print_error(msg: str) -> None:
        """打印错误信息"""
        print(f"{ColorPrinter.RED}✗ {msg}{ColorPrinter.ENDC}")
    
    @staticmethod
    def print_warning(msg: str) -> None:
        """打印警告信息"""
        print(f"{ColorPrinter.YELLOW}! {msg}{ColorPrinter.ENDC}")
    
    @staticmethod
    def print_info(msg: str) -> None:
        """打印普通信息"""
        print(f"{ColorPrinter.BLUE}> {msg}{ColorPrinter.ENDC}")

async def test_service_health() -> Dict[str, bool]:
    """测试所有MCP服务的健康状态
    
    Returns:
        Dict[str, bool]: 各服务的健康状态
    """
    ColorPrinter.print_header("测试MCP服务健康状态")
    
    services = get_all_services()
    if not services:
        ColorPrinter.print_warning("未配置任何MCP服务")
        return {}
    
    results = {}
    for service_name, url in services.items():
        ColorPrinter.print_info(f"正在检查服务 '{service_name}' ({url})...")
        is_healthy = await check_service_health(service_name)
        results[service_name] = is_healthy
        
        if is_healthy:
            ColorPrinter.print_success(f"服务 '{service_name}' 运行正常")
        else:
            ColorPrinter.print_error(f"服务 '{service_name}' 不可用")
    
    return results

async def discover_tools() -> Dict[str, List[Dict[str, Any]]]:
    """发现所有服务的工具
    
    Returns:
        Dict[str, List[Dict[str, Any]]]: 各服务及其工具列表
    """
    ColorPrinter.print_header("发现MCP工具")
    
    async with MCPClient() as client:
        tools_by_service = await client.discover_tools()
        
        for service_name, tools in tools_by_service.items():
            if tools:
                ColorPrinter.print_success(f"服务 '{service_name}' 提供 {len(tools)} 个工具:")
                for i, tool in enumerate(tools, 1):
                    print(f"  {i}. {tool.get('name')}: {tool.get('description', '无描述')}")
            else:
                ColorPrinter.print_warning(f"服务 '{service_name}' 未提供任何工具")
        
        if not tools_by_service:
            ColorPrinter.print_error("未发现任何MCP工具")
            
    return tools_by_service

async def test_search_tool() -> bool:
    """测试搜索工具
    
    Returns:
        bool: 测试是否成功
    """
    ColorPrinter.print_header("测试搜索工具")
    
    service_name = "search_service"
    tool_name = "search_relevant_information"
    test_query = "多代理协作系统"
    
    try:
        async with MCPClient(service_name) as client:
            ColorPrinter.print_info(f"正在搜索: '{test_query}'...")
            
            result = await client.call_tool_with_retry(
                tool_name,
                {"topic": test_query, "depth": 2},
                service_name
            )
            
            if "results" in result:
                result_count = len(result["results"])
                ColorPrinter.print_success(f"搜索成功，获取到 {result_count} 条结果")
                
                if result_count > 0:
                    print("\n搜索结果示例:")
                    for i, item in enumerate(result["results"][:3], 1):
                        print(f"  {i}. {item.get('title', '无标题')}")
                        print(f"     {item.get('snippet', '无摘要')[:100]}...")
                
                return True
            else:
                ColorPrinter.print_error("搜索结果格式不正确")
                return False
                
    except Exception as e:
        ColorPrinter.print_error(f"搜索测试失败: {str(e)}")
        return False

async def test_outline_tool() -> bool:
    """测试大纲工具
    
    Returns:
        bool: 测试是否成功
    """
    ColorPrinter.print_header("测试大纲工具")
    
    service_name = "outline_service"
    tool_name = "generate_structured_outline"
    test_topic = "未来智能城市"
    
    try:
        async with MCPClient(service_name) as client:
            ColorPrinter.print_info(f"正在生成主题为 '{test_topic}' 的故事大纲...")
            
            result = await client.call_tool_with_retry(
                tool_name,
                {
                    "topic": test_topic,
                    "research": [
                        {"title": "智能城市概念", "content": "智能城市是运用信息和通信技术手段感测、分析、整合城市运行核心系统的各项关键信息，从而对包括民生、环保、公共安全、城市服务、工商业活动在内的各种需求做出智能响应。"},
                        {"title": "未来交通系统", "content": "未来交通系统将实现全自动驾驶，采用共享模式和清洁能源，大幅减少交通拥堵和环境污染。"}
                    ],
                    "structure": "四部分"
                },
                service_name
            )
            
            if "sections" in result:
                section_count = len(result["sections"])
                ColorPrinter.print_success(f"大纲生成成功，包含 {section_count} 个部分")
                
                print(f"\n故事标题: {result.get('title', '无标题')}")
                for section_name, section_data in result.get("sections", {}).items():
                    print(f"  • {section_name}: {section_data.get('title', '无小标题')}")
                
                return True
            else:
                ColorPrinter.print_error("大纲结果格式不正确")
                return False
                
    except Exception as e:
        ColorPrinter.print_error(f"大纲测试失败: {str(e)}")
        return False

async def run_integration_test(args):
    """运行集成测试
    
    Args:
        args: 命令行参数
    """
    # 初始化配置
    init_config()
    
    # 测试服务健康状态
    health_results = await test_service_health()
    
    # 如果指定了服务且该服务不健康，则退出
    if args.service and args.service in health_results and not health_results[args.service]:
        ColorPrinter.print_error(f"指定的服务 '{args.service}' 不可用，测试终止")
        return
    
    # 发现工具
    if not args.skip_discovery:
        tools_map = await discover_tools()
    
    # 根据参数决定测试哪些工具
    if args.test_search or args.test_all:
        await test_search_tool()
    
    if args.test_outline or args.test_all:
        await test_outline_tool()
    
    # 测试总结
    ColorPrinter.print_header("集成测试完成")
    healthy_services = sum(1 for status in health_results.values() if status)
    ColorPrinter.print_info(f"服务健康状态: {healthy_services}/{len(health_results)} 个服务正常")

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="MCP服务集成测试工具")
    
    parser.add_argument("--service", type=str, help="指定要测试的服务名称")
    parser.add_argument("--skip-discovery", action="store_true", help="跳过工具发现步骤")
    parser.add_argument("--test-search", action="store_true", help="测试搜索工具")
    parser.add_argument("--test-outline", action="store_true", help="测试大纲工具")
    parser.add_argument("--test-all", action="store_true", help="测试所有工具")
    
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_integration_test(args)) 