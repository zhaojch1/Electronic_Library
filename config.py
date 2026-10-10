"""全局配置：模型、路径、并发、评审维度等。

API Key 读取顺序（禁止硬编码进源码）：
1. 环境变量 DEEPSEEK_API_KEY
2. 项目根目录下的 .env 文件中的 DEEPSEEK_API_KEY
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"


def _load_dotenv(path: Path) -> None:
    """极简 .env 解析：仅支持 KEY=VALUE 行，已存在的环境变量优先。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------ #
# DeepSeek API
# ------------------------------------------------------------------ #
API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
API_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")

REQUEST_TIMEOUT = int(os.getenv("DEEPSEEK_TIMEOUT", "180"))       # 单次请求超时（秒）
MAX_RETRIES = int(os.getenv("DEEPSEEK_MAX_RETRIES", "3"))         # 失败重试次数
RETRY_BACKOFF = float(os.getenv("DEEPSEEK_RETRY_BACKOFF", "2.0"))  # 指数退避基数（秒）

# 是否开启 thinking（推理）模式，可按需在 .env 中调整以控制成本
THINKING_ENABLED = _env_bool("THINKING_ENABLED", False)
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "high")          # low / medium / high

# ------------------------------------------------------------------ #
# 流程与并发
# ------------------------------------------------------------------ #
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "3"))          # 写作智能体并发上限
WRITER_COUNT = int(os.getenv("WRITER_COUNT", "3"))                # 写作智能体数量
OUTLINE_MIN_CHARS = int(os.getenv("OUTLINE_MIN_CHARS", "1800"))   # 大纲目标字数下限
OUTLINE_MAX_CHARS = int(os.getenv("OUTLINE_MAX_CHARS", "2400"))   # 大纲目标字数上限
SCORE_CLOSE_THRESHOLD = float(os.getenv("SCORE_CLOSE_THRESHOLD", "3"))  # 分数接近阈值

# ------------------------------------------------------------------ #
# 成本统计（每百万 token 单价，单位：元；默认 0 表示仅记录 token 不估算费用）
# ------------------------------------------------------------------ #
PRICE_INPUT_PER_M = float(os.getenv("PRICE_INPUT_PER_M", "0"))
PRICE_OUTPUT_PER_M = float(os.getenv("PRICE_OUTPUT_PER_M", "0"))

# ------------------------------------------------------------------ #
# 写作智能体「风格人设」——用于保证候选方案多样性
# ------------------------------------------------------------------ #
WRITER_PERSONAS = [
    {
        "name": "学术严谨派",
        "style": (
            "以严谨、系统的学术写作风格组织大纲：概念定义清晰，逻辑层层递进，"
            "引用理论框架与结构化论证，强调知识体系与可验证性。"
        ),
    },
    {
        "name": "畅销商用派",
        "style": (
            "以畅销书、商业爆款的写作风格组织大纲：开篇强钩子、冲突密集、节奏明快，"
            "强调卖点、爽点与读者情绪价值，注重实用性与传播性。"
        ),
    },
    {
        "name": "文学叙事派",
        "style": (
            "以纯文学叙事风格组织大纲：注重人物弧光、意象与氛围营造，语言细腻有质感，"
            "强调主题深度与情感张力，追求回味悠长的阅读体验。"
        ),
    },
]


def personas_for_count(count: int) -> list[dict]:
    """按需要的数量返回写作风格人设列表（超出预设时循环复用）。"""
    if count <= 0:
        return []
    return [WRITER_PERSONAS[i % len(WRITER_PERSONAS)] for i in range(count)]


# ------------------------------------------------------------------ #
# 评审维度与权重
# ------------------------------------------------------------------ #
REVIEW_DIMENSIONS = [
    {"key": "novelty", "name": "创意与新颖度", "weight": 0.25, "desc": "立意、设定是否独特"},
    {"key": "structure", "name": "结构完整性", "weight": 0.20, "desc": "章节逻辑、起承转合是否完整"},
    {"key": "relevance", "name": "主题契合度", "weight": 0.20, "desc": "是否符合题目包要求"},
    {"key": "extensibility", "name": "可延展性", "weight": 0.15, "desc": "能否支撑目标字数与成书"},
    {"key": "appeal", "name": "读者吸引力", "weight": 0.10, "desc": "卖点、爽点、吸引力"},
    {"key": "language", "name": "语言质量", "weight": 0.10, "desc": "表达、文笔、可读性"},
]
