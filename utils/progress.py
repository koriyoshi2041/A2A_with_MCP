#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - 进度处理工具
提供任务进度跟踪和报告功能
"""

import os
import sys
import time
import threading
from typing import Dict, Any, Optional, Callable

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logging import get_logger

logger = get_logger(__name__)

class TaskProgress:
    """任务进度跟踪器"""
    
    def __init__(self, task_id: str, total_steps: int = 100):
        """初始化进度跟踪器
        
        Args:
            task_id: 任务ID
            total_steps: 总步数
        """
        self.task_id = task_id
        self.total_steps = total_steps
        self.current_step = 0
        self.progress = 0.0
        self.status = "pending"
        self.message = ""
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.complete_time = None
        self.subscribers = []
        self.lock = threading.RLock()
    
    def update(self, 
               step: Optional[int] = None, 
               progress: Optional[float] = None, 
               status: Optional[str] = None, 
               message: Optional[str] = None,
               extra_data: Optional[Dict[str, Any]] = None):
        """更新进度
        
        Args:
            step: 当前步骤
            progress: 进度百分比(0-100)
            status: 状态
            message: 状态消息
            extra_data: 额外数据
        """
        with self.lock:
            # 更新步骤
            if step is not None:
                if step < 0:
                    step = 0
                elif step > self.total_steps:
                    step = self.total_steps
                self.current_step = step
                self.progress = (step / self.total_steps) * 100
                
            # 直接更新进度
            if progress is not None:
                if progress < 0:
                    progress = 0
                elif progress > 100:
                    progress = 100
                self.progress = progress
                
            # 更新状态
            if status:
                old_status = self.status
                self.status = status
                
                # 如果任务完成，记录完成时间
                if status in ["completed", "failed", "canceled"] and old_status not in ["completed", "failed", "canceled"]:
                    self.complete_time = time.time()
                    
                # 如果任务从完成状态变回运行状态，重置完成时间
                if status == "running" and old_status in ["completed", "failed", "canceled"]:
                    self.complete_time = None
            
            # 更新消息
            if message:
                self.message = message
                
            # 更新时间
            self.last_update_time = time.time()
            
            # 通知订阅者
            update_data = {
                "task_id": self.task_id,
                "progress": self.progress,
                "status": self.status,
                "message": self.message,
                "current_step": self.current_step,
                "total_steps": self.total_steps,
                "time": self.last_update_time
            }
            
            # 添加额外数据
            if extra_data:
                update_data.update(extra_data)
                
            self._notify_subscribers(update_data)
    
    def get_progress(self) -> Dict[str, Any]:
        """获取当前进度
        
        Returns:
            进度信息
        """
        with self.lock:
            # 计算耗时
            elapsed = self.last_update_time - self.start_time
            
            # 如果未完成，计算预计剩余时间
            remaining = None
            if self.status == "running" and self.progress > 0:
                rate = elapsed / self.progress
                remaining = rate * (100 - self.progress)
                
            # 如果已完成，计算总耗时
            total_time = None
            if self.complete_time:
                total_time = self.complete_time - self.start_time
                
            return {
                "task_id": self.task_id,
                "progress": self.progress,
                "status": self.status,
                "message": self.message,
                "current_step": self.current_step,
                "total_steps": self.total_steps,
                "start_time": self.start_time,
                "last_update_time": self.last_update_time,
                "complete_time": self.complete_time,
                "elapsed_time": elapsed,
                "estimated_remaining": remaining,
                "total_time": total_time
            }
    
    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """订阅进度更新
        
        Args:
            callback: 回调函数
        """
        with self.lock:
            if callback not in self.subscribers:
                self.subscribers.append(callback)
                
                # 立即通知当前状态
                callback(self.get_progress())
    
    def unsubscribe(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """取消订阅进度更新
        
        Args:
            callback: 回调函数
        """
        with self.lock:
            if callback in self.subscribers:
                self.subscribers.remove(callback)
    
    def _notify_subscribers(self, data: Dict[str, Any]) -> None:
        """通知所有订阅者
        
        Args:
            data: 通知数据
        """
        for callback in list(self.subscribers):
            try:
                callback(data)
            except Exception as e:
                logger.error(f"调用进度更新回调出错: {str(e)}")
                # 移除失败的订阅者
                self.subscribers.remove(callback)

class ProgressTracker:
    """进度跟踪管理器"""
    
    def __init__(self):
        """初始化进度跟踪管理器"""
        self.tasks = {}
        self.lock = threading.RLock()
    
    def create_task(self, task_id: str, total_steps: int = 100) -> TaskProgress:
        """创建任务进度跟踪器
        
        Args:
            task_id: 任务ID
            total_steps: 总步数
            
        Returns:
            任务进度跟踪器
        """
        with self.lock:
            if task_id in self.tasks:
                # 如果任务已存在但已完成，重新创建
                task = self.tasks[task_id]
                if task.status in ["completed", "failed", "canceled"]:
                    self.tasks[task_id] = TaskProgress(task_id, total_steps)
            else:
                self.tasks[task_id] = TaskProgress(task_id, total_steps)
                
            return self.tasks[task_id]
    
    def get_task(self, task_id: str) -> Optional[TaskProgress]:
        """获取任务进度跟踪器
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务进度跟踪器
        """
        with self.lock:
            return self.tasks.get(task_id)
    
    def remove_task(self, task_id: str) -> None:
        """移除任务进度跟踪器
        
        Args:
            task_id: 任务ID
        """
        with self.lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
    
    def update_progress(self, 
                        task_id: str, 
                        step: Optional[int] = None, 
                        progress: Optional[float] = None, 
                        status: Optional[str] = None, 
                        message: Optional[str] = None,
                        extra_data: Optional[Dict[str, Any]] = None) -> None:
        """更新任务进度
        
        Args:
            task_id: 任务ID
            step: 当前步骤
            progress: 进度百分比(0-100)
            status: 状态
            message: 状态消息
            extra_data: 额外数据
        """
        with self.lock:
            task = self.get_task(task_id)
            if task:
                task.update(step, progress, status, message, extra_data)
            else:
                logger.warning(f"尝试更新不存在的任务: {task_id}")
    
    def subscribe(self, task_id: str, callback: Callable[[Dict[str, Any]], None]) -> bool:
        """订阅任务进度更新
        
        Args:
            task_id: 任务ID
            callback: 回调函数
            
        Returns:
            是否成功订阅
        """
        with self.lock:
            task = self.get_task(task_id)
            if task:
                task.subscribe(callback)
                return True
            else:
                logger.warning(f"尝试订阅不存在的任务: {task_id}")
                return False
    
    def unsubscribe(self, task_id: str, callback: Callable[[Dict[str, Any]], None]) -> bool:
        """取消订阅任务进度更新
        
        Args:
            task_id: 任务ID
            callback: 回调函数
            
        Returns:
            是否成功取消订阅
        """
        with self.lock:
            task = self.get_task(task_id)
            if task:
                task.unsubscribe(callback)
                return True
            else:
                logger.warning(f"尝试取消订阅不存在的任务: {task_id}")
                return False

# 全局进度跟踪管理器
progress_tracker = ProgressTracker()

def update_progress(
    task_id: str, 
    progress: float, 
    message: str = "", 
    status: str = "running",
    extra_data: Optional[Dict[str, Any]] = None
) -> None:
    """更新任务进度的便捷函数
    
    Args:
        task_id: 任务ID
        progress: 进度百分比(0-100)
        message: 状态消息
        status: 状态
        extra_data: 额外数据
    """
    progress_tracker.update_progress(
        task_id, 
        progress=progress, 
        status=status, 
        message=message,
        extra_data=extra_data
    )

def test_progress_tracker():
    """测试进度跟踪器"""
    import random
    
    # 创建任务
    task_id = "test-task-123"
    task = progress_tracker.create_task(task_id)
    
    # 订阅进度更新
    def progress_callback(data):
        print(f"进度更新: {data['progress']:.1f}%, {data['message']}")
        
    progress_tracker.subscribe(task_id, progress_callback)
    
    # 模拟任务进度
    print("开始模拟任务进度...")
    for i in range(10):
        # 随机进度增量
        progress = (i + 1) * 10 + random.uniform(-3, 3)
        message = f"处理步骤 {i+1}/10"
        
        # 更新进度
        update_progress(task_id, progress, message)
        
        # 等待
        time.sleep(0.5)
        
    # 完成任务
    update_progress(task_id, 100, "任务完成", "completed")
    
    # 获取最终进度
    final_progress = task.get_progress()
    print(f"\n最终状态: {final_progress['status']}")
    print(f"总耗时: {final_progress['total_time']:.2f}秒")
    
if __name__ == "__main__":
    test_progress_tracker() 