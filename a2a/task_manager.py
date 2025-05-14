#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - 任务管理器
负责任务的创建、状态跟踪和结果返回
"""

import os
import sys
import json
import uuid
import asyncio
import time
from typing import Dict, List, Any, Optional, Callable, Awaitable, Tuple
import traceback
from datetime import datetime

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TASK_TIMEOUT, MAX_RETRIES, PROGRESS_UPDATE_INTERVAL
from utils.logging import get_logger
from utils.progress import TaskProgress, TaskStatus, progress_tracker
from a2a.schema import (
    Task, TaskStatus, AgentRole, Message, MessageType,
    StoryOutline, StorySection, Story
)
from flow.flows import StoryFlowFactory
from mcp.client import get_tools, call_tool

logger = get_logger(__name__)

class TaskManager:
    """
    任务管理器类
    管理A2A协议中的任务生命周期
    """
    
    def __init__(self):
        """初始化任务管理器"""
        self.tasks: Dict[str, Task] = {}
        self.tasks_lock = asyncio.Lock()
        self.running_tasks: Dict[str, asyncio.Task] = {}
        self.webhooks: Dict[str, Set[Callable[[str, Any], Awaitable[None]]]] = {}
        self.flow_factory = StoryFlowFactory()
        
    async def handle_task_send(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理任务发送请求
        
        Args:
            request: 任务请求
            
        Returns:
            任务响应
        """
        try:
            # 验证请求
            if "inputs" not in request:
                return {"error": "Missing required field: inputs"}
                
            # 生成任务ID
            task_id = str(uuid.uuid4())
            
            # 初始化任务
            self.tasks[task_id] = Task(
                task_id=task_id,
                inputs=request["inputs"],
                status=TaskStatus.RUNNING,
                progress=0.0,
                updated_at=datetime.now(),
                messages=[]
            )
            
            # 创建进度跟踪
            progress_tracker.create_task(task_id)
            
            # 启动任务执行
            self.running_tasks[task_id] = asyncio.create_task(
                self._execute_task(task_id)
            )
            
            # 设置任务超时
            timeout_task = asyncio.create_task(self._task_timeout(task_id))
            
            logger.info(f"任务已创建: {task_id}")
            
            # 返回任务ID
            return {
                "task_id": task_id,
                "state": {"status": "pending"}
            }
        except Exception as e:
            logger.error(f"处理任务发送请求时出错: {str(e)}")
            traceback.print_exc()
            return {"error": f"处理任务失败: {str(e)}"}
            
    async def handle_task_subscribe(self, request: Dict[str, Any], send_update: Callable) -> None:
        """
        处理任务状态订阅请求
        
        Args:
            request: 订阅请求
            send_update: 用于发送更新的回调函数
        """
        try:
            # 验证请求
            if "task_id" not in request:
                await send_update({"error": "Missing required field: task_id"})
                return
                
            task_id = request["task_id"]
            
            # 检查任务是否存在
            if task_id not in self.tasks:
                await send_update({"error": f"Task not found: {task_id}"})
                return
                
            # 设置订阅
            if task_id not in self.webhooks:
                self.webhooks[task_id] = set()
            self.webhooks[task_id].add(send_update)
            
            # 创建进度跟踪订阅
            await progress_tracker.subscribe(task_id, self._on_progress_update)
            
            # 立即发送当前状态
            await send_update({
                "task_id": task_id,
                "state": self.tasks[task_id].status.value
            })
            
            logger.info(f"添加任务订阅: {task_id}")
        except Exception as e:
            logger.error(f"处理任务订阅请求时出错: {str(e)}")
            traceback.print_exc()
            await send_update({"error": f"订阅任务失败: {str(e)}"})
            
    async def remove_subscription(self, task_id: str, send_update: Callable) -> None:
        """
        移除任务订阅
        
        Args:
            task_id: 任务ID
            send_update: 订阅的回调函数
        """
        if task_id in self.webhooks and send_update in self.webhooks[task_id]:
            self.webhooks[task_id].remove(send_update)
            logger.info(f"移除任务订阅: {task_id}")
            
    async def update_task_progress(self, 
                                 task_id: str, 
                                 progress: float, 
                                 message: str = "",
                                 artifacts: Optional[Dict[str, Any]] = None) -> None:
        """
        更新任务进度
        
        Args:
            task_id: 任务ID
            progress: 进度(0.0-1.0)
            message: 进度消息
            artifacts: 附加数据
        """
        if task_id not in self.tasks:
            logger.warning(f"尝试更新不存在的任务: {task_id}")
            return
            
        # 更新进度跟踪
        progress_tracker.update_progress(task_id, progress, message, artifacts)
        
        # 更新任务状态
        self.tasks[task_id].progress = progress
        self.tasks[task_id].updated_at = datetime.now()
        
        if artifacts:
            self.tasks[task_id].result = artifacts.get("result")
            
        # 触发进度更新事件
        await self._notify_webhook(task_id, "progress", {"progress": progress})
        
    async def complete_task(self, 
                          task_id: str, 
                          result: Any = None,
                          success: bool = True,
                          message: str = "") -> None:
        """
        完成任务
        
        Args:
            task_id: 任务ID
            result: 任务结果
            success: 是否成功
            message: 完成消息
        """
        if task_id not in self.tasks:
            logger.warning(f"尝试完成不存在的任务: {task_id}")
            return
            
        status = "succeeded" if success else "failed"
        
        # 更新任务状态
        self.tasks[task_id].status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
        self.tasks[task_id].progress = 1.0 if success else self.tasks[task_id].progress
        self.tasks[task_id].updated_at = datetime.now()
        self.tasks[task_id].result = result
        
        # 更新进度跟踪
        if success:
            progress_tracker.complete_task(
                task_id, 
                True, 
                message, 
                {"result": result} if result is not None else None
            )
        else:
            progress_tracker.fail_task(
                task_id, 
                message, 
                {"result": result} if result is not None else None
            )
            
        # 取消超时任务
        if task_id in self.running_tasks:
            self.running_tasks[task_id].cancel()
            del self.running_tasks[task_id]
            
        # 添加完成消息
        self._add_system_message(
            task_id,
            f"故事生成完成, 状态: {status}",
            MessageType.RESULT
        )
        
        logger.info(f"任务已完成: {task_id}, 状态: {status}")
            
    async def cancel_task(self, task_id: str, reason: str = "已取消") -> None:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            reason: 取消原因
        """
        if task_id not in self.tasks:
            logger.warning(f"尝试取消不存在的任务: {task_id}")
            return
            
        # 检查任务是否已经终止
        task = self.tasks[task_id]
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELED]:
            logger.warning(f"任务已经结束: {task_id}, 状态: {task.status}")
            return
            
        # 取消正在运行的任务
        if task_id in self.running_tasks:
            self.running_tasks[task_id].cancel()
            del self.running_tasks[task_id]
            
        # 更新任务状态
        task.status = TaskStatus.CANCELED
        task.updated_at = datetime.now()
        
        # 添加取消消息
        self._add_system_message(
            task_id,
            f"任务已取消, 原因: {reason}",
            MessageType.TEXT
        )
        
        # 更新进度跟踪
        progress_tracker.cancel_task(task_id)
        
        logger.info(f"任务已取消: {task_id}, 原因: {reason}")
        
    async def get_task_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态
        """
        if task_id not in self.tasks:
            return None
            
        return {
            "status": self.tasks[task_id].status.value,
            "progress": self.tasks[task_id].progress,
            "updated_at": self.tasks[task_id].updated_at.isoformat()
        }
    
    async def _execute_task(self, task_id: str):
        """
        执行任务的核心逻辑
        
        Args:
            task_id: 任务ID
        """
        if task_id not in self.tasks:
            logger.error(f"尝试执行不存在的任务: {task_id}")
            return
            
        try:
            # 获取任务数据
            task = self.tasks[task_id]
            
            # 添加系统消息
            self._add_system_message(task_id, f"开始处理任务 {task_id}", MessageType.SYSTEM)
            
            # 更新任务状态
            await self._update_task_status(task_id, TaskStatus.RUNNING, 0.05)
            
            # 准备共享数据
            shared = {
                "task_id": task_id,
                "prompt": task.inputs.get("content", ""),
                "options": {
                    "style": task.inputs.get("style", "general"),
                    "length": task.inputs.get("length", "medium"),
                    "tone": task.inputs.get("tone", "neutral")
                },
                "progress_tracker": progress_tracker
            }
            
            # 创建进度更新任务
            progress_task = asyncio.create_task(
                self._update_progress_periodically(task_id, shared)
            )
            
            # 创建和启动流程
            flow = self.flow_factory()
            
            # 添加系统消息
            self._add_system_message(task_id, "初始化故事生成流程", MessageType.SYSTEM)
            
            # 执行流程
            try:
                await flow.run_async(shared)
                
                # 检查结果
                result = shared.get("result")
                if result:
                    # 成功完成
                    title = result.get("title", "未命名故事")
                    content = result.get("content", "")
                    
                    # 创建最终故事对象
                    story = Story(
                        title=title,
                        content=content,
                        sections=shared.get("sections", []),
                        metadata={
                            "prompt": shared["prompt"],
                            "options": shared["options"],
                            "generated_at": datetime.now().isoformat()
                        }
                    )
                    
                    # 添加系统消息
                    self._add_system_message(
                        task_id, 
                        f"故事生成完成: {title}",
                        MessageType.RESULT
                    )
                    
                    # 更新任务状态
                    await self._update_task_status(task_id, TaskStatus.COMPLETED, 1.0)
                    
                    # 更新任务结果
                    self.tasks[task_id].result = story.dict()
                    
                    # 创建最终成果
                    artifacts = [{
                        "type": "text/plain",
                        "data": content,
                        "name": f"{title}.txt"
                    }]
                    
                    # 触发webhook通知
                    await self._notify_webhook(
                        task_id, 
                        "completed", 
                        {"artifacts": artifacts, "result": story.dict()}
                    )
                else:
                    # 检查是否有错误
                    error = shared.get("error", "未知错误")
                    
                    # 添加系统消息
                    self._add_system_message(
                        task_id, 
                        f"故事生成失败: {error}",
                        MessageType.ERROR
                    )
                    
                    # 更新任务状态
                    await self._update_task_status(task_id, TaskStatus.FAILED)
                    
                    # 触发webhook通知
                    await self._notify_webhook(
                        task_id, 
                        "failed", 
                        {"error": error}
                    )
            except Exception as e:
                # 记录异常
                logger.error(f"执行流程出错: {str(e)}")
                traceback.print_exc()
                
                # 添加系统消息
                self._add_system_message(
                    task_id, 
                    f"执行流程出错: {str(e)}",
                    MessageType.ERROR
                )
                
                # 更新任务状态
                await self._update_task_status(task_id, TaskStatus.FAILED)
                
                # 触发webhook通知
                await self._notify_webhook(
                    task_id, 
                    "failed", 
                    {"error": str(e)}
                )
            
            # 取消进度更新任务
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
                
        except Exception as e:
            # 记录异常
            logger.error(f"执行任务 {task_id} 出错: {str(e)}")
            traceback.print_exc()
            
            # 添加系统消息
            self._add_system_message(
                task_id, 
                f"执行任务出错: {str(e)}",
                MessageType.ERROR
            )
            
            # 更新任务状态
            await self._update_task_status(task_id, TaskStatus.FAILED)
            
            # 触发webhook通知
            await self._notify_webhook(
                task_id, 
                "failed", 
                {"error": str(e)}
            )
            
        finally:
            # 移除运行中的任务
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]
    
    async def _update_progress_periodically(self, task_id: str, shared: Dict[str, Any]):
        """定期更新任务进度
        
        Args:
            task_id: 任务ID
            shared: 共享存储
        """
        try:
            while True:
                # 从共享存储中获取进度
                progress = shared.get("progress", 0.0)
                
                # 更新任务状态中的进度
                async with self.tasks_lock:
                    if task_id in self.tasks:
                        self.tasks[task_id].progress = progress
                        
                # 触发进度更新事件
                await self._notify_webhook(task_id, "progress", {"progress": progress})
                
                # 等待一段时间
                await asyncio.sleep(PROGRESS_UPDATE_INTERVAL)
                
        except asyncio.CancelledError:
            # 正常取消
            raise
            
        except Exception as e:
            logger.error(f"更新进度时出错: {str(e)}")
            traceback.print_exc()
    
    async def _update_task_status(self, task_id: str, status: TaskStatus, progress: Optional[float] = None):
        """更新任务状态
        
        Args:
            task_id: 任务ID
            status: 任务状态
            progress: 任务进度
        """
        async with self.tasks_lock:
            if task_id not in self.tasks:
                logger.warning(f"任务不存在: {task_id}")
                return
                
            task = self.tasks[task_id]
            
            # 更新状态
            task.status = status
            
            # 如果提供了进度，更新进度
            if progress is not None:
                task.progress = progress
                
            # 更新时间
            task.updated_at = datetime.now()
                
        # 触发状态更新事件
        update_data = {
            "status": status.value,
            "progress": task.progress,
            "updated_at": task.updated_at.isoformat()
        }
        
        # 如果任务失败，添加错误信息
        if status == TaskStatus.FAILED and task.error:
            update_data["error"] = task.error
            
        await self._notify_webhook(task_id, "status_update", update_data)
    
    def _add_system_message(self, task_id: str, content: str, message_type: MessageType):
        """添加系统消息
        
        Args:
            task_id: 任务ID
            content: 消息内容
            message_type: 消息类型
        """
        if task_id not in self.tasks:
            logger.warning(f"任务不存在: {task_id}")
            return
            
        task = self.tasks[task_id]
        
        # 创建消息
        message = Message(
            message_id=str(uuid.uuid4()),
            sender=AgentRole.COORDINATOR,
            message_type=message_type,
            content=content
        )
        
        # 添加到任务消息列表
        task.messages.append(message)
        
        # 触发消息事件
        asyncio.create_task(
            self._notify_webhook(task_id, "message", message)
        )
    
    async def add_agent_message(
        self, 
        task_id: str, 
        sender: AgentRole, 
        receiver: Optional[AgentRole],
        content: str, 
        message_type: MessageType,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """添加代理消息
        
        Args:
            task_id: 任务ID
            sender: 发送者角色
            receiver: 接收者角色
            content: 消息内容
            message_type: 消息类型
            metadata: 元数据
        """
        async with self.tasks_lock:
            if task_id not in self.tasks:
                logger.warning(f"任务不存在: {task_id}")
                return
                
            task = self.tasks[task_id]
            
            # 创建消息
            message = Message(
                message_id=str(uuid.uuid4()),
                sender=sender,
                receiver=receiver,
                message_type=message_type,
                content=content,
                metadata=metadata or {}
            )
            
            # 添加到任务消息列表
            task.messages.append(message)
            
            # 触发消息事件
            await self._notify_webhook(task_id, "message", message)
    
    async def _notify_webhook(self, task_id: str, event: str, data: Any):
        """通知webhook回调
        
        Args:
            task_id: 任务ID
            event: 事件类型
            data: 事件数据
        """
        if task_id not in self.webhooks:
            return
            
        callbacks = list(self.webhooks[task_id])
        
        for callback in callbacks:
            try:
                await callback(event, data)
            except Exception as e:
                logger.error(f"调用webhook回调时出错: {str(e)}")
                traceback.print_exc()
    
    async def _task_timeout(self, task_id: str) -> None:
        """
        任务超时处理
        
        Args:
            task_id: 任务ID
        """
        try:
            # 等待超时时间
            await asyncio.sleep(TASK_TIMEOUT)
            
            # 检查任务是否仍在运行
            if (task_id in self.tasks and 
                self.tasks[task_id].status in ["pending", "running"]):
                
                logger.warning(f"任务超时: {task_id}")
                
                # 取消任务
                if task_id in self.running_tasks:
                    self.running_tasks[task_id].cancel()
                    del self.running_tasks[task_id]
                
                # 更新状态
                await self.complete_task(
                    task_id, 
                    None, 
                    False, 
                    "任务超时"
                )
        except asyncio.CancelledError:
            # 超时任务被取消
            pass
        except Exception as e:
            logger.error(f"任务超时处理时出错: {str(e)}")
            traceback.print_exc()
    
    async def _on_progress_update(self, progress: TaskProgress) -> None:
        """
        进度更新回调
        
        Args:
            progress: 任务进度
        """
        task_id = progress.task_id
        
        # 通知订阅者
        if task_id in self.webhooks:
            update = {
                "task_id": task_id,
                "state": {
                    "status": progress.status,
                    "progress": progress.progress,
                    "message": progress.message
                }
            }
            
            if progress.artifacts:
                update["state"]["artifacts"] = progress.artifacts
                
            # 当任务完成时，包含结果
            if progress.status in [TaskStatus.SUCCEEDED, TaskStatus.FAILED]:
                if "result" in progress.artifacts:
                    update["state"]["result"] = progress.artifacts["result"]
                
            # 通知所有订阅者
            for send_update in self.webhooks[task_id]:
                try:
                    await send_update(update)
                except Exception as e:
                    logger.error(f"通知订阅者时出错: {str(e)}")

class StoryGeneratorTaskManager(TaskManager):
    """
    故事生成器任务管理器
    实现故事生成的具体任务执行逻辑
    """
    
    def __init__(self, flow_factory):
        """
        初始化故事生成器任务管理器
        
        Args:
            flow_factory: 创建故事生成流程的工厂函数
        """
        super().__init__()
        self.flow_factory = flow_factory
        
    async def _execute_task(self, task_id: str):
        """执行故事生成任务
        
        Args:
            task_id: 任务ID
        """
        try:
            # 获取任务
            task = await self.get_task(task_id)
            if not task:
                logger.error(f"任务不存在: {task_id}")
                return
                
            # 记录开始时间
            start_time = time.time()
            
            # 准备共享存储
            shared = {
                "task_id": task_id,
                "prompt": task.prompt,
                "task_manager": self,  # 用于回调
                "progress": 0.0,
                "outline": None,
                "sections": [],
                "result": None,
                "error": None
            }
            
            # 创建故事生成流程
            flow = self.flow_factory()
            
            # 启动进度更新任务
            progress_task = asyncio.create_task(
                self._update_progress_periodically(task_id, shared)
            )
            
            try:
                # 执行流
                await flow.run_async(shared)
                
                # 检查结果
                if "story" in shared["results"]:
                    # 成功完成
                    await self.complete_task(
                        task_id,
                        shared["results"],
                        True,
                        "故事生成完成"
                    )
                else:
                    # 没有生成故事
                    await self.complete_task(
                        task_id,
                        shared["results"],
                        False,
                        "未能生成故事"
                    )
                    
            except asyncio.CancelledError:
                # 任务被取消
                logger.info(f"任务被取消: {task_id}")
                
                # 更新任务状态
                await self._update_task_status(task_id, TaskStatus.CANCELED)
                
                # 添加消息
                self._add_system_message(
                    task_id,
                    "任务已取消",
                    MessageType.TEXT
                )
                
                # 重新抛出异常，以便正确处理
                raise
                
            except Exception as e:
                # 任务执行出错
                error_msg = f"任务执行出错: {str(e)}"
                logger.error(error_msg)
                traceback.print_exc()
                
                # 更新任务状态和错误
                async with self.tasks_lock:
                    task.error = error_msg
                    
                # 添加错误消息
                self._add_system_message(
                    task_id,
                    error_msg,
                    MessageType.ERROR
                )
                
                # 更新任务状态
                await self._update_task_status(task_id, TaskStatus.FAILED)
                
            finally:
                # 取消进度更新任务
                progress_task.cancel()
                try:
                    await progress_task
                except asyncio.CancelledError:
                    pass
                    
            # 记录结束时间和总耗时
            end_time = time.time()
            duration = end_time - start_time
            logger.info(f"任务 {task_id} 已完成，耗时: {duration:.2f}秒")
            
            # 从运行中任务列表移除
            async with self.tasks_lock:
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
                    
        except asyncio.CancelledError:
            logger.info(f"任务 {task_id} 被取消")
            
            # 从运行中任务列表移除
            async with self.tasks_lock:
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]
            
            # 重新抛出异常，以便正确处理
            raise
            
        except Exception as e:
            # 处理其他异常
            error_msg = f"任务执行过程中发生未预期的错误: {str(e)}"
            logger.error(error_msg)
            traceback.print_exc()
            
            # 更新任务状态和错误
            async with self.tasks_lock:
                if task_id in self.tasks:
                    self.tasks[task_id].error = error_msg
                    
            # 添加错误消息
            self._add_system_message(
                task_id,
                error_msg,
                MessageType.ERROR
            )
            
            # 更新任务状态
            await self._update_task_status(task_id, TaskStatus.FAILED)
            
            # 从运行中任务列表移除
            async with self.tasks_lock:
                if task_id in self.running_tasks:
                    del self.running_tasks[task_id]

