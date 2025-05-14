"""
多代理协作故事生成器项目 - 流程层
实现PocketFlow流程和节点

flow 包提供了故事生成相关的流程实现

这个包包含了:
1. nodes - 流程节点
2. flows - 流程定义
"""

from flow.nodes import StoryPlanningNode, StoryWritingNode, StoryEditingNode, ErrorHandlingNode
from flow.flows import StoryFlowFactory 