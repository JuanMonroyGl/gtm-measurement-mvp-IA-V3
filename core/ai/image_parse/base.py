"""Contracts for AI-backed plan parsing with text-first image support."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Protocol


class ImageParseProvider(Protocol):
    def parse(
        self,
        *,
        case_id: str,
        image_paths: list[Path],
        native_text_entries: list[dict[str, Any]] | None = None,
        image_evidence: list[dict[str, Any]] | None = None,
        text_context: str | None = None,
    ) -> dict:
        ...
