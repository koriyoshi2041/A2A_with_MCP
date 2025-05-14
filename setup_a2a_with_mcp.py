#!/usr/bin/env python3
"""
多代理协作故事生成器项目设置脚本
该脚本帮助创建项目的基本目录结构和文件框架
"""

import os
import sys
import shutil
import argparse
from pathlib import Path

# 目标目录结构
PROJECT_STRUCTURE = {
    "": ["README.md", "requirements.txt", "config.py", "a2a_server.py", "a2a_client.py"],
    "flow": ["__init__.py", "nodes.py", "flows.py", "shared.py"],
    "a2a": ["__init__.py", "task_manager.py", "server.py", "client.py"],
    "mcp": ["__init__.py", "client.py"],
    "mcp/services": ["__init__.py", "search_service.py", "outline_service.py", 
                    "writing_service.py", "editing_service.py"],
    "mcp/local": ["__init__.py", "search.py", "outline.py", "writing.py", "editing.py"],
    "utils": ["__init__.py", "llm.py", "logging.py", "progress.py"]
}

def create_directory_structure(base_path):
    """创建目录结构"""
    for directory in PROJECT_STRUCTURE:
        dir_path = os.path.join(base_path, directory)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"创建目录: {dir_path}")
        
        for file in PROJECT_STRUCTURE[directory]:
            file_path = os.path.join(dir_path, file)
            if not os.path.exists(file_path):
                with open(file_path, 'w') as f:
                    f.write("")
                print(f"创建文件: {file_path}")

def copy_template_files(base_path, template_path):
    """从模板目录复制基础文件"""
    # 如果有模板目录，复制模板文件
    if os.path.exists(template_path):
        # 复制基础文件
        template_files = {
            "README.md": "README.md",
            "requirements.txt": "requirements.txt",
            "config.py": "config.py",
            "utils/llm.py": "utils/llm.py",
            "mcp/client.py": "mcp/client.py", 
            "mcp/local/search.py": "mcp/local/search.py",
            "flow/nodes.py": "flow/nodes.py",
            "flow/flows.py": "flow/flows.py",
            "a2a/task_manager.py": "a2a/task_manager.py",
            "a2a_server.py": "a2a_server.py",
            "a2a_client.py": "a2a_client.py"
        }
        
        for src, dest in template_files.items():
            src_path = os.path.join(template_path, src)
            dest_path = os.path.join(base_path, dest)
            if os.path.exists(src_path):
                shutil.copy2(src_path, dest_path)
                print(f"复制模板文件: {src} -> {dest}")

def main():
    parser = argparse.ArgumentParser(description='设置多代理协作故事生成器项目')
    parser.add_argument('--path', type=str, default='PocketFlow/cookbook/a2a_with_mcp',
                        help='项目路径，默认为PocketFlow/cookbook/a2a_with_mcp')
    parser.add_argument('--template', type=str, default='',
                        help='模板目录路径，包含基础代码模板')
    
    args = parser.parse_args()
    
    # 确保目标路径存在
    target_path = args.path
    if not os.path.exists(os.path.dirname(target_path)):
        print(f"错误: 父目录 {os.path.dirname(target_path)} 不存在")
        return 1
    
    # 创建目录结构
    create_directory_structure(target_path)
    
    # 如果提供了模板目录，复制模板文件
    if args.template:
        copy_template_files(target_path, args.template)
    
    print(f"\n项目框架已创建在 {target_path}")
    print("接下来步骤:")
    print("1. 安装依赖: pip install -r requirements.txt")
    print("2. 运行服务器: python a2a_server.py")
    print("3. 在另一个终端运行客户端: python a2a_client.py")
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 