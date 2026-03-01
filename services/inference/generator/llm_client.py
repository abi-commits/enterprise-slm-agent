"""LLM client for the consolidated Inference Service.

This module provides integration with vLLM for LLM inference, as well as
support for external LLM APIs (OpenAI, Anthropic) as fallbacks.
The same client is used for both query optimization and answer generation.

Supports both standard request/response and Server-Sent Events (SSE)
streaming for improved UX on long responses.
"""

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

# Model pricing per 1M tokens (in USD)
# These are example prices - adjust based on actual model pricing
MODEL_PRICING = {
    "Qwen/Qwen2.5-14B-Instruct": {
        "prompt": 0.5,  # $0.5 per 1M prompt tokens
        "completion": 1.0,  # $1.0 per 1M completion tokens
    },
    "Qwen/Qwen2.5-7B-Instruct": {
        "prompt": 0.2,
        "completion": 0.4,
    },
    "Qwen/Qwen2.5-1.5B-Instruct": {
        "prompt": 0.1,
        "completion": 0.2,
    },
    "abi-commits/qwen-query-optimizer": {
        "prompt": 0.1,  # Same as base model
        "completion": 0.2,
    },
    "gpt-4": {
        "prompt": 30.0,
        "completion": 60.0,
    },
    "gpt-4-turbo": {
        "prompt": 10.0,
        "completion": 30.0,
    },
    "gpt-3.5-turbo": {
        "prompt": 0.5,
        "completion": 1.5,
    },
    "claude-3-opus": {
        "prompt": 15.0,
        "completion": 75.0,
    },
    "claude-3-sonnet": {
        "prompt": 3.0,
        "completion": 15.0,
    },
    "claude-3-haiku": {
        "prompt": 0.25,
        "completion": 1.25,
    },
}

# Default pricing for unknown models
DEFAULT_PRICING = {"prompt": 1.0, "completion": 2.0}


@dataclass
class LLMResponse:
    """Response from LLM generation."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    cost_usd: float
    finish_reason: str = "stop"


@dataclass
class LLMStreamChunk:
    """A single chunk from streaming LLM generation."""

    token: str
    is_final: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str | None = None

    def to_sse_data(self) -> str:
        """Format chunk as SSE data payload."""
        return json.dumps({
            "token": self.token,
            "is_final": self.is_final,
            "finish_reason": self.finish_reason,
        })


class LLMClient:
    """LLM client for text generation.

    Supports vLLM (primary) and external LLM APIs (fallback).
    This single client is shared between the query optimizer and generator.
    """

    def __init__(self):
        """Initialize the LLM client."""
        self.settings = get_settings()
        self._vllm_client: httpx.AsyncClient | None = None

    async def _get_vllm_client(self) -> httpx.AsyncClient:
        """Get or create the reusable HTTP client for vLLM."""
        if self._vllm_client is None or self._vllm_client.is_closed:
            self._vllm_client = httpx.AsyncClient(
                timeout=60.0,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._vllm_client

    async def check_vllm_health(self) -> bool:
        """Check if vLLM server is healthy.

        Returns:
            True if vLLM is accessible, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.settings.vllm_url}/health")
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"vLLM health check failed: {e}")
            return False

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
        use_vllm: bool | None = None,
    ) -> LLMResponse:
        """Generate text using LLM.

        Args:
            prompt: Input prompt for generation
            model: Model name (defaults to settings.llm_model)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling parameter
            use_vllm: Whether to use vLLM (defaults to settings.use_vllm)

        Returns:
            LLMResponse with generated text and metadata

        Raises:
            httpx.HTTPError: If the request fails
        """
        time.time()

        model = model or self.settings.llm_model
        use_vllm = use_vllm if use_vllm is not None else self.settings.use_vllm

        logger.info(f"Generating with model: {model}, use_vllm: {use_vllm}")

        if use_vllm:
            try:
                return await self._generate_vllm(
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                )
            except Exception as e:
                logger.error(f"vLLM generation failed, falling back to external: {e}")
                return await self._generate_external(
                    prompt=prompt,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                )
        else:
            return await self._generate_external(
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )

    async def _generate_vllm(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> LLMResponse:
        """Internal method for vLLM generation."""
        client = await self._get_vllm_client()

        # OpenAI-compatible completions API for vLLM
        url = f"{self.settings.vllm_url}/v1/completions"
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
        }

        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        text = data["choices"][0]["text"].strip()
        usage = data["usage"]
        prompt_tokens = usage["prompt_tokens"]
        completion_tokens = usage["completion_tokens"]
        total_tokens = usage["total_tokens"]
        finish_reason = data["choices"][0].get("finish_reason", "stop")

        cost = self._calculate_cost(model, prompt_tokens, completion_tokens)

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            model=model,
            cost_usd=cost,
            finish_reason=finish_reason,
        )

    async def _generate_external(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> LLMResponse:
        """Internal method for external LLM fallback (e.g., mock or template)."""
        # In a real system, this would call OpenAI/Anthropic APIs
        # For now, we return a mock response or use a simple template logic
        logger.info(f"External LLM fallback triggered for model: {model}")

        # Mocking an external response for development
        text = f"[LLM generation not available in local dev without vLLM. Prompt length: {len(prompt)}]"
        prompt_tokens = len(prompt) // 4
        completion_tokens = len(text) // 4

        return LLMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            model=f"{model}-fallback",
            cost_usd=0.0,
            finish_reason="stop",
        )

    async def generate_stream(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Generate text using LLM with streaming response."""
        model = model or self.settings.llm_model
        client = await self._get_vllm_client()

        url = f"{self.settings.vllm_url}/v1/completions"
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }

        try:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break

                    data = json.loads(data_str)
                    choice = data["choices"][0]
                    token = choice.get("text", "")
                    finish_reason = choice.get("finish_reason")

                    yield LLMStreamChunk(
                        token=token,
                        is_final=finish_reason is not None,
                        finish_reason=finish_reason,
                    )
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield LLMStreamChunk(
                token=f"\n[Streaming Error: {str(e)}]",
                is_final=True,
                finish_reason="error",
            )

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate the USD cost of a request based on token usage."""
        pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
        return prompt_cost + completion_cost

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._vllm_client and not self._vllm_client.is_closed:
            await self._vllm_client.aclose()


# Singleton instance
_llm_client = None

def get_llm_client() -> LLMClient:
    """Get the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
