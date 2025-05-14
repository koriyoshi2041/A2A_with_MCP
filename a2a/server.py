#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - A2A服务器
实现A2A协议的JSON-RPC服务器
"""

import os
import sys
import json
import asyncio
import uuid
import logging
from typing import Dict, List, Any, Optional, Callable, Awaitable
import traceback
from aiohttp import web
import aiohttp
from aiohttp.web import Request, Response, WebSocketResponse
from datetime import datetime
from pydantic import ValidationError
import time

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入项目模块
from config import A2A_SERVER_HOST, A2A_SERVER_PORT, TASK_TIMEOUT, MAX_RETRIES
from utils.logging import get_logger
from a2a.task_manager import StoryGeneratorTaskManager
from flow.flows import StoryFlowFactory
from a2a.schema import (
    Task, TaskStatus, Message, TaskResponse, 
    TaskProgressResponse, TaskResultResponse, ErrorResponse,
    CreateTaskRequest, AgentRole, MessageType
)
from a2a.task_manager import TaskManager

logger = get_logger(__name__)

class A2AServer:
    """
    A2A服务器类
    实现A2A协议的JSON-RPC服务器
    """
    
    def __init__(self, host: str = A2A_SERVER_HOST, port: int = A2A_SERVER_PORT):
        """
        初始化服务器
        
        Args:
            host: 服务器主机
            port: 服务器端口
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        
        # 初始化WebSocket客户端字典
        self.websocket_clients = {}
        
        # 创建流程工厂
        self.flow_factory = StoryFlowFactory()
        
        # 创建任务管理器
        self.task_manager = StoryGeneratorTaskManager(self.flow_factory.create_flow)
        
        # 设置路由
        self._setup_routes()
        
    def _setup_routes(self):
        """设置服务器路由"""
        self.app.add_routes([
            # API 端点
            web.post('/api/tasks', self.create_task),
            web.get('/api/tasks/{task_id}', self.get_task),
            web.delete('/api/tasks/{task_id}', self.cancel_task),
            
            # WebSocket 端点
            web.get('/ws/tasks/{task_id}', self.websocket_handler),
            
            # 静态文件服务（可选，用于UI）
            # web.static('/static', 'static'),
            
            # 首页
            web.get('/', self.index_handler)
        ])
        
    async def start(self):
        """启动服务器"""
        runner = web.AppRunner(self.app)
        await runner.setup()
        self.site = web.TCPSite(runner, self.host, self.port)
        await self.site.start()
        logger.info(f"服务器已启动: http://{self.host}:{self.port}")
        
        # 保持运行，直到被中断
        while True:
            await asyncio.sleep(3600)  # 休眠1小时
            
    async def stop(self):
        """停止服务器"""
        # 关闭所有WebSocket连接
        for task_id, clients in self.websocket_clients.items():
            for ws in clients:
                if not ws.closed:
                    await ws.close(code=1000, message=b'Server shutdown')
        
        # 停止任务管理器
        await self.task_manager.stop_all_tasks()
        
        # 清理资源
        if hasattr(self, 'site'):
            await self.site.stop()
            
        logger.info("服务器已关闭")
    
    async def index_handler(self, request: web.Request) -> web.Response:
        """处理首页请求
        
        Args:
            request: HTTP请求
            
        Returns:
            HTTP响应
        """
        return web.json_response({
            "service": "A2A故事生成服务器",
            "version": "1.0.0",
            "status": "running",
            "documentation": "/api/docs",  # 文档URL（如果有）
        })
    
    async def create_task(self, request: web.Request) -> web.Response:
        """创建新任务
        
        Args:
            request: HTTP请求
            
        Returns:
            HTTP响应
        """
        try:
            # 解析请求体
            body = await request.json()
            logger.info(f"收到创建任务请求: {body}")
            
            # 验证请求格式
            if "jsonrpc" not in body or body["jsonrpc"] != "2.0":
                return web.json_response({
                    "jsonrpc": "2.0",
                    "error": {"code": -32600, "message": "无效的请求格式"},
                    "id": body.get("id")
                }, status=400)
                
            # 验证方法
            if body.get("method") != "tasks/send":
                return web.json_response({
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"方法 {body.get('method')} 不支持"},
                    "id": body.get("id")
                }, status=400)
                
            # 验证参数
            params = body.get("params", {})
            if "task" not in params:
                return web.json_response({
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "缺少任务参数"},
                    "id": body.get("id")
                }, status=400)
                
            task = params["task"]
            if "input" not in task:
                return web.json_response({
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": "缺少输入参数"},
                    "id": body.get("id")
                }, status=400)
                
            # 准备任务参数
            task_input = task["input"]
            task_params = {
                "inputs": task_input
            }
            
            # 调用任务管理器创建任务
            task_result = await self.task_manager.handle_task_send(task_params)
            
            # 检查结果
            if "error" in task_result:
                return web.json_response({
                    "jsonrpc": "2.0",
                    "error": {"code": -32000, "message": task_result["error"]},
                    "id": body.get("id")
                }, status=500)
                
            # 返回成功响应
            return web.json_response({
                "jsonrpc": "2.0",
                "result": {
                    "task_id": task_result["task_id"],
                    "state": task_result["state"]
                },
                "id": body.get("id")
            })
            
        except json.JSONDecodeError:
            return web.json_response({
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "解析请求失败，无效的JSON"},
                "id": None
            }, status=400)
        except Exception as e:
            logger.error(f"处理任务创建请求时出错: {str(e)}")
            traceback.print_exc()
            return web.json_response({
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"内部错误: {str(e)}"},
                "id": body.get("id") if isinstance(body, dict) else None
            }, status=500)
    
    async def get_task(self, request: web.Request) -> web.Response:
        """获取任务状态
        
        Args:
            request: HTTP请求
            
        Returns:
            HTTP响应
        """
        task_id = request.match_info.get('task_id')
        
        try:
            task = await self.task_manager.get_task(task_id)
            if task is None:
                return web.json_response(
                    ErrorResponse(
                        error="Task not found",
                        detail=f"Task {task_id} does not exist"
                    ).dict(),
                    status=404
                )
            
            # 如果任务已完成，返回结果
            if task.status == TaskStatus.COMPLETED:
                response = TaskResultResponse(
                    task_id=task.task_id,
                    status=task.status,
                    progress=task.progress,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    result=task.result or ""
                )
            else:
                # 否则返回进度
                last_messages = task.messages[-5:] if task.messages else []
                
                response = TaskProgressResponse(
                    task_id=task.task_id,
                    status=task.status,
                    progress=task.progress,
                    created_at=task.created_at,
                    updated_at=task.updated_at,
                    messages=last_messages
                )
                
            return web.json_response(response.dict())
            
        except Exception as e:
            logger.error(f"获取任务错误: {str(e)}")
            return web.json_response(
                ErrorResponse(
                    error="Failed to get task",
                    detail=str(e)
                ).dict(),
                status=500
            )
    
    async def cancel_task(self, request: web.Request) -> web.Response:
        """取消任务
        
        Args:
            request: HTTP请求
            
        Returns:
            HTTP响应
        """
        task_id = request.match_info.get('task_id')
        
        try:
            success = await self.task_manager.cancel_task(task_id)
            if not success:
                return web.json_response(
                    ErrorResponse(
                        error="Task not found",
                        detail=f"Task {task_id} does not exist"
                    ).dict(),
                    status=404
                )
                
            task = await self.task_manager.get_task(task_id)
            
            response = TaskResponse(
                task_id=task.task_id,
                status=task.status,
                progress=task.progress,
                created_at=task.created_at,
                updated_at=task.updated_at
            )
            return web.json_response(response.dict())
            
        except Exception as e:
            logger.error(f"取消任务错误: {str(e)}")
            return web.json_response(
                ErrorResponse(
                    error="Failed to cancel task",
                    detail=str(e)
                ).dict(),
                status=500
            )
    
    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """处理WebSocket连接，提供任务状态订阅
        
        Args:
            request: HTTP请求
            
        Returns:
            WebSocket响应
        """
        task_id = request.match_info.get('task_id')
        if not task_id:
            return web.Response(status=400, text="缺少任务ID")
            
        # 创建WebSocket响应
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        logger.info(f"建立WebSocket连接: {task_id}")
        
        # 添加到连接池
        if task_id not in self.websocket_clients:
            self.websocket_clients[task_id] = set()
        self.websocket_clients[task_id].add(ws)
        
        # 定义发送更新的回调函数
        async def send_update(update):
            if ws.closed:
                return
                
            try:
                # 格式化为A2A协议的JSON-RPC响应
                if isinstance(update, dict) and "error" in update:
                    response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": update["error"]},
                        "id": None
                    }
                else:
                    response = {
                        "jsonrpc": "2.0",
                        "result": update,
                        "id": None
                    }
                    
                await ws.send_json(response)
            except Exception as e:
                logger.error(f"发送WebSocket更新失败: {str(e)}")
        
        try:
            # 订阅任务状态
            subscribe_request = {
                "task_id": task_id
            }
            
            # 处理订阅请求
            await self.task_manager.handle_task_subscribe(subscribe_request, send_update)
            
            # 等待客户端消息（通常是心跳或取消）
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        
                        if "method" in data and data["method"] == "cancel":
                            # 取消任务请求
                            logger.info(f"收到取消任务请求: {task_id}")
                            
                            await self.task_manager.cancel_task(task_id, "客户端请求取消")
                            await send_update({"status": "cancelled", "message": "任务已取消"})
                        elif "method" in data and data["method"] == "ping":
                            # 心跳请求
                            await send_update({"type": "pong", "timestamp": time.time()})
                    except json.JSONDecodeError:
                        logger.warning(f"无效的WebSocket消息: {msg.data}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket连接错误: {ws.exception()}")
                    break
                    
        except Exception as e:
            logger.error(f"处理WebSocket连接时出错: {str(e)}")
            traceback.print_exc()
            
            # 尝试发送错误通知
            try:
                if not ws.closed:
                    await ws.send_json({
                        "jsonrpc": "2.0",
                        "error": {"code": -32603, "message": f"内部错误: {str(e)}"},
                        "id": None
                    })
            except:
                pass
                
        finally:
            # 从连接池移除
            if task_id in self.websocket_clients and ws in self.websocket_clients[task_id]:
                self.websocket_clients[task_id].remove(ws)
                
            # 取消任务订阅
            await self.task_manager.remove_subscription(task_id, send_update)
            
            # 关闭连接
            if not ws.closed:
                await ws.close()
                
            logger.info(f"WebSocket连接关闭: {task_id}")
            
        return ws

def main():
    """主函数"""
    server = A2AServer()
    server.run()

if __name__ == "__main__":
    main() 