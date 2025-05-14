"""
A2A协议的数据模型和模式定义
"""

from enum import Enum
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field

# 任务状态枚举
class TaskStatus(str, Enum):
    PENDING = "pending"       # 等待中
    RUNNING = "running"       # 运行中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    CANCELED = "canceled"     # 已取消

# 代理角色枚举
class AgentRole(str, Enum):
    COORDINATOR = "coordinator"   # 协调者
    OUTLINER = "outliner"         # 大纲制作者
    WRITER = "writer"             # 写作者
    EDITOR = "editor"             # 编辑者
    RESEARCHER = "researcher"     # 研究者

# 代理间消息类型
class MessageType(str, Enum):
    TEXT = "text"                 # 纯文本
    ACTION = "action"             # 动作
    RESULT = "result"             # 结果
    ERROR = "error"               # 错误
    PROGRESS = "progress"         # 进度
    SYSTEM = "system"             # 系统消息

# 基础消息模型
class Message(BaseModel):
    message_id: str = Field(..., description="消息ID")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    sender: AgentRole = Field(..., description="发送者角色")
    receiver: Optional[AgentRole] = Field(None, description="接收者角色，None表示广播")
    message_type: MessageType = Field(..., description="消息类型")
    content: str = Field(..., description="消息内容")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")

# 任务模型
class Task(BaseModel):
    task_id: str = Field(..., description="任务ID")
    inputs: Dict[str, Any] = Field(..., description="任务输入参数")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    progress: float = Field(default=0.0, description="任务进度，0-1.0")
    messages: List[Message] = Field(default_factory=list, description="任务消息列表")
    result: Optional[Any] = Field(None, description="最终故事结果")
    error: Optional[str] = Field(None, description="错误信息")
    
    class Config:
        use_enum_values = True

# 故事大纲模型
class StoryOutline(BaseModel):
    title: str = Field(..., description="故事标题")
    sections: List[Dict[str, Any]] = Field(..., description="章节大纲")
    
    class Config:
        schema_extra = {
            "example": {
                "title": "迷失的星球",
                "sections": [
                    {"id": "section1", "title": "意外着陆", "content": "探险队遭遇陨石带，被迫在未知行星紧急着陆"},
                    {"id": "section2", "title": "探索新世界", "content": "队员们开始探索这个神秘的星球"},
                    {"id": "section3", "title": "危险发现", "content": "队员们发现行星上有古老文明的遗迹"},
                    {"id": "section4", "title": "返回地球", "content": "面对困境，队员们寻找返回地球的方法"}
                ]
            }
        }

# 故事章节模型
class StorySection(BaseModel):
    section_id: str = Field(..., description="章节ID")
    title: str = Field(..., description="章节标题")
    content: str = Field(..., description="章节内容")
    order: int = Field(..., description="章节顺序")
    
    class Config:
        schema_extra = {
            "example": {
                "section_id": "section_1",
                "title": "意外着陆",
                "content": "飞船穿越大气层时剧烈震动，警报声不断...",
                "order": 1
            }
        }

# 完整故事模型
class Story(BaseModel):
    title: str = Field(..., description="故事标题")
    content: str = Field(..., description="完整故事内容")
    sections: List[Dict[str, Any]] = Field(default_factory=list, description="故事章节列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    class Config:
        schema_extra = {
            "example": {
                "title": "迷失的星球",
                "content": "完整的故事内容...",
                "sections": [
                    {"id": "section1", "title": "意外着陆", "content": "飞船穿越大气层时剧烈震动，警报声不断..."},
                    {"id": "section2", "title": "探索新世界", "content": "队员们开始探索这个神秘的星球..."}
                ],
                "metadata": {
                    "prompt": "写一个关于太空探险的科幻故事",
                    "options": {"style": "sci-fi", "length": "medium", "tone": "adventurous"},
                    "generated_at": "2024-06-15T10:30:00.000Z"
                }
            }
        }

# API请求和响应模型
class CreateTaskRequest(BaseModel):
    task: Dict[str, Any] = Field(..., description="任务定义")
    
    class Config:
        schema_extra = {
            "example": {
                "task": {
                    "input": {
                        "content": "写一个关于太空探险的科幻故事",
                        "style": "sci-fi",
                        "length": "medium",
                        "tone": "adventurous"
                    }
                }
            }
        }

class TaskResponse(BaseModel):
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    progress: float = Field(..., description="任务进度")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

class TaskProgressResponse(TaskResponse):
    messages: List[Message] = Field(default_factory=list, description="最新消息")

class TaskResultResponse(TaskResponse):
    result: Any = Field(..., description="任务结果")

class ErrorResponse(BaseModel):
    error: str = Field(..., description="错误信息")
    detail: Optional[str] = Field(None, description="详细错误信息") 