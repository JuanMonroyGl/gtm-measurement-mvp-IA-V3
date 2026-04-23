"""AI feature flags and model settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class AIConfig:
    enabled: bool
    provider: str
    enable_image_parse: bool
    enable_dom_explorer: bool
    enable_selector_rerank: bool
    selector_rerank_only_on_ambiguity: bool
    model_image: str
    model_dom: str
    model_selector: str
    image_detail: str
    max_tokens_image: int
    max_tokens_dom: int
    max_tokens_selector: int
    cache_dir: str

    @classmethod
    def from_env(cls) -> "AIConfig":
        return cls(
            enabled=_as_bool(os.getenv("AI_ENABLED", "false")),
            provider=os.getenv("AI_PROVIDER", "openai"),
            enable_image_parse=_as_bool(os.getenv("AI_ENABLE_IMAGE_PARSE", "false")),
            enable_dom_explorer=_as_bool(os.getenv("AI_ENABLE_DOM_EXPLORER", "false")),
            enable_selector_rerank=_as_bool(os.getenv("AI_ENABLE_SELECTOR_RERANK", "false")),
            selector_rerank_only_on_ambiguity=_as_bool(
                os.getenv("AI_SELECTOR_RERANK_ONLY_ON_AMBIGUITY", "true")
            ),
            model_image=os.getenv("AI_MODEL_IMAGE", "gpt-5-mini"),
            model_dom=os.getenv("AI_MODEL_DOM", "gpt-5-mini"),
            model_selector=os.getenv("AI_MODEL_SELECTOR", "gpt-5-mini"),
            image_detail=os.getenv("AI_IMAGE_DETAIL", "low"),
            max_tokens_image=int(os.getenv("AI_MAX_OUTPUT_TOKENS_IMAGE", "700")),
            max_tokens_dom=int(os.getenv("AI_MAX_OUTPUT_TOKENS_DOM", "500")),
            max_tokens_selector=int(os.getenv("AI_MAX_OUTPUT_TOKENS_SELECTOR", "350")),
            cache_dir=os.getenv("AI_CACHE_DIR", ".cache/ai"),
        )
