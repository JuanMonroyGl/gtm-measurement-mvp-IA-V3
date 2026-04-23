from __future__ import annotations

from core.ai.dom_explorer.base import DomExplorerProvider


class OpenAIDomExplorerProvider(DomExplorerProvider):
    def suggest_next_action(self, payload: dict) -> dict:
        raise NotImplementedError("Pendiente de integrar en una siguiente ronda.")
