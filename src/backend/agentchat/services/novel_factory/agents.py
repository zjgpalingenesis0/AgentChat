"""Novel Factory 各个 Agent 的实现"""

import json
from typing import List, Dict
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.utils.json import parse_json_markdown

from agentchat.services.novel_factory.prompts import (
    ARCHITECT_SYSTEM,
    OUTLINER_SYSTEM,
    NOVELIST_SYSTEM,
    EDITOR_SYSTEM,
    SUMMARIZER_SYSTEM
)
from agentchat.services.novel_factory.state import NovelState


def architect_node(state: NovelState, llm) -> dict:
    """
    总设计师 Agent - 根据用户输入生成设定集和章节大纲
    """
    num_chapters = len(state.get("chapter_outlines", [])) or 5

    messages = [
        SystemMessage(content=ARCHITECT_SYSTEM),
        HumanMessage(content=(
            f"请根据以下创意灵感，创建一部长篇小说的完整设定集和章节大纲。\n\n"
            f"创意灵感：{state['user_input']}\n\n"
            f"要求章节数量：{num_chapters} 章\n\n"
            f"请严格按照 JSON 格式输出。"
        )),
    ]

    response = llm.invoke(messages)
    content = response.content

    data = parse_json_markdown(content)

    return {
        "story_bible": data["story_bible"],
        "chapter_outlines": data["chapter_outlines"],
        "current_chapter": 0,
    }


def outliner_node(state: NovelState, llm) -> dict:
    """
    章节细化师 Agent - 将章节大纲扩展为详细的场景节拍
    """
    chapter_idx = state["current_chapter"]
    chapter_outline = state["chapter_outlines"][chapter_idx]
    story_bible = state["story_bible"]
    past_summaries = state.get("past_summaries", [])

    summaries_text = ""
    if past_summaries:
        summaries_text = "\n\n前情摘要：\n" + "\n---\n".join(
            f"第{i+1}章：{s}" for i, s in enumerate(past_summaries)
        )

    messages = [
        SystemMessage(content=OUTLINER_SYSTEM),
        HumanMessage(content=(
            f"设定集：\n{json.dumps(story_bible, ensure_ascii=False, indent=2)}\n\n"
            f"当前章节大纲：\n{json.dumps(chapter_outline, ensure_ascii=False, indent=2)}"
            f"{summaries_text}\n\n"
            f"请为本章生成详细的场景节拍（Scene Beats），严格按 JSON 数组格式输出。"
        )),
    ]

    response = llm.invoke(messages)
    content = response.content

    beats = parse_json_markdown(content)

    return {
        "current_beats": beats,
        "current_beat_index": 0,
        "completed_scenes": [],
        "revision_count": 0,
    }


def _extract_character_cards(story_bible: dict, character_names: List[str]) -> List[dict]:
    """从设定集中提取相关的角色卡片"""
    all_chars = story_bible.get("characters", [])
    return [c for c in all_chars if c.get("name") in character_names]


def novelist_node(state: NovelState, llm) -> dict:
    """
    小说家 Agent - 为单个场景节拍撰写实际的叙事散文
    """
    beat = state["current_beats"][state["current_beat_index"]]
    story_bible = state["story_bible"]
    past_summaries = state.get("past_summaries", [])
    editor_feedback = state.get("editor_feedback", "")

    # 只提供最近 3 章的摘要以避免上下文过载
    recent_summaries = past_summaries[-3:] if past_summaries else []

    # 提取此场景中角色的角色卡片
    character_cards = _extract_character_cards(
        story_bible, beat.get("characters", [])
    )

    prompt_parts = [
        f"## 当前场景节拍\n{json.dumps(beat, ensure_ascii=False, indent=2)}",
        f"\n## 出场角色卡片\n{json.dumps(character_cards, ensure_ascii=False, indent=2)}",
    ]

    if recent_summaries:
        summaries_text = "\n---\n".join(
            f"第{len(past_summaries) - len(recent_summaries) + i + 1}章：{s}"
            for i, s in enumerate(recent_summaries)
        )
        prompt_parts.append(f"\n## 近期剧情摘要\n{summaries_text}")

    if editor_feedback:
        prompt_parts.append(
            f"\n## 编辑修改意见（请在本次修改中逐一解决）\n{editor_feedback}"
        )

    messages = [
        SystemMessage(content=NOVELIST_SYSTEM),
        HumanMessage(content="\n".join(prompt_parts)),
    ]

    response = llm.invoke(messages)

    return {
        "draft_text": response.content,
    }


def editor_node(state: NovelState, llm) -> dict:
    """
    编辑/评论家 Agent - 对照设定集审查草稿
    """
    beat = state["current_beats"][state["current_beat_index"]]
    story_bible = state["story_bible"]
    draft = state["draft_text"]

    messages = [
        SystemMessage(content=EDITOR_SYSTEM),
        HumanMessage(content=(
            f"## 待审稿件\n{draft}\n\n"
            f"## 场景节拍要求\n{json.dumps(beat, ensure_ascii=False, indent=2)}\n\n"
            f"## 设定集\n{json.dumps(story_bible, ensure_ascii=False, indent=2)}\n\n"
            f"请严格按 JSON 格式输出审稿意见。"
        )),
    ]

    response = llm.invoke(messages)
    content = response.content

    review = parse_json_markdown(content)

    approved = review.get("approved", True)

    # 为小说家构建人类可读的反馈
    feedback_lines = []
    if not approved:
        feedback_lines.append(f"整体评价：{review.get('summary', '')}")
        for issue in review.get("issues", []):
            feedback_lines.append(
                f"- [{issue.get('severity', '?')}] {issue.get('type', '?')}: "
                f"{issue.get('description', '')} → 建议：{issue.get('suggestion', '')}"
            )

    return {
        "editor_approved": approved,
        "editor_feedback": "\n".join(feedback_lines) if feedback_lines else "",
        "revision_count": state["revision_count"] + 1,
    }


def summarizer_node(state: NovelState, llm) -> dict:
    """
    摘要师 Agent - 将完成的章节压缩为情节摘要
    """
    chapter_idx = state["current_chapter"]
    chapter_outline = state["chapter_outlines"][chapter_idx]
    scenes = state["completed_scenes"]
    full_text = "\n\n".join(scenes)

    messages = [
        SystemMessage(content=SUMMARIZER_SYSTEM),
        HumanMessage(content=(
            f"## 章节标题\n{chapter_outline.get('title', f'第{chapter_idx+1}章')}\n\n"
            f"## 章节全文\n{full_text}\n\n"
            f"请为本章撰写精炼的剧情摘要。"
        )),
    ]

    response = llm.invoke(messages)
    summary = response.content.strip()

    past_summaries = list(state.get("past_summaries", []))
    past_summaries.append(summary)

    completed_chapters = list(state.get("completed_chapters", []))
    completed_chapters.append({
        "chapter_number": chapter_idx + 1,
        "title": chapter_outline.get("title", f"第{chapter_idx+1}章"),
        "text": full_text,
        "summary": summary,
    })

    return {
        "past_summaries": past_summaries,
        "completed_chapters": completed_chapters,
        "current_chapter": chapter_idx + 1,
    }