"""出题智能体（Topic Agent）。

职责：完全自由发挥，生成一个新颖、具体、可写成一本书的选题包（JSON）。
"""

from __future__ import annotations

import json

import config
from llm_client import chat_json

SYSTEM_PROMPT = """你是一位资深的图书策划编辑与选题专家，服务于一座全部由 AI 创作的电子图书馆。
你的任务是为这座图书馆策划一个全新的书籍选题。

要求：
1. 选题必须新颖、具体、有辨识度，避免市面上常见的套路与同质化内容。
2. 选题要能支撑一整本书的篇幅（数万至十余万字），具备清晰的主线与可延展性。
3. 只输出一个合法的 JSON 对象，不要输出任何解释文字或 Markdown 代码块标记。

JSON 字段（全部必填）：
{
  "title": "书名（有吸引力、精炼）",
  "genre": "体裁/类别，如：科幻、悬疑、历史、科普、商业、心理等",
  "target_audience": "目标读者群体描述",
  "theme": "核心主题/立意（一到两句）",
  "word_target": "预期成书字数（数字，例如 120000）",
  "chapter_count": "预期章节数（数字，例如 24）",
  "requirements": "创作要求与风格约束（语言风格、禁忌、叙事视角、重点等）",
  "reference_points": ["差异化角度或参考要点1", "要点2", "要点3"]
}"""


def run_topic_agent(constraints: str | None = None) -> tuple[dict, dict]:
    """生成题目包。

    :param constraints: 可选的约束条件（题材、受众、难度、领域等）。
    :return: (topic_dict, usage)
    """
    user_prompt = "请为我策划一个全新的书籍选题。请自由发挥，追求新颖与可写性。"
    if constraints:
        user_prompt += f"\n\n附加约束条件（需满足）：{constraints}"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    topic, usage, _raw = chat_json(messages, thinking=config.THINKING_ENABLED, temperature=1.0)
    return _normalize(topic), usage


def _normalize(topic: dict) -> dict:
    """补齐缺失字段，保证下游可安全读取。"""
    defaults = {
        "title": "未命名书籍",
        "genre": "综合",
        "target_audience": "一般读者",
        "theme": "",
        "word_target": 100000,
        "chapter_count": 20,
        "requirements": "",
        "reference_points": [],
    }
    result = {**defaults, **(topic or {})}
    if not isinstance(result.get("reference_points"), list):
        result["reference_points"] = [str(result["reference_points"])]
    return result


def as_pretty_json(topic: dict) -> str:
    return json.dumps(topic, ensure_ascii=False, indent=2)
