"""DeepSeek API 封装。

- 使用标准库 urllib，无需额外依赖。
- 提供超时、指数退避重试、异常捕获。
- 提供 JSON 解析与「解析失败自动重试」的便捷方法。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

import config


class LLMError(Exception):
    """LLM 调用相关错误。"""


def _build_payload(messages: list[dict], *, json_mode: bool, thinking: bool | None,
                   reasoning_effort: str | None, temperature: float,
                   max_tokens: int | None) -> dict:
    payload: dict = {
        "model": config.MODEL,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
    if json_mode:
        # DeepSeek 兼容 OpenAI 的 response_format
        payload["response_format"] = {"type": "json_object"}

    use_thinking = config.THINKING_ENABLED if thinking is None else thinking
    if use_thinking:
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = reasoning_effort or config.REASONING_EFFORT
    return payload


def _post(payload: dict) -> dict:
    if not config.API_KEY:
        raise LLMError(
            "未检测到 DeepSeek API Key。请设置环境变量 DEEPSEEK_API_KEY，"
            "或在项目根目录创建 .env 文件写入 DEEPSEEK_API_KEY=sk-xxx。"
        )
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        config.API_BASE_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.API_KEY}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=config.REQUEST_TIMEOUT) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def chat(messages: list[dict], *, json_mode: bool = False, thinking: bool | None = None,
         reasoning_effort: str | None = None, temperature: float = 0.8,
         max_tokens: int | None = None) -> tuple[str, dict]:
    """调用 DeepSeek，返回 (content, usage)。

    带指数退避重试，捕获网络、HTTP、解析异常。
    """
    payload = _build_payload(
        messages, json_mode=json_mode, thinking=thinking,
        reasoning_effort=reasoning_effort, temperature=temperature,
        max_tokens=max_tokens,
    )

    last_err: Exception | None = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = _post(payload)
            choices = resp.get("choices") or []
            if not choices:
                raise LLMError(f"响应缺少 choices 字段：{resp}")
            content = (choices[0].get("message") or {}).get("content") or ""
            usage = resp.get("usage") or {}
            return content, usage
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                pass
            last_err = LLMError(f"HTTP {e.code}: {detail or e.reason}")
            # 4xx（除 429）通常无需重试
            if 400 <= e.code < 500 and e.code != 429:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, LLMError) as e:
            last_err = e

        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF ** attempt)

    raise LLMError(f"LLM 调用失败（已重试 {config.MAX_RETRIES} 次）：{last_err}")


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict:
    """从模型输出中稳健地抽取 JSON 对象。

    依次尝试：直接解析 → 提取 ```json 代码块 → 截取首个 { 到最后一个 }。
    """
    if not text or not text.strip():
        raise LLMError("模型返回内容为空，无法解析 JSON。")

    candidates: list[str] = [text.strip()]
    block = _JSON_BLOCK_RE.search(text)
    if block:
        candidates.append(block.group(1).strip())
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise LLMError(f"无法解析 JSON，原始内容前 200 字：{text[:200]}")


def chat_json(messages: list[dict], *, retries: int | None = None, thinking: bool | None = None,
              reasoning_effort: str | None = None, temperature: float = 0.7,
              max_tokens: int | None = None) -> tuple[dict, dict, str]:
    """调用 LLM 并解析为 JSON，解析失败时追加纠正提示重试。

    返回 (json_obj, usage, raw_content)。
    """
    max_attempts = retries if retries is not None else config.MAX_RETRIES
    convo = list(messages)
    last_err: Exception | None = None
    usage_total: dict = {}

    for attempt in range(1, max_attempts + 1):
        content, usage = chat(
            convo, json_mode=True, thinking=thinking,
            reasoning_effort=reasoning_effort, temperature=temperature,
            max_tokens=max_tokens,
        )
        _merge_usage(usage_total, usage)
        try:
            return extract_json(content), usage_total, content
        except LLMError as e:
            last_err = e
            convo = convo + [
                {"role": "assistant", "content": content[:2000]},
                {"role": "user", "content": "上一条回复不是合法的 JSON。请只输出一个合法的 JSON 对象，"
                                            "不要输出任何解释或 Markdown 代码块标记。"},
            ]

    raise LLMError(f"JSON 解析失败（已重试 {max_attempts} 次）：{last_err}")


def _merge_usage(total: dict, usage: dict) -> None:
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if usage.get(key):
            total[key] = total.get(key, 0) + int(usage[key])
