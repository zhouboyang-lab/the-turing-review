"""社区审稿人运行器 — 支持 Prompt 模式和 API 模式。"""

import asyncio
from openai import AsyncOpenAI
import anthropic

from app.reviewers.base import BaseReviewer
from app.config import (
    ANTHROPIC_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL, CLAUDE_MODEL, OPENAI_MODEL, DEEPSEEK_MODEL,
    GUEST_API_TIMEOUT,
)


class GuestReviewerRunner(BaseReviewer):
    """
    社区审稿人执行器。

    根据 mode 决定调用方式：
    - prompt: 使用我们的 API key + 用户自定义 personality
    - api: 调用用户提供的 OpenAI-compatible 端点
    """

    def __init__(
        self,
        guest_id: int,
        display_name: str,
        mode: str,
        personality: str = "",
        backend_model: str = "",
        api_base_url: str = "",
        api_key: str = "",
        api_model_name: str = "",
    ):
        self.guest_id = guest_id
        self.name = display_name
        self.model_provider = f"guest_{mode}"
        self.personality = personality
        self.mode = mode
        self.backend_model = backend_model
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.api_model_name = api_model_name

    async def _call_api(self, system_prompt: str, user_prompt: str) -> str:
        if self.mode == "prompt":
            return await self._call_prompt_mode(system_prompt, user_prompt)
        else:
            return await self._call_api_mode(system_prompt, user_prompt)

    async def _call_prompt_mode(self, system_prompt: str, user_prompt: str) -> str:
        """使用我们的 API key，注入用户的 personality。"""
        if self.backend_model == "claude":
            client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            response = await asyncio.wait_for(
                client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                ),
                timeout=GUEST_API_TIMEOUT,
            )
            return response.content[0].text

        elif self.backend_model == "openai":
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=OPENAI_MODEL,
                    max_tokens=4096,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                ),
                timeout=GUEST_API_TIMEOUT,
            )
            return response.choices[0].message.content

        elif self.backend_model == "deepseek":
            client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    max_tokens=4096,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                ),
                timeout=GUEST_API_TIMEOUT,
            )
            return response.choices[0].message.content

        else:
            raise ValueError(f"Unknown backend model: {self.backend_model}")

    async def _call_api_mode(self, system_prompt: str, user_prompt: str) -> str:
        """调用用户提供的 OpenAI-compatible 端点。"""
        client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.api_base_url,
        )
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=self.api_model_name,
                max_tokens=4096,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            ),
            timeout=GUEST_API_TIMEOUT,
        )
        return response.choices[0].message.content


def build_guest_runner(gr) -> GuestReviewerRunner:
    """从数据库 GuestReviewer 行构建运行时实例。"""
    from app.services.crypto_service import decrypt_api_key

    return GuestReviewerRunner(
        guest_id=gr.id,
        display_name=gr.display_name,
        mode=gr.mode,
        personality=gr.personality,
        backend_model=gr.backend_model,
        api_base_url=gr.api_base_url,
        api_key=decrypt_api_key(gr.api_key_encrypted) if gr.api_key_encrypted else "",
        api_model_name=gr.api_model_name,
    )
