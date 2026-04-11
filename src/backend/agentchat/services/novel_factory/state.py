"""NovelState — 小说创作流程的全局状态定义"""

from typing import TypedDict, List


class NovelState(TypedDict):
    """小说创作流程的状态字典"""

    # 用户的初始创意灵感
    user_input: str

    # 全局设定集 (Story Bible): 角色、世界规则、核心冲突等
    story_bible: dict

    # 由 Architect 生成的高层级章节大纲
    chapter_outlines: List[dict]

    # 当前正在撰写的章节索引 (0-based)
    current_chapter: int

    # 当前章节的详细场景节拍 (Scene Beats)
    current_beats: List[dict]

    # 当前正在撰写的场景节拍索引 (0-based)
    current_beat_index: int

    # Novelist 为当前节拍生成的原始草稿文本
    draft_text: str

    # Editor 对当前草稿的反馈意见
    editor_feedback: str

    # Editor 是否批准了当前草稿
    editor_approved: bool

    # 当前节拍已经经历的修改轮数
    revision_count: int

    # 每个节拍的最大修改次数限制（防止无限循环）
    max_revisions: int

    # 已完成章节的剧情摘要列表
    past_summaries: List[str]

    # 当前章节内已完成的场景文本
    completed_scenes: List[str]

    # 已完全完成的章节存档 [{title, text, summary}, ...]
    completed_chapters: List[dict]