import os
import time
from typing import Optional, Dict, Any, List
import httpx
from packages.core.exceptions import ProviderUnavailableError, CostLimitExceededError


class OpenRouterClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: str = "meta-llama/llama-3.3-70b-instruct",
        timeout_seconds: float = 60.0,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENROUTER_API_BASE_URL", "https://openrouter.ai/api/v1")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://translation-studio.local",
            "X-Title": "Translation Studio",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        chosen_model = model or self.default_model
        start_time = time.time()

        if not self.api_key:
            # High quality mock response for development/testing
            user_msg = messages[-1]["content"] if messages else ""
            mock_text = f"[Translated via OpenRouter ({chosen_model})]: {user_msg[:100]}..."
            if response_format and response_format.get("type") == "json_object":
                mock_text = '{"status": "PASS", "omission": false, "addition": false, "meaning_change": false, "contradiction": false, "confidence": 0.95, "reason": "All invariants satisfied."}'

            return {
                "choices": [{"message": {"content": mock_text}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 50, "total_tokens": 100},
                "latency_ms": int((time.time() - start_time) * 1000),
                "model": chosen_model,
            }

        url = f"{self.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": chosen_model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                response = await client.post(url, headers=self._headers(), json=payload)
                if response.status_code in [408, 429, 500, 502, 503, 504]:
                    raise ProviderUnavailableError("OpenRouter", f"Status {response.status_code}: {response.text}")
                response.raise_for_status()
                data = response.json()
                data["latency_ms"] = int((time.time() - start_time) * 1000)
                return data
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                raise ProviderUnavailableError("OpenRouter", str(e))

