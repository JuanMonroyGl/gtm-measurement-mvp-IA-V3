"""No-op provider for image_parse."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.ai.image_parse.base import ImageParseProvider


class NoopImageParseProvider(ImageParseProvider):
    def parse(
        self,
        *,
        case_id: str,
        image_paths: list[Path],
        native_text_entries: list[dict[str, Any]] | None = None,
        image_evidence: list[dict[str, Any]] | None = None,
        text_context: str | None = None,
    ) -> dict:
        input_modalities = []
        if native_text_entries:
            input_modalities.append("native_text")
        if image_evidence:
            input_modalities.append("image_evidence")
        if image_paths:
            input_modalities.append("images")

        return {
            "provider": "noop",
            "enabled": False,
            "case_id": case_id,
            "used_native_text": bool(native_text_entries),
            "used_image_evidence": bool(image_evidence),
            "used_images": bool(image_paths),
            "text_context_chars": len(text_context or ""),
            "input_modalities": input_modalities,
            "image_count": len(image_paths),
            "interactions": [],
            "warnings": ["AI image_parse desactivado; se usa pipeline determinístico."],
        }
