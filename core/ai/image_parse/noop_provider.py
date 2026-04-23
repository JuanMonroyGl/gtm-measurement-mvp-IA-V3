"""No-op provider for image_parse."""

from __future__ import annotations

from pathlib import Path

from core.ai.image_parse.base import ImageParseProvider


class NoopImageParseProvider(ImageParseProvider):
    def parse(self, *, case_id: str, image_paths: list[Path]) -> dict:
        return {
            "provider": "noop",
            "enabled": False,
            "case_id": case_id,
            "image_count": len(image_paths),
            "interactions": [],
            "warnings": ["AI image_parse desactivado; se usa pipeline determinístico."],
        }