async def test_task_manager():
    """测试任务管理器"""
    
    # 定义一个简单的流程工厂
    def flow_factory():
        return MockFlow()
    
    # 模拟流程类    
    class MockFlow:
        async def run_async(self, shared):
            print("模拟流程运行...")
            
            # 模拟进度更新
            for i in range(1, 11):
                progress = 0.2 + i * 0.07  # 从0.2到0.9
                message = f"正在生成故事 {int(progress*100)}%"
                progress_tracker.update_progress(
                    shared["task_id"], 
                    progress, 
                    message
                )
                await asyncio.sleep(0.5)
                
            # 生成结果
            shared["results"] = {
                "story": "这是一个由AI生成的测试故事。从前有一个小村庄..."
            }
            
            print("模拟流程完成")
    
    # 创建任务管理器
    task_manager = StoryGeneratorTaskManager(flow_factory)
    
    # 定义更新回调
    async def send_update(update):
        print(f"任务更新: {json.dumps(update, indent=2, ensure_ascii=False)}")
    
    # 发送任务
    response = await task_manager.handle_task_send({
        "inputs": {
            "prompt": "写一个关于太空探索的故事"
        }
    })
    
    task_id = response["task_id"]
    print(f"创建任务: {task_id}")
    
    # 订阅任务
    await task_manager.handle_task_subscribe({"task_id": task_id}, send_update)
    
    # 等待任务完成
    while True:
        state = await task_manager.get_task_state(task_id)
        if state["status"] in ["succeeded", "failed", "canceled"]:
            break
        await asyncio.sleep(0.5)
    
    print("任务完成")

if __name__ == "__main__":
    asyncio.run(test_task_manager()) 