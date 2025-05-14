# MCP工具服务接口规范

本文档详细说明了多代理协作故事生成器如何与MCP (Machine-Centric Protocol) 服务进行集成，包括接口格式、调用方式和响应处理。

## 1. MCP服务概述

MCP (Machine-Centric Protocol) 是一种为AI代理提供工具访问能力的标准化协议。在本项目中，我们直接调用外部MCP服务来获取故事生成过程中所需的专业能力，包括：

- **搜索服务**：提供信息检索能力
- **大纲服务**：生成结构化故事大纲
- **写作服务**：创作故事内容
- **润色服务**：优化和编辑完整故事

## 2. 接口格式

### 2.1 服务端点配置

每个MCP服务应提供以下两个标准端点：

1. **工具发现端点**：`GET /tools`
2. **工具执行端点**：`POST /run/{tool_name}`

### 2.2 工具发现接口

**请求**：

```
GET {service_url}/tools
```

**响应**：

```json
[
  {
    "name": "search_relevant_information",
    "description": "查询与故事主题相关的信息",
    "inputSchema": {
      "type": "object",
      "properties": {
        "topic": {"type": "string", "description": "搜索主题"},
        "depth": {"type": "integer", "description": "搜索深度"}
      },
      "required": ["topic"]
    }
  },
  {
    "name": "another_tool",
    "description": "另一个工具的描述",
    "inputSchema": {
      "type": "object",
      "properties": {
        "param1": {"type": "string"},
        "param2": {"type": "array"}
      },
      "required": ["param1"]
    }
  }
]
```

### 2.3 工具执行接口

**请求**：

```
POST {service_url}/run/{tool_name}
Content-Type: application/json

{
  "param1": "value1",
  "param2": "value2"
}
```

**响应**：

```json
{
  "result": "工具执行结果",
  "metadata": {
    "execution_time": 1.25,
    "status": "success"
  }
}
```

## 3. 具体服务要求

### 3.1 搜索服务 (`search_service`)

**工具名称**：`search_relevant_information`

**输入参数**：
```json
{
  "topic": "用户故事主题",
  "depth": 3,
  "type": "reference"
}
```

**期望输出**：
```json
{
  "results": [
    {
      "title": "资料标题1",
      "snippet": "相关摘要内容...",
      "relevance": 0.95
    },
    {
      "title": "资料标题2",
      "snippet": "相关摘要内容...",
      "relevance": 0.87
    }
  ],
  "metadata": {
    "total_results": 25,
    "filtered_results": 2
  }
}
```

### 3.2 大纲服务 (`outline_service`)

**工具名称**：`generate_structured_outline`

**输入参数**：
```json
{
  "topic": "用户故事主题",
  "research": [
    {"title": "资料1", "content": "..."},
    {"title": "资料2", "content": "..."}
  ],
  "structure": "四部分"
}
```

**期望输出**：
```json
{
  "title": "故事标题",
  "sections": {
    "introduction": {
      "title": "引言",
      "key_points": ["点1", "点2"],
      "characters": ["角色1", "角色2"]
    },
    "development": {
      "title": "发展",
      "key_points": ["点1", "点2"],
      "conflict": "主要冲突"
    },
    "climax": {
      "title": "高潮",
      "key_points": ["点1", "点2"],
      "resolution_setup": "解决方案铺垫"
    },
    "conclusion": {
      "title": "结局",
      "key_points": ["点1", "点2"],
      "theme": "主题寓意"
    }
  }
}
```

### 3.3 写作服务 (`writing_service`)

**工具名称**：`write_story_section`

**输入参数**：
```json
{
  "section_name": "introduction",
  "outline": {
    "title": "引言",
    "key_points": ["点1", "点2"],
    "characters": ["角色1", "角色2"]
  },
  "style": "descriptive"
}
```

**期望输出**：
```json
{
  "content": "Section content...",
  "word_count": 500,
  "reading_time": "3 min"
}
```

### 3.4 润色服务 (`editing_service`)

**工具名称**：`polish_story`

**输入参数**：
```json
{
  "draft": "完整故事草稿...",
  "focus_areas": ["character_development", "pacing", "language"],
  "target_audience": "young_adult"
}
```

