"""命令行入口（供开发 / 后续批量化使用，非用户主路径）。

用法示例：
    python main.py
    python main.py --genre 科幻悬疑 --audience 青少年 --writers 3
    python main.py --thinking
"""

from __future__ import annotations

import argparse
import sys

import config
import pipeline


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass


def build_constraints(args: argparse.Namespace) -> str | None:
    parts = []
    if args.genre:
        parts.append(f"体裁/题材：{args.genre}")
    if args.audience:
        parts.append(f"目标读者：{args.audience}")
    if args.extra:
        parts.append(args.extra)
    return "；".join(parts) if parts else None


def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description="电子图书馆 · AI 书籍大纲择优")
    parser.add_argument("--genre", help="体裁/题材约束，如：科幻、悬疑、科普")
    parser.add_argument("--audience", help="目标读者，如：青少年、职场人")
    parser.add_argument("--extra", help="其他自定义约束")
    parser.add_argument("--writers", type=int, default=None, help="写作智能体数量（默认取配置）")
    parser.add_argument("--thinking", action="store_true", help="本次运行开启 thinking 推理")
    parser.add_argument("--no-thinking", action="store_true", help="本次运行关闭 thinking 推理")
    args = parser.parse_args()

    if args.thinking:
        config.THINKING_ENABLED = True
    if args.no_thinking:
        config.THINKING_ENABLED = False

    def progress(_stage: str, message: str) -> None:
        print(f"[流程] {message}")

    try:
        result = pipeline.run_pipeline(
            constraints=build_constraints(args),
            writer_count=args.writers,
            progress=progress,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[错误] {e}", file=sys.stderr)
        return 1

    topic = result["topic"]
    print("\n" + "=" * 64)
    print(f"书名：{topic['title']}")
    print(f"题材：{topic['genre']} ｜ 目标读者：{topic['target_audience']}")
    print(f"优胜候选：#{result['winner_index']}（{result['winner_persona']}）")
    print(f"产出目录：{result['output_dir']}")
    print(f"Token 消耗：{result['usage'].get('total_tokens', 0)}")
    print("=" * 64 + "\n")
    print(result["winner_outline"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
