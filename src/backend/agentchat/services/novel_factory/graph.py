"""Novel Factory LangGraph 流程编排"""

from functools import partial
from typing import Callable, Dict
from langgraph.graph import END, StateGraph

from agentchat.services.novel_factory.state import NovelState
from agentchat.services.novel_factory.agents import (
    architect_node,
    outliner_node,
    novelist_node,
    editor_node,
    summarizer_node
)


def _advance_beat(state: NovelState) -> dict:
    """
    将批准的草稿移动到 completed_scenes 并推进节拍索引
    """
    completed = list(state.get("completed_scenes", []))
    completed.append(state["draft_text"])

    return {
        "completed_scenes": completed,
        "current_beat_index": state["current_beat_index"] + 1,
        "revision_count": 0,
        "editor_feedback": "",
    }


def _after_editor(state: NovelState) -> str:
    """
    编辑审查后的决策

    返回:
      - "revise"          → 发回小说家修改
      - "advance_beat"    → 草稿批准，移动到下一个节拍
    """
    if not state["editor_approved"] and state["revision_count"] < state["max_revisions"]:
        return "revise"
    # 批准或用尽修改预算 —— 接受草稿
    return "advance_beat"


def _after_advance(state: NovelState) -> str:
    """
    推进节拍索引后的决策

    返回:
      - "next_beat"       → 本章还有更多节拍
      - "summarize"       → 章节完成，生成摘要
    """
    if state["current_beat_index"] < len(state["current_beats"]):
        return "next_beat"
    return "summarize"


def _after_summary(state: NovelState) -> str:
    """
    章节摘要后的决策

    返回:
      - "next_chapter"    → 更多章节要写
      - "end"             → 小说完成
    """
    if state["current_chapter"] < len(state["chapter_outlines"]):
        return "next_chapter"
    return "end"


def build_graph(llm) -> Callable:
    """
    构建并编译 Novel Factory LangGraph

    Args:
        llm: LangChain 聊天模型实例 (例如 ChatOpenAI, ChatAnthropic)

    Returns:
        编译后的 LangGraph，准备好被调用
    """
    graph = StateGraph(NovelState)

    # --- 节点 (通过 partial 绑定共享的 LLM) ---
    graph.add_node("architect", partial(architect_node, llm=llm))
    graph.add_node("outliner", partial(outliner_node, llm=llm))
    graph.add_node("novelist", partial(novelist_node, llm=llm))
    graph.add_node("editor", partial(editor_node, llm=llm))
    graph.add_node("advance_beat", _advance_beat)
    graph.add_node("summarizer", partial(summarizer_node, llm=llm))

    # --- 边 ---
    graph.set_entry_point("architect")

    # architect → outliner (总是)
    graph.add_edge("architect", "outliner")

    # outliner → novelist (总是)
    graph.add_edge("outliner", "novelist")

    # novelist → editor (总是)
    graph.add_edge("novelist", "editor")

    # editor → 条件: 修改或推进
    graph.add_conditional_edges(
        "editor",
        _after_editor,
        {
            "revise": "novelist",
            "advance_beat": "advance_beat",
        },
    )

    # advance_beat → 条件: 下一个节拍或摘要
    graph.add_conditional_edges(
        "advance_beat",
        _after_advance,
        {
            "next_beat": "novelist",
            "summarize": "summarizer",
        },
    )

    # summarizer → 条件: 下一章或结束
    graph.add_conditional_edges(
        "summarizer",
        _after_summary,
        {
            "next_chapter": "outliner",
            "end": END,
        },
    )

    return graph.compile()