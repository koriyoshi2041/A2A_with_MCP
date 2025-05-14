"""
MCP配置模块

定义MCP服务的各项配置
"""

import os
import sys
from typing import Optional, Dict, Any

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logging import get_logger

logger = get_logger(__name__)

# MCP服务URL
MCP_SERVICE_URL = os.environ.get("MCP_SERVICE_URL", "http://localhost:8000/api/v1")

# MCP专用服务URL配置
MCP_SERVICES = {
    "search_service": os.environ.get("MCP_SEARCH_SERVICE", f"{MCP_SERVICE_URL}/search"),
    "outline_service": os.environ.get("MCP_OUTLINE_SERVICE", f"{MCP_SERVICE_URL}/outline"),
    "writing_service": os.environ.get("MCP_WRITING_SERVICE", f"{MCP_SERVICE_URL}/writing"),
    "editing_service": os.environ.get("MCP_EDITING_SERVICE", f"{MCP_SERVICE_URL}/editing"),
}

# MCP服务API密钥
MCP_API_KEY = os.environ.get("MCP_API_KEY", "")

# MCP请求超时时间(秒)
MCP_REQUEST_TIMEOUT = int(os.environ.get("MCP_REQUEST_TIMEOUT", "30"))

# 服务特定超时时间（秒）
MCP_TIMEOUTS = {
    "search_service": int(os.environ.get("MCP_SEARCH_TIMEOUT", "15")),
    "outline_service": int(os.environ.get("MCP_OUTLINE_TIMEOUT", "30")),
    "writing_service": int(os.environ.get("MCP_WRITING_TIMEOUT", "60")),
    "editing_service": int(os.environ.get("MCP_EDITING_TIMEOUT", "90")),
}

# 最大重试次数
MAX_RETRIES = int(os.environ.get("MCP_MAX_RETRIES", "3"))

# 重试间隔时间(秒)
RETRY_INTERVAL = float(os.environ.get("MCP_RETRY_INTERVAL", "2.0"))

# 是否启用调试模式
DEBUG_MODE = os.environ.get("MCP_DEBUG", "false").lower() in ["true", "1", "yes"]

# 健康检查配置
HEALTH_CHECK = {
    "enabled": os.environ.get("MCP_HEALTH_CHECK", "true").lower() in ["true", "1", "yes"],
    "interval": int(os.environ.get("MCP_HEALTH_CHECK_INTERVAL", "60")),
    "timeout": float(os.environ.get("MCP_HEALTH_CHECK_TIMEOUT", "5.0")),
    "required_services": ["search_service", "outline_service"],
    "optional_services": ["writing_service", "editing_service"],
}

def get_mcp_service_url() -> str:
    """获取MCP服务URL
    
    Returns:
        str: 服务URL
    """
    return MCP_SERVICE_URL

def get_service_url(service_name: str) -> str:
    """获取特定MCP服务的URL
    
    Args:
        service_name: 服务名称
        
    Returns:
        str: 服务URL
    """
    return MCP_SERVICES.get(service_name, MCP_SERVICE_URL)

def get_mcp_api_key() -> Optional[str]:
    """获取MCP服务API密钥
    
    Returns:
        Optional[str]: API密钥，如果未配置则返回None
    """
    return MCP_API_KEY if MCP_API_KEY else None

def get_request_timeout(service_name: Optional[str] = None) -> int:
    """获取请求超时时间
    
    Args:
        service_name: 可选的服务名称，用于获取特定服务的超时时间
        
    Returns:
        int: 超时时间(秒)
    """
    if service_name and service_name in MCP_TIMEOUTS:
        return MCP_TIMEOUTS[service_name]
    return MCP_REQUEST_TIMEOUT

def get_max_retries() -> int:
    """获取最大重试次数
    
    Returns:
        int: 重试次数
    """
    return MAX_RETRIES

def get_auth_headers() -> Dict[str, str]:
    """获取认证头信息
    
    Returns:
        Dict[str, str]: 包含认证信息的字典
    """
    headers = {}
    if MCP_API_KEY:
        headers["X-API-Key"] = MCP_API_KEY
    return headers

def is_service_required(service_name: str) -> bool:
    """检查服务是否为必需服务
    
    Args:
        service_name: 服务名称
        
    Returns:
        bool: 如果是必需服务则返回True，否则返回False
    """
    return service_name in HEALTH_CHECK["required_services"]

def get_all_services() -> Dict[str, str]:
    """获取所有配置的服务
    
    Returns:
        Dict[str, str]: 服务名称和URL的字典
    """
    return MCP_SERVICES.copy()

def initialize():
    """初始化MCP配置
    
    验证必要配置项并打印配置信息
    """
    if not MCP_SERVICE_URL:
        logger.warning("MCP服务URL未配置")
    else:
        logger.info(f"MCP服务基础地址: {MCP_SERVICE_URL}")
        
    for service_name, url in MCP_SERVICES.items():
        if is_service_required(service_name) and not url:
            logger.warning(f"必需的MCP服务 {service_name} 未配置URL")
        elif url:
            logger.info(f"MCP {service_name} 地址: {url}")
        
    if not MCP_API_KEY:
        logger.warning("MCP API密钥未配置")
    
    if DEBUG_MODE:
        logger.info("MCP调试模式已启用")
        logger.info(f"默认请求超时: {MCP_REQUEST_TIMEOUT}秒")
        for service, timeout in MCP_TIMEOUTS.items():
            logger.info(f"{service} 超时: {timeout}秒")
        logger.info(f"最大重试次数: {MAX_RETRIES}")
        logger.info(f"重试间隔: {RETRY_INTERVAL}秒")

if __name__ == "__main__":
    initialize()
    print("MCP配置加载完成。") 