#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - A2A服务器
提供基于FastAPI的A2A服务接口
"""

import os
import sys
import uuid
import asyncio
import uvicorn
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入项目模块
from a2a.schema import (
    Task, TaskStatus, AgentRole, MessageType, Message,
    CreateTaskRequest, TaskResponse, TaskProgressResponse, TaskResultResponse, ErrorResponse
)
from utils.logging import get_logger
from utils.progress import ProgressTracker
from flow.shared import create_shared_store
from flow.main import create_story_flow

# 创建日志记录器
logger = get_logger(__name__)

# 创建FastAPI应用
app = FastAPI(
    title="多代理协作故事生成器",
    description="基于PocketFlow框架的多代理协作故事生成系统，集成A2A和MCP协议",
    version="0.1.0"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 任务存储
tasks = {}
progress_tracker = ProgressTracker()
progress_subscribers = {}

# 模型
class SubscribeRequest(BaseModel):
    callback_url: str

# 路由
@app.get("/")
async def root():
    """健康检查和欢迎页"""
    return {"message": "多代理协作故事生成器 A2A服务正在运行"}

@app.post("/api/tasks", response_model=TaskResponse)
async def create_task(request: CreateTaskRequest, background_tasks: BackgroundTasks):
    """创建新任务"""
    # 生成任务ID
    task_id = str(uuid.uuid4())
    
    # 提取任务输入
    task_input = request.task
    
    # 记录日志
    logger.info(f"创建新任务: {task_id}, 输入: {task_input}")
    
    # 创建任务对象
    task = Task(
        task_id=task_id,
        inputs=task_input,
        status=TaskStatus.PENDING,
        progress=0.0
    )
    
    # 存储任务
    tasks[task_id] = task
    
    # 创建初始消息
    initial_message = Message(
        message_id=str(uuid.uuid4()),
        sender=AgentRole.COORDINATOR,
        message_type=MessageType.SYSTEM,
        content=f"任务已创建，正在处理: {task_input.get('content', '')}"
    )
    task.messages.append(initial_message)
    
    # 在后台执行任务
    background_tasks.add_task(process_task, task_id, task_input)
    
    # 返回任务信息
    return TaskResponse(
        task_id=task_id,
        status=task.status,
        progress=task.progress,
        created_at=task.created_at,
        updated_at=task.updated_at
    )

@app.get("/api/tasks/{task_id}", response_model=TaskProgressResponse)
async def get_task(task_id: str):
    """获取任务状态"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    task = tasks[task_id]
    
    # 获取最近的消息（最多10条）
    recent_messages = task.messages[-10:] if task.messages else []
    
    return TaskProgressResponse(
        task_id=task_id,
        status=task.status,
        progress=task.progress,
        created_at=task.created_at,
        updated_at=task.updated_at,
        messages=recent_messages
    )

@app.get("/api/tasks/{task_id}/result", response_model=TaskResultResponse)
async def get_task_result(task_id: str):
    """获取任务结果"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    task = tasks[task_id]
    
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=400, 
            detail=f"任务 {task_id} 尚未完成，当前状态: {task.status}"
        )
    
    if task.result is None:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 没有结果")
    
    return TaskResultResponse(
        task_id=task_id,
        status=task.status,
        progress=task.progress,
        created_at=task.created_at,
        updated_at=task.updated_at,
        result=task.result
    )

@app.post("/api/tasks/{task_id}/subscribe")
async def subscribe_to_task(task_id: str, request: SubscribeRequest):
    """订阅任务进度更新"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    # 添加到订阅者列表
    if task_id not in progress_subscribers:
        progress_subscribers[task_id] = []
    
    progress_subscribers[task_id].append(request.callback_url)
    
    return {"message": f"已订阅任务 {task_id} 的进度更新"}

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    # 删除任务
    del tasks[task_id]
    
    # 删除订阅者
    if task_id in progress_subscribers:
        del progress_subscribers[task_id]
    
    # 删除进度跟踪器
    progress_tracker.remove_task(task_id)
    
    return {"message": f"任务 {task_id} 已删除"}

