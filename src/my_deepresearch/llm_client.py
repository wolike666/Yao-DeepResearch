from __future__ import annotations

from openai import OpenAI

# LLM 封装层
class LLMClient:
    # OpenAI 兼容接口的轻量封装，统一管理模型调用参数。
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

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        # 单轮对话调用：system + user，返回模型文本输出。
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            timeout=self.timeout,
        )
        return (resp.choices[0].message.content or "").strip()
