from __future__ import annotations

from core.ai.selector_rerank.base import SelectorRerankProvider


class NoopSelectorRerankProvider(SelectorRerankProvider):
    def rerank(self, payload: dict) -> dict:
        return {
            "provider": "noop",
            "enabled": False,
            "selected_selector": None,
            "confidence": 0.0,
            "reason": "AI selector_rerank desactivado.",
            "requires_human_review": True,
        }
