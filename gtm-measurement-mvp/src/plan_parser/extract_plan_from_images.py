"""Plan parser stubs for image-driven measurement plans.

This phase intentionally focuses on the skeleton:
- discover image files for a case
- leave room for multimodal analysis (not only OCR)
- produce traceable textual evidence placeholders
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ImageEvidence:
    """Evidence extracted from a single input image."""

    image_path: str
    extracted_text: str | None
    extraction_method: str
    confidence: float | None


def discover_case_images(case_images_dir: Path) -> list[Path]:
    """Return sorted image paths for a case."""
    if not case_images_dir.exists():
        return []

    allowed_ext = {".png", ".jpg", ".jpeg", ".webp"}
    return sorted(
        p for p in case_images_dir.iterdir() if p.is_file() and p.suffix.lower() in allowed_ext
    )


def extract_support_text_from_images(case_images_dir: Path) -> list[ImageEvidence]:
    """Stub for multimodal image analysis with textual support extraction.

    Notes:
    - This is intentionally not OCR-only by design.
    - A future implementation can combine OCR, vision-language models,
      layout analysis, and icon/CTA detection.
    """
    images = discover_case_images(case_images_dir)
    evidences: list[ImageEvidence] = []

    for image_path in images:
        evidences.append(
            ImageEvidence(
                image_path=str(image_path),
                extracted_text=None,
                extraction_method="stub_multimodal_support_text",
                confidence=None,
            )
        )

    return evidences


def parse_measurement_plan(case_images_dir: Path) -> dict[str, Any]:
    """Build a preliminary parsing result from image inputs."""
    evidences = extract_support_text_from_images(case_images_dir)

    return {
        "parser_status": "stub",
        "image_count": len(evidences),
        "evidence": [e.__dict__ for e in evidences],
        "interactions_raw": [],
        "warnings": [
            "Parser en modo stub: sin extracción final de interacciones en esta fase."
        ],
    }
