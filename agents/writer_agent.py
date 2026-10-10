"""写作智能体（Writer Agent）。

职责：根据题目包，以指定风格人设独立撰写一份约 2000 字的书籍大纲。
"""

from __future__ import annotations

import json

import config
from llm_client import chat

SYSTEM_TEMPLATE = """你是一位专业图书作者，正在为一部即将成书的新书撰写**大纲**。
本次你的写作风格人设是【{persona_name}】：
{persona_style}

请严格依据给定的选题包，独立完成一份约 {min_chars}–{max_chars} 字的书籍大纲。
要求：
1. 风格人设要鲜明地体现在大纲的立意、结构与语言上，与其他作者拉开差异。
2. 大纲需包含以下部分（用 Markdown 标题组织）：
   - 书名与一句话卖点（Logline）
   - 核心设定 / 背景世界观
   - 主要人物 或 核心概念
   - 分章节结构（每章标题 + 内容概述，章节数与选题包基本一致）
   - 主线与高潮 / 结局走向
   - 差异化亮点
3. 只输出大纲正文本身，不要输出任何与大纲无关的说明文字。
4. 直接输出 Markdown 文本，不要包在代码块里。"""


def run_writer_agent(topic: dict, persona: dict, index: int) -> tuple[str, dict]:
    """生成一份大纲。

    :param topic: 题目包 dict。
    :param persona: 风格人设 dict（含 name / style）。
    :param index: 候选编号（从 1 开始）。
    :return: (outline_markdown, usage)
    """
    system_prompt = SYSTEM_TEMPLATE.format(
        persona_name=persona.get("name", "通用"),
        persona_style=persona.get("style", ""),
        min_chars=config.OUTLINE_MIN_CHARS,
        max_chars=config.OUTLINE_MAX_CHARS,
    )
    user_prompt = (
        "以下是要写的书籍选题包（JSON）：\n"
        f"{json.dumps(topic, ensure_ascii=False, indent=2)}\n\n"
        "请据此撰写约 2000 字的书籍大纲。"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    content, usage = chat(messages, thinking=config.THINKING_ENABLED, temperature=1.0)
    return content.strip(), usage
