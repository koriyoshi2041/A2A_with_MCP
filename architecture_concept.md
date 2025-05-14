# 多代理协作故事生成器 - 概念架构图

本文档使用Mermaid图表展示系统各组件之间的关系，帮助开发者理解整体架构。

## 系统层次结构

```mermaid
graph TD
    subgraph "用户交互"
        A[用户] <--> B[A2A客户端]
    end
    
    subgraph "A2A服务层"
        B <--> C[A2A服务器]
        C <--> D[任务管理器]
    end
    
    subgraph "PocketFlow核心层"
        D <--> E[任务流程]
        
        subgraph "故事生成流程"
            E --> F[工具发现节点]
            F --> G[决策节点]
            G -->|search| H[搜索节点]
            G -->|outline| I[大纲节点]
            G -->|write| J[写作节点]
            G -->|edit| K[润色节点]
            G -->|complete| L[完成节点]
            
            H --> G
            I --> G
            J --> G
            K --> G
        end
    end
    
    subgraph "MCP调用层"
        H <--> M[搜索MCP服务]
        I <--> N[大纲MCP服务]
        J <--> O[写作MCP服务]
        K <--> P[润色MCP服务]
    end
    
    style A fill:#f9f,stroke:#333
    style B fill:#bbf,stroke:#333
    style C fill:#bbf,stroke:#333
    style D fill:#bbf,stroke:#333
    style E fill:#bfb,stroke:#333
    style F fill:#bfb,stroke:#333
    style G fill:#bfb,stroke:#333
    style H fill:#bfb,stroke:#333
    style I fill:#bfb,stroke:#333
    style J fill:#bfb,stroke:#333
    style K fill:#bfb,stroke:#333
    style L fill:#bfb,stroke:#333
    style M fill:#fbb,stroke:#333
    style N fill:#fbb,stroke:#333
    style O fill:#fbb,stroke:#333
    style P fill:#fbb,stroke:#333
```

## 数据流图

```mermaid
sequenceDiagram
    participant User as 用户
    participant Client as A2A客户端
    participant Server as A2A服务器
    participant TaskMgr as 任务管理器
    participant Flow as PocketFlow流程
    participant MCP as MCP服务
    
    User->>Client: 故事请求
    Client->>Server: 发送任务请求
    Server->>TaskMgr: 创建任务
    TaskMgr->>Flow: 初始化流程
    
    Note over Flow: 开始故事生成流程
    
    Flow->>MCP: 获取可用工具
    MCP-->>Flow: 返回工具列表
    
    loop 故事创作循环
        Flow->>Flow: 决策下一步行动
        
        alt 搜索相关信息
            Flow->>MCP: 调用搜索服务
            MCP-->>Flow: 返回搜索结果
            Flow->>TaskMgr: 更新进度(25%)
        else 生成故事大纲
            Flow->>MCP: 调用大纲服务
            MCP-->>Flow: 返回结构化大纲
            Flow->>TaskMgr: 更新进度(50%)
        else 写作故事章节
            Flow->>MCP: 调用写作服务(并行)
            MCP-->>Flow: 返回故事章节
            Flow->>TaskMgr: 更新进度(75%)
        else 润色完整故事
            Flow->>MCP: 调用润色服务
            MCP-->>Flow: 返回完整故事
            Flow->>TaskMgr: 更新进度(95%)
        end
    end
    
    Flow->>TaskMgr: 完成任务(100%)
    TaskMgr->>Server: 更新任务状态
    Server-->>Client: 实时进度更新
    Client-->>User: 显示进度和结果
```

## 组件依赖关系

```mermaid
graph LR
    subgraph "前端"
        A[a2a_client.py]
    end
    
    subgraph "服务端"
        B[a2a_server.py] --> C[a2a/server.py]
        C --> D[a2a/task_manager.py]
    end
    
    subgraph "核心组件"
        D --> E[flow/flows.py]
        E --> F[flow/nodes.py]
        F --> G[flow/shared.py]
    end
    
    subgraph "MCP集成"
        F --> H[mcp/client.py]
        H --> I[mcp/config.py]
    end
    
    subgraph "通用工具"
        F --> J[utils/llm.py]
        D --> K[utils/progress.py]
        B --> L[utils/logging.py]
    end
    
    A --> C
    
    style A fill:#bbf,stroke:#333
    style B fill:#bbf,stroke:#333
    style C fill:#bbf,stroke:#333
    style D fill:#bbf,stroke:#333
    style E fill:#bfb,stroke:#333
    style F fill:#bfb,stroke:#333
    style G fill:#bfb,stroke:#333
    style H fill:#fbb,stroke:#333
    style I fill:#fbb,stroke:#333
    style J fill:#ddd,stroke:#333
    style K fill:#ddd,stroke:#333
    style L fill:#ddd,stroke:#333
```

## 节点决策流程

```mermaid
stateDiagram-v2
    [*] --> 初始状态
    初始状态 --> 工具发现: 获取可用工具
    
    工具发现 --> 决策: 完成工具收集
    
    决策 --> 搜索: 选择search
    搜索 --> 决策: 搜索完成
    
    决策 --> 大纲: 选择outline
    大纲 --> 决策: 大纲生成完成
    
    决策 --> 写作: 选择write
    写作 --> 决策: 章节写作完成
    
    决策 --> 润色: 选择edit
    润色 --> 决策: 润色完成
    
    决策 --> 完成: 选择complete
    完成 --> [*]: 任务结束
```

## 可扩展性设计

系统设计允许通过以下方式扩展功能：

1. 添加新的MCP服务类型
2. 自定义节点类型以支持新的流程步骤
3. 扩展A2A协议以支持更多客户端类型

这些扩展可以在不改变核心架构的情况下实现，保持系统的灵活性和可扩展性。 