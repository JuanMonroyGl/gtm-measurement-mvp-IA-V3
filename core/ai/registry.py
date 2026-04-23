"""Provider registry for optional AI modules."""

from __future__ import annotations

from core.ai.config import AIConfig
from core.ai.dom_explorer.noop_provider import NoopDomExplorerProvider
from core.ai.image_parse.noop_provider import NoopImageParseProvider
from core.ai.selector_rerank.noop_provider import NoopSelectorRerankProvider


def image_parse_provider(config: AIConfig):
    if config.enabled and config.enable_image_parse and config.provider == "openai":
        from core.ai.image_parse.openai_provider import OpenAIImageParseProvider

        return OpenAIImageParseProvider(config)
    return NoopImageParseProvider()


def dom_explorer_provider(config: AIConfig):
    return NoopDomExplorerProvider()


def selector_rerank_provider(config: AIConfig):
    return NoopSelectorRerankProvider()
