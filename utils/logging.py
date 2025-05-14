#!/usr/bin/env python3
"""
多代理协作故事生成器项目 - 日志工具
提供统一的日志记录功能
"""

import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
import functools

# 导入配置
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import LOG_LEVEL, LOG_FILE

# 创建日志目录（如果需要）
if LOG_FILE:
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

# 将字符串日志级别转换为logging常量
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}
LOGGING_LEVEL = LOG_LEVELS.get(LOG_LEVEL.upper(), logging.INFO)

# 全局日志格式
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
formatter = logging.Formatter(LOG_FORMAT)

# 缓存记录器实例
loggers = {}

def get_logger(name):
    """获取指定名称的日志记录器
    
    Args:
        name: 日志记录器名称，通常为模块名
        
    Returns:
        日志记录器实例
    """
    # 如果已经创建过该记录器，直接返回
    if name in loggers:
        return loggers[name]
        
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(LOGGING_LEVEL)
    
    # 避免重复处理程序
    if logger.handlers:
        return logger
        
    # 添加控制台处理程序
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 添加文件处理程序（如果配置了日志文件）
    if LOG_FILE:
        try:
            file_handler = RotatingFileHandler(
                LOG_FILE, 
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            # 如果无法写入日志文件，仅记录到控制台
            console_handler.setLevel(logging.WARNING)
            logger.warning(f"无法写入日志文件 {LOG_FILE}: {str(e)}")
        
    # 缓存记录器实例
    loggers[name] = logger
    
    return logger

# 应用默认日志记录器
logger = get_logger('app')

def log_function_call(func):
    """装饰器：记录函数调用
    
    记录函数的调用、结果和异常
    
    Args:
        func: 要装饰的函数
        
    Returns:
        装饰后的函数
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        module_name = func.__module__
        func_name = func.__name__
        logger = get_logger(module_name)
        
        logger.debug(f"调用函数 {func_name}")
        
        try:
            result = func(*args, **kwargs)
            logger.debug(f"函数 {func_name} 完成")
            return result
        except Exception as e:
            logger.exception(f"函数 {func_name} 异常: {str(e)}")
            raise
            
    return wrapper

def log_async_function_call(func):
    """异步函数装饰器：记录异步函数调用
    
    记录异步函数的调用、结果和异常
    
    Args:
        func: 要装饰的异步函数
        
    Returns:
        装饰后的异步函数
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        module_name = func.__module__
        func_name = func.__name__
        logger = get_logger(module_name)
        
        logger.debug(f"调用异步函数 {func_name}")
        
        try:
            result = await func(*args, **kwargs)
            logger.debug(f"异步函数 {func_name} 完成")
            return result
        except Exception as e:
            logger.exception(f"异步函数 {func_name} 异常: {str(e)}")
            raise
            
    return wrapper

if __name__ == "__main__":
    # 测试日志功能
    test_logger = get_logger("test")
    test_logger.debug("这是一条调试日志")
    test_logger.info("这是一条信息日志")
    test_logger.warning("这是一条警告日志")
    test_logger.error("这是一条错误日志")
    
    # 测试装饰器
    @log_function_call
    def test_function(a, b):
        print(f"测试函数：{a} + {b} = {a + b}")
        return a + b
        
    test_function(3, 5) 