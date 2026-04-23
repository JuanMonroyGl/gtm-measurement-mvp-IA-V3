from __future__ import annotations

from core.ai.selector_rerank.base import SelectorRerankProvider


class OpenAISelectorRerankProvider(SelectorRerankProvider):
    def rerank(self, payload: dict) -> dict:
        raise NotImplementedError("Pendiente de integrar en una siguiente ronda.")
