"""Qwen model integration for the Inference Service (Query Optimizer)."""

import json
import logging
from typing import Optional

import httpx
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize

from core.config.settings import get_settings

from services.inference.optimizer.prompts import build_optimization_prompt

logger = logging.getLogger(__name__)
settings = get_settings()


class QueryOptimizerModel:
    """Query optimizer using Qwen-2.5 SLM via vLLM or transformers fallback."""

    def __init__(self):
        self.model_name = settings.llm_model
        self.vllm_url = settings.vllm_url
        self.use_vllm = settings.use_vllm
        self._model_loaded = False
        self._vllm_available = False
        self._transformers_model = None
        self._transformers_tokenizer = None

        # Download NLTK data for keyword extraction
        self._setup_nltk()

    def _setup_nltk(self) -> None:
        """Download required NLTK data."""
        try:
            nltk.data.find('tokenizers/punkt')
        except LookupError:
            nltk.download('punkt', quiet=True)

        try:
            nltk.data.find('corpora/stopwords')
        except LookupError:
            nltk.download('stopwords', quiet=True)

    async def initialize(self) -> None:
        """Initialize the model (lazy loading)."""
        if self._model_loaded:
            return

        # Try vLLM first
        if self.use_vllm:
            self._vllm_available = await self._check_vllm_available()
            if self._vllm_available:
                logger.info(f"Using vLLM at {self.vllm_url} for inference")
                self._model_loaded = True
                return

        # Fallback to transformers
        logger.info("vLLM not available, falling back to transformers")
        await self._load_transformers_model()
        self._model_loaded = True

    async def _check_vllm_available(self) -> bool:
        """Check if vLLM is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.vllm_url}/v1/models")
                if response.status_code == 200:
                    logger.info("vLLM is available")
                    return True
        except Exception as e:
            logger.warning(f"vLLM not available: {e}")
        return False

    async def _load_transformers_model(self) -> None:
        """Load model using transformers library."""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info(f"Loading {self.model_name} with transformers...")
            self._transformers_tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True
            )
            self._transformers_model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                device_map="auto"
            )
            logger.info("Transformers model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load transformers model: {e}")
            raise

    def is_ready(self) -> bool:
        """Check if model is ready."""
        return self._model_loaded

    def is_vllm_available(self) -> bool:
        """Check if vLLM is available."""
        return self._vllm_available

    async def optimize_query(
        self,
        query: str,
        user_context: Optional[str] = None
    ) -> dict:
        """Optimize a query using the Qwen model.

        Returns:
            dict with optimized_queries, confidence, keywords, reasoning
        """
        if not self._model_loaded:
            await self.initialize()

        prompt = build_optimization_prompt(query, user_context or "")

        try:
            if self._vllm_available:
                result = await self._call_vllm(prompt)
            else:
                result = await self._call_transformers(prompt)

            # Parse the result
            parsed = self._parse_response(result)
            return parsed

        except Exception as e:
            logger.error(f"Error optimizing query: {e}")
            # Return fallback response
            return self._fallback_optimization(query)

    async def _call_vllm(self, prompt: str) -> str:
        """Call vLLM for inference."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.vllm_url}/v1/completions",
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "max_tokens": 512,
                    "temperature": 0.3,
                    "stop": ["```\n"]
                }
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["text"]

    async def _call_transformers(self, prompt: str) -> str:
        """Call transformers for inference."""
        if self._transformers_model is None or self._transformers_tokenizer is None:
            await self._load_transformers_model()

        inputs = self._transformers_tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(self._transformers_model.device) for k, v in inputs.items()}

        outputs = self._transformers_model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.3,
            do_sample=True,
            pad_token_id=self._transformers_tokenizer.pad_token_id
        )

        generated_text = self._transformers_tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True
        )
        return generated_text

    def _parse_response(self, response_text: str) -> dict:
        """Parse the model response into structured data."""
        # Try to extract JSON from response
        try:
            # Find JSON block
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                parsed = json.loads(json_str)

                # Validate and ensure defaults
                return {
                    "optimized_queries": parsed.get("optimized_queries", []),
                    "confidence": float(parsed.get("confidence", 0.5)),
                    "keywords": parsed.get("keywords", []),
                    "reasoning": parsed.get("reasoning", "")
                }
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse JSON response: {e}")

        # Fallback: try to extract keywords using NLTK
        return self._fallback_optimization(response_text)

    def _fallback_optimization(self, query: str) -> dict:
        """Fallback optimization using NLTK when model fails."""
        keywords = self.extract_keywords_nltk(query)

        # Generate simple optimized queries
        optimized_queries = [
            query,
            f"{query} policy guidelines",
            f"{query} information documentation"
        ]

        # Estimate confidence based on query characteristics
        confidence = self._estimate_confidence(query)

        return {
            "optimized_queries": optimized_queries,
            "confidence": confidence,
            "keywords": keywords,
            "reasoning": "Used NLTK-based fallback due to model unavailability"
        }

    def extract_keywords_nltk(self, text: str) -> list[str]:
        """Extract keywords using NLTK."""
        try:
            # Tokenize
            tokens = word_tokenize(text.lower())

            # Remove stopwords and non-alphabetic
            stop_words = set(stopwords.words('english'))
            keywords = [
                token for token in tokens
                if token.isalpha() and token not in stop_words and len(token) > 2
            ]

            # Remove duplicates while preserving order
            seen = set()
            unique_keywords = []
            for kw in keywords:
                if kw not in seen:
                    seen.add(kw)
                    unique_keywords.append(kw)

            return unique_keywords[:10]  # Return max 10 keywords

        except Exception as e:
            logger.warning(f"NLTK keyword extraction failed: {e}")
            # Simple fallback
            words = text.lower().split()
            return [w for w in words if len(w) > 2][:10]

    def _estimate_confidence(self, query: str) -> float:
        """Estimate confidence based on query characteristics."""
        query_lower = query.lower().strip()

        # Low confidence indicators
        low_confidence_patterns = [
            "help", "info", "stuff", "things", "something",
            "anything", "what is", "how do", "can i"
        ]

        # High confidence indicators (specific terms)
        high_confidence_indicators = [
            "policy", "procedure", "guideline", "form",
            "request", "process", "documentation", "manual"
        ]

        score = 0.5  # Base score

        # Adjust based on query length
        word_count = len(query.split())
        if 3 <= word_count <= 10:
            score += 0.1
        elif word_count > 10:
            score += 0.15
        elif word_count < 3:
            score -= 0.2

        # Check for low confidence patterns
        for pattern in low_confidence_patterns:
            if pattern in query_lower:
                score -= 0.15

        # Check for high confidence indicators
        for indicator in high_confidence_indicators:
            if indicator in query_lower:
                score += 0.1

        # Clamp to 0-1 range
        return max(0.0, min(1.0, score))


# Global model instance
_model: Optional[QueryOptimizerModel] = None


async def get_model() -> QueryOptimizerModel:
    """Get the global model instance."""
    global _model
    if _model is None:
        _model = QueryOptimizerModel()
        await _model.initialize()
    return _model
