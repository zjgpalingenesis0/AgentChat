"""
Novel Factory 工具
基于多智能体协作的 AI 小说创作工具
"""

from loguru import logger
from langchain.tools import tool


@tool(parse_docstring=True)
def create_novel(
    inspiration: str,
    chapters: int = 5,
    style: str = "默认",
    max_revisions: int = 3
):
    """
    使用 AI 多智能体协作系统创作小说。包含世界观设计、章节规划、正文撰写、审稿修改等完整流程。

    Args:
        inspiration (str): 创作灵感，描述你想写的故事。例如："一个关于时间旅行者在末日废墟中寻找失落文明的故事"
        chapters (int): 需要生成多少章小说，默认 5 章，范围 1-50 章
        style (str): 写作风格，例如：科幻、言情、悬疑、武侠、奇幻等，默认为"默认"
        max_revisions (int): 每个场景的最大修改次数，默认 3 次，范围 1-10 次

    Returns:
        str: 小说创作结果，包括创作过程描述、世界观设定、章节信息和下载链接
    """
    return _create_novel(inspiration, chapters, style, max_revisions)


def _create_novel(
    inspiration: str,
    chapters: int = 5,
    style: str = "默认",
    max_revisions: int = 3
) -> str:
    """
    执行小说创作的核心函数
    """
    import asyncio

    # 验证参数
    if not inspiration or not inspiration.strip():
        return "❌ 错误：请提供创作灵感，描述你想写的故事。"

    if chapters < 1 or chapters > 50:
        return "❌ 错误：章节数必须在 1-50 之间。"

    if max_revisions < 1 or max_revisions > 10:
        return "❌ 错误：修改次数必须在 1-10 之间。"

    logger.info(f"开始创作小说: {inspiration[:50]}..., 章节数: {chapters}, 风格: {style}")

    # 使用集成到项目中的 Novel Factory
    from agentchat.services.novel_factory import NovelFactory

    # 创建工厂实例
    factory = NovelFactory()

    # 异步执行并收集结果
    result_messages = []
    final_result = None

    async def run_creation():
        nonlocal final_result
        async for event in factory.create_novel(
            inspiration=inspiration,
            chapters=chapters,
            style=style,
            max_revisions=max_revisions
        ):
            if event["type"] == "progress":
                result_messages.append(event["message"])
                logger.info(f"Novel Factory: {event['message']}")
            elif event["type"] == "milestone":
                result_messages.append(f"✅ {event['message']}")
            elif event["type"] == "revision":
                result_messages.append(f"🔄 {event['message']}")
            elif event["type"] == "complete":
                final_result = event
            elif event["type"] == "error":
                result_messages.append(f"❌ {event['message']}")
                final_result = event

    # 运行异步任务
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_creation())
    finally:
        loop.close()

    # 构建返回结果
    if final_result and final_result.get("type") == "complete":
        data = final_result.get("data", {})
        total_chapters = data.get("total_chapters", 0)
        chapter_titles = data.get("chapter_titles", [])

        result = f"""
🎉 **小说创作完成！**

📖 **创作流程**:
{" → ".join(result_messages)}

📚 **生成章节** ({total_chapters} 章):
{chr(10).join(f"  - {title}" for title in chapter_titles)}
"""

        # 添加下载链接
        download_links = data.get("download_links")
        if download_links:
            result += f"""
📥 **下载链接:**
- 完整小说: [点击下载]({download_links['novel']})
- 设定集: [点击下载]({download_links['story_bible']})
"""
        else:
            local_files = data.get("local_files", {})
            result += f"""
📁 **本地文件路径:**
- {local_files.get('novel', '')}
- {local_files.get('story_bible', '')}
"""

        result += "\n✨ 创作已完成，你可以查看或下载生成的小说！"
        return result

    else:
        return "\n".join(result_messages) if result_messages else "❌ 创作未能完成，请重试。"