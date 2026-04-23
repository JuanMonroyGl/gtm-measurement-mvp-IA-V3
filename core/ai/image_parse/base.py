"""Contracts for AI-backed image parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ImageParseProvider(Protocol):
    def parse(self, *, case_id: str, image_paths: list[Path]) -> dict:
        ...
