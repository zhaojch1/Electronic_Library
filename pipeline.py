"""主流程编排（黑箱核心）。

用户视角：点一下按钮 → 得到 1 份优胜大纲。
系统视角：出题 → 并发写作 → 评审择优 → 落盘。
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import config
from agents import reviewer_agent, topic_agent, writer_agent


class PipelineError(Exception):
    """流程级错误。"""


def _now_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _cost(usage: dict) -> float:
    """按配置单价估算费用（元）；单价为 0 时返回 0。"""
    p = usage.get("prompt_tokens", 0) / 1_000_000 * config.PRICE_INPUT_PER_M
    c = usage.get("completion_tokens", 0) / 1_000_000 * config.PRICE_OUTPUT_PER_M
    return round(p + c, 6)


def _merge(*usages: dict) -> dict:
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for u in usages:
        for k in total:
            total[k] += int((u or {}).get(k, 0))
    return total


def run_pipeline(constraints: str | None = None, writer_count: int | None = None,
                 progress=None) -> dict:
    """执行完整流程。

    :param constraints: 可选约束条件（题材/受众/难度等）。
    :param writer_count: 写作智能体数量，默认取配置。
    :param progress: 可选回调 progress(stage: str, message: str)。
    :return: 结果 dict（含 book_id、winner_outline、review、输出目录等）。
    """

    def emit(stage: str, message: str) -> None:
        if progress:
            try:
                progress(stage, message)
            except Exception:  # noqa: BLE001 —— 回调异常不影响主流程
                pass

    count = writer_count or config.WRITER_COUNT
    personas = config.personas_for_count(count)
    book_id = _now_id()
    out_dir = config.OUTPUT_DIR / book_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 1. 出题 ----------
    emit("topic", "正在生成选题…")
    topic, topic_usage = topic_agent.run_topic_agent(constraints)
    _dump(out_dir / "topic.json", topic)
    emit("topic", f"选题完成：《{topic['title']}》")

    # ---------- 2. 并发写作 ----------
    emit("writing", f"正在并发创作 {count} 份候选大纲…")
    outlines: list[dict] = []
    writer_usages: list[dict] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=min(count, config.MAX_CONCURRENCY)) as executor:
        futures = {
            executor.submit(writer_agent.run_writer_agent, topic, personas[i], i + 1): i + 1
            for i in range(count)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            persona_name = personas[idx - 1]["name"]
            try:
                content, usage = fut.result()
                if not content.strip():
                    raise PipelineError("返回内容为空")
                outlines.append({"index": idx, "persona": persona_name, "content": content})
                writer_usages.append(usage)
                emit("writing", f"候选 {idx}（{persona_name}）创作完成")
            except Exception as e:  # noqa: BLE001 —— 单个失败不影响整体
                errors.append(f"候选 {idx}（{persona_name}）失败：{e}")
                emit("writing", f"候选 {idx}（{persona_name}）失败，已跳过")

    if not outlines:
        raise PipelineError("全部写作智能体均失败，无法继续评审。\n" + "\n".join(errors))

    outlines.sort(key=lambda o: o["index"])
    for o in outlines:
        (out_dir / f"outline_{o['index']}.md").write_text(
            f"# 候选 {o['index']} · 风格：{o['persona']}\n\n{o['content']}\n", encoding="utf-8"
        )
    emit("writing", f"写作完成，共 {len(outlines)} 份有效候选")

    # ---------- 3. 评审择优 ----------
    emit("review", "正在评审并择优…")
    review, review_usage = reviewer_agent.run_reviewer_agent(topic, outlines)
    _dump(out_dir / "review.json", review)

    winner_index = review.get("winner")
    winner = next((o for o in outlines if o["index"] == winner_index), outlines[0])

    # ---------- 4. 落盘 ----------
    final_path = out_dir / "outline_final.md"
    final_path.write_text(
        f"# {topic['title']}\n\n> 题材：{topic['genre']} ｜ 目标读者：{topic['target_audience']}\n"
        f"> 风格：{winner['persona']} ｜ 综合评分：{_winner_score(review, winner['index'])}\n\n"
        f"{winner['content']}\n",
        encoding="utf-8",
    )

    total_usage = _merge(topic_usage, *writer_usages, review_usage)
    usage_doc = {
        "book_id": book_id,
        "model": config.MODEL,
        "thinking": config.THINKING_ENABLED,
        "writer_count": count,
        "stages": {
            "topic": topic_usage,
            "writers": writer_usages,
            "review": review_usage,
        },
        "total": {**total_usage, "estimated_cost_cny": _cost(total_usage)},
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _dump(out_dir / "usage.json", usage_doc)

    emit("done", f"完成，优胜大纲已生成（风格：{winner['persona']}）")

    return {
        "book_id": book_id,
        "output_dir": str(out_dir),
        "topic": topic,
        "winner_index": winner["index"],
        "winner_persona": winner["persona"],
        "winner_outline": winner["content"],
        "winner_path": str(final_path),
        "review": review,
        "usage": usage_doc["total"],
        "errors": errors,
    }


def _winner_score(review: dict, index: int):
    for c in review.get("candidates", []):
        if c.get("index") == index:
            return c.get("total_score", "—")
    return "—"
