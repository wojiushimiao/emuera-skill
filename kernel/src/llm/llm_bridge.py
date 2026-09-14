from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field

import aiohttp

from .llm_content import LLMContentGenerator
from .llm_context import LLMContextManager
from .llm_debug import LLMDebugAssistant
from .llm_safety import LLMDegradationHandler, LLMSafetyGuard
from .llm_script import LLMScriptModifier, LLMScriptGenerator


@dataclass
class LLMConfig:
    api_endpoint: str = ""
    api_key: str = ""
    model_name: str = "gpt-4"
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 30.0
    enable_content_gen: bool = True
    enable_script_gen: bool = False
    enable_script_mod: bool = False
    enable_debug: bool = True
    safety_level: str = "strict"
    max_concurrent: int = 3
    cache_ttl: int = 300
    require_approval: bool = True


@dataclass
class CacheEntry:
    content: str = ""
    timestamp: float = 0.0
    ttl: int = 300


class LLMBridge:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._semaphore = asyncio.Semaphore(config.max_concurrent)
        self.cache: dict[str, CacheEntry] = {}

        self.content_generator = LLMContentGenerator(self)
        self.script_generator = LLMScriptGenerator(self)
        self.script_modifier = LLMScriptModifier(self)
        self.debug_assistant = LLMDebugAssistant(self)
        self.context_manager = LLMContextManager()
        self.safety_guard = LLMSafetyGuard()
        self.degradation_handler = LLMDegradationHandler()

    async def initialize(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _call_api(self, messages: list[dict], **kwargs) -> str:
        cache_key = self._compute_cache_key(messages, kwargs)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        payload = {
            "model": kwargs.get("model", self.config.model_name),
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", self.config.max_tokens),
            "temperature": kwargs.get("temperature", self.config.temperature),
        }

        async with self._semaphore:
            try:
                result = await self._send_request(payload)
            except aiohttp.ClientError:
                return self.degradation_handler.handle_degradation(
                    "api_unreachable",
                    {"messages_length": len(messages)},
                )
            except asyncio.TimeoutError:
                return self.degradation_handler.handle_degradation(
                    "timeout",
                    {"messages_length": len(messages)},
                )

        self._set_cached(cache_key, result)
        return result

    async def _send_request(self, payload: dict) -> str:
        if self._session is None:
            await self.initialize()

        async with self._session.post(
            self.config.api_endpoint,
            json=payload,
        ) as response:
            response.raise_for_status()
            data = await response.json()
            return data["choices"][0]["message"]["content"]

    def _compute_cache_key(self, messages: list[dict], kwargs: dict) -> str:
        raw = json.dumps({"messages": messages, "kwargs": kwargs}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _get_cached(self, key: str) -> str | None:
        entry = self.cache.get(key)
        if entry is None:
            return None
        if time.time() - entry.timestamp > entry.ttl:
            del self.cache[key]
            return None
        return entry.content

    def _set_cached(self, key: str, content: str) -> None:
        self.cache[key] = CacheEntry(
            content=content,
            timestamp=time.time(),
            ttl=self.config.cache_ttl,
        )