# 任务进度更新回调
def progress_callback(update_data):
    """处理进度更新"""
    task_id = update_data.get("task_id")
    if not task_id or task_id not in tasks:
        return
    
    task = tasks[task_id]
    
    # 更新任务进度
    progress = update_data.get("progress", 0)
    if isinstance(progress, float):
        task.progress = progress
    
    # 更新任务状态
    status = update_data.get("status")
    if status:
        if status == "running":
            task.status = TaskStatus.RUNNING
        elif status == "completed":
            task.status = TaskStatus.COMPLETED
        elif status == "failed":
            task.status = TaskStatus.FAILED
    
    # 更新时间
    task.updated_at = update_data.get("time", task.updated_at)
    
    # 添加消息
    message = update_data.get("message")
    if message:
        new_message = Message(
            message_id=str(uuid.uuid4()),
            sender=AgentRole.COORDINATOR,
            message_type=MessageType.PROGRESS,
            content=message,
            metadata={"progress": task.progress}
        )
        task.messages.append(new_message)
    
    # 通知订阅者（异步方式）
    notify_subscribers(task_id, update_data)

async def notify_subscribers(task_id, update_data):
    """通知订阅者进度更新"""
    if task_id not in progress_subscribers:
        return
    
    import aiohttp
    
    async with aiohttp.ClientSession() as session:
        for callback_url in progress_subscribers[task_id]:
            try:
                async with session.post(callback_url, json=update_data) as response:
                    if response.status != 200:
                        logger.warning(f"通知订阅者失败: {callback_url}, 状态码: {response.status}")
            except Exception as e:
                logger.error(f"通知订阅者错误: {callback_url}, 错误: {str(e)}")

async def process_task(task_id, task_input):
    """处理任务"""
    # 获取任务
    task = tasks[task_id]
    
    try:
        # 更新任务状态
        task.status = TaskStatus.RUNNING
        
        # 创建进度跟踪器
        task_progress = progress_tracker.create_task(task_id)
        task_progress.subscribe(progress_callback)
        
        # 创建共享存储
        shared = create_shared_store(task_id, task_input, task_progress)
        
        # 创建故事生成流程
        story_flow = create_story_flow()
        
        # 运行流程
        logger.info(f"开始执行任务 {task_id}")
        await story_flow.run_async(shared)
        
        # 获取结果
        result = shared.get("result")
        
        if result:
            # 任务成功完成
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.progress = 1.0
            
            # 添加完成消息
            completion_message = Message(
                message_id=str(uuid.uuid4()),
                sender=AgentRole.COORDINATOR,
                message_type=MessageType.RESULT,
                content=f"任务已完成: {result.get('title', '未命名故事')}",
                metadata={"result": result}
            )
            task.messages.append(completion_message)
            
            logger.info(f"任务 {task_id} 已完成")
        else:
            # 检查是否有错误
            error = shared.get("error")
            
            if error:
                task.error = error
                task.status = TaskStatus.FAILED
                
                # 添加错误消息
                error_message = Message(
                    message_id=str(uuid.uuid4()),
                    sender=AgentRole.COORDINATOR,
                    message_type=MessageType.ERROR,
                    content=f"任务失败: {error}"
                )
                task.messages.append(error_message)
                
                logger.error(f"任务 {task_id} 失败: {error}")
            else:
                # 没有结果也没有错误
                task.status = TaskStatus.FAILED
                task.error = "任务完成但没有返回结果"
                
                logger.warning(f"任务 {task_id} 完成但没有返回结果")
    
    except Exception as e:
        # 处理异常
        task.status = TaskStatus.FAILED
        task.error = str(e)
        
        # 添加错误消息
        error_message = Message(
            message_id=str(uuid.uuid4()),
            sender=AgentRole.COORDINATOR,
            message_type=MessageType.ERROR,
            content=f"任务执行过程中出错: {str(e)}"
        )
        task.messages.append(error_message)
        
        logger.exception(f"任务 {task_id} 执行过程中出错")
    
    finally:
        # 清理资源
        progress_tracker.remove_task(task_id)
        
def main():
    """启动服务器"""
    # 读取端口
    port = int(os.environ.get("A2A_SERVER_PORT", 5000))
    
    # 启动服务器
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main() 