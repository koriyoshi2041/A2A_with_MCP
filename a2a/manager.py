"""
任务管理器模块

负责创建、管理和执行故事生成任务
"""

import os
import sys
import time
import uuid
import json
import asyncio
from typing import Dict, List, Any, Optional, Callable, Union

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TASK_TIMEOUT, MAX_RETRIES
from utils.logging import get_logger, log_function_call, log_async_function_call
from utils.progress import progress_tracker, update_progress
from mcp.client import MCPClient, MCPClientException
from flow.flows import StoryFlowFactory

logger = get_logger(__name__)

class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        """初始化任务管理器"""
        self.tasks = {}  # 存储所有任务
        self.lock = asyncio.Lock()  # 用于任务字典的并发访问
        self.mcp_client = MCPClient()  # MCP客户端
        self.flow_factory = StoryFlowFactory()  # 流程工厂
        
        logger.info("任务管理器初始化完成")
    
    @log_async_function_call
    async def create_task(self, 
                        prompt: str, 
                        task_type: str = "story",
                        options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """创建新任务
        
        Args:
            prompt: 用户提示词
            task_type: 任务类型，默认为"story"
            options: 任务选项
            
        Returns:
            Dict: 包含任务ID和初始状态的字典
        """
        # 生成任务ID
        task_id = str(uuid.uuid4())
        
        # 创建任务时间戳
        created_at = time.time()
        
        # 标准化选项
        if not options:
            options = {}
            
        # 创建任务对象
        task = {
            "id": task_id,
            "type": task_type,
            "prompt": prompt,
            "options": options,
            "status": "pending",
            "created_at": created_at,
            "updated_at": created_at,
            "result": None,
            "error": None
        }
        
        # 保存任务
        async with self.lock:
            self.tasks[task_id] = task
            
        # 创建进度跟踪器
        progress_tracker.create_task(task_id)
        update_progress(task_id, 0, "任务已创建", "pending")
        
        logger.info(f"创建任务: {task_id}, 类型: {task_type}")
        
        # 异步启动任务
        asyncio.create_task(self._execute_task(task_id))
        
        return {
            "task_id": task_id,
            "status": "pending",
            "created_at": created_at
        }
    
    @log_async_function_call
    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务信息，如果任务不存在则返回None
        """
        async with self.lock:
            task = self.tasks.get(task_id)
            
        if not task:
            logger.warning(f"尝试获取不存在的任务: {task_id}")
            return None
            
        # 复制任务信息，避免外部修改
        return task.copy()
    
    @log_async_function_call
    async def get_task_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务进度
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 任务进度信息，如果任务不存在则返回None
        """
        # 获取任务
        async with self.lock:
            task = self.tasks.get(task_id)
            
        if not task:
            logger.warning(f"尝试获取不存在任务的进度: {task_id}")
            return None
            
        # 获取进度
        task_progress = progress_tracker.get_task(task_id)
        if not task_progress:
            return {
                "task_id": task_id,
                "status": task["status"],
                "progress": 0,
                "message": "无进度信息"
            }
            
        progress_data = task_progress.get_progress()
        
        # 返回进度信息
        return {
            "task_id": task_id,
            "status": task["status"],
            "progress": progress_data["progress"],
            "message": progress_data["message"],
            "updated_at": progress_data["last_update_time"]
        }
    
    @log_async_function_call
    async def cancel_task(self, task_id: str) -> bool:
        """取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功取消任务
        """
        # 获取任务
        async with self.lock:
            task = self.tasks.get(task_id)
            
        if not task:
            logger.warning(f"尝试取消不存在的任务: {task_id}")
            return False
            
        # 只能取消未完成的任务
        if task["status"] in ["completed", "failed", "canceled"]:
            logger.warning(f"尝试取消已完成的任务: {task_id}, 状态: {task['status']}")
            return False
            
        # 更新任务状态
        async with self.lock:
            task["status"] = "canceled"
            task["updated_at"] = time.time()
            task["error"] = "用户取消"
            
        # 更新进度
        update_progress(task_id, 0, "任务已取消", "canceled")
        
        logger.info(f"取消任务: {task_id}")
        return True
    
    @log_async_function_call
    async def _execute_task(self, task_id: str) -> None:
        """执行任务
        
        Args:
            task_id: 任务ID
        """
        # 获取任务
        async with self.lock:
            task = self.tasks.get(task_id)
            
        if not task:
            logger.error(f"尝试执行不存在的任务: {task_id}")
            return
            
        # 更新任务状态为运行中
        async with self.lock:
            task["status"] = "running"
            task["updated_at"] = time.time()
            
        # 更新进度
        update_progress(task_id, 0, "任务开始执行", "running")
        
        logger.info(f"开始执行任务: {task_id}, 类型: {task['type']}")
        
        try:
            # 根据任务类型选择不同的执行流程
            if task["type"] == "story":
                result = await self._execute_story_task(task)
            else:
                raise ValueError(f"不支持的任务类型: {task['type']}")
                
            # 任务成功完成
            async with self.lock:
                task["status"] = "completed"
                task["updated_at"] = time.time()
                task["result"] = result
                
            # 更新进度
            update_progress(task_id, 100, "任务已完成", "completed")
            
            logger.info(f"任务完成: {task_id}")
            
        except Exception as e:
            # 任务执行失败
            error_message = str(e)
            logger.error(f"任务执行失败: {task_id}, 错误: {error_message}")
            
            async with self.lock:
                task["status"] = "failed"
                task["updated_at"] = time.time()
                task["error"] = error_message
                
            # 更新进度
            update_progress(task_id, 0, f"任务失败: {error_message}", "failed")
    
    @log_async_function_call
    async def _execute_story_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行故事生成任务
        
        Args:
            task: 任务信息
            
        Returns:
            Dict: 生成的故事结果
        """
        task_id = task["id"]
        prompt = task["prompt"]
        options = task["options"]
        
        # 创建任务的共享数据
        shared = {
            "task_id": task_id,
            "prompt": prompt,
            "options": options.copy(),
            "result": None
        }
        
        # 创建任务进度更新回调
        def progress_callback(data):
            progress = data.get("progress", 0)
            message = data.get("message", "")
            update_progress(task_id, progress, message)
            
        # 订阅进度更新
        progress_tracker.subscribe(task_id, progress_callback)
        
        # 创建故事生成流程
        flow = self.flow_factory.create_story_flow()
        
        try:
            # 运行流程
            await flow.run_async(shared)
            
            # 获取结果
            if not shared.get("result"):
                raise Exception("故事生成失败，未返回结果")
                
            return shared["result"]
            
        except Exception as e:
            logger.error(f"故事生成流程执行失败: {str(e)}")
            raise
        
    @log_async_function_call
    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """清理旧任务
        
        Args:
            max_age_hours: 保留任务的最大小时数
            
        Returns:
            int: 清理的任务数量
        """
        # 当前时间
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # 要删除的任务ID列表
        to_delete = []
        
        # 查找旧任务
        async with self.lock:
            for task_id, task in self.tasks.items():
                # 只清理已完成的任务
                if task["status"] in ["completed", "failed", "canceled"]:
                    task_age = now - task["updated_at"]
                    if task_age > max_age_seconds:
                        to_delete.append(task_id)
        
        # 删除旧任务
        count = 0
        async with self.lock:
            for task_id in to_delete:
                del self.tasks[task_id]
                count += 1
                
        if count > 0:
            logger.info(f"清理了 {count} 个旧任务")
            
        return count
        
# 创建全局任务管理器实例
task_manager = TaskManager()

async def test_task_manager():
    """测试任务管理器"""
    # 创建任务
    prompt = "写一个关于太空探索的科幻故事"
    task_info = await task_manager.create_task(prompt)
    
    task_id = task_info["task_id"]
    print(f"创建任务: {task_id}")
    
    # 监控任务进度
    while True:
        # 获取任务状态
        task = await task_manager.get_task(task_id)
        progress = await task_manager.get_task_progress(task_id)
        
        # 打印进度
        status = task["status"]
        progress_value = progress["progress"]
        message = progress["message"]
        
        print(f"任务状态: {status}, 进度: {progress_value:.1f}%, 消息: {message}")
        
        # 如果任务完成，打印结果
        if status in ["completed", "failed", "canceled"]:
            if status == "completed":
                print("\n生成的故事:")
                print("-" * 50)
                story = task["result"]
                print(f"标题: {story.get('title', '无标题')}")
                print(f"大纲: {story.get('outline', '无大纲')}")
                print("\n内容:")
                print(story.get('content', '无内容'))
                print("-" * 50)
            elif status == "failed":
                print(f"任务失败: {task['error']}")
            elif status == "canceled":
                print("任务已取消")
                
            break
            
        # 等待一段时间再检查
        await asyncio.sleep(1)
    
if __name__ == "__main__":
    asyncio.run(test_task_manager()) 