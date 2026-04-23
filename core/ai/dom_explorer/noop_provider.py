from __future__ import annotations

from core.ai.dom_explorer.base import DomExplorerProvider


class NoopDomExplorerProvider(DomExplorerProvider):
    def suggest_next_action(self, payload: dict) -> dict:
        return {
            "provider": "noop",
            "enabled": False,
            "action": "none",
            "confidence": 0.0,
            "reason": "AI dom_explorer desactivado.",
        }
