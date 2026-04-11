"""Novel Factory - 小说创作工厂主类"""

import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, AsyncGenerator, Optional
from loguru import logger

from langchain_openai import ChatOpenAI

from agentchat.settings import app_settings
from agentchat.services.storage import storage_client
from agentchat.services.novel_factory.graph import build_graph
from agentchat.services.novel_factory.state import NovelState
from agentchat.core.models.manager import ModelManager


class NovelFactory:
    """
    AI 多智能体小说创作工厂

    通过 LangGraph 编排多个智能体协作完成小说创作流程：
    1. Architect (总设计师) - 世界观和章节大纲
    2. Outliner (章节细化师) - 场景节拍
    3. Novelist (小说家) - 正文撰写
    4. Editor (编辑) - 审查修改
    5. Summarizer (摘要师) - 章节摘要
    """

    def __init__(
        self,
        llm_id: Optional[str] = None,
        user_id: str = "system"
    ):
        """
        初始化 Novel Factory

        Args:
            llm_id: LLM 模型 ID，如果为 None 则使用默认模型
            user_id: 用户 ID，用于文件存储路径
        """
        self.llm_id = llm_id
        self.user_id = user_id
        self.llm = None
        self.graph = None

    async def initialize(self):
        """初始化 LLM 和图"""
        if self.llm is None:
            self.llm = await self._get_llm()

        if self.graph is None:
            self.graph = build_graph(self.llm)

    async def _get_llm(self):
        """
        获取 LLM 实例

        优先使用配置的模型，否则使用默认对话模型
        """
        if self.llm_id:
            # 从数据库获取模型配置
            from agentchat.api.services.llm import LLMService
            model_config = await LLMService.get_llm_by_id(self.llm_id)
            return ModelManager.get_user_model(**model_config)
        else:
            # 使用默认对话模型
            return ModelManager.get_conversation_model()

    async def create_novel(
        self,
        inspiration: str,
        chapters: int = 5,
        style: str = "默认",
        max_revisions: int = 3
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        创建小说

        Args:
            inspiration: 创作灵感
            chapters: 章节数量 (1-50)
            style: 写作风格
            max_revisions: 每个场景最大修改次数 (1-10)

        Yields:
            事件字典，包含进度更新
        """
        # 验证参数
        if not inspiration or not inspiration.strip():
            yield {
                "type": "error",
                "message": "请提供创作灵感"
            }
            return

        if chapters < 1 or chapters > 50:
            yield {
                "type": "error",
                "message": "章节数必须在 1-50 之间"
            }
            return

        if max_revisions < 1 or max_revisions > 10:
            yield {
                "type": "error",
                "message": "修改次数必须在 1-10 之间"
            }
            return

        # 初始化
        await self.initialize()

        # 设置输出目录
        output_dir = Path("./output/novel_factory")
        output_dir.mkdir(parents=True, exist_ok=True)

        # 生成运行 ID
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 构建输入
        user_input = f"{inspiration}\n\n写作风格: {style}" if style != "默认" else inspiration

        # 初始状态
        initial_state: NovelState = {
            "user_input": user_input,
            "story_bible": {},
            "chapter_outlines": [{}] * chapters,
            "current_chapter": 0,
            "current_beats": [],
            "current_beat_index": 0,
            "draft_text": "",
            "editor_feedback": "",
            "editor_approved": False,
            "revision_count": 0,
            "max_revisions": max_revisions,
            "past_summaries": [],
            "completed_scenes": [],
            "completed_chapters": [],
        }

        # 进度标签映射
        progress_labels = {
            "architect": "📐 正在构建世界观和章节大纲...",
            "outliner": "📝 正在细化章节场景...",
            "novelist": "✍️  正在撰写场景草稿...",
            "editor": "🔍 正在审查草稿质量...",
            "advance_beat": "✅ 场景通过审核，进入下一场景",
            "summarizer": "📋 正在生成章节摘要...",
        }

        # 流式执行
        current_node = ""
        final_state = None

        try:
            for event in self.graph.stream(initial_state, {"recursion_limit": 150}):
                for node_name, node_output in event.items():
                    # 发送进度更新
                    if node_name != current_node:
                        current_node = node_name
                        logger.info(f"Novel Factory: {progress_labels.get(node_name, node_name)}")
                        yield {
                            "type": "progress",
                            "stage": node_name,
                            "message": progress_labels.get(node_name, f"正在执行 {node_name}...")
                        }

                    # 特定节点的详细信息
                    if node_name == "architect" and "story_bible" in node_output:
                        yield {
                            "type": "milestone",
                            "stage": "worldview",
                            "message": "世界观构建完成！",
                            "data": {
                                "story_bible": node_output["story_bible"]
                            }
                        }

                    elif node_name == "summarizer" and "completed_chapters" in node_output:
                        ch = node_output["completed_chapters"][-1]
                        yield {
                            "type": "milestone",
                            "stage": "chapter_complete",
                            "message": f"第 {ch.get('chapter_number', '?')} 章「{ch.get('title', '')}」完成！",
                            "data": {
                                "chapter_number": ch.get("chapter_number"),
                                "title": ch.get("title"),
                                "summary": ch.get("summary")
                            }
                        }

                    elif node_name == "editor" and "editor_approved" in node_output:
                        if not node_output["editor_approved"]:
                            yield {
                                "type": "revision",
                                "message": f"草稿需要修改 (第 {node_output.get('revision_count', '?')} 次)",
                                "feedback": node_output.get("editor_feedback", "")
                            }

                    final_state = {**initial_state, **(final_state or {}), **node_output}

            # 保存文件
            if final_state and final_state.get("completed_chapters"):
                yield {
                    "type": "saving",
                    "message": "正在保存生成的文件..."
                }

                result = await self._save_results(
                    final_state["completed_chapters"],
                    final_state.get("story_bible", {}),
                    output_dir,
                    run_id
                )

                yield {
                    "type": "complete",
                    "message": "🎉 小说创作完成！",
                    "data": result
                }
            else:
                yield {
                    "type": "error",
                    "message": "创作未能完成，请重试"
                }

        except Exception as e:
            logger.error(f"Novel Factory 执行错误: {e}")
            yield {
                "type": "error",
                "message": f"创作过程中出现错误: {str(e)}"
            }

    async def _save_results(
        self,
        completed_chapters: list,
        story_bible: dict,
        output_dir: Path,
        run_id: str
    ) -> dict:
        """
        保存小说结果

        Returns:
            包含文件信息的字典
        """
        full_parts = []
        chapter_summaries = []

        for ch in completed_chapters:
            num = ch["chapter_number"]
            title = ch["title"]
            text = ch["text"]
            summary = ch.get("summary", "")

            # 保存章节文件
            chapter_file = output_dir / f"chapter_{num:02d}_{run_id}.md"
            chapter_file.write_text(
                f"# {title}\n\n{text}\n",
                encoding="utf-8"
            )
            logger.info(f"已保存章节: {chapter_file}")

            full_parts.append(f"# {title}\n\n{text}")
            chapter_summaries.append(f"第 {num} 章: {title}")

        # 保存完整小说
        full_novel = output_dir / f"full_novel_{run_id}.md"
        full_novel.write_text(
            "\n\n---\n\n".join(full_parts) + "\n",
            encoding="utf-8"
        )

        # 保存设定集
        bible_file = output_dir / f"story_bible_{run_id}.json"
        bible_file.write_text(
            json.dumps(story_bible, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # 尝试上传到存储
        download_links = None
        try:
            storage_prefix = f"novel_factory/{run_id}"

            # 上传完整小说
            with open(full_novel, 'r', encoding='utf-8') as f:
                novel_content = f.read()
            storage_client.upload_file(
                f"{storage_prefix}/full_novel.md",
                novel_content.encode('utf-8')
            )

            # 上传设定集
            with open(bible_file, 'r', encoding='utf-8') as f:
                bible_content = f.read()
            storage_client.upload_file(
                f"{storage_prefix}/story_bible.json",
                bible_content.encode('utf-8')
            )

            novel_url = f"{app_settings.storage.active.base_url}/{storage_prefix}/full_novel.md"
            bible_url = f"{app_settings.storage.active.base_url}/{storage_prefix}/story_bible.json"

            download_links = {
                "novel": novel_url,
                "story_bible": bible_url
            }

        except Exception as e:
            logger.error(f"上传存储失败: {e}")

        return {
            "total_chapters": len(completed_chapters),
            "chapter_titles": chapter_summaries,
            "output_dir": str(output_dir),
            "local_files": {
                "novel": str(full_novel),
                "story_bible": str(bible_file)
            },
            "download_links": download_links
        }