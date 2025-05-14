"""
API服务模块

提供HTTP API接口服务，用于创建和管理故事生成任务
"""

import os
import sys
import json
import time
import asyncio
from typing import Dict, List, Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import A2A_SERVER_HOST, A2A_SERVER_PORT
from utils.logging import get_logger
from a2a.manager import task_manager

# 创建FastAPI应用
app = FastAPI(
    title="故事生成服务",
    description="基于A2A和MCP的多智能体协作故事生成系统",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头部
)

# 获取日志记录器
logger = get_logger(__name__)

# 定义数据模型
class TaskCreateRequest(BaseModel):
    """任务创建请求模型"""
    prompt: str = Field(..., description="故事提示词")
    task_type: str = Field("story", description="任务类型，默认为故事生成")
    options: Dict[str, Any] = Field(default_factory=dict, description="任务选项")

class TaskResponse(BaseModel):
    """任务响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    created_at: float = Field(..., description="创建时间")

class TaskProgressResponse(BaseModel):
    """任务进度响应模型"""
    task_id: str = Field(..., description="任务ID")
    status: str = Field(..., description="任务状态")
    progress: float = Field(..., description="进度百分比")
    message: str = Field("", description="状态消息")
    updated_at: Optional[float] = Field(None, description="更新时间")

class TaskDetailResponse(BaseModel):
    """任务详情响应模型"""
    id: str = Field(..., description="任务ID")
    type: str = Field(..., description="任务类型")
    prompt: str = Field(..., description="提示词")
    options: Dict[str, Any] = Field(..., description="任务选项")
    status: str = Field(..., description="任务状态")
    created_at: float = Field(..., description="创建时间")
    updated_at: float = Field(..., description="更新时间")
    result: Optional[Dict[str, Any]] = Field(None, description="任务结果")
    error: Optional[str] = Field(None, description="错误信息")

@app.get("/")
async def read_root():
    """API根路径"""
    return {"message": "故事生成服务API", "version": "1.0.0"}

@app.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskCreateRequest):
    """创建任务"""
    try:
        # 创建任务
        task_info = await task_manager.create_task(
            prompt=request.prompt,
            task_type=request.task_type,
            options=request.options
        )
        
        logger.info(f"通过API创建任务: {task_info['task_id']}")
        return task_info
        
    except Exception as e:
        logger.error(f"创建任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")

@app.get("/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(task_id: str):
    """获取任务详情"""
    # 获取任务
    task = await task_manager.get_task(task_id)
    
    # 检查任务是否存在
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
        
    return task

@app.get("/tasks/{task_id}/progress", response_model=TaskProgressResponse)
async def get_task_progress(task_id: str):
    """获取任务进度"""
    # 获取任务进度
    progress = await task_manager.get_task_progress(task_id)
    
    # 检查任务是否存在
    if not progress:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
        
    return progress

@app.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消任务"""
    # 取消任务
    result = await task_manager.cancel_task(task_id)
    
    # 检查任务是否存在或已完成
    if not result:
        task = await task_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
        else:
            raise HTTPException(status_code=400, detail=f"任务 {task_id} 无法取消，状态: {task['status']}")
    
    return {"message": f"任务 {task_id} 已取消"}

@app.on_event("startup")
async def startup_event():
    """服务启动时执行的操作"""
    # 启动后台任务清理任务
    asyncio.create_task(periodic_cleanup())
    logger.info("API服务已启动")

@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时执行的操作"""
    logger.info("API服务正在关闭")

async def periodic_cleanup():
    """定期清理旧任务"""
    while True:
        try:
            # 每12小时清理一次任务
            await asyncio.sleep(12 * 3600)
            count = await task_manager.cleanup_old_tasks(24)
            logger.info(f"定期清理: 清理了 {count} 个旧任务")
        except Exception as e:
            logger.error(f"定期清理任务异常: {str(e)}")
            # 出错后等待一段时间再重试
            await asyncio.sleep(300)

def start_server():
    """启动API服务器"""
    host = A2A_SERVER_HOST
    port = A2A_SERVER_PORT
    
    # 使用uvicorn启动FastAPI应用
    uvicorn.run(
        "a2a.api:app", 
        host=host, 
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    start_server() 