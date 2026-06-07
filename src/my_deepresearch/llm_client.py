from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openai import OpenAI


class LLMClient:
    """Light wrapper around an OpenAI-compatible chat completions client."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        temperature: float = 0.2,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is empty. Please set it in .env.")

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self._token_estimator = _build_token_estimator(model)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        usage_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            timeout=self.timeout,
        )
        content = (resp.choices[0].message.content or "").strip()
        usage = _extract_usage(
            resp=resp,
            model=self.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_text=content,
            estimator=self._token_estimator,
            usage_context=usage_context or {},
        )
        return {
            "content": content,
            "usage": usage,
        }


def _build_token_estimator(model: str) -> Callable[[str], int]:
    try:
        import tiktoken  # type: ignore

        try:
            encoding = tiktoken.encoding_for_model(model)
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")

        def _estimate_with_tiktoken(text: str) -> int:
            if not text:
                return 0
            return len(encoding.encode(text))

        return _estimate_with_tiktoken
    except Exception:
        return _estimate_tokens_fallback


def _estimate_tokens_fallback(text: str) -> int:
    content = text or ""
    if not content:
        return 0

    cjk_chars = sum(1 for ch in content if "\u4e00" <= ch <= "\u9fff")
    other_chars = len(content) - cjk_chars
    estimated = cjk_chars + max(1, other_chars // 4)
    return max(1, estimated)


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_usage_from_response(resp: Any) -> tuple[int | None, int | None, int | None]:
    usage = getattr(resp, "usage", None)
    if usage is None and isinstance(resp, dict):
        usage = resp.get("usage")
    if usage is None:
        return None, None, None

    prompt_tokens = _safe_int(getattr(usage, "prompt_tokens", None))
    if prompt_tokens is None and isinstance(usage, dict):
        prompt_tokens = _safe_int(usage.get("prompt_tokens"))

    completion_tokens = _safe_int(getattr(usage, "completion_tokens", None))
    if completion_tokens is None and isinstance(usage, dict):
        completion_tokens = _safe_int(usage.get("completion_tokens"))

    total_tokens = _safe_int(getattr(usage, "total_tokens", None))
    if total_tokens is None and isinstance(usage, dict):
        total_tokens = _safe_int(usage.get("total_tokens"))

    return prompt_tokens, completion_tokens, total_tokens


def _extract_usage(
    resp: Any,
    model: str,
    system_prompt: str,
    user_prompt: str,
    output_text: str,
    estimator: Callable[[str], int],
    usage_context: dict[str, Any],
) -> dict[str, Any]:
    prompt_tokens, completion_tokens, total_tokens = _extract_usage_from_response(resp)
    source = "official"
    estimated = False

    if prompt_tokens is None or completion_tokens is None or total_tokens is None:
        prompt_input = system_prompt + "\n" + user_prompt
        prompt_tokens = estimator(prompt_input)
        completion_tokens = estimator(output_text)
        total_tokens = prompt_tokens + completion_tokens
        source = "estimated"
        estimated = True

    return {
        "model": model,
        "source": source,
        "estimated": estimated,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": int(total_tokens),
        "purpose": str(usage_context.get("purpose") or "").strip(),
        "step": usage_context.get("step"),
    }
