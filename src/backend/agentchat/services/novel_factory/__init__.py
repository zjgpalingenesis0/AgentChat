"""
Novel Factory - AI 多智能体小说创作服务

基于 LangGraph 的长篇小说创作流水线系统，通过多个 AI Agent 协作完成：
- 世界观设计 (Architect)
- 章节规划 (Outliner)
- 正文撰写 (Novelist)
- 审查修改 (Editor)
- 摘要生成 (Summarizer)
"""

from agentchat.services.novel_factory.factory import NovelFactory
from agentchat.services.novel_factory.state import NovelState

__all__ = ["NovelFactory", "NovelState"]