**期望输出**：
```json
{
  "polished_content": "最终润色后的内容...",
  "improvements": [
    {"type": "character_depth", "count": 5},
    {"type": "language_enhancement", "count": 12},
    {"type": "pacing_adjustment", "count": 3}
  ],
  "word_count": 2500
}
```

## 4. 异步与流式响应支持

### 4.1 异步执行

对于耗时较长的操作，MCP服务可以支持异步执行模式：

**请求**：
```
POST {service_url}/run/{tool_name}?async=true
```

**响应**：
```json
{
  "task_id": "abc123",
  "status": "processing",
  "poll_url": "/tasks/abc123"
}
```

后续通过轮询获取结果：
```
GET {service_url}/tasks/{task_id}
```

### 4.2 流式响应

对于生成类工具，MCP服务可支持流式响应：

**请求**：
```
POST {service_url}/run/{tool_name}?stream=true
```

**响应**：
服务器将以Server-Sent Events (SSE) 格式返回流式数据，每个事件为：

```
event: progress
data: {"completed": 25, "message": "生成中..."}

event: content
data: {"chunk": "第一段内容..."}

event: content
data: {"chunk": "第二段内容..."}

event: done
data: {"status": "success"}
```

## 5. 错误处理

MCP服务应使用标准HTTP状态码表示请求状态：

- **200 OK**：请求成功
- **400 Bad Request**：请求参数错误
- **404 Not Found**：工具不存在
- **500 Internal Server Error**：服务内部错误
- **503 Service Unavailable**：服务暂时不可用

错误响应格式示例：

```json
{
  "error": {
    "code": "invalid_parameters",
    "message": "参数'topic'是必需的",
    "details": {
      "missing_parameters": ["topic"]
    }
  }
}
```

## 6. 示例代码

### 6.1 工具发现

```python
async def get_tools(service_url):
    """从MCP服务器获取可用工具列表"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{service_url}/tools", timeout=10.0)
            response.raise_for_status()
            tools_data = response.json()
            return [MCPTool(**tool) for tool in tools_data]
        except httpx.HTTPStatusError as e:
            logger.error(f"获取工具列表失败: HTTP {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"获取工具异常: {str(e)}")
            return []
```

### 6.2 工具调用

```python
async def call_tool(service_url, tool_name, arguments, stream=False):
    """调用MCP工具函数"""
    async with httpx.AsyncClient() as client:
        try:
            if not stream:
                # 常规调用
                response = await client.post(
                    f"{service_url}/run/{tool_name}",
                    json=arguments,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
            else:
                # 流式调用
                async with client.stream(
                    "POST",
                    f"{service_url}/run/{tool_name}?stream=true",
                    json=arguments,
                    timeout=30.0
                ) as response:
                    response.raise_for_status()
                    result = {"chunks": []}
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            data = json.loads(line[5:].strip())
                            if "chunk" in data:
                                result["chunks"].append(data["chunk"])
                    
                    result["content"] = "".join(result["chunks"])
                    return result
        except Exception as e:
            logger.error(f"调用工具 {tool_name} 失败: {str(e)}")
            raise
```

## 7. 健康检查和服务发现

为确保系统可靠性，建议实现MCP服务健康检查机制：

```python
async def check_mcp_service_health(service_url):
    """检查MCP服务健康状态"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{service_url}/health", timeout=5.0)
            return response.status_code == 200
        except:
            return False

async def discover_mcp_services():
    """动态发现可用的MCP服务"""
    services = {}
    for service_type, url in MCP_SERVICES.items():
        if await check_mcp_service_health(url):
            services[service_type] = url
    return services
```

## 8. 安全考虑

在生产环境中集成MCP服务时，应考虑以下安全措施：

1. 使用HTTPS进行所有通信
2. 实现API密钥或JWT认证
3. 为输入参数实现严格的验证和清理
4. 设置合理的超时和重试策略
5. 实现速率限制以防止滥用

## 总结

通过遵循本规范进行MCP服务集成，可以确保多代理协作故事生成系统能够可靠地访问所需的外部工具能力，同时保持架构的灵活性和可扩展性。 