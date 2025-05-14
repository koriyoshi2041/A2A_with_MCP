#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - A2A客户端
实现A2A协议的客户端
"""

import os
import sys
import json
import asyncio
import time
import argparse
from typing import Dict, List, Any, Optional, Callable, Awaitable
import traceback
import aiohttp
import websockets

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入项目模块
from config import A2A_SERVER_HOST, A2A_SERVER_PORT
from utils.logging import get_logger
from a2a.schema import (
    Task, TaskStatus, MessageType, CreateTaskRequest,
    TaskResponse, TaskProgressResponse, TaskResultResponse
)

logger = get_logger(__name__)

class A2AClient:
    """A2A客户端基础类"""
    
    def __init__(self, host: str = A2A_SERVER_HOST, port: int = A2A_SERVER_PORT):
        """初始化客户端
        
        Args:
            host: 服务器主机
            port: 服务器端口
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.websocket_url = f"ws://{host}:{port}"
        self.session = None
        
    async def __aenter__(self):
        """异步上下文管理器"""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.session:
            await self.session.close()
            
    async def create_task(self, prompt: str) -> Optional[str]:
        """创建新任务
        
        Args:
            prompt: 故事提示
            
        Returns:
            任务ID
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            request = CreateTaskRequest(prompt=prompt)
            async with self.session.post(
                f"{self.base_url}/api/tasks", 
                json=request.dict()
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"创建任务失败: {error_text}")
                    return None
                    
                data = await response.json()
                task_response = TaskResponse(**data)
                return task_response.task_id
                
        except Exception as e:
            logger.error(f"创建任务异常: {str(e)}")
            return None
            
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            async with self.session.get(
                f"{self.base_url}/api/tasks/{task_id}"
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"获取任务状态失败: {error_text}")
                    return None
                    
                data = await response.json()
                return data
                
        except Exception as e:
            logger.error(f"获取任务状态异常: {str(e)}")
            return None
            
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            async with self.session.delete(
                f"{self.base_url}/api/tasks/{task_id}"
            ) as response:
                return response.status == 200
                
        except Exception as e:
            logger.error(f"取消任务异常: {str(e)}")
            return False
            
    async def subscribe_task(self, task_id: str, callback: Callable[[str, Any], None]):
        """订阅任务更新
        
        Args:
            task_id: 任务ID
            callback: 回调函数，接收事件类型和数据
        """
        ws_url = f"{self.websocket_url}/ws/tasks/{task_id}"
        
        try:
            async with websockets.connect(ws_url) as ws:
                while True:
                    try:
                        message = await ws.recv()
                        data = json.loads(message)
                        
                        event = data.get("event")
                        event_data = data.get("data")
                        
                        # 调用回调函数
                        callback(event, event_data)
                        
                        # 如果任务已完成或失败，退出循环
                        if event == "status_update" and event_data.get("status") in [
                            TaskStatus.COMPLETED.value,
                            TaskStatus.FAILED.value,
                            TaskStatus.CANCELED.value
                        ]:
                            break
                            
                    except websockets.ConnectionClosed:
                        logger.warning("WebSocket连接已关闭")
                        break
                    except Exception as e:
                        logger.error(f"处理WebSocket消息异常: {str(e)}")
                        traceback.print_exc()
                        
        except Exception as e:
            logger.error(f"WebSocket连接异常: {str(e)}")
            traceback.print_exc()

class CommandLineInterface:
    """命令行界面客户端"""
    
    def __init__(self, host: str = A2A_SERVER_HOST, port: int = A2A_SERVER_PORT):
        """初始化命令行界面
        
        Args:
            host: 服务器主机
            port: 服务器端口
        """
        self.client = A2AClient(host, port)
        self.task_msgs = {}  # 消息历史
        
    async def generate_story(self, prompt: str):
        """生成故事
        
        Args:
            prompt: 故事提示
        """
        print(f"\n🔍 正在为您创建故事: {prompt}\n")
        
        # 创建任务
        async with self.client:
            task_id = await self.client.create_task(prompt)
            
            if not task_id:
                print("❌ 创建任务失败")
                return
                
            print(f"📝 已创建任务 ID: {task_id}")
            print("⏳ 正在生成故事，请稍候...\n")
            
            # 订阅任务更新
            await self._subscribe_and_display(task_id)
            
    async def _subscribe_and_display(self, task_id: str):
        """订阅并显示任务进度
        
        Args:
            task_id: 任务ID
        """
        # 初始状态
        self.task_msgs[task_id] = {
            "last_progress": 0,
            "messages": []
        }
        
        # 显示进度条
        await self._print_progress_bar(0)
        
        # 定义WebSocket回调
        def ws_callback(event, data):
            if event == "connected":
                pass  # 已连接
            elif event == "message":
                # 添加到消息历史
                self.task_msgs[task_id]["messages"].append(data)
                
                # 根据消息类型显示
                msg_type = data.get("message_type")
                sender = data.get("sender")
                content = data.get("content")
                
                if msg_type == MessageType.TEXT.value:
                    print(f"📟 {sender}: {content}")
                elif msg_type == MessageType.ACTION.value:
                    print(f"🔄 {sender} 正在执行: {content}")
                elif msg_type == MessageType.RESULT.value:
                    print(f"✅ {sender} 完成: {content}")
                elif msg_type == MessageType.ERROR.value:
                    print(f"❌ {sender} 错误: {content}")
                
            elif event == "progress":
                # 更新进度条
                progress = data.get("progress", 0)
                asyncio.create_task(self._print_progress_bar(progress))
                
            elif event == "status_update":
                status = data.get("status")
                
                if status == TaskStatus.COMPLETED.value:
                    print("\n✨ 故事生成完成!")
                    asyncio.create_task(self._print_final_result(task_id))
                    
                elif status == TaskStatus.FAILED.value:
                    error = data.get("error", "未知错误")
                    print(f"\n❌ 故事生成失败: {error}")
                    
                elif status == TaskStatus.CANCELED.value:
                    print("\n⚠️ 故事生成已取消")
            
            elif event == "error":
                print(f"\n❌ 错误: {data}")
        
        # 订阅任务更新
        await self.client.subscribe_task(task_id, ws_callback)
    
    async def _print_progress_bar(self, progress: float):
        """打印进度条
        
        Args:
            progress: 进度值 (0-100)
        """
        width = 30
        filled = int(width * progress / 100)
        bar = "█" * filled + "░" * (width - filled)
        sys.stdout.write(f"\r⏳ 生成进度: [{bar}] {progress:.1f}%")
        sys.stdout.flush()
        
    async def _print_final_result(self, task_id: str):
        """获取并打印最终结果
        
        Args:
            task_id: 任务ID
        """
        status = await self.client.get_task_status(task_id)
        
        if not status:
            print("❌ 无法获取任务结果")
            return
            
        if "result" in status:
            story = status["result"]
            
            # 打印故事
            print("\n" + "=" * 50)
            print("📚 生成的故事:")
            print("=" * 50)
            print(story)
            print("=" * 50)
            print("\n故事已成功生成! 您可以继续输入新的提示，或按 q 退出。")
        else:
            print("❌ 任务未完成或无结果")

async def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="A2A客户端 - 故事生成器")
    parser.add_argument("--prompt", type=str, help="故事生成提示")
    parser.add_argument("--host", type=str, default=A2A_SERVER_HOST, help="服务器主机")
    parser.add_argument("--port", type=int, default=A2A_SERVER_PORT, help="服务器端口")
    
    args = parser.parse_args()
    
    # 创建界面
    cli = CommandLineInterface(args.host, args.port)
    
    # 如果提供了提示，使用它
    if args.prompt:
        await cli.generate_story(args.prompt)
    else:
        # 否则交互式提示
        print("📚 欢迎使用多代理协作故事生成器!")
        print("请输入您想要创作的故事提示，或输入q退出")
        
        while True:
            prompt = input("\n请输入故事提示> ")
            
            if prompt.lower() in ["q", "quit", "exit"]:
                break
                
            if prompt:
                await cli.generate_story(prompt)

if __name__ == "__main__":
    asyncio.run(main()) 