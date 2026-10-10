"""审阅评分智能体（Reviewer Agent）。

职责：横向对比多份候选大纲，按维度逐项打分、排序，选出最优的一份。
"""

from __future__ import annotations

import json

import config
from llm_client import chat_json


def _dimension_lines() -> str:
    lines = []
    for d in config.REVIEW_DIMENSIONS:
        lines.append(f"- {d['key']}（{d['name']}，权重 {int(d['weight'] * 100)}%）：{d['desc']}")
    return "\n".join(lines)


def _system_prompt() -> str:
    keys = ", ".join(f'"{d["key"]}"' for d in config.REVIEW_DIMENSIONS)
    return f"""你是一位严苛、客观的资深图书评审，负责在多份候选大纲中择优。

评审维度（请对每份大纲的每个维度给出 0–100 的整数分）：
{_dimension_lines()}

评审要求：
1. 必须**横向对比**所有候选，而非孤立评分；分数要能体现相对优劣。
2. 每份大纲给出：各维度得分、加权总分（0–100，保留 1 位小数）、优点、不足。
3. 选出总分最高的 1 份作为 winner，并给出清晰的选择理由。
4. 若最高分与次高分的差距小于 {config.SCORE_CLOSE_THRESHOLD} 分，必须在 reason 中明确说明「分数接近」。
5. 只输出一个合法的 JSON 对象，不要输出任何解释文字或 Markdown 代码块标记。

JSON 结构（严格遵循，键名使用给定 key）：
{{
  "candidates": [
    {{
      "index": 1,
      "dimensions": {{ {keys} }},
      "total_score": 88.5,
      "pros": "优点…",
      "cons": "不足…"
    }}
  ],
  "ranking": [2, 1, 3],
  "winner": 2,
  "reason": "选择理由…"
}}"""


def run_reviewer_agent(topic: dict, outlines: list[dict]) -> tuple[dict, dict]:
    """评审多份大纲，返回 (review_result, usage)。

    :param topic: 题目包。
    :param outlines: [{"index": 1, "persona": "学术严谨派", "content": "..."}]
    """
    blocks = []
    for item in outlines:
        blocks.append(
            f"===== 候选 {item['index']}（风格：{item.get('persona', '—')}）=====\n{item['content']}"
        )
    user_prompt = (
        "【题目包】\n"
        f"{json.dumps(topic, ensure_ascii=False, indent=2)}\n\n"
        "【候选大纲】\n"
        + "\n\n".join(blocks)
        + "\n\n请对以上候选大纲进行横向评审并选出最优的一份。"
    )
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": user_prompt},
    ]
    review, usage, _raw = chat_json(messages, thinking=config.THINKING_ENABLED, temperature=0.3)
    return _normalize(review, outlines), usage


def _normalize(review: dict, outlines: list[dict]) -> dict:
    """兜底：确保 winner 合法、字段齐全。"""
    valid_indices = [o["index"] for o in outlines]

    candidates = review.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        candidates = []

    def _total(c: dict) -> float:
        try:
            return float(c.get("total_score", 0))
        except (TypeError, ValueError):
            return 0.0

    winner = review.get("winner")
    if winner not in valid_indices:
        # 从候选里挑总分最高者
        scored = [c for c in candidates if c.get("index") in valid_indices]
        if scored:
            winner = max(scored, key=_total).get("index")
        elif valid_indices:
            winner = valid_indices[0]

    ranking = review.get("ranking")
    if not isinstance(ranking, list) or sorted(ranking) != sorted(valid_indices):
        scored = sorted(
            [c for c in candidates if c.get("index") in valid_indices],
            key=_total, reverse=True,
        )
        ranking = [c.get("index") for c in scored] or list(valid_indices)

    review["candidates"] = candidates
    review["ranking"] = ranking
    review["winner"] = winner
    review.setdefault("reason", "")
    return review
