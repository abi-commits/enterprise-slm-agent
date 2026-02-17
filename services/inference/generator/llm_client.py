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
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

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
    finish_reason: Optional[str] = None
    
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
        self._vllm_client: Optional[httpx.AsyncClient] = None

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
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
        use_vllm: Optional[bool] = None,
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
        start_time = time.time()

        model = model or self.settings.llm_model
        use_vllm = use_vllm if use_vllm is not None else self.settings.use_vllm

        logger.info(f"Generating with model: {model}, use_vllm: {use_vllm}")

        if use_vllm:
            response = await self._generate_vllm(
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
        else:
            response = await self._generate_external(
                prompt=prompt,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"LLM generation completed in {elapsed_ms:.2f}ms, "
            f"tokens: {response.total_tokens}, cost: ${response.cost_usd:.6f}"
        )

        return response

    async def _generate_vllm(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> LLMResponse:
        """Generate using vLLM server.

        Args:
            prompt: Input prompt
            model: Model name
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling

        Returns:
            LLMResponse from vLLM
        """
        vllm_url = self.settings.vllm_url

        # Prepare request payload for vLLM
        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": False,
        }

        try:
            client = await self._get_vllm_client()
            response = await client.post(
                f"{vllm_url}/v1/completions",
                json=payload,
            )
            response.raise_for_status()

                data = response.json()

                # Extract token usage from vLLM response
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get(
                    "total_tokens", prompt_tokens + completion_tokens
                )

                # Extract generated text
                choices = data.get("choices", [])
                if choices:
                    text = choices[0].get("text", "")
                    finish_reason = choices[0].get("finish_reason", "stop")
                else:
                    text = ""
                    finish_reason = "stop"

                # Calculate cost
                cost = self._calculate_cost(
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

                return LLMResponse(
                    text=text,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    model=model,
                    cost_usd=cost,
                    finish_reason=finish_reason,
                )

        except httpx.HTTPError as e:
            logger.error(f"vLLM request failed: {e}")
            raise

    async def _generate_external(
        self,
        prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> LLMResponse:
        """Generate using external LLM API (OpenAI/Anthropic).

        This is a fallback when vLLM is not available.

        Args:
            prompt: Input prompt
            model: Model name
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling

        Returns:
            LLMResponse from external API
        """
        # For now, we'll use a placeholder that throws an error
        # In production, this would implement OpenAI/Anthropic API calls
        logger.warning(
            "External LLM API not configured - falling back to template generation"
        )

        # Return a minimal response indicating no LLM was used
        return LLMResponse(
            text="[LLM generation not available - please configure vLLM or external API]",
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            model=model,
            cost_usd=0.0,
            finish_reason="stop",
        )

    async def generate_stream(
        self,
        prompt: str,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Generate text using LLM with streaming response.

        Yields tokens as they are generated for real-time display.

        Args:
            prompt: Input prompt for generation
            model: Model name (defaults to settings.llm_model)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling parameter

        Yields:
            LLMStreamChunk for each generated token
        """
        model = model or self.settings.llm_model
        vllm_url = self.settings.vllm_url

        logger.info(f"Starting streaming generation with model: {model}")

        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }

        full_text = ""
        prompt_tokens = 0
        completion_tokens = 0

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{vllm_url}/v1/completions",
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        
                        # SSE format: "data: {...}"
                        if line.startswith("data: "):
                            data_str = line[6:]  # Remove "data: " prefix
                            
                            if data_str.strip() == "[DONE]":
                                # Final chunk
                                yield LLMStreamChunk(
                                    token="",
                                    is_final=True,
                                    prompt_tokens=prompt_tokens,
                                    completion_tokens=completion_tokens,
                                    total_tokens=prompt_tokens + completion_tokens,
                                    finish_reason="stop",
                                )
                                break
                            
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                
                                if choices:
                                    choice = choices[0]
                                    token = choice.get("text", "")
                                    finish_reason = choice.get("finish_reason")
                                    
                                    if token:
                                        full_text += token
                                        completion_tokens += 1
                                        
                                        yield LLMStreamChunk(
                                            token=token,
                                            is_final=finish_reason is not None,
                                            completion_tokens=completion_tokens,
                                            finish_reason=finish_reason,
                                        )
                                    
                                    if finish_reason:
                                        # Get final usage stats if available
                                        usage = data.get("usage", {})
                                        prompt_tokens = usage.get("prompt_tokens", 0)
                                        
                                        yield LLMStreamChunk(
                                            token="",
                                            is_final=True,
                                            prompt_tokens=prompt_tokens,
                                            completion_tokens=completion_tokens,
                                            total_tokens=prompt_tokens + completion_tokens,
                                            finish_reason=finish_reason,
                                        )
                                        break
                                        
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse streaming chunk: {data_str}")
                                continue

        except httpx.HTTPError as e:
            logger.error(f"Streaming generation failed: {e}")
            yield LLMStreamChunk(
                token=f"[Error: {str(e)}]",
                is_final=True,
                finish_reason="error",
            )

    def _calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Calculate the cost of LLM generation.

        Args:
            model: Model name
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Cost in USD
        """
        pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)

        prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]

        return prompt_cost + completion_cost

    async def close(self):
        """Close any open connections."""
        if self._vllm_client:
            await self._vllm_client.aclose()
            self._vllm_client = None


# Global client instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get the global LLM client instance.

    Returns:
        LLMClient instance
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
