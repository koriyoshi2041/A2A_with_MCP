#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - 客户端入口点
启动A2A客户端
"""

import os
import sys
import asyncio
import argparse

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入项目模块
from config import A2A_SERVER_HOST, A2A_SERVER_PORT
from a2a.client import CommandLineInterface
from utils.logging import get_logger

logger = get_logger(__name__)

async def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="A2A客户端 - 故事生成器")
    parser.add_argument("--prompt", type=str, help="故事生成提示")
    parser.add_argument("--host", type=str, default=A2A_SERVER_HOST, help="服务器主机")
    parser.add_argument("--port", type=int, default=A2A_SERVER_PORT, help="服务器端口")
    
    args = parser.parse_args()
    
    # 创建界面
    cli = CommandLineInterface()
    
    try:
        # 如果提供了提示，使用它
        if args.prompt:
            await cli.generate_story(args.prompt)
        else:
            # 否则交互式提示
            print("\n📚 欢迎使用多代理协作故事生成器!")
            print("请输入您想要创作的故事提示，或输入q退出\n")
            
            while True:
                prompt = input("请输入故事提示> ")
                
                if prompt.lower() in ["q", "quit", "exit"]:
                    break
                    
                if prompt:
                    await cli.generate_story(prompt)
    except KeyboardInterrupt:
        print("\n感谢使用故事生成器!")
    except Exception as e:
        logger.error(f"客户端运行出错: {str(e)}")
        print(f"\n❌ 错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 