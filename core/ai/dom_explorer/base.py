from __future__ import annotations

from typing import Protocol


class DomExplorerProvider(Protocol):
    def suggest_next_action(self, payload: dict) -> dict:
        ...
