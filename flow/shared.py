#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - 共享存储设计
定义系统中的共享数据结构
"""

from typing import Dict, List, Any, Optional
import json

class SharedStore:
    """共享存储类，用于在流程间传递数据"""
    
    def __init__(self, initial_data: Optional[Dict[str, Any]] = None):
        """
        初始化共享存储
        
        Args:
            initial_data: 初始数据
        """
        self._data = {} if initial_data is None else initial_data.copy()
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取指定键的值"""
        return self._data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """设置指定键的值"""
        self._data[key] = value
    
    def update(self, data: Dict[str, Any]) -> None:
        """批量更新多个键值"""
        self._data.update(data)
    
    def delete(self, key: str) -> None:
        """删除指定键"""
        if key in self._data:
            del self._data[key]
    
    def has(self, key: str) -> bool:
        """检查是否存在指定键"""
        return key in self._data
    
    def clear(self) -> None:
        """清空所有数据"""
        self._data.clear()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self._data.copy()
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self._data, ensure_ascii=False)
    
    def __getitem__(self, key):
        """支持字典风格访问: shared[key]"""
        return self._data[key]
    
    def __setitem__(self, key, value):
        """支持字典风格设置: shared[key] = value"""
        self._data[key] = value
    
    def __delitem__(self, key):
        """支持字典风格删除: del shared[key]"""
        del self._data[key]
    
    def __contains__(self, key):
        """支持使用in操作符: key in shared"""
        return key in self._data
    
    def __repr__(self):
        """字符串表示"""
        return f"SharedStore({self._data})"

# 默认共享存储结构
DEFAULT_SHARED_STORE = {
    # 任务信息
    "task_id": None,             # 任务ID
    "prompt": "",                # 用户故事提示
    "options": {                 # 故事生成选项
        "style": "general",      # 风格 (sci-fi, fantasy, mystery, etc)
        "length": "medium",      # 长度 (short, medium, long)
        "tone": "neutral"        # 语调 (dramatic, humorous, serious, etc)
    },
    "progress": 0.0,             # 当前进度 (0.0-1.0)
    "progress_tracker": None,    # 进度跟踪器
    
    # 服务与工具
    "mcp_service_url": None,     # MCP服务URL
    "available_services": [],    # 可用服务列表
    "mcp_tools": {},             # 服务类型 -> 工具列表的映射
    
    # 搜索相关
    "search_queries": [],         # 已执行的搜索查询
    "search_results": {},         # 查询 -> 结果的映射
    
    # 大纲相关
    "title": "",                  # 故事标题
    "outline": {                  # 故事大纲
        "title": "",              # 标题
        "sections": []            # 章节列表
    },
    
    # 内容相关
    "content": "",                # 故事内容
    "sections": [],               # 章节内容列表
    
    # 结果
    "result": None,               # 最终结果
    "error": None                 # 错误信息
}

def create_shared_store(task_id: str, inputs: Dict[str, Any], 
                      progress_tracker=None) -> SharedStore:
    """
    创建一个初始化的共享存储
    
    Args:
        task_id: 任务ID
        inputs: 任务输入
        progress_tracker: 进度跟踪器
        
    Returns:
        初始化的共享存储
    """
    shared_data = DEFAULT_SHARED_STORE.copy()
    
    # 更新任务信息
    shared_data["task_id"] = task_id
    
    # 提取主要输入
    if "content" in inputs:
        shared_data["prompt"] = inputs["content"]
    elif "prompt" in inputs:
        shared_data["prompt"] = inputs["prompt"]
    
    # 处理选项
    if "options" in inputs:
        shared_data["options"].update(inputs["options"])
    else:
        # 提取可能的单独选项
        for key in ["style", "length", "tone"]:
            if key in inputs:
                shared_data["options"][key] = inputs[key]
    
    # 设置MCP服务URL
    if "mcp_service_url" in inputs:
        shared_data["mcp_service_url"] = inputs["mcp_service_url"]
    
    # 设置进度跟踪器
    if progress_tracker:
        shared_data["progress_tracker"] = progress_tracker
        
    return SharedStore(shared_data)

# 测试共享存储
if __name__ == "__main__":
    # 创建共享存储
    shared = create_shared_store(
        "test-task-123", 
        {"content": "创作一个科幻故事", "style": "sci-fi"}
    )
    
    # 访问和修改
    print(f"任务ID: {shared['task_id']}")
    print(f"提示: {shared['prompt']}")
    print(f"选项: {shared['options']}")
    
    # 使用get方法
    print(f"大纲: {shared.get('outline')}")
    
    # 修改数据
    shared["title"] = "太空冒险"
    shared["outline"]["title"] = "太空冒险"
    shared["outline"]["sections"] = [
        {"id": "section1", "title": "引言", "content": "人类踏上星际旅程..."},
        {"id": "section2", "title": "发现", "content": "宇航员发现了一个奇怪的信号..."}
    ]
    
    # 添加搜索结果
    shared["search_results"]["太空探索"] = {"text": "关于太空探索的搜索结果..."}
    
    # 添加内容
    shared["content"] = "这是完成的故事内容..."
    shared["sections"] = shared["outline"]["sections"]
    
    # 添加结果
    shared["result"] = {
        "title": shared["title"],
        "content": shared["content"],
        "sections": shared["sections"]
    }
    
    # 转换为JSON查看
    print(shared.to_json()) 