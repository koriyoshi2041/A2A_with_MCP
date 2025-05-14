#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - 配置文件
"""

import os
from typing import Dict, Any

# 日志配置
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE = os.environ.get("LOG_FILE", "logs/a2a_with_mcp.log")

# A2A服务器配置
A2A_SERVER_HOST = os.environ.get("A2A_SERVER_HOST", "0.0.0.0")
A2A_SERVER_PORT = int(os.environ.get("A2A_SERVER_PORT", "5000"))
MAX_CONCURRENT_TASKS = int(os.environ.get("MAX_CONCURRENT_TASKS", "10"))

# MCP服务配置
MCP_SERVICE_HOST = os.environ.get("MCP_SERVICE_HOST", "localhost")
MCP_SERVICE_PORT = int(os.environ.get("MCP_SERVICE_PORT", "8000"))
MCP_SERVICE_URL = os.environ.get("MCP_SERVICE_URL", f"http://{MCP_SERVICE_HOST}:{MCP_SERVICE_PORT}/api")
MCP_SERVICE_TIMEOUT = int(os.environ.get("MCP_SERVICE_TIMEOUT", "30"))

# 重试配置
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
RETRY_WAIT_TIME = int(os.environ.get("RETRY_WAIT_TIME", "2"))

# LLM配置（用于本地LLM功能）
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "2000"))

# 故事生成器默认选项
DEFAULT_STORY_OPTIONS = {
    "style": "general",    # general, sci-fi, fantasy, mystery, etc.
    "length": "medium",    # short, medium, long
    "tone": "neutral",     # neutral, dramatic, humorous, serious, etc.
    "edit_level": "moderate"  # light, moderate, intensive
}

# 可用的服务类型
AVAILABLE_SERVICE_TYPES = ["search", "outline", "writing", "editing"]

# 工具调用配置
TOOL_CALL_TIMEOUT = int(os.environ.get("TOOL_CALL_TIMEOUT", "60"))  # 秒

def get_mcp_service_url(service_type: str = None) -> str:
    """
    获取MCP服务URL
    
    Args:
        service_type: 服务类型，如果指定则返回特定服务URL
        
    Returns:
        MCP服务URL
    """
    # 基础URL
    base_url = MCP_SERVICE_URL
    
    # 如果未指定服务类型，返回基础URL
    if not service_type:
        return base_url
    
    # 特定服务URL的环境变量
    env_var = f"MCP_{service_type.upper()}_SERVICE_URL"
    specific_url = os.environ.get(env_var)
    
    if specific_url:
        return specific_url
    
    # 否则在基础URL上添加服务类型
    if base_url.endswith('/'):
        return f"{base_url}{service_type}"
    else:
        return f"{base_url}/{service_type}"

# 测试配置
if __name__ == "__main__":
    import json
    
    print("=== 配置信息 ===")
    print(f"A2A服务器: {A2A_SERVER_HOST}:{A2A_SERVER_PORT}")
    print(f"MCP服务: {MCP_SERVICE_URL}")
    print(f"最大并发任务: {MAX_CONCURRENT_TASKS}")
    print(f"日志级别: {LOG_LEVEL}")
    
    for service_type in AVAILABLE_SERVICE_TYPES:
        print(f"{service_type}服务URL: {get_mcp_service_url(service_type)}")
        
    print(f"默认故事选项: {json.dumps(DEFAULT_STORY_OPTIONS, ensure_ascii=False, indent=2)}") 