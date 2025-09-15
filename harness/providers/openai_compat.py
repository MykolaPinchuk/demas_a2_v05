import json
import os
import time
import urllib.request
from typing import Dict, List, Optional, Tuple


class OpenAICompatError(RuntimeError):
    pass


class OpenAICompatChat:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        extra_headers: Optional[Dict[str, str]] = None,
        timeout: int = 45,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.extra_headers = extra_headers or {}

    def _headers(self) -> Dict[str, str]:
        # Most providers accept Authorization: Bearer; some accept x-api-key
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        # Also include x-api-key for providers that prefer it
        headers.setdefault("x-api-key", self.api_key)
        headers.update(self.extra_headers)
        return headers

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_output_tokens: int = 2000,
        seed: Optional[int] = None,
    ) -> Tuple[str, Dict[str, float]]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if seed is not None:
            payload["seed"] = seed
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.base_url, data=data, headers=self._headers())
        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read().decode("utf-8")
        except Exception as e:
            raise OpenAICompatError(str(e))
        elapsed = time.time() - start
        try:
            obj = json.loads(raw)
        except Exception as e:
            raise OpenAICompatError(f"Invalid JSON from provider: {e}; raw={raw[:200]}...")
        # OpenAI format: choices[0].message.content
        try:
            content = obj["choices"][0]["message"]["content"]
        except Exception as e:
            raise OpenAICompatError(f"Unexpected provider response: {obj}")
        usage = obj.get("usage", {})
        meta = {
            "elapsed": elapsed,
            "prompt_tokens": float(usage.get("prompt_tokens", 0)),
            "completion_tokens": float(usage.get("completion_tokens", 0)),
            "total_tokens": float(usage.get("total_tokens", 0)),
        }
        return content, meta

